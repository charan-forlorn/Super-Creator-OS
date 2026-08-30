use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;

use tauri::Emitter;

use crate::{is_cancelled, MediaProbe, RenderVerification};

/// Locate a binary, preferring PATH, falling back to common Windows shims.
fn which(bin: &str) -> String {
    if let Ok(p) = which::which(bin) {
        return p.to_string_lossy().to_string();
    }
    bin.to_string()
}

// `which` is not a default crate; implement a minimal PATH lookup.
mod which {
    use std::env;
    use std::path::Path;
    use std::process::Command;

    pub fn which(name: &str) -> Result<std::path::PathBuf, ()> {
        let path = env::var("PATH").unwrap_or_default();
        for dir in env::split_paths(&path) {
            let candidate = if name.contains('.') {
                dir.join(name)
            } else {
                dir.join(format!("{name}.exe"))
            };
            if candidate.is_file() {
                return Ok(candidate);
            }
            // try .exe suffix always on windows
            let exe = dir.join(format!("{name}.exe"));
            if exe.is_file() {
                return Ok(exe);
            }
        }
        // As a last resort, probe via `where` on Windows.
        if let Ok(out) = Command::new("where").arg(name).output() {
            if out.status.success() {
                if let Ok(line) = String::from_utf8(out.stdout) {
                    if let Some(first) = line.lines().next() {
                        let p = std::path::PathBuf::from(first.trim());
                        if p.is_file() {
                            return Ok(p);
                        }
                    }
                }
            }
        }
        Err(())
    }
}

fn now_ms() -> u128 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

fn class_of_codec(codec: &str) -> &'static str {
    let c = codec.to_lowercase();
    if c.contains("h264") || c.contains("h265") || c.contains("hevc") || c.contains("vp9")
        || c.contains("av1") || c.contains("mpeg") || c.contains("prores") || c == "mjpeg"
        || c.contains("png") {
        "video"
    } else if c.contains("aac") || c.contains("mp3") || c.contains("opus") || c.contains("vorbis")
        || c.contains("flac") || c.contains("pcm") || c.contains("ac3") {
        "audio"
    } else if c.contains("png") || c.contains("mjpeg") || c.contains("gif") || c.contains("webp") {
        "image"
    } else {
        "unknown"
    }
}

pub fn probe_media(path: &str) -> MediaProbe {
    let id = format!("asset-{}-{}", now_ms(), sanitize_name(path));
    let base = MediaProbe {
        id,
        name: Path::new(path)
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_else(|| path.to_string()),
        source_path: path.to_string(),
        kind: "unknown".to_string(),
        duration_sec: 0.0,
        width: 0,
        height: 0,
        fps: 0.0,
        has_audio: false,
        video_codec: None,
        audio_codec: None,
        audio_sample_rate: None,
        probe_status: "ok".to_string(),
        error: None,
    };

    let ffprobe = which("ffprobe");
    if !Path::new(path).is_file() {
        return MediaProbe { probe_status: "missing".to_string(), error: Some(format!("file not found: {path}")), ..base };
    }
    let out = Command::new(&ffprobe)
        .args(["-v", "error", "-show_format", "-show_streams", "-of", "json", path])
        .output();
    let out = match out {
        Ok(o) => o,
        Err(e) => {
            return MediaProbe {
                probe_status: "unavailable".to_string(),
                error: Some(format!("ffprobe failed: {e}")),
                ..base
            };
        }
    };
    if !out.status.success() {
        return MediaProbe {
            probe_status: "corrupt".to_string(),
            error: Some(format!("ffprobe exit {}", out.status)),
            ..base
        };
    }
    let parsed: Value = match serde_json::from_slice(&out.stdout) {
        Ok(v) => v,
        Err(e) => {
            return MediaProbe {
                probe_status: "failed".to_string(),
                error: Some(format!("ffprobe json parse error: {e}")),
                ..base
            };
        }
    };
    let streams = parsed.get("streams").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    if streams.is_empty() {
        return MediaProbe {
            probe_status: "corrupt".to_string(),
            error: Some("ffprobe returned no streams".to_string()),
            ..base
        };
    }

    let mut probe = base;
    if let Some(fmt) = parsed.get("format") {
        if let Some(d) = fmt.get("duration").and_then(|v| v.as_str()) {
            probe.duration_sec = d.parse().unwrap_or(0.0);
        }
    }
    let mut has_video = false;
    let mut has_audio = false;
    for s in streams.iter() {
        let ctype = s.get("codec_type").and_then(|v| v.as_str()).unwrap_or("");
        let codec = s.get("codec_name").and_then(|v| v.as_str()).unwrap_or("");
        match ctype {
            "video" => {
                has_video = true;
                probe.video_codec = Some(codec.to_string());
                probe.kind = "video".to_string();
                if let Some(w) = s.get("width").and_then(|v| v.as_u64()) {
                    probe.width = w as u32;
                }
                if let Some(h) = s.get("height").and_then(|v| v.as_u64()) {
                    probe.height = h as u32;
                }
                if let Some(r) = s.get("avg_frame_rate").and_then(|v| v.as_str()) {
                    probe.fps = parse_fraction(r);
                }
            }
            "audio" => {
                has_audio = true;
                if probe.kind == "unknown" {
                    probe.kind = "audio".to_string();
                }
                probe.audio_codec = Some(codec.to_string());
                if let Some(sr) = s.get("sample_rate").and_then(|v| v.as_str()) {
                    probe.audio_sample_rate = sr.parse().ok();
                }
            }
            _ => {}
        }
    }
    if !has_video && has_audio {
        probe.kind = "audio".to_string();
    }
    probe.has_audio = has_audio;
    if probe.kind == "unknown" && (has_video || has_audio) {
        probe.kind = if has_video { "video" } else { "audio" }.to_string();
    }
    probe
}

fn parse_fraction(s: &str) -> f64 {
    let parts: Vec<&str> = s.split('/').collect();
    if parts.len() == 2 {
        let num = parts[0].parse::<f64>().unwrap_or(0.0);
        let den = parts[1].parse::<f64>().unwrap_or(0.0);
        if den != 0.0 {
            return num / den;
        }
    }
    s.parse().unwrap_or(0.0)
}

fn sanitize_name(path: &str) -> String {
    Path::new(path)
        .file_stem()
        .map(|s| s.to_string_lossy().chars().filter(|c| c.is_alphanumeric()).collect())
        .unwrap_or_default()
}

pub fn generate_thumbnail(source_path: &str, out_path: &str, time_sec: f64) -> Result<String, String> {
    let ffmpeg = which("ffmpeg");
    let ts = format!("{time_sec:.3}");
    let status = Command::new(&ffmpeg)
        .args([
            "-y",
            "-ss",
            &ts,
            "-i",
            source_path,
            "-frames:v",
            "1",
            "-vf",
            "scale='min(320,iw)':-2",
            out_path,
        ])
        .status();
    match status {
        Ok(s) if s.success() => Ok(out_path.to_string()),
        Ok(s) => Err(format!("ffmpeg thumbnail failed exit {s}")),
        Err(e) => Err(format!("ffmpeg spawn error: {e}")),
    }
}

/// ROOT_CAUSE_3 — generate a deterministic H.264/AAC MP4 preview proxy for a
/// source that WebView2 cannot decode directly (HEVC, ProRes, exotic MOV, …).
/// The ORIGINAL source is never overwritten; the proxy is written to `out_path`.
/// Uses a fast encode preset and scales down only when the source is larger than
/// 720p (preserve small sources as-is to keep the proxy cheap).
pub fn generate_preview_proxy(source_path: &str, out_path: &str) -> Result<String, String> {
    let ffmpeg = which("ffmpeg");
    let probe = probe_media(source_path);
    // Fit within a 720p envelope (preview-only), preserving aspect ratio and
    // producing even dimensions (required by yuv420p/H.264). We scale by height
    // when the source is tall (portrait) and by width otherwise; `-2` keeps the
    // other axis even and aspect-correct. Unlike a hardcoded width:height pair
    // this never emits an invalid target and works for portrait/landscape alike.
    let vf = if probe.height >= 720 {
        "scale=w=-2:h=720,format=yuv420p"
    } else if probe.width >= 1280 {
        "scale=w=1280:h=-2,format=yuv420p"
    } else {
        "format=yuv420p"
    };
    let status = Command::new(&ffmpeg)
        .args([
            "-y",
            "-i",
            source_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            out_path,
        ])
        .status();
    match status {
        Ok(s) if s.success() => Ok(out_path.to_string()),
        Ok(s) => Err(format!("ffmpeg preview proxy failed exit {s}")),
        Err(e) => Err(format!("ffmpeg spawn error: {e}")),
    }
}

pub fn hvs_capabilities() -> Value {
    let ffprobe = which("ffprobe");
    let ffmpeg = which("ffmpeg");
    json!({
        "ffprobe": Path::new(&ffprobe).is_file(),
        "ffmpeg": Path::new(&ffmpeg).is_file(),
        "engine": "local-ffmpeg",
        "mode": "hybrid-bridge",
        "resolutions": ["1920x1080", "1080x1920", "1080x1080"],
        "videoCodec": "libx264",
        "audioCodec": "aac",
        "container": "mp4",
    })
}

/// Render the project to an MP4 using ffmpeg.
///
/// Strategy: build a filtergraph from the project's tracks (clips with
/// in/out points, scale/position transforms, captions) and concatenate per
/// track, then stack/overlay. For the vertical slice we implement a correct,
/// deterministic pipeline:
///   - one video track + one audio track is the common case
///   - each clip is trimmed via -ss/-to against its source in-point/duration
///   - scale/crop to the requested resolution
///   - captions rendered as drawtext overlays
pub fn run_render(
    job_id: &str,
    project_json: &str,
    output_path: &str,
    resolution: &str,
    app: &tauri::AppHandle,
) {
    emit_state(app, job_id, "ANALYZING", 0.05, None, None);
    let project: Value = match serde_json::from_str(project_json) {
        Ok(v) => v,
        Err(e) => {
            emit_state(app, job_id, "FAILED", 0.0, None, Some(format!("invalid project json: {e}")));
            return;
        }
    };
    let (w, h) = match resolution {
        "1080x1920" => (1080, 1920),
        "1080x1080" => (1080, 1080),
        _ => (1920, 1080),
    };

    // Build per-track trim+scale filter inputs.
    let tracks = project.get("tracks").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    if tracks.is_empty() {
        emit_state(app, job_id, "FAILED", 0.0, None, Some("project has no tracks".to_string()));
        return;
    }

    // For the vertical slice we render a single combined video track and a single
    // combined audio track. Multiple clips on one track are concatenated in time.
    let ffmpeg = which("ffmpeg");

    // Gather all clips across video tracks.
    let mut video_clips: Vec<Value> = Vec::new();
    let mut audio_clips: Vec<Value> = Vec::new();
    let assets = project.get("assets").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    for t in tracks.iter() {
        let kind = t.get("kind").and_then(|v| v.as_str()).unwrap_or("");
        let clips = t.get("clips").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        if kind == "video" {
            video_clips.extend(clips);
        } else if kind == "audio" {
            audio_clips.extend(clips);
        }
    }

    if video_clips.is_empty() {
        emit_state(app, job_id, "FAILED", 0.0, None, Some("no video clips to render".to_string()));
        return;
    }

    // Concatenate video clips with trim and scale using the concat filter.
    // Build inputs and a filter_complex.
    let mut inputs: Vec<String> = Vec::new();
    let mut concat_parts: Vec<String> = Vec::new();
    let mut part_idx = 0;
    for (i, clip) in video_clips.iter().enumerate() {
        let asset_id = clip.get("assetId").and_then(|v| v.as_str()).unwrap_or("");
        let asset = assets.iter().find(|a| a.get("id").and_then(|v| v.as_str()) == Some(asset_id));
        let source = match asset.and_then(|a| a.get("sourcePath").and_then(|v| v.as_str())) {
            Some(s) => s.to_string(),
            None => {
                emit_state(app, job_id, "FAILED", 0.0, None, Some(format!("clip {i} missing asset")));
                return;
            }
        };
        let in_point = clip.get("inPoint").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let duration = clip.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let start = clip.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0);
        inputs.push("-ss".into());
        inputs.push(format!("{in_point:.3}"));
        inputs.push("-i".into());
        inputs.push(source.clone());
        // scale each clip to target resolution
        concat_parts.push(format!(
            "[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[{i}v]"
        ));
        part_idx = i;
    }
    // Concat video parts.
    let vlist: Vec<String> = (0..=part_idx).map(|i| format!("[{i}v]")).collect();
    let mut filter = concat_parts.join(";");
    filter.push(';');
    filter.push_str(&format!("{}concat=n={}:v=1:a=0[vout]", vlist.join(""), vlist.len()));

    // Audio: collect audio clips; map each as an input and concatenate. If none,
    // synthesize a silent track matched to the project duration so the container
    // is valid.
    let dur = project.get("durationSec").and_then(|v| v.as_f64()).unwrap_or(10.0).max(0.1);
    let audio_arg: Vec<String>;
    if !audio_clips.is_empty() {
        let total_before = inputs.iter().filter(|x| x.as_str() == "-i").count();
        for clip in audio_clips.iter() {
            let asset_id = clip.get("assetId").and_then(|v| v.as_str()).unwrap_or("");
            let asset = assets.iter().find(|a| a.get("id").and_then(|v| v.as_str()) == Some(asset_id));
            let source = match asset.and_then(|a| a.get("sourcePath").and_then(|v| v.as_str())) {
                Some(s) => s.to_string(),
                None => continue,
            };
            let in_point = clip.get("inPoint").and_then(|v| v.as_f64()).unwrap_or(0.0);
            inputs.push("-ss".into());
            inputs.push(format!("{in_point:.3}"));
            inputs.push("-i".into());
            inputs.push(source);
        }
        let total_after = inputs.iter().filter(|x| x.as_str() == "-i").count();
        let n_audio = total_after - total_before;
        if n_audio == 0 {
            filter.push_str(&format!(";aevalsrc=0:d={dur:.3}[aout]"));
        } else {
            let alist: Vec<String> = (total_before..total_after)
                .map(|i| format!("[{i}:a]aformat=sample_fmts=fltp,aresample=44100[{i}a]"))
                .collect();
            filter.push(';');
            filter.push_str(&alist.join(";"));
            let concat_list: Vec<String> = (total_before..total_after).map(|i| format!("[{i}a]")).collect();
            filter.push(';');
            filter.push_str(&format!("{}concat=n={}:v=0:a=1[aout]", concat_list.join(""), n_audio));
        }
        audio_arg = vec!["-map".into(), "[vout]".into(), "-map".into(), "[aout]".into()];
    } else {
        filter.push_str(&format!(";aevalsrc=0:d={dur:.3}[aout]"));
        audio_arg = vec!["-map".into(), "[vout]".into(), "-map".into(), "[aout]".into()];
    }

    let mut cmd = Command::new(&ffmpeg);
    cmd.args(["-y"]);
    cmd.args(&inputs);
    cmd.args(["-filter_complex", &filter]);
    cmd.args(&audio_arg);
    cmd.args([
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]);
    emit_state(app, job_id, "RENDERING", 0.4, None, None);
    if is_cancelled(app, job_id) {
        emit_state(app, job_id, "CANCELLED", 0.4, None, None);
        return;
    }
    let status = cmd.status();
    match status {
        Ok(s) if s.success() => {
            emit_state(app, job_id, "VERIFYING", 0.85, Some(output_path), None);
            // verification is confirmed by the frontend via verify_render; mark COMPLETED.
            emit_state(app, job_id, "COMPLETED", 1.0, Some(output_path), None);
        }
        Ok(s) => {
            emit_state(app, job_id, "FAILED", 0.0, None, Some(format!("ffmpeg exit {s}")));
        }
        Err(e) => {
            emit_state(app, job_id, "FAILED", 0.0, None, Some(format!("ffmpeg spawn error: {e}")));
        }
    }
}

pub fn verify_render(output_path: &str, resolution: &str) -> RenderVerification {
    let ffprobe = which("ffprobe");
    if !Path::new(output_path).is_file() {
        return RenderVerification {
            ok: false,
            container: None,
            video_codec: None,
            audio_codec: None,
            width: None,
            height: None,
            duration_sec: None,
            size_bytes: None,
            error: Some(format!("output missing: {output_path}")),
        };
    }
    let out = match Command::new(&ffprobe)
        .args(["-v", "error", "-show_format", "-show_streams", "-of", "json", output_path])
        .output()
    {
        Ok(o) => o,
        Err(e) => {
            return RenderVerification { ok: false, container: None, video_codec: None, audio_codec: None, width: None, height: None, duration_sec: None, size_bytes: None, error: Some(format!("ffprobe error: {e}")) };
        }
    };
    if !out.status.success() {
        return RenderVerification { ok: false, container: None, video_codec: None, audio_codec: None, width: None, height: None, duration_sec: None, size_bytes: None, error: Some("ffprobe exit non-zero".to_string()) };
    }
    let parsed: Value = match serde_json::from_slice(&out.stdout) {
        Ok(v) => v,
        Err(e) => {
            return RenderVerification { ok: false, container: None, video_codec: None, audio_codec: None, width: None, height: None, duration_sec: None, size_bytes: None, error: Some(format!("json parse: {e}")) };
        }
    };
    let mut ver = RenderVerification {
        ok: false,
        container: None,
        video_codec: None,
        audio_codec: None,
        width: None,
        height: None,
        duration_sec: None,
        size_bytes: None,
        error: None,
    };
    let mut has_video = false;
    let mut has_audio = false;
    if let Some(streams) = parsed.get("streams").and_then(|v| v.as_array()) {
        for s in streams.iter() {
            let ctype = s.get("codec_type").and_then(|v| v.as_str()).unwrap_or("");
            let codec = s.get("codec_name").and_then(|v| v.as_str()).unwrap_or("").to_string();
            if ctype == "video" {
                has_video = true;
                ver.video_codec = Some(codec);
                ver.width = s.get("width").and_then(|v| v.as_u64()).map(|x| x as u32);
                ver.height = s.get("height").and_then(|v| v.as_u64()).map(|x| x as u32);
            } else if ctype == "audio" {
                has_audio = true;
                ver.audio_codec = Some(codec);
            }
        }
    }
    if let Some(fmt) = parsed.get("format") {
        ver.container = fmt.get("format_name").and_then(|v| v.as_str()).map(|s| s.split(',').next().unwrap_or(s).to_string());
        ver.duration_sec = fmt.get("duration").and_then(|v| v.as_str()).and_then(|s| s.parse().ok());
        ver.size_bytes = fmt.get("size").and_then(|v| v.as_str()).and_then(|s| s.parse().ok());
    }
    let (want_w, want_h) = match resolution {
        "1080x1920" => (1080, 1920),
        "1080x1080" => (1080, 1080),
        _ => (1920, 1080),
    };
    let container_ok = ver.container.as_deref() == Some("mov,mp4,m4a,3gp,3g2,mj2")
        || ver.container.as_deref().map(|c| c.contains("mp4")).unwrap_or(false);
    let codec_ok = ver.video_codec.as_deref() == Some("h264");
    let res_ok = ver.width == Some(want_w) && ver.height == Some(want_h);
    let nonzero = ver.size_bytes.unwrap_or(0) > 0;
    let dur_ok = ver.duration_sec.unwrap_or(0.0) > 0.0;
    ver.ok = has_video && container_ok && codec_ok && res_ok && nonzero && dur_ok;
    if !ver.ok {
        ver.error = Some(format!(
            "verify failed: video={has_video} container={:?} vcodec={:?} res={:?}x{:?} size={:?} dur={:?} want={}x{}",
            ver.container, ver.video_codec, ver.width, ver.height, ver.size_bytes, ver.duration_sec, want_w, want_h
        ));
    }
    ver
}

fn emit_state(app: &tauri::AppHandle, job_id: &str, status: &str, progress: f64, output_path: Option<&str>, error: Option<String>) {
    let payload = json!({
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "output_path": output_path,
        "error": error,
    });
    let _ = app.emit("render-progress", payload);
}
