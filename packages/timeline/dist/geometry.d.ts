import type { Project, Clip } from "@haios/project-model";
export interface SnapResult {
    value: number;
    snapped: boolean;
    /** What it snapped to (for UI feedback). */
    target?: "playhead" | "clip-start" | "clip-end" | "grid";
}
export type SnapTarget = "playhead" | "clip-start" | "clip-end" | "grid";
export interface SnapCandidate {
    value: number;
    target: SnapTarget;
    clipId?: string;
}
export interface MagneticSnapResult {
    snapped: boolean;
    delta: number;
    guideSec?: number;
    target?: SnapTarget;
    clipId?: string;
}
export interface TimelineView {
    /** Pixels per second at zoom = 1. */
    pxPerSecBase: number;
    /** Zoom multiplier >= 0.1. */
    zoom: number;
    /** Visible scroll offset in seconds. */
    scrollSec: number;
    /** Playhead position in seconds. */
    playheadSec: number;
    /** Grid snap interval in seconds (0 = snapping disabled). */
    snapInterval: number;
}
export declare function pxPerSec(view: TimelineView): number;
export declare function secToPx(view: TimelineView, sec: number): number;
export declare function pxToSec(view: TimelineView, px: number): number;
/** Collect typed magnetic snap candidates, excluding active moving clips. */
export declare function collectSnapCandidates(project: Project, view: TimelineView, excludeClipIds?: ReadonlySet<string>): SnapCandidate[];
export declare function findMagneticSnap(edges: readonly number[], candidates: readonly SnapCandidate[], toleranceSec: number): MagneticSnapResult;
/** Collect legacy numeric snap points for existing callers. */
export declare function collectSnapPoints(project: Project, view: TimelineView): number[];
/**
 * Snap a value (e.g. a drag start position) to the nearest snap point within
 * `toleranceSec`. Returns the original value when nothing is close enough.
 */
export declare function snap(value: number, points: number[], toleranceSec: number): SnapResult;
/** Clamp a value to [min, max]. */
export declare function clamp(value: number, min: number, max: number): number;
/** Clip that is under the playhead at `sec`, if any (topmost track wins). */
export declare function clipAtTime(project: Project, trackId: string, sec: number): Clip | undefined;
//# sourceMappingURL=geometry.d.ts.map