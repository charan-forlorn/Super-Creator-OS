const EPS = 1e-6;
export class ClipMathError extends Error {
    constructor(message) {
        super(message);
        this.name = "ClipMathError";
    }
}
/** Source seconds consumed by a timeline clip. */
export function sourceSpan(clip) {
    return clip.duration * (clip.playbackRate ?? 1);
}
/** The source end consumed by a clip. */
export function sourceEnd(clip) {
    return clip.inPoint + sourceSpan(clip);
}
/**
 * A clip is valid iff it consumes a sub-range within its source asset.
 *   inPoint >= 0  AND  inPoint + duration <= assetDuration (+ eps)
 * Returns null when valid, otherwise a human-readable failure reason.
 */
export function validateClipAgainstAsset(clip, asset) {
    if (clip.duration <= 0) {
        return `clip duration must be > 0 (got ${clip.duration})`;
    }
    if (clip.inPoint < 0) {
        return `clip inPoint must be >= 0 (got ${clip.inPoint})`;
    }
    const end = sourceEnd(clip);
    if (end > asset.durationSec + EPS) {
        return `clip consumes source [${clip.inPoint}, ${end}] but asset is only ${asset.durationSec}s`;
    }
    return null;
}
/**
 * Trim the LEFT edge to a new in-point. The source end (inPoint+duration) is
 * preserved; only the duration shrinks/grows. `newInPoint` must keep
 * 0 <= duration.
 */
export function trimLeft(clip, newInPoint) {
    const end = sourceEnd(clip);
    const rate = clip.playbackRate ?? 1;
    const newDuration = (end - newInPoint) / rate;
    if (newDuration <= 0) {
        throw new ClipMathError(`INVALID_TRIM_LEFT: newInPoint ${newInPoint} would yield duration ${newDuration}`);
    }
    if (newInPoint < 0) {
        throw new ClipMathError(`INVALID_TRIM_LEFT: newInPoint ${newInPoint} < 0`);
    }
    return { ...clip, inPoint: newInPoint, duration: newDuration };
}
/**
 * Trim the RIGHT edge to a new end (timeline-relative end of source window).
 * In-point is preserved; duration = newEnd - inPoint.
 */
export function trimRight(clip, newSourceEnd) {
    const rate = clip.playbackRate ?? 1;
    const newDuration = (newSourceEnd - clip.inPoint) / rate;
    if (newDuration <= 0) {
        throw new ClipMathError(`INVALID_TRIM_RIGHT: newSourceEnd ${newSourceEnd} produces duration ${newDuration}`);
    }
    return { ...clip, duration: newDuration };
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
export function splitClip(clip, t) {
    if (!(t > 0 && t < clip.duration)) {
        throw new ClipMathError(`INVALID_SPLIT_POINT: t=${t} must satisfy 0 < t < ${clip.duration}`);
    }
    const rate = clip.playbackRate ?? 1;
    const left = { ...clip, duration: t };
    const right = {
        ...clip,
        id: `${clip.id}__r`,
        inPoint: clip.inPoint + t * rate,
        start: clip.start + t,
        duration: clip.duration - t,
    };
    return { left, right };
}
/** Move a clip (and its right sibling chain is the caller's concern). */
export function moveClip(clip, newStart) {
    if (newStart < 0) {
        throw new ClipMathError(`INVALID_MOVE: newStart ${newStart} < 0`);
    }
    return { ...clip, start: newStart };
}
//# sourceMappingURL=clip-math.js.map