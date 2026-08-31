use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::Manager;

mod bridge;

// Shared mutable registry of render jobs (job_id -> cancellation flag).
// Cancellation is cooperative: the render loop checks the flag between ffmpeg steps.
struct RenderState {
    jobs: Mutex<HashMap<String, RenderJob>>,
}

struct RenderJob {
    cancelled: bool,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MediaProbe {
    pub id: String,
    pub name: String,
    pub source_path: String,
    pub kind: String,
    pub duration_sec: f64,
    pub width: u32,
    pub height: u32,
    pub fps: f64,
    pub has_audio: bool,
    pub video_codec: Option<String>,
    pub audio_codec: Option<String>,
    pub audio_sample_rate: Option<u32>,
    pub probe_status: String,
    pub error: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderStateView {
    pub job_id: String,
    pub status: String,
    pub progress: f64,
    pub output_path: Option<String>,
    pub error: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RenderVerification {
    pub ok: bool,
    pub container: Option<String>,
    pub video_codec: Option<String>,
    pub audio_codec: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub duration_sec: Option<f64>,
    pub size_bytes: Option<u64>,
    pub error: Option<String>,
}

/// Probe a local media file with ffprobe. Never mutates the source.
#[tauri::command]
fn probe_media(path: String) -> MediaProbe {
    bridge::probe_media(&path)
}

/// Generate a single thumbnail frame at the given time (seconds) into `out_path`.
#[tauri::command]
fn generate_thumbnail(source_path: String, out_path: String, time_sec: f64) -> Result<String, String> {
    bridge::generate_thumbnail(&source_path, &out_path, time_sec)
}

/// Generate a deterministic H.264/AAC MP4 preview proxy for a source that the
/// WebView cannot decode directly. Original media is never overwritten.
#[tauri::command]
fn generate_preview_proxy(source_path: String, out_path: String) -> Result<String, String> {
    bridge::generate_preview_proxy(&source_path, &out_path)
}

/// Report local backend capabilities (binaries present, engine seams).
#[tauri::command]
fn hvs_capabilities() -> serde_json::Value {
    bridge::hvs_capabilities()
}

/// R2.2 — Build (or HIT) a deterministic H.264/AAC MP4 preview proxy inside the
/// managed cache. Returns the cache path. On HIT the existing file is reused.
#[tauri::command]
fn ensure_preview_proxy(
    source_path: String,
    video_codec: Option<String>,
    audio_codec: Option<String>,
    app: tauri::AppHandle,
) -> Result<String, String> {
    bridge::ensure_preview_proxy(&app, &source_path, &video_codec, &audio_codec)
}

/// R2.2 — Build (or HIT) a deterministic thumbnail inside the managed cache.
#[tauri::command]
fn ensure_thumbnail(source_path: String, time_sec: f64, app: tauri::AppHandle) -> Result<String, String> {
    bridge::ensure_thumbnail(&app, &source_path, time_sec)
}

/// R2.2 — Invalidate a cache entry by deterministic key + kind.
#[tauri::command]
fn invalidate_cache(kind: String, key: String, app: tauri::AppHandle) -> bool {
    bridge::invalidate_cache_entry(&app, &kind, &key)
}

/// Start a render. Returns the job id. Runs ffmpeg synchronously on a spawned
/// thread and reports progress to the frontend via an event.
#[tauri::command]
fn hvs_render(
    project_json: String,
    output_path: String,
    resolution: String,
    app: tauri::AppHandle,
) -> Result<String, String> {
    let job_id = format!(
        "job-{}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0)
    );
    {
        let state = app.state::<RenderState>();
        state.jobs.lock().unwrap().insert(
            job_id.clone(),
            RenderJob { cancelled: false },
        );
    }
    let job_id_clone = job_id.clone();
    let out_clone = output_path.clone();
    let res_clone = resolution.clone();
    let app_clone = app.clone();
    std::thread::spawn(move || {
        bridge::run_render(
            &job_id_clone,
            &project_json,
            &out_clone,
            &res_clone,
            &app_clone,
        );
    });
    Ok(job_id)
}

/// Verify a rendered output file with ffprobe against the requested spec.
#[tauri::command]
fn verify_render(output_path: String, resolution: String) -> RenderVerification {
    bridge::verify_render(&output_path, &resolution)
}

/// Request cancellation of a running render job. Cooperative: the render loop
/// observes the flag and stops before finalizing.
#[tauri::command]
fn cancel_render(job_id: String, app: tauri::AppHandle) -> Result<bool, String> {
    let state = app.state::<RenderState>();
    let mut jobs = state.jobs.lock().unwrap();
    if let Some(job) = jobs.get_mut(&job_id) {
        job.cancelled = true;
        Ok(true)
    } else {
        Err(format!("unknown job id: {job_id}"))
    }
}

/// Check whether a render job was cancelled (used by the render loop).
pub fn is_cancelled(app: &tauri::AppHandle, job_id: &str) -> bool {
    let cancelled = {
        app.state::<RenderState>()
            .jobs
            .lock()
            .unwrap()
            .get(job_id)
            .map(|j| j.cancelled)
            .unwrap_or(false)
    };
    cancelled
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(RenderState { jobs: Mutex::new(HashMap::new()) })
        .invoke_handler(tauri::generate_handler![
            probe_media,
            generate_thumbnail,
            generate_preview_proxy,
            hvs_capabilities,
            ensure_preview_proxy,
            ensure_thumbnail,
            invalidate_cache,
            hvs_render,
            verify_render,
            cancel_render
        ])
        .run(tauri::generate_context!())
        .expect("error while running HAIOS AI Video Studio");
}
