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

export function pxPerSec(view: TimelineView): number {
  return view.pxPerSecBase * view.zoom;
}

export function secToPx(view: TimelineView, sec: number): number {
  return (sec - view.scrollSec) * pxPerSec(view);
}

export function pxToSec(view: TimelineView, px: number): number {
  return view.scrollSec + px / pxPerSec(view);
}

/** Collect typed magnetic snap candidates, excluding active moving clips. */
export function collectSnapCandidates(project: Project, view: TimelineView, excludeClipIds: ReadonlySet<string> = new Set()): SnapCandidate[] {
  const out: SnapCandidate[] = [{ value: view.playheadSec, target: "playhead" }];
  for (const track of project.tracks) {
    for (const c of track.clips) {
      if (excludeClipIds.has(c.id)) continue;
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

export function findMagneticSnap(edges: readonly number[], candidates: readonly SnapCandidate[], toleranceSec: number): MagneticSnapResult {
  let best: { distance: number; delta: number; candidate: SnapCandidate } | null = null;
  for (const edge of edges) {
    for (const candidate of candidates) {
      const delta = candidate.value - edge;
      const distance = Math.abs(delta);
      if (distance > toleranceSec) continue;
      if (!best || distance < best.distance - 1e-12) best = { distance, delta, candidate };
    }
  }
  if (!best) return { snapped: false, delta: 0 };
  return {
    snapped: true,
    delta: Number(best.delta.toFixed(12)),
    guideSec: best.candidate.value,
    target: best.candidate.target,
    ...(best.candidate.clipId ? { clipId: best.candidate.clipId } : {}),
  };
}

/** Collect legacy numeric snap points for existing callers. */
export function collectSnapPoints(project: Project, view: TimelineView): number[] {
  return [...new Set(collectSnapCandidates(project, view).map((c) => c.value))].sort((a, b) => a - b);
}

/**
 * Snap a value (e.g. a drag start position) to the nearest snap point within
 * `toleranceSec`. Returns the original value when nothing is close enough.
 */
export function snap(value: number, points: number[], toleranceSec: number): SnapResult {
  let best = value;
  let bestDist = toleranceSec;
  let target: SnapResult["target"];
  for (const p of points) {
    const d = Math.abs(p - value);
    if (d < bestDist) {
      bestDist = d;
      best = p;
      target = p === value ? undefined : "grid";
    }
  }
  if (best === value) return { value, snapped: false };
  return { value: best, snapped: true, target };
}

/** Clamp a value to [min, max]. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Clip that is under the playhead at `sec`, if any (topmost track wins). */
export function clipAtTime(project: Project, trackId: string, sec: number): Clip | undefined {
  const track = project.tracks.find((t) => t.id === trackId);
  if (!track) return undefined;
  return track.clips.find((c) => sec >= c.start && sec < c.start + c.duration);
}
