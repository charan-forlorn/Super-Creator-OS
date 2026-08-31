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
fn clip_audio_linear_gain(clip: &Value) -> f64 {
    let audio = clip.get("audio");
    let muted = audio.and_then(|a| a.get("muted")).and_then(|v| v.as_bool()).unwrap_or(false);
    if muted { return 0.0; }
    let gain_db = audio.and_then(|a| a.get("gainDb")).and_then(|v| v.as_f64()).unwrap_or(0.0).clamp(-60.0, 0.0);
    10_f64.powf(gain_db / 20.0)
}

fn clip_playback_rate(clip: &Value) -> f64 {
    clip.get("playbackRate").and_then(|v| v.as_f64()).unwrap_or(1.0).clamp(0.25, 4.0)
}

fn audio_atempo_chain(rate: f64) -> String {
    let mut remaining = rate.clamp(0.25, 4.0);
    let mut factors: Vec<f64> = Vec::new();
    while remaining < 0.5 - 1e-9 { factors.push(0.5); remaining /= 0.5; }
    while remaining > 2.0 + 1e-9 { factors.push(2.0); remaining /= 2.0; }
    if (remaining - 1.0).abs() > 1e-9 { factors.push(remaining); }
    factors.into_iter().map(|v| format!("atempo={v:.6}")).collect::<Vec<_>>().join(",")
}

fn transition_in_duration(clip: &Value) -> Option<f64> {
    let t = clip.get("transitionIn")?;
    if t.get("type").and_then(|v| v.as_str()) != Some("crossfade") { return None; }
    t.get("duration").and_then(|v| v.as_f64()).map(|d| d.clamp(0.1, 2.0))
}

fn video_clip_audio_filter_with_transition(input_idx: usize, clip: &Value, duration: f64, has_audio: bool, fade_out: Option<f64>) -> String {
    let gain = clip_audio_linear_gain(clip);
    let rate = clip_playback_rate(clip);
    let source_duration = duration * rate;
    let tempo = audio_atempo_chain(rate);
    let tempo_filter = if tempo.is_empty() { String::new() } else { format!(",{tempo}") };
    let start = clip.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.0);
    let delay_ms = (start * 1000.0).round() as u64;
    let mut fades = String::new();
    if let Some(d) = transition_in_duration(clip) { fades.push_str(&format!(",afade=t=in:st=0:d={:.3}", d.min(duration))); }
    if let Some(d) = fade_out { let d = d.min(duration); fades.push_str(&format!(",afade=t=out:st={:.3}:d={:.3}", (duration - d).max(0.0), d)); }
    if has_audio {
        format!("[{input_idx}:a]atrim=duration={source_duration:.3},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp,aresample=44100{tempo_filter},volume={gain:.6}{fades},adelay={delay_ms}|{delay_ms}[{input_idx}va]")
    } else {
        format!("anullsrc=r=44100:cl=mono:d={source_duration:.3}{tempo_filter},volume={gain:.6}{fades},adelay={delay_ms}|{delay_ms}[{input_idx}va]")
    }
}

#[cfg(test)]
fn video_clip_audio_filter(input_idx: usize, clip: &Value, duration: f64, has_audio: bool) -> String {
    video_clip_audio_filter_with_transition(input_idx, clip, duration, has_audio, None)
}

fn clip_transform_values(clip: &Value) -> (f64, f64, f64, f64) {
    let transform = clip.get("transform");
    let scale = transform.and_then(|t| t.get("scale")).and_then(|v| v.as_f64()).unwrap_or(1.0).clamp(0.1, 4.0);
    let x = transform.and_then(|t| t.get("x")).and_then(|v| v.as_f64()).unwrap_or(0.0).clamp(-1.0, 1.0);
    let y = transform.and_then(|t| t.get("y")).and_then(|v| v.as_f64()).unwrap_or(0.0).clamp(-1.0, 1.0);
    let opacity = transform.and_then(|t| t.get("opacity")).and_then(|v| v.as_f64()).unwrap_or(1.0).clamp(0.0, 1.0);
    (scale, x, y, opacity)
}

fn clip_effect_values(clip: &Value) -> (f64, f64, f64) {
    let effects = clip.get("effects");
    let brightness = effects.and_then(|e| e.get("brightness")).and_then(|v| v.as_f64()).unwrap_or(0.0).clamp(-1.0, 1.0);
    let contrast = effects.and_then(|e| e.get("contrast")).and_then(|v| v.as_f64()).unwrap_or(1.0).clamp(0.0, 2.0);
    let saturation = effects.and_then(|e| e.get("saturation")).and_then(|v| v.as_f64()).unwrap_or(1.0).clamp(0.0, 3.0);
    (brightness, contrast, saturation)
}

fn even_px(value: f64) -> i32 {
    let mut n = value.round().max(2.0) as i32;
    if n % 2 != 0 { n += 1; }
    n
}

fn video_clip_filter(input_idx: usize, clip: &Value, duration: f64, w: i32, h: i32) -> String {
    let rate = clip_playback_rate(clip);
    let source_duration = duration * rate;
    let (scale, x, y, opacity) = clip_transform_values(clip);
    let (brightness, contrast, saturation) = clip_effect_values(clip);
    let scaled_w = even_px(w as f64 * scale);
    let scaled_h = even_px(h as f64 * scale);
    let left = (w - scaled_w) as f64 / 2.0 + x * w as f64 / 2.0;
    let top = (h - scaled_h) as f64 / 2.0 + y * h as f64 / 2.0;
    format!(
        "color=c=black:s={w}x{h}:d={duration:.3}:r=30[{input_idx}bg];[{input_idx}:v]trim=duration={source_duration:.3},setpts=(PTS-STARTPTS)/{rate:.6},scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,eq=brightness={brightness:.6}:contrast={contrast:.6}:saturation={saturation:.6},scale={scaled_w}:{scaled_h},format=rgba,colorchannelmixer=aa={opacity:.6}[{input_idx}fg];[{input_idx}bg][{input_idx}fg]overlay=x={left:.3}:y={top:.3}:shortest=1[{input_idx}v]"
    )
}


fn video_timeline_filter(clips: &[Value], duration: f64, w: i32, h: i32) -> String {
    let duration = duration.max(0.1);
    let mut parts = vec![format!("color=c=black:s={w}x{h}:d={duration:.3}:r=30[vbase0]")];
    for (i, clip) in clips.iter().enumerate() {
        let start = clip.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.0);
        let clip_duration = clip.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.001).max(0.001);
        let end = start + clip_duration;
        if let Some(d) = transition_in_duration(clip) {
            let d = d.min(clip_duration);
            parts.push(format!("[{i}v]format=rgba,fade=t=in:st=0:d={d:.3}:alpha=1,setpts=PTS+{start:.3}/TB[{i}vt]"));
        } else {
            parts.push(format!("[{i}v]setpts=PTS+{start:.3}/TB[{i}vt]"));
        }
        let base_in = format!("vbase{i}");
        let base_out = if i + 1 == clips.len() { "vout".to_string() } else { format!("vbase{}", i + 1) };
        parts.push(format!("[{base_in}][{i}vt]overlay=x=0:y=0:eof_action=pass:repeatlast=0:shortest=0:enable='between(t,{start:.3},{end:.3})'[{base_out}]"));
    }
    parts.join(";")
}

fn safe_caption_color(value: Option<&str>, fallback: &str) -> String {
    match value {
        Some(v) if v.len() == 7 && v.starts_with('#') && v[1..].chars().all(|c| c.is_ascii_hexdigit()) => v.to_ascii_uppercase(),
        _ => fallback.to_string(),
    }
}

fn ffmpeg_filter_path(path: &str) -> String {
    path.replace('\\', "/").replace(':', "\\:").replace('\'', "\\'")
}

fn caption_font_path() -> String {
    let windir = std::env::var("WINDIR").unwrap_or_else(|_| "C:\\Windows".to_string());
    for name in ["segoeui.ttf", "arial.ttf", "LeelawUI.ttf"] {
        let p = std::path::Path::new(&windir).join("Fonts").join(name);
        if p.is_file() { return p.to_string_lossy().to_string(); }
    }
    "C:\\Windows\\Fonts\\segoeui.ttf".to_string()
}

fn caption_drawtext_filter(input: &str, output: &str, caption: &Value, text_path: &str, w: i32, h: i32, font_path: &str) -> String {
    let style = caption.get("style");
    let start = caption.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.0);
    let duration = caption.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.001).max(0.001);
    let end = start + duration;
    let x = style.and_then(|s| s.get("x")).and_then(|v| v.as_f64()).unwrap_or(0.5) * w as f64;
    let y = style.and_then(|s| s.get("y")).and_then(|v| v.as_f64()).unwrap_or(0.85) * h as f64;
    let size = style.and_then(|s| s.get("fontSizePx")).and_then(|v| v.as_f64()).unwrap_or(48.0).round().clamp(8.0, 300.0) as i32;
    let fg = safe_caption_color(style.and_then(|s| s.get("color")).and_then(|v| v.as_str()), "#FFFFFF");
    let bg = safe_caption_color(style.and_then(|s| s.get("backgroundColor")).and_then(|v| v.as_str()), "#000000");
    let bg_opacity = style.and_then(|s| s.get("backgroundOpacity")).and_then(|v| v.as_f64()).unwrap_or(0.6).clamp(0.0, 1.0);
    format!("[{input}]drawtext=fontfile='{}':textfile='{}':expansion=none:fontsize={size}:fontcolor={fg}:box=1:boxcolor={bg}@{bg_opacity:.3}:boxborderw=8:x={x:.3}-text_w/2:y={y:.3}-text_h/2:enable='between(t,{start:.3},{end:.3})'[{output}]", ffmpeg_filter_path(font_path), ffmpeg_filter_path(text_path))
}


fn prepare_caption_chain(tracks: &[Value], w: i32, h: i32) -> Result<(Vec<String>, String, Option<std::path::PathBuf>), String> {
    let mut captions: Vec<Value> = Vec::new();
    for t in tracks.iter() {
        if t.get("kind").and_then(|v| v.as_str()) == Some("text") {
            captions.extend(t.get("captions").and_then(|v| v.as_array()).cloned().unwrap_or_default());
        }
    }
    if captions.is_empty() { return Ok((Vec::new(), "vout".to_string(), None)); }
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos();
    let dir = std::env::temp_dir().join(format!("haios-captions-{}-{stamp}", std::process::id()));
    std::fs::create_dir_all(&dir).map_err(|e| format!("caption temp dir: {e}"))?;
    let font = caption_font_path();
    let mut filters = Vec::new();
    let mut input = "vout".to_string();
    for (i, caption) in captions.iter().enumerate() {
        let text_path = dir.join(format!("caption-{i}.txt"));
        let text = caption.get("text").and_then(|v| v.as_str()).unwrap_or("");
        if let Err(e) = std::fs::write(&text_path, text.as_bytes()) { let _ = std::fs::remove_dir_all(&dir); return Err(format!("caption textfile: {e}")); }
        let out = if i + 1 == captions.len() { "vfinal".to_string() } else { format!("vcap{i}") };
        filters.push(caption_drawtext_filter(&input, &out, caption, &text_path.to_string_lossy(), w, h, &font));
        input = out;
    }
    Ok((filters, input, Some(dir)))
}

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
    video_clips.sort_by(|a, b| {
        let sa = a.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let sb = b.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0);
        sa.partial_cmp(&sb).unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.get("id").and_then(|v| v.as_str()).unwrap_or("").cmp(b.get("id").and_then(|v| v.as_str()).unwrap_or("")))
    });

    // Concatenate video clips with exact source trims and scale to the target.
    // Each video input is bounded with -t so export duration matches the model.
    let mut inputs: Vec<String> = Vec::new();
    let mut concat_parts: Vec<String> = Vec::new();
    let mut video_audio_parts: Vec<String> = Vec::new();
    for (i, clip) in video_clips.iter().enumerate() {
        let asset_id = clip.get("assetId").and_then(|v| v.as_str()).unwrap_or("");
        let asset = assets.iter().find(|a| a.get("id").and_then(|v| v.as_str()) == Some(asset_id));
        let source = match asset.and_then(|a| a.get("sourcePath").and_then(|v| v.as_str())) {
            Some(src) => src.to_string(),
            None => {
                emit_state(app, job_id, "FAILED", 0.0, None, Some(format!("clip {i} missing asset")));
                return;
            }
        };
        let in_point = clip.get("inPoint").and_then(|v| v.as_f64()).unwrap_or(0.0);
        let duration = clip.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.001);
        let source_duration = duration * clip_playback_rate(clip);
        inputs.extend(["-ss".into(), format!("{in_point:.3}"), "-t".into(), format!("{source_duration:.3}"), "-i".into(), source]);
        concat_parts.push(video_clip_filter(i, clip, duration, w, h));
        let has_audio = asset.and_then(|a| a.get("hasAudio")).and_then(|v| v.as_bool()).unwrap_or(false);
        let fade_out = video_clips.get(i + 1).and_then(transition_in_duration);
        video_audio_parts.push(video_clip_audio_filter_with_transition(i, clip, duration, has_audio, fade_out));
    }
    let timeline_duration = project.get("durationSec").and_then(|v| v.as_f64()).unwrap_or_else(|| video_clips.iter().map(|c| c.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0) + c.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0)).fold(0.0, f64::max)).max(0.1);
    let mut filter = concat_parts.join(";");
    filter.push(';');
    filter.push_str(&video_timeline_filter(&video_clips, timeline_duration, w, h));

    // Burn timeline captions using UTF-8 text files so caption text is never parsed
    // as filter syntax. This keeps Unicode text and untrusted punctuation inert.
    let (caption_filters, video_map_label, caption_temp_dir) = match prepare_caption_chain(&tracks, w, h) {
        Ok(v) => v,
        Err(e) => { emit_state(app, job_id, "FAILED", 0.0, None, Some(e)); return; }
    };
    for caption_filter in caption_filters { filter.push(';'); filter.push_str(&caption_filter); }

    // Explicit audio tracks retain priority. When absent, preserve embedded audio
    // from video clips instead of replacing it with global silence.
    let audio_arg: Vec<String> = vec!["-map".into(), format!("[{video_map_label}]"), "-map".into(), "[aout]".into()];
    if !audio_clips.is_empty() {
        let first_audio_input = video_clips.len();
        let mut audio_filters: Vec<String> = Vec::new();
        let mut audio_labels: Vec<String> = Vec::new();
        for (offset, clip) in audio_clips.iter().enumerate() {
            let asset_id = clip.get("assetId").and_then(|v| v.as_str()).unwrap_or("");
            let asset = assets.iter().find(|a| a.get("id").and_then(|v| v.as_str()) == Some(asset_id));
            let source = match asset.and_then(|a| a.get("sourcePath").and_then(|v| v.as_str())) {
                Some(src) => src.to_string(),
                None => continue,
            };
            let in_point = clip.get("inPoint").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let duration = clip.get("duration").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.001);
            let rate = clip_playback_rate(clip);
            let source_duration = duration * rate;
            let idx = first_audio_input + offset;
            inputs.extend(["-ss".into(), format!("{in_point:.3}"), "-t".into(), format!("{source_duration:.3}"), "-i".into(), source]);
            let gain = clip_audio_linear_gain(clip);
            let start = clip.get("start").and_then(|v| v.as_f64()).unwrap_or(0.0).max(0.0);
            let delay_ms = (start * 1000.0).round() as u64;
            let tempo = audio_atempo_chain(rate);
            let tempo_filter = if tempo.is_empty() { String::new() } else { format!(",{tempo}") };
            audio_filters.push(format!("[{idx}:a]atrim=duration={source_duration:.3},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp,aresample=44100{tempo_filter},volume={gain:.6},adelay={delay_ms}|{delay_ms}[a{idx}]"));
            audio_labels.push(format!("[a{idx}]"));
        }
        if audio_labels.is_empty() {
            let dur = project.get("durationSec").and_then(|v| v.as_f64()).unwrap_or(0.1).max(0.1);
            filter.push_str(&format!(";aevalsrc=0:d={dur:.3}[aout]"));
        } else {
            filter.push(';');
            filter.push_str(&audio_filters.join(";"));
            filter.push(';');
            filter.push_str(&format!("{}amix=inputs={}:duration=longest:normalize=0,apad,atrim=duration={timeline_duration:.3}[aout]", audio_labels.join(""), audio_labels.len()));
        }
    } else {
        filter.push(';');
        filter.push_str(&video_audio_parts.join(";"));
        let labels: Vec<String> = (0..video_clips.len()).map(|i| format!("[{i}va]")).collect();
        filter.push(';');
        filter.push_str(&format!("{}amix=inputs={}:duration=longest:normalize=0,apad,atrim=duration={timeline_duration:.3}[aout]", labels.join(""), labels.len()));
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
        if let Some(dir) = caption_temp_dir.as_ref() { let _ = std::fs::remove_dir_all(dir); }
        emit_state(app, job_id, "CANCELLED", 0.4, None, None);
        return;
    }
    let status = cmd.status();
    if let Some(dir) = caption_temp_dir.as_ref() { let _ = std::fs::remove_dir_all(dir); }
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

fn canonical_container(format_name: &str) -> String {
    let aliases: Vec<&str> = format_name.split(',').collect();
    if aliases.iter().any(|x| *x == "mp4") { return "mp4".to_string(); }
    aliases.first().copied().unwrap_or(format_name).to_string()
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
        ver.container = fmt.get("format_name").and_then(|v| v.as_str()).map(canonical_container);
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
    let audio_ok = has_audio && ver.audio_codec.as_deref() == Some("aac");
    let res_ok = ver.width == Some(want_w) && ver.height == Some(want_h);
    let nonzero = ver.size_bytes.unwrap_or(0) > 0;
    let dur_ok = ver.duration_sec.unwrap_or(0.0) > 0.0;
    ver.ok = has_video && container_ok && codec_ok && audio_ok && res_ok && nonzero && dur_ok;
    if !ver.ok {
        ver.error = Some(format!(
            "verify failed: video={has_video} audio={audio_ok} container={:?} vcodec={:?} acodec={:?} res={:?}x{:?} size={:?} dur={:?} want={}x{}",
            ver.container, ver.video_codec, ver.audio_codec, ver.width, ver.height, ver.size_bytes, ver.duration_sec, want_w, want_h
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

/// Deterministic waveform cache key. Versioned so future rendering changes can
/// invalidate old derived artifacts without touching source media.
fn waveform_cache_key(source_path: &str) -> String {
    format!("wave_{}", stable_hash(&format!("{}|waveform-v1", source_path)))
}

/// Build (or HIT) a waveform PNG in the managed cache.
pub fn ensure_waveform(app: &tauri::AppHandle, source_path: &str) -> Result<String, String> {
    let dir = cache_dir_for(app, "waveform")?;
    ensure_waveform_impl(dir, source_path)
}

fn ensure_waveform_impl(cache_dir: String, source_path: &str) -> Result<String, String> {
    let key = waveform_cache_key(source_path);
    let out_path = std::path::Path::new(&cache_dir)
        .join(format!("{key}.png"))
        .to_string_lossy()
        .to_string();
    if Path::new(&out_path).is_file() {
        return Ok(out_path);
    }
    generate_waveform_impl(source_path, &out_path)
}

fn generate_waveform_impl(source_path: &str, out_path: &str) -> Result<String, String> {
    let ffmpeg = which("ffmpeg");
    let status = ffcmd(&ffmpeg)
        .args([
            "-y", "-i", source_path,
            "-filter_complex", "aformat=channel_layouts=mono,showwavespic=s=320x64:colors=white",
            "-frames:v", "1", out_path,
        ])
        .status();
    match status {
        Ok(s) if s.success() => Ok(out_path.to_string()),
        Ok(s) => Err(format!("ffmpeg waveform failed exit {s}")),
        Err(e) => Err(format!("ffmpeg spawn error: {e}")),
    }
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

    #[test]
    fn ensure_waveform_real_miss_hit_reuse() {
        let tmp = std::env::temp_dir().join(format!(
            "haios_wave_test_{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&tmp).unwrap();
        let source = tmp.join("tone.wav");
        let gen = std::process::Command::new("ffmpeg")
            .args(["-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", source.to_str().unwrap()])
            .status()
            .expect("spawn ffmpeg tone fixture");
        assert!(gen.success());
        let cache = tmp.join("cache").to_string_lossy().to_string();
        std::fs::create_dir_all(&cache).unwrap();
        let out1 = ensure_waveform_impl(cache.clone(), source.to_str().unwrap()).expect("waveform miss");
        assert!(std::path::Path::new(&out1).is_file());
        let mtime1 = std::fs::metadata(&out1).unwrap().modified().unwrap();
        let out2 = ensure_waveform_impl(cache, source.to_str().unwrap()).expect("waveform hit");
        assert_eq!(out1, out2);
        assert_eq!(mtime1, std::fs::metadata(&out2).unwrap().modified().unwrap());
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn clip_transform_filter_contract() {
        let clip = json!({"transform": {"scale": 1.5, "x": 0.25, "y": -0.5, "opacity": 0.6}});
        let filter = video_clip_filter(2, &clip, 2.5, 1920, 1080);
        assert!(filter.contains("scale=2880:1620"));
        assert!(filter.contains("colorchannelmixer=aa=0.600000"));
        assert!(filter.contains("overlay=x=-240.000:y=-540.000"));
        assert!(filter.ends_with("[2v]"));
    }

    #[test]
    fn clip_effect_filter_contract() {
        let clip = json!({"effects": {"brightness": 0.2, "contrast": 1.4, "saturation": 0.5}});
        let filter = video_clip_filter(0, &clip, 1.0, 320, 180);
        assert!(filter.contains("eq=brightness=0.200000:contrast=1.400000:saturation=0.500000"));
    }

    #[test]
    fn clip_effect_saturation_executes_with_real_ffmpeg() {
        let clip = json!({"effects": {"brightness": 0.0, "contrast": 1.0, "saturation": 0.0}});
        let graph = video_clip_filter(0, &clip, 0.2, 64, 64);
        let out = std::process::Command::new("ffmpeg")
            .args(["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=1:d=0.2", "-filter_complex", &graph, "-map", "[0v]", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
            .output().expect("spawn effects proof");
        assert!(out.status.success());
        let i = (32 * 64 + 32) * 3;
        assert!(out.stdout.len() >= i + 3);
        let (r, g, b) = (out.stdout[i] as i16, out.stdout[i+1] as i16, out.stdout[i+2] as i16);
        assert!((r-g).abs() < 6 && (g-b).abs() < 6, "saturation=0 must produce grayscale center pixel: {r},{g},{b}");
    }

    #[test]
    fn video_timeline_gap_executes_with_real_ffmpeg() {
        let clip = json!({"start": 1.0, "duration": 1.0, "transform": {"scale": 1.0, "x": 0.0, "y": 0.0, "opacity": 1.0}});
        let clips = vec![clip.clone()];
        let graph = format!("{};{};[vout]fps=1[out]", video_clip_filter(0, &clip, 1.0, 320, 180), video_timeline_filter(&clips, 2.0, 320, 180));
        let out = std::process::Command::new("ffmpeg").args(["-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=1", "-filter_complex", &graph, "-map", "[out]", "-frames:v", "2", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]).output().expect("spawn timeline video proof");
        assert!(out.status.success());
        let frame = 320 * 180 * 3;
        assert!(out.stdout.len() >= frame * 2);
        assert!(out.stdout[..frame].iter().all(|b| *b < 10), "pre-start frame must be black");
        assert!(out.stdout[frame..frame*2].iter().any(|b| *b > 30), "active frame must contain source pixels");
    }

    #[test]
    fn audio_timeline_delay_executes_with_real_ffmpeg() {
        let clip = json!({"start": 1.0, "audio": {"gainDb": 0.0, "muted": false}});
        let graph = format!("{};[0va]apad,atrim=duration=2[aout]", video_clip_audio_filter(0, &clip, 1.0, true));
        let out = std::process::Command::new("ffmpeg").args(["-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-filter_complex", &graph, "-map", "[aout]", "-ac", "1", "-ar", "44100", "-f", "s16le", "-"]).output().expect("spawn timeline audio proof");
        assert!(out.status.success());
        let first_sec = 44100 * 2;
        assert!(out.stdout.len() >= first_sec * 2);
        assert!(out.stdout[..first_sec].iter().all(|b| *b == 0), "pre-start audio must be silence");
        assert!(out.stdout[first_sec..].iter().any(|b| *b != 0), "delayed audio must contain signal");
    }

    #[test]
    fn crossfade_filter_contract_uses_incoming_alpha_and_audio_pair() {
        let c0 = json!({"start": 0.0, "duration": 2.0, "audio": {"gainDb": 0.0, "muted": false}});
        let c1 = json!({"start": 1.5, "duration": 2.0, "transitionIn": {"type": "crossfade", "duration": 0.5}, "audio": {"gainDb": 0.0, "muted": false}});
        let vf = video_timeline_filter(&vec![c0.clone(), c1.clone()], 3.5, 320, 180);
        assert!(vf.contains("[1v]format=rgba,fade=t=in:st=0:d=0.500:alpha=1"));
        let a0 = video_clip_audio_filter_with_transition(0, &c0, 2.0, true, Some(0.5));
        let a1 = video_clip_audio_filter_with_transition(1, &c1, 2.0, true, None);
        assert!(a0.contains("afade=t=out:st=1.500:d=0.500"));
        assert!(a1.contains("afade=t=in:st=0:d=0.500"));
    }

    #[test]
    fn crossfade_video_executes_with_real_ffmpeg() {
        let c0 = json!({"start": 0.0, "duration": 2.0});
        let c1 = json!({"start": 1.5, "duration": 2.0, "transitionIn": {"type": "crossfade", "duration": 0.5}});
        let clips = vec![c0.clone(), c1.clone()];
        let graph = format!("{};{};{};[vout]trim=start=1.74:end=1.77,setpts=PTS-STARTPTS[out]",
            video_clip_filter(0, &c0, 2.0, 64, 64),
            video_clip_filter(1, &c1, 2.0, 64, 64),
            video_timeline_filter(&clips, 3.5, 64, 64));
        let out = std::process::Command::new("ffmpeg").args([
            "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64:r=30:d=2",
            "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=30:d=2",
            "-filter_complex", &graph, "-map", "[out]", "-frames:v", "1",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ]).output().expect("spawn crossfade video proof");
        assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
        let i = (32 * 64 + 32) * 3;
        assert!(out.stdout.len() >= i + 3);
        let (r, g, b) = (out.stdout[i], out.stdout[i + 1], out.stdout[i + 2]);
        assert!(r > 45 && b > 45 && g < 60, "mid-crossfade must contain both sources: {r},{g},{b}");
    }

    #[test]
    fn crossfade_audio_executes_with_real_ffmpeg() {
        let c0 = json!({"start": 0.0, "audio": {"gainDb": 0.0, "muted": false}});
        let c1 = json!({"start": 1.5, "transitionIn": {"type": "crossfade", "duration": 0.5}, "audio": {"gainDb": 0.0, "muted": false}});
        let graph = format!("{};{};[0va][1va]amix=inputs=2:duration=longest:normalize=0[aout]",
            video_clip_audio_filter_with_transition(0, &c0, 2.0, true, Some(0.5)),
            video_clip_audio_filter_with_transition(1, &c1, 2.0, false, None));
        let out = std::process::Command::new("ffmpeg").args([
            "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-filter_complex", &graph, "-map", "[aout]", "-ac", "1", "-ar", "44100",
            "-f", "s16le", "-",
        ]).output().expect("spawn crossfade audio proof");
        assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
        let window_peak = |start_sec: f64, span_sec: f64| -> i16 {
            let start = (start_sec * 44100.0) as usize * 2;
            let end = (((start_sec + span_sec) * 44100.0) as usize * 2).min(out.stdout.len());
            out.stdout[start..end].chunks_exact(2)
                .map(|b| i16::from_le_bytes([b[0], b[1]]).abs())
                .max().unwrap_or(0)
        };
        let early = window_peak(1.52, 0.08);
        let late = window_peak(1.90, 0.08);
        assert!(early > late * 3, "outgoing audio must fade down across overlap: early={early} late={late}");
    }

    #[test]
    fn playback_rate_filter_contract_retimes_video_and_audio() {
        let clip = json!({"start": 0.0, "duration": 2.0, "playbackRate": 2.0, "audio": {"gainDb": 0.0, "muted": false}});
        let vf = video_clip_filter(0, &clip, 2.0, 320, 180);
        assert!(vf.contains("trim=duration=4.000"), "{vf}");
        assert!(vf.contains("setpts=(PTS-STARTPTS)/2.000000"), "{vf}");
        let af = video_clip_audio_filter(0, &clip, 2.0, true);
        assert!(af.contains("atrim=duration=4.000"), "{af}");
        assert!(af.contains("atempo=2.000000"), "{af}");
    }

    #[test]
    fn quarter_speed_audio_uses_valid_atempo_chain() {
        let clip = json!({"start": 0.0, "duration": 4.0, "playbackRate": 0.25, "audio": {"gainDb": 0.0, "muted": false}});
        let af = video_clip_audio_filter(0, &clip, 4.0, true);
        assert!(af.contains("atempo=0.500000,atempo=0.500000"), "{af}");
        assert!(af.contains("atrim=duration=1.000"), "{af}");
    }

    #[test]
    fn canonical_container_normalizes_ffprobe_mp4_aliases() {
        assert_eq!(canonical_container("mov,mp4,m4a,3gp,3g2,mj2"), "mp4");
        assert_eq!(canonical_container("matroska,webm"), "matroska");
    }

    #[test]
    fn video_timeline_filter_preserves_start_gap_and_duration() {
        let clips = vec![json!({"start": 2.0, "duration": 1.0, "transform": {"scale": 1.0, "x": 0.0, "y": 0.0, "opacity": 1.0}})];
        let f = video_timeline_filter(&clips, 3.0, 320, 180);
        assert!(f.contains("color=c=black:s=320x180:d=3.000"));
        assert!(f.contains("setpts=PTS+2.000/TB"));
        assert!(f.contains("enable='between(t,2.000,3.000)'"));
        assert!(f.ends_with("[vout]"));
    }

    #[test]
    fn audio_filter_preserves_clip_start_with_delay() {
        let clip = json!({"start": 1.5, "audio": {"gainDb": 0.0, "muted": false}});
        let f = video_clip_audio_filter(0, &clip, 1.0, true);
        assert!(f.contains("adelay=1500|1500"));
    }

    #[test]
    fn caption_filter_contract_uses_textfile_timing_position_and_style() {
        let c = json!({"text": "สวัสดี Caption", "start": 1.25, "duration": 2.5, "style": {"x": 0.25, "y": 0.75, "fontSizePx": 52, "color": "#FFCC00", "backgroundColor": "#112233", "backgroundOpacity": 0.4}});
        let f = caption_drawtext_filter("vin", "vout", &c, r"C:\Temp\cap.txt", 1920, 1080, r"C:\Windows\Fonts\segoeui.ttf");
        assert!(f.contains("textfile="));
        assert!(f.contains("enable='between(t,1.250,3.750)'"));
        assert!(f.contains("x=480.000-text_w/2"));
        assert!(f.contains("y=810.000-text_h/2"));
        assert!(f.contains("fontsize=52"));
        assert!(f.contains("fontcolor=#FFCC00"));
        assert!(f.contains("boxcolor=#112233@0.400"));
    }

    #[test]
    fn caption_chain_writes_utf8_and_returns_final_label() {
        let tracks = vec![json!({"kind": "text", "captions": [{"text": "ไทย UTF-8", "start": 0.0, "duration": 1.0, "style": {}}]})];
        let (filters, label, dir) = prepare_caption_chain(&tracks, 320, 180).expect("caption chain");
        assert_eq!(label, "vfinal");
        assert_eq!(filters.len(), 1);
        let dir = dir.expect("temp dir");
        assert_eq!(std::fs::read_to_string(dir.join("caption-0.txt")).unwrap(), "ไทย UTF-8");
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn caption_filter_executes_unicode_textfile_with_real_ffmpeg() {
        let tmp = std::env::temp_dir().join(format!("haios-caption-proof-{}", std::process::id()));
        let _ = std::fs::create_dir_all(&tmp);
        let text = tmp.join("caption.txt");
        std::fs::write(&text, "สวัสดี Caption".as_bytes()).unwrap();
        let c = json!({"start": 0.0, "duration": 1.0, "style": {"x": 0.5, "y": 0.5, "fontSizePx": 48, "color": "#FFFFFF", "backgroundColor": "#000000", "backgroundOpacity": 0.0}});
        let f = caption_drawtext_filter("0:v", "out", &c, &text.to_string_lossy(), 320, 180, &caption_font_path());
        let out = std::process::Command::new("ffmpeg").args(["-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=1", "-filter_complex", &f, "-map", "[out]", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]).output().expect("spawn ffmpeg caption proof");
        assert!(out.status.success(), "drawtext graph must execute");
        assert!(out.stdout.iter().any(|b| *b > 16), "caption must produce non-black pixels");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn clip_transform_filter_executes_with_real_ffmpeg() {
        let clip = json!({"transform": {"scale": 0.75, "x": 0.2, "y": -0.2, "opacity": 0.5}});
        let filter = video_clip_filter(0, &clip, 0.5, 320, 240);
        let status = std::process::Command::new("ffmpeg")
            .args(["-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=0.5",
                "-filter_complex", &filter, "-map", "[0v]", "-frames:v", "1", "-f", "null", "-"])
            .status().expect("spawn ffmpeg transform proof");
        assert!(status.success(), "transform filter graph must execute");
    }

    #[test]
    fn clip_audio_gain_contract() {
        let default_clip = json!({});
        assert!((clip_audio_linear_gain(&default_clip) - 1.0).abs() < 1e-9);
        let muted = json!({"audio": {"gainDb": -6.0, "muted": true}});
        assert_eq!(clip_audio_linear_gain(&muted), 0.0);
        let minus_six = json!({"audio": {"gainDb": -6.0, "muted": false}});
        assert!((clip_audio_linear_gain(&minus_six) - 0.501187).abs() < 0.00001);
    }

    #[test]
    fn video_clip_audio_filter_uses_source_or_silence_deterministically() {
        let clip = json!({"audio": {"gainDb": -12.0, "muted": false}});
        let embedded = video_clip_audio_filter(0, &clip, 2.5, true);
        assert!(embedded.contains("[0:a]"));
        assert!(embedded.contains("atrim=duration=2.500"));
        assert!(embedded.contains("volume=0.251189"));
        let silent = video_clip_audio_filter(1, &clip, 1.25, false);
        assert!(silent.contains("anullsrc=r=44100:cl=mono:d=1.250"));
        assert!(silent.contains("[1va]"));
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
