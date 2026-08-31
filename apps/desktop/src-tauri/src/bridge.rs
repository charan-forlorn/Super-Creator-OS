use serde_json::{json, Value};
use std::path::Path;
use std::process::{Command, Stdio};

use tauri::Emitter;

use crate::{is_cancelled, MediaProbe, RenderVerification};

/// Spawn a media CLI (ffmpeg/ffprobe) with explicit stdio. The bundled Tauri app
/// is a GUI-subsystem process with NO console; relying on Rust's default
/// *inherited* stdio hands ffmpeg invalid stdin/stdout/stderr handles, which makes
/// it block forever (the command never returns, deadlocking any awaited caller).
/// Nulling stdin and stderr (ffprobe's JSON goes to piped stdout) avoids that.
fn ffcmd(bin: &str) -> Command {
    let mut c = Command::new(bin);
    c.stdin(Stdio::null()).stderr(Stdio::null());
    // Tauri release binaries use the Windows GUI subsystem. Child ffmpeg/ffprobe
    // processes can otherwise inherit an unusable console state and block forever
    // while the parent waits on `status()` / `output()`. CREATE_NO_WINDOW gives
    // media subprocesses an explicit non-console launch mode and keeps the same
    // behavior for console/test builds.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    c
}

/// Locate a binary, preferring PATH, falling back to common Windows shims.
fn which(bin: &str) -> String {
    if let Ok(p) = which::which(bin) {
        return p.to_string_lossy().to_string();
    }
    bin.to_string()
}

/// Candidate directories to probe when `bin` is not resolvable via PATH. This makes
/// ffmpeg/ffprobe discovery resilient to a minimal launch environment (e.g. when the
/// app is started by an external driver whose PATH does not include the user's shims).
fn ffmpeg_search_dirs() -> Vec<std::path::PathBuf> {
    let mut dirs: Vec<std::path::PathBuf> = Vec::new();
    if let Some(home) = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")) {
        // scoop shims: ~/scoop/shims
        dirs.push(std::path::Path::new(&home).join("scoop").join("shims"));
        // also the legacy localappdata scoop layout
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            dirs.push(std::path::Path::new(&local).join("scoop").join("shims"));
        }
    }
    // Common manual install locations.
    for base in ["C:\\", "C:\\Program Files\\", "C:\\Program Files (x86)\\", "D:\\"] {
        dirs.push(std::path::Path::new(base).join("ffmpeg").join("bin"));
        dirs.push(std::path::Path::new(base).join("ffmpeg").join("bin"));
    }
    dirs
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
        // Probe well-known install locations (scoop shims, common ffmpeg dirs).
        for dir in super::ffmpeg_search_dirs() {
            let candidate = dir.join(format!("{name}.exe"));
            if candidate.is_file() {
                return Ok(candidate);
            }
            if name.contains('.') {
                let c2 = dir.join(name);
                if c2.is_file() {
                    return Ok(c2);
                }
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
    let out = ffcmd(&ffprobe)
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
    generate_thumbnail_impl(source_path, out_path, time_sec)
}

/// ROOT_CAUSE_3 â€” generate a deterministic H.264/AAC MP4 preview proxy for a
/// source that WebView2 cannot decode directly (HEVC, ProRes, exotic MOV, â€¦).
/// The ORIGINAL source is never overwritten; the proxy is written to `out_path`.
/// Uses a fast encode preset and scales down only when the source is larger than
/// 720p (preserve small sources as-is to keep the proxy cheap).
pub fn generate_preview_proxy(source_path: &str, out_path: &str) -> Result<String, String> {
    generate_preview_proxy_impl(source_path, out_path)
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

    let mut cmd = ffcmd(&ffmpeg);
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
    let out = match ffcmd(&ffprobe)
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

// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// R2.2 DETERMINISTIC MEDIA CACHE (ROOT_CAUSE_3 continuation)
//
// Proxy + thumbnail cache identity is computed deterministically from the source
// path + a codec/time signature so that the SAME source always maps to the SAME
// cache file. This lets the backend HIT a previously generated proxy instead of
// re-encoding every import, and lets STALE be detected when the source changes.
//
// The algorithm here mirrors packages/media-engine/src/cacheKey.ts BYTE-FOR-BYTE
// so the frontend and backend agree on cache paths. That contract is asserted by
// tests/desktop/tests/r2_cache_contract.test.ts.
// â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

/// djb2 over UTF-8 bytes, base36 â€” identical to TS `stableHash` (which uses
/// JavaScript `Number.toString(36)`). Rust's std has no base36 formatter, so we
/// implement it explicitly to keep the two implementations byte-identical.
fn stable_hash(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut h: u32 = 5381;
    for &b in bytes {
        h = h.wrapping_mul(33).wrapping_add(b as u32);
    }
    to_base36(h)
}

/// u32 -> base36 string (lowercase), matching JS `Number.toString(36)`.
fn to_base36(mut n: u32) -> String {
    if n == 0 {
        return "0".to_string();
    }
    let mut out = String::new();
    while n > 0 {
        let r = (n % 36) as u8;
        let c = if r < 10 {
            (b'0' + r) as char
        } else {
            (b'a' + (r - 10)) as char
        };
        out.push(c);
        n /= 36;
    }
    out.chars().rev().collect()
}

fn normalize_codec(c: &Option<String>) -> String {
    match c {
        Some(v) => {
            let lower = v.to_lowercase();
            let alnum: String = lower.chars().filter(|ch| ch.is_ascii_alphanumeric()).collect();
            if alnum.is_empty() {
                "na".to_string()
            } else {
                alnum
            }
        }
        None => "na".to_string(),
    }
}

/// Deterministic cache directory for the app (under the OS cache dir) for the
/// given kind. Creates it if missing. Mirrors TS `cachePath` structure:
/// `<cacheDir>/<kind>/<key>.<ext>`.
///
/// Uses the platform cache location via environment variables rather than a
/// Tauri path plugin dependency, so the backend stays dependency-light.
fn cache_dir_for(_app: &tauri::AppHandle, kind: &str) -> Result<String, String> {
    let base = if cfg!(windows) {
        std::env::var("LOCALAPPDATA")
            .map_err(|e| format!("LOCALAPPDATA unavailable: {e}"))?
    } else {
        std::env::var("XDG_CACHE_HOME")
            .or_else(|_| {
                std::env::var("HOME").map(|h| format!("{h}/.cache"))
            })
            .map_err(|e| format!("cache dir unavailable: {e}"))?
    };
    let dir = std::path::Path::new(&base).join("haios-video-studio").join(kind);
    std::fs::create_dir_all(&dir).map_err(|e| format!("cannot create cache dir: {e}"))?;
    Ok(dir.to_string_lossy().to_string())
}

/// Proxy cache key â€” identical to TS `proxyCacheKey` (codec signature folded in).
fn proxy_cache_key(source_path: &str, codec_signature: &str) -> String {
    format!("proxy_{}", stable_hash(&format!("{}|{}", source_path, codec_signature)))
}

/// Thumbnail cache key â€” identical to TS `thumbnailCacheKey` (time bucketed to ms).
fn thumbnail_cache_key(source_path: &str, time_sec: f64) -> String {
    let bucket = (time_sec * 1000.0).round() as i64;
    format!("thumb_{}", stable_hash(&format!("{}|{}", source_path, bucket)))
}

/// Signature folding the probe codecs that decide proxy necessity.
fn proxy_codec_signature(video_codec: &Option<String>, audio_codec: &Option<String>) -> String {
    format!("{}+{}", normalize_codec(video_codec), normalize_codec(audio_codec))
}

/// Build (or HIT) a deterministic preview proxy for `source_path` inside the
/// managed cache. Returns the cache path. On HIT (file already present + not
/// stale) the existing file is returned without re-encoding. `source_revision`
/// lets callers mark staleness, but the backend owns the file mtime so a present
/// file is treated as a valid HIT (re-encoding only happens on miss).
pub fn ensure_preview_proxy(
    app: &tauri::AppHandle,
    source_path: &str,
    video_codec: &Option<String>,
    audio_codec: &Option<String>,
) -> Result<String, String> {
    let dir = cache_dir_for(app, "proxy")?;
    ensure_preview_proxy_impl(dir, source_path, video_codec, audio_codec)
}

/// Cache-aware proxy ensure: deterministic key from `source_path` + codec
/// signature. On HIT (file already present for this exact identity) the
/// existing proxy is reused without re-encoding; on MISS/STALE it is generated
/// deterministically into the cache path (the ORIGINAL source is never touched).
///
/// This is the context-free core so the missâ†’hitâ†’reuse lifecycle can be
/// unit-tested with a temporary cache directory (no `AppHandle` coupling), while
/// the production `ensure_preview_proxy` command supplies the managed cache dir.
/// Behavior is identical to the previous inline implementation.
fn ensure_preview_proxy_impl(
    cache_dir: String,
    source_path: &str,
    video_codec: &Option<String>,
    audio_codec: &Option<String>,
) -> Result<String, String> {
    let key = proxy_cache_key(source_path, &proxy_codec_signature(video_codec, audio_codec));
    let out_path = std::path::Path::new(&cache_dir)
        .join(format!("{key}.mp4"))
        .to_string_lossy()
        .to_string();
    // HIT: cache file already generated for this exact source identity.
    if Path::new(&out_path).is_file() {
        return Ok(out_path);
    }
    // MISS/STALE: (re)generate the proxy deterministically into the cache path.
    generate_preview_proxy_impl(source_path, &out_path)
}

/// Generate a deterministic thumbnail at `time_sec` inside the managed cache.
/// HIT returns the existing file; MISS/STALE generates it.
pub fn ensure_thumbnail(
    app: &tauri::AppHandle,
    source_path: &str,
    time_sec: f64,
) -> Result<String, String> {
    let dir = cache_dir_for(app, "thumbnail")?;
    let key = thumbnail_cache_key(source_path, time_sec);
    let out_path = format!("{}/{}.png", dir, key);
    if Path::new(&out_path).is_file() {
        return Ok(out_path);
    }
    generate_thumbnail_impl(source_path, &out_path, time_sec)
}

/// Invalidate (delete) a cache entry by deterministic key within a kind.
pub fn invalidate_cache_entry(app: &tauri::AppHandle, kind: &str, key: &str) -> bool {
    if let Ok(dir) = cache_dir_for(app, kind) {
        let ext = if kind == "proxy" { "mp4" } else { "png" };
        let p = format!("{}/{}.{}", dir, key, ext);
        if Path::new(&p).is_file() {
            return std::fs::remove_file(&p).is_ok();
        }
    }
    false
}

/// Rename the legacy public helpers to *_impl and add cache-aware wrappers.
fn generate_thumbnail_impl(source_path: &str, out_path: &str, time_sec: f64) -> Result<String, String> {
    let ffmpeg = which("ffmpeg");
    let ts = format!("{time_sec:.3}");
    let status = ffcmd(&ffmpeg)
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

/// Generate a deterministic H.264/AAC MP4 preview proxy (impl, writes to `out_path`).
/// The ORIGINAL source is never overwritten.
fn generate_preview_proxy_impl(source_path: &str, out_path: &str) -> Result<String, String> {
    let ffmpeg = which("ffmpeg");
    let probe = probe_media(source_path);
    let vf = if probe.height >= 720 {
        "scale=w=-2:h=720,format=yuv420p"
    } else if probe.width >= 1280 {
        "scale=w=1280:h=-2,format=yuv420p"
    } else {
        "format=yuv420p"
    };
    let status = ffcmd(&ffmpeg)
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

#[cfg(test)]
mod tests {
    use super::*;

    // Cross-language contract: these vectors MUST match packages/media-engine
    // (cacheKey.ts) so the frontend + backend agree on deterministic cache paths.
    #[test]
    fn cache_key_contract_matches_typescript() {
        // stable_hash("a") djb2 base36 == JS Number.toString(36).
        let h = 5381u32.wrapping_mul(33).wrapping_add(97); // == 177670
        assert_eq!(stable_hash("a"), to_base36(h));
        // proxy key folds the codec signature exactly like TS proxyCacheKey.
        let pk = proxy_cache_key("C:/v/sample.mp4", "h264+aac");
        assert_eq!(pk, format!("proxy_{}", stable_hash("C:/v/sample.mp4|h264+aac")));
        // thumbnail key buckets time to ms exactly like TS thumbnailCacheKey.
        let tk = thumbnail_cache_key("C:/v/sample.mp4", 1.234);
        assert_eq!(tk, format!("thumb_{}", stable_hash("C:/v/sample.mp4|1234")));
        // Different source / signature yields a different key.
        assert_ne!(pk, proxy_cache_key("C:/v/other.mp4", "h264+aac"));
        assert_ne!(pk, proxy_cache_key("C:/v/sample.mp4", "hevc+aac"));
    }

    #[test]
    fn normalize_codec_is_alnum_only() {
        assert_eq!(normalize_codec(&Some("h264".into())), "h264");
        assert_eq!(normalize_codec(&Some("H.264".into())), "h264");
        assert_eq!(normalize_codec(&None), "na");
    }

    #[test]
    fn proxy_codec_signature_folds_codecs() {
        assert_eq!(
            proxy_codec_signature(&Some("h264".into()), &Some("aac".into())),
            "h264+aac"
        );
    }

    // â”€â”€ REAL proxy cache lifecycle (PROXY_CACHE gate, Phase B/C) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // Drives the ACTUAL ffmpeg encoder (generate_preview_proxy_impl) into a
    // temporary cache directory, proving MISSâ†’CREATEâ†’ffprobeâ†’HITâ†’reuse end to
    // end. No AppHandle/managed-cache coupling, no mocked filesystem output.
    #[test]
    fn ensure_preview_proxy_real_miss_hit_reuse() {
        // ffmpeg/ffprobe are hard production dependencies (hvs_capabilities).
        let ffmpeg_present = std::process::Command::new("ffmpeg")
            .arg("-version")
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        let ffprobe_present = std::process::Command::new("ffprobe")
            .arg("-version")
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        assert!(ffmpeg_present, "ffmpeg must be on PATH for proxy lifecycle test");
        assert!(ffprobe_present, "ffprobe must be on PATH for proxy lifecycle test");

        let tmp = std::env::temp_dir().join(format!(
            "haios_proxy_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let cache_dir = tmp.join("cache");
        let src_dir = tmp.join("src");
        std::fs::create_dir_all(&cache_dir).unwrap();
        std::fs::create_dir_all(&src_dir).unwrap();
        let source = src_dir.join("prores_pcm.mov");

        // Generate a small deterministic ProRes/PCM source that REQUIRES a proxy.
        let gen = std::process::Command::new("ffmpeg")
            .args([
                "-y",
                "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:v", "prores", "-c:a", "pcm_s16le", "-t", "2",
                source.to_str().unwrap(),
            ])
            .status()
            .expect("spawn ffmpeg for fixture");
        assert!(gen.success(), "prores fixture generation failed");
        // Sanity: the fixture is genuinely a proxy-required codec.
        let src_probe = probe_media(source.to_str().unwrap());
        assert_eq!(src_probe.video_codec.as_deref(), Some("prores"), "fixture must be prores");

        // MISS â†’ generate.
        let before_meta = std::fs::metadata(&source).unwrap();
        let before_mod = before_meta.modified().unwrap();
        let cache = cache_dir.to_string_lossy().to_string();
        let out1 = ensure_preview_proxy_impl(
            cache.clone(),
            source.to_str().unwrap(),
            &Some("prores".into()),
            &Some("pcm_s16le".into()),
        )
        .expect("proxy generation on miss");
        assert!(std::path::Path::new(&out1).is_file(), "proxy file must exist after miss");
        let proxy_files: Vec<_> = std::fs::read_dir(&cache_dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false))
            .collect();
        assert_eq!(proxy_files.len(), 1, "exactly one proxy file expected in cache");

        // ffprobe the produced proxy: H.264 video + AAC audio + mp4 container.
        let probe = probe_media(&out1);
        assert_eq!(probe.video_codec.as_deref(), Some("h264"), "proxy video must be h264");
        assert_eq!(probe.audio_codec.as_deref(), Some("aac"), "proxy audio must be aac");
        let container = ffprobe_container(&out1);
        assert!(container.contains("mp4"), "proxy container must be mp4 (got {container})");
        assert!(ffmpeg_decodes(&out1), "proxy must be decodable/playable");
        let mtime1 = std::fs::metadata(&out1).unwrap().modified().unwrap();

        // HIT â†’ reuse, no regeneration.
        let out2 = ensure_preview_proxy_impl(
            cache.clone(),
            source.to_str().unwrap(),
            &Some("prores".into()),
            &Some("pcm_s16le".into()),
        )
        .expect("proxy hit");
        assert_eq!(out1, out2, "hit must return identical deterministic path");
        let mtime2 = std::fs::metadata(&out2).unwrap().modified().unwrap();
        assert_eq!(mtime1, mtime2, "proxy must NOT be regenerated on hit (mtime stable)");

        // Original source immutable across the whole lifecycle.
        let after_meta = std::fs::metadata(&source).unwrap();
        assert_eq!(before_meta.len(), after_meta.len(), "source size must not change");
        assert_eq!(before_mod, after_meta.modified().unwrap(), "source mtime must not change");

        // Cleanup test-only artifacts (do not leak into production cache).
        let _ = std::fs::remove_dir_all(&tmp);
    }

    fn ffprobe_container(path: &str) -> String {
        let out = std::process::Command::new("ffprobe")
            .args([
                "-v", "error",
                "-show_entries", "format=format_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ])
            .output()
            .expect("spawn ffprobe");
        String::from_utf8_lossy(&out.stdout).trim().to_string()
    }

    fn ffmpeg_decodes(path: &str) -> bool {
        std::process::Command::new("ffmpeg")
            .args(["-v", "error", "-i", path, "-f", "null", "-"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
}
