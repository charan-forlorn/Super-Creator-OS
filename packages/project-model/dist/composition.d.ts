import type { Caption, Clip, ExportResolution, MediaAsset, Project } from "./schema.js";
export interface CompositionVisualLayer {
    trackId: string;
    /** Project track index. Larger zIndex renders in front of smaller zIndex. */
    zIndex: number;
    kind: "video" | "text";
    clips: Clip[];
    captions: Caption[];
}
export interface CompositionAudioClip {
    clipId: string;
    assetId: string;
    sourcePath: string;
    startSec: number;
    inPointSec: number;
    durationSec: number;
    playbackRate: number;
    gainDb: number;
}
export interface CompositionAudioLayer {
    trackId: string;
    /** Project track index; audio layers are mixed, not replaced. */
    mixIndex: number;
    kind: "video" | "audio";
    clips: CompositionAudioClip[];
}
export interface CompositionPlan {
    schemaVersion: 2;
    durationSec: number;
    aspectRatio: ExportResolution;
    assets: MediaAsset[];
    visualLayers: CompositionVisualLayer[];
    audioLayers: CompositionAudioLayer[];
}
/**
 * Compile persisted Project v2 state into one JSON-serializable runtime plan.
 * Project track order is canonical: lower index is background, higher index foreground.
 * Visibility affects visuals only; mute affects audio only; lock is editing-only authority.
 */
export declare function compileCompositionPlan(project: Project): CompositionPlan;
//# sourceMappingURL=composition.d.ts.map