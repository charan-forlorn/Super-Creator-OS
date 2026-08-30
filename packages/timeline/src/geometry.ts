import type { Project, Clip } from "@haios/project-model";

export interface SnapResult {
  value: number;
  snapped: boolean;
  /** What it snapped to (for UI feedback). */
  target?: "playhead" | "clip-start" | "clip-end" | "grid";
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

/**
 * Collect snap candidates from the project: clip edges + playhead + grid lines.
 */
export function collectSnapPoints(project: Project, view: TimelineView): number[] {
  const pts: number[] = [view.playheadSec];
  for (const track of project.tracks) {
    for (const c of track.clips) {
      pts.push(c.start, c.start + c.duration);
    }
  }
  if (view.snapInterval > 0) {
    const maxSec = Math.max(project.durationSec, view.playheadSec) + 10;
    for (let s = 0; s <= maxSec; s += view.snapInterval) pts.push(s);
  }
  return [...new Set(pts)].sort((a, b) => a - b);
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
