export function pxPerSec(view) {
    return view.pxPerSecBase * view.zoom;
}
export function secToPx(view, sec) {
    return (sec - view.scrollSec) * pxPerSec(view);
}
export function pxToSec(view, px) {
    return view.scrollSec + px / pxPerSec(view);
}
/** Collect typed magnetic snap candidates, excluding active moving clips. */
export function collectSnapCandidates(project, view, excludeClipIds = new Set()) {
    const out = [{ value: view.playheadSec, target: "playhead" }];
    for (const track of project.tracks) {
        for (const c of track.clips) {
            if (excludeClipIds.has(c.id))
                continue;
            out.push({ value: c.start, target: "clip-start", clipId: c.id });
            out.push({ value: c.start + c.duration, target: "clip-end", clipId: c.id });
        }
    }
    if (view.snapInterval > 0) {
        const maxSec = Math.max(project.durationSec, view.playheadSec) + 10;
        for (let value = 0; value <= maxSec; value += view.snapInterval) {
            out.push({ value, target: "grid" });
        }
    }
    return out;
}
export function findMagneticSnap(edges, candidates, toleranceSec) {
    let best = null;
    for (const edge of edges) {
        for (const candidate of candidates) {
            const delta = candidate.value - edge;
            const distance = Math.abs(delta);
            if (distance > toleranceSec)
                continue;
            if (!best || distance < best.distance - 1e-12)
                best = { distance, delta, candidate };
        }
    }
    if (!best)
        return { snapped: false, delta: 0 };
    return {
        snapped: true,
        delta: Number(best.delta.toFixed(12)),
        guideSec: best.candidate.value,
        target: best.candidate.target,
        ...(best.candidate.clipId ? { clipId: best.candidate.clipId } : {}),
    };
}
/** Collect legacy numeric snap points for existing callers. */
export function collectSnapPoints(project, view) {
    return [...new Set(collectSnapCandidates(project, view).map((c) => c.value))].sort((a, b) => a - b);
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