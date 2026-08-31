import type { Clip, MediaAsset } from "./schema.js";
export declare class ClipMathError extends Error {
    constructor(message: string);
}
/** Source seconds consumed by a timeline clip. */
export declare function sourceSpan(clip: {
    duration: number;
    playbackRate?: number;
}): number;
/** The source end consumed by a clip. */
export declare function sourceEnd(clip: {
    inPoint: number;
    duration: number;
    playbackRate?: number;
}): number;
/**
 * A clip is valid iff it consumes a sub-range within its source asset.
 *   inPoint >= 0  AND  inPoint + duration <= assetDuration (+ eps)
 * Returns null when valid, otherwise a human-readable failure reason.
 */
export declare function validateClipAgainstAsset(clip: Pick<Clip, "inPoint" | "duration"> & Partial<Pick<Clip, "playbackRate">>, asset: Pick<MediaAsset, "durationSec">): string | null;
export interface TrimResult {
    /** The mutated clip. */
    clip: Clip;
}
/**
 * Trim the LEFT edge to a new in-point. The source end (inPoint+duration) is
 * preserved; only the duration shrinks/grows. `newInPoint` must keep
 * 0 <= duration.
 */
export declare function trimLeft(clip: Clip, newInPoint: number): Clip;
/**
 * Trim the RIGHT edge to a new end (timeline-relative end of source window).
 * In-point is preserved; duration = newEnd - inPoint.
 */
export declare function trimRight(clip: Clip, newSourceEnd: number): Clip;
export interface SplitResult {
    left: Clip;
    right: Clip;
}
/**
 * Split a clip at timeline offset `t` seconds from the clip's start.
 * Requires 0 < t < duration. The two resulting clips together cover exactly the
 * same source range as the original (source-end preserved).
 *
 *   left:  inPoint = clip.inPoint,            duration = t
 *   right: inPoint = clip.inPoint + t,         start = clip.start + t,
 *          duration = clip.duration - t
 */
export declare function splitClip(clip: Clip, t: number): SplitResult;
/** Move a clip (and its right sibling chain is the caller's concern). */
export declare function moveClip(clip: Clip, newStart: number): Clip;
//# sourceMappingURL=clip-math.d.ts.map