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
export declare const PROBE_STATUS: readonly ["ok", "missing", "unavailable", "corrupt", "failed"];
export type ProbeStatus = (typeof PROBE_STATUS)[number];
export declare const mediaProbeSchema: z.ZodObject<{
    id: z.ZodString;
    name: z.ZodString;
    sourcePath: z.ZodString;
    kind: z.ZodEnum<["video", "audio", "image", "unknown"]>;
    durationSec: z.ZodNumber;
    width: z.ZodNumber;
    height: z.ZodNumber;
    fps: z.ZodNumber;
    hasAudio: z.ZodBoolean;
    videoCodec: z.ZodNullable<z.ZodString>;
    audioCodec: z.ZodNullable<z.ZodString>;
    audioSampleRate: z.ZodNullable<z.ZodNumber>;
    probeStatus: z.ZodEnum<["ok", "missing", "unavailable", "corrupt", "failed"]>;
    error: z.ZodNullable<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    id: string;
    name: string;
    sourcePath: string;
    kind: "unknown" | "video" | "audio" | "image";
    durationSec: number;
    width: number;
    height: number;
    fps: number;
    hasAudio: boolean;
    videoCodec: string | null;
    audioCodec: string | null;
    audioSampleRate: number | null;
    probeStatus: "ok" | "missing" | "unavailable" | "corrupt" | "failed";
    error: string | null;
}, {
    id: string;
    name: string;
    sourcePath: string;
    kind: "unknown" | "video" | "audio" | "image";
    durationSec: number;
    width: number;
    height: number;
    fps: number;
    hasAudio: boolean;
    videoCodec: string | null;
    audioCodec: string | null;
    audioSampleRate: number | null;
    probeStatus: "ok" | "missing" | "unavailable" | "corrupt" | "failed";
    error: string | null;
}>;
export type MediaProbe = z.infer<typeof mediaProbeSchema>;
export declare const RENDER_STATES: readonly ["QUEUED", "ANALYZING", "RENDERING", "VERIFYING", "COMPLETED", "FAILED", "CANCELLED"];
export type RenderState = (typeof RENDER_STATES)[number];
export declare const renderProgressSchema: z.ZodObject<{
    jobId: z.ZodString;
    status: z.ZodEnum<["QUEUED", "ANALYZING", "RENDERING", "VERIFYING", "COMPLETED", "FAILED", "CANCELLED"]>;
    progress: z.ZodNumber;
    outputPath: z.ZodNullable<z.ZodString>;
    error: z.ZodNullable<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    status: "QUEUED" | "ANALYZING" | "RENDERING" | "VERIFYING" | "COMPLETED" | "FAILED" | "CANCELLED";
    error: string | null;
    jobId: string;
    progress: number;
    outputPath: string | null;
}, {
    status: "QUEUED" | "ANALYZING" | "RENDERING" | "VERIFYING" | "COMPLETED" | "FAILED" | "CANCELLED";
    error: string | null;
    jobId: string;
    progress: number;
    outputPath: string | null;
}>;
export type RenderProgress = z.infer<typeof renderProgressSchema>;
export declare const renderVerificationSchema: z.ZodObject<{
    ok: z.ZodBoolean;
    container: z.ZodNullable<z.ZodString>;
    videoCodec: z.ZodNullable<z.ZodString>;
    audioCodec: z.ZodNullable<z.ZodString>;
    width: z.ZodNullable<z.ZodNumber>;
    height: z.ZodNullable<z.ZodNumber>;
    durationSec: z.ZodNullable<z.ZodNumber>;
    sizeBytes: z.ZodNullable<z.ZodNumber>;
    error: z.ZodNullable<z.ZodString>;
}, "strip", z.ZodTypeAny, {
    ok: boolean;
    durationSec: number | null;
    width: number | null;
    height: number | null;
    videoCodec: string | null;
    audioCodec: string | null;
    error: string | null;
    container: string | null;
    sizeBytes: number | null;
}, {
    ok: boolean;
    durationSec: number | null;
    width: number | null;
    height: number | null;
    videoCodec: string | null;
    audioCodec: string | null;
    error: string | null;
    container: string | null;
    sizeBytes: number | null;
}>;
export type RenderVerification = z.infer<typeof renderVerificationSchema>;
export declare const hvsCapabilitiesSchema: z.ZodObject<{
    ffprobe: z.ZodBoolean;
    ffmpeg: z.ZodBoolean;
    engine: z.ZodString;
    mode: z.ZodString;
    resolutions: z.ZodArray<z.ZodString, "many">;
    videoCodec: z.ZodString;
    audioCodec: z.ZodString;
    container: z.ZodString;
}, "strip", z.ZodTypeAny, {
    videoCodec: string;
    audioCodec: string;
    container: string;
    ffprobe: boolean;
    ffmpeg: boolean;
    engine: string;
    mode: string;
    resolutions: string[];
}, {
    videoCodec: string;
    audioCodec: string;
    container: string;
    ffprobe: boolean;
    ffmpeg: boolean;
    engine: string;
    mode: string;
    resolutions: string[];
}>;
export type HvsCapabilities = z.infer<typeof hvsCapabilitiesSchema>;
/** Map a probed media file into a typed MediaAsset for the project model. */
export declare function probeToAsset(probe: MediaProbe): MediaAsset;
/** Expected resolution dimensions for export presets. */
export declare function resolutionDims(r: ExportResolution): {
    w: number;
    h: number;
};
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
export declare function previewNeedsProxy(input: PreviewCompatInput): boolean;
