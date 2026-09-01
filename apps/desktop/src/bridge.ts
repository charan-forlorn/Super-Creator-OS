// Frontend -> Tauri bridge. Thin typed wrappers over the Rust commands.
// Keeps all IPC surface in one place so the UI never calls invoke() directly.
import { invoke } from "@tauri-apps/api/core";

export interface MediaProbe {
  id: string;
  name: string;
  sourcePath: string;
  kind: string;
  durationSec: number;
  width: number;
  height: number;
  fps: number;
  hasAudio: boolean;
  videoCodec: string | null;
  audioCodec: string | null;
  audioSampleRate: number | null;
  probeStatus: string;
  error: string | null;
}

export interface RenderVerification {
  ok: boolean;
  container: string | null;
  videoCodec: string | null;
  audioCodec: string | null;
  width: number | null;
  height: number | null;
  durationSec: number | null;
  sizeBytes: number | null;
  error: string | null;
}

export interface RenderProgress {
  jobId: string;
  status: string; // QUEUED|ANALYZING|RENDERING|VERIFYING|COMPLETED|FAILED|CANCELLED
  progress: number;
  outputPath: string | null;
  error: string | null;
}

export interface HvsCapabilities {
  ffprobe: boolean;
  ffmpeg: boolean;
  engine: string;
  mode: string;
  resolutions: string[];
  videoCodec: string;
  audioCodec: string;
  container: string;
}

export interface ProjectAutosaveEnvelope {
  projectJson: string;
  projectPath: string | null;
  savedAtMs: number;
  projectId: string;
}

export async function probeMedia(path: string): Promise<MediaProbe> {
  return invoke<MediaProbe>("probe_media", { path });
}

export async function generateThumbnail(sourcePath: string, outPath: string, timeSec: number): Promise<string> {
  return invoke<string>("generate_thumbnail", { sourcePath, outPath, timeSec });
}

export async function ensurePreviewProxy(sourcePath: string, videoCodec: string | null, audioCodec: string | null): Promise<string> {
  return invoke<string>("ensure_preview_proxy", { sourcePath, videoCodec, audioCodec });
}

export async function ensureThumbnail(sourcePath: string, timeSec: number): Promise<string> {
  return invoke<string>("ensure_thumbnail", { sourcePath, timeSec });
}

export async function ensureWaveform(sourcePath: string): Promise<string> {
  return invoke<string>("ensure_waveform", { sourcePath });
}

export async function invalidateCache(kind: string, key: string): Promise<boolean> {
  return invoke<boolean>("invalidate_cache", { kind, key });
}

export async function generatePreviewProxy(sourcePath: string, outPath: string): Promise<string> {
  return invoke<string>("generate_preview_proxy", { sourcePath, outPath });
}

export async function hvsCapabilities(): Promise<HvsCapabilities> {
  return invoke<HvsCapabilities>("hvs_capabilities");
}

export async function hvsRender(projectJson: string, outputPath: string, resolution: string): Promise<string> {
  return invoke<string>("hvs_render", { projectJson, outputPath, resolution });
}

export async function verifyRender(outputPath: string, resolution: string): Promise<RenderVerification> {
  return invoke<RenderVerification>("verify_render", { outputPath, resolution });
}

export async function cancelRender(jobId: string): Promise<boolean> {
  return invoke<boolean>("cancel_render", { jobId });
}

export async function listenRenderProgress(handler: (progress: RenderProgress) => void): Promise<() => void> {
  const { listen } = await import("@tauri-apps/api/event");
  return listen<RenderProgress>("render-progress", (event) => handler(event.payload));
}

export async function saveProjectFile(path: string, projectJson: string): Promise<void> {
  return invoke<void>("project_save", { path, projectJson });
}

export async function openProjectFile(path: string): Promise<string> {
  return invoke<string>("project_open", { path });
}

export async function autosaveProject(projectId: string, projectJson: string, projectPath: string | null): Promise<void> {
  return invoke<void>("project_autosave", { projectId, projectJson, projectPath });
}

export async function latestProjectAutosave(): Promise<ProjectAutosaveEnvelope | null> {
  return invoke<ProjectAutosaveEnvelope | null>("project_latest_autosave");
}

export async function clearProjectAutosave(projectId: string): Promise<boolean> {
  return invoke<boolean>("project_clear_autosave", { projectId });
}

export async function selectMediaFile(): Promise<string | null> {
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: true,
    filters: [{ name: "Media", extensions: ["mp4", "mov", "webm", "mkv", "mp3", "wav", "png", "jpg"] }],
  });
  if (Array.isArray(selected)) return selected[0] ?? null;
  return selected;
}

export async function selectOutputFile(): Promise<string | null> {
  const { save } = await import("@tauri-apps/plugin-dialog");
  return save({ filters: [{ name: "MP4", extensions: ["mp4"] }], defaultPath: "render.mp4" });
}
