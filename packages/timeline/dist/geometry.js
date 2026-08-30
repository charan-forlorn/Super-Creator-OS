export function pxPerSec(view) {
    return view.pxPerSecBase * view.zoom;
}
export function secToPx(view, sec) {
    return (sec - view.scrollSec) * pxPerSec(view);
}
export function pxToSec(view, px) {
    return view.scrollSec + px / pxPerSec(view);
}
/**
 * Collect snap candidates from the project: clip edges + playhead + grid lines.
 */
export function collectSnapPoints(project, view) {
    const pts = [view.playheadSec];
    for (const track of project.tracks) {
        for (const c of track.clips) {
            pts.push(c.start, c.start + c.duration);
        }
    }
    if (view.snapInterval > 0) {
        const maxSec = Math.max(project.durationSec, view.playheadSec) + 10;
        for (let s = 0; s <= maxSec; s += view.snapInterval)
            pts.push(s);
    }
    return [...new Set(pts)].sort((a, b) => a - b);
}
/**
 * Snap a value (e.g. a drag start position) to the nearest snap point within
 * `toleranceSec`. Returns the original value when nothing is close enough.
 */
export function snap(value, points, toleranceSec) {
    let best = value;
    let bestDist = toleranceSec;
    let target;
    for (const p of points) {
        const d = Math.abs(p - value);
        if (d < bestDist) {
            bestDist = d;
            best = p;
            target = p === value ? undefined : "grid";
        }
    }
    if (best === value)
        return { value, snapped: false };
    return { value: best, snapped: true, target };
}
/** Clamp a value to [min, max]. */
export function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}
/** Clip that is under the playhead at `sec`, if any (topmost track wins). */
export function clipAtTime(project, trackId, sec) {
    const track = project.tracks.find((t) => t.id === trackId);
    if (!track)
        return undefined;
    return track.clips.find((c) => sec >= c.start && sec < c.start + c.duration);
}
//# sourceMappingURL=geometry.js.map