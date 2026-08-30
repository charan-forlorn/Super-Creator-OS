import { z } from "zod";
import type { ExportResolution, MediaAsset } from "@haios/project-model";

/**
 * Explicit Tauri <-> Frontend bridge contract.
 *
 * These types are the SINGLE source of truth for the IPC surface between the
 * React frontend and the Rust backend. The Rust commands return JSON that
 * deserializes into these shapes. Keeping them here (not duplicated in either
 * side) prevents the two ends from drifting.
 */

export const PROBE_STATUS = [
  "ok",
  "missing",
  "unavailable",
  "corrupt",
  "failed",
] as const;
export type ProbeStatus = (typeof PROBE_STATUS)[number];

export const mediaProbeSchema = z.object({
  id: z.string(),
  name: z.string(),
  sourcePath: z.string(),
  kind: z.enum(["video", "audio", "image", "unknown"]),
  durationSec: z.number().nonnegative(),
  width: z.number().int().nonnegative(),
  height: z.number().int().nonnegative(),
  fps: z.number().nonnegative(),
  hasAudio: z.boolean(),
  videoCodec: z.string().nullable(),
  audioCodec: z.string().nullable(),
  audioSampleRate: z.number().int().nullable(),
  probeStatus: z.enum(PROBE_STATUS),
  error: z.string().nullable(),
});
export type MediaProbe = z.infer<typeof mediaProbeSchema>;

export const RENDER_STATES = [
  "QUEUED",
  "ANALYZING",
  "RENDERING",
  "VERIFYING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
] as const;
export type RenderState = (typeof RENDER_STATES)[number];

export const renderProgressSchema = z.object({
  jobId: z.string(),
  status: z.enum(RENDER_STATES),
  progress: z.number().min(0).max(1),
  outputPath: z.string().nullable(),
  error: z.string().nullable(),
});
export type RenderProgress = z.infer<typeof renderProgressSchema>;

export const renderVerificationSchema = z.object({
  ok: z.boolean(),
  container: z.string().nullable(),
  videoCodec: z.string().nullable(),
  audioCodec: z.string().nullable(),
  width: z.number().int().nullable(),
  height: z.number().int().nullable(),
  durationSec: z.number().nullable(),
  sizeBytes: z.number().nullable(),
  error: z.string().nullable(),
});
export type RenderVerification = z.infer<typeof renderVerificationSchema>;

export const hvsCapabilitiesSchema = z.object({
  ffprobe: z.boolean(),
  ffmpeg: z.boolean(),
  engine: z.string(),
  mode: z.string(),
  resolutions: z.array(z.string()),
  videoCodec: z.string(),
  audioCodec: z.string(),
  container: z.string(),
});
export type HvsCapabilities = z.infer<typeof hvsCapabilitiesSchema>;

/** Map a probed media file into a typed MediaAsset for the project model. */
export function probeToAsset(probe: MediaProbe): MediaAsset {
  if (probe.probeStatus !== "ok") {
    throw new Error(`cannot build asset from failed probe: ${probe.error ?? probe.probeStatus}`);
  }
  return {
    id: probe.id,
    name: probe.name,
    sourcePath: probe.sourcePath,
    kind: probe.kind === "audio" ? "audio" : probe.kind === "video" ? "video" : "image",
    durationSec: probe.durationSec,
    width: probe.width || undefined,
    height: probe.height || undefined,
    fps: probe.fps || undefined,
    hasAudio: probe.hasAudio,
    createdAt: new Date().toISOString(),
  };
}

/** Expected resolution dimensions for export presets. */
export function resolutionDims(r: ExportResolution): { w: number; h: number } {
  switch (r) {
    case "1080x1920": return { w: 1080, h: 1920 };
    case "1080x1080": return { w: 1080, h: 1080 };
    default: return { w: 1920, h: 1080 };
  }
}

/**
 * ROOT_CAUSE_3 — WebView2 preview codec compatibility decision.
 *
 * WebView2's underlying media stack (system/dependent on OS decoders) cannot
 * always decode HEVC, ProRes, exotic MOV variants, or odd audio codecs. We
 * therefore decide, deterministically from ffprobe metadata, whether the
 * ORIGINAL can be previewed directly or whether a cached H.264/AAC MP4 proxy
 * must be generated (original source always preserved for final render).
 */
export interface PreviewCompatInput {
  kind: "video" | "audio" | "image" | "unknown";
  videoCodec?: string | null;
  audioCodec?: string | null;
}

// Codecs WebView2/Chromium reliably decode for preview.
const DIRECT_VIDEO_CODECS = new Set([
  "h264",
  "avc1",
  "avc",
  "vp8",
  "vp9",
  "theora",
  "mpeg4",
  "mp4v",
]);
const DIRECT_AUDIO_CODECS = new Set([
  "aac",
  "mp3",
  "mp3float",
  "vorbis",
  "opus",
  "flac",
  "pcm_s16le",
  "pcm_s16be",
  "pcm_s24le",
  "pcm_f32le",
]);

export function previewNeedsProxy(input: PreviewCompatInput): boolean {
  // Non-video media (audio/image) is always previewable through the asset
  // protocol without transcoding.
  if (input.kind !== "video") return false;
  const v = (input.videoCodec ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const a = (input.audioCodec ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  // If we cannot read a video codec at all we optimistically try direct
  // playback (fail-closed at the WebView via error diagnostics); we do NOT
  // assume a proxy is needed when metadata is missing.
  if (!v) return false;
  if (!DIRECT_VIDEO_CODECS.has(v)) return true;
  // Only require an audio-codec proxy when audio is present and unsupported.
  // A silent H.264 clip can still play directly.
  if (a && !DIRECT_AUDIO_CODECS.has(a)) return true;
  return false;
}
