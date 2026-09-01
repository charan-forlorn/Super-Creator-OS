import { createEmptyProject, type Clip } from "@haios/project-model";
import {
  collectSnapCandidates,
  findMagneticSnap,
  type TimelineView,
} from "../src/geometry.js";

const view: TimelineView = {
  pxPerSecBase: 80,
  zoom: 1,
  scrollSec: 0,
  playheadSec: 10,
  snapInterval: 1,
};

function clip(id: string, start: number, duration: number): Clip {
  return { id, assetId: "a", inPoint: 0, start, duration, trackId: "v" };
}

function project() {
  const p = createEmptyProject("snap", "p");
  p.durationSec = 20;
  p.tracks = [{ id: "v", kind: "video", clips: [clip("moving", 2, 4), clip("anchor", 12, 3)] }];
  return p;
}
describe("R2.14E precision magnetic snapping", () => {
  it("collects typed candidates and excludes moving clip edges", () => {
    const candidates = collectSnapCandidates(project(), view, new Set(["moving"]));
    expect(candidates).toContainEqual({ value: 10, target: "playhead" });
    expect(candidates).toContainEqual({ value: 12, target: "clip-start", clipId: "anchor" });
    expect(candidates).toContainEqual({ value: 15, target: "clip-end", clipId: "anchor" });
    expect(candidates.some((c) => c.clipId === "moving")).toBe(false);
  });

  it("snaps a moving left edge to the nearest valid target", () => {
    const result = findMagneticSnap([9.82, 13.82], collectSnapCandidates(project(), view, new Set(["moving"])), 0.25);
    expect(result).toMatchObject({ snapped: true, delta: 0.18, guideSec: 10, target: "playhead" });
  });

  it("snaps a moving right edge and preserves the group delta", () => {
    const result = findMagneticSnap([7.4, 11.9], collectSnapCandidates(project(), view, new Set(["moving"])), 0.25);
    expect(result.snapped).toBe(true);
    expect(result.delta).toBeCloseTo(0.1);
    expect(result.guideSec).toBe(12);
  });
  it("prefers the smallest absolute correction deterministically", () => {
    const candidates = [
      { value: 5, target: "grid" as const },
      { value: 8, target: "clip-start" as const, clipId: "a" },
    ];
    const result = findMagneticSnap([4.82, 7.94], candidates, 0.25);
    expect(result.snapped).toBe(true);
    expect(result.delta).toBeCloseTo(0.06);
    expect(result.guideSec).toBe(8);
    expect(result.target).toBe("clip-start");
  });

  it("returns no snap outside tolerance", () => {
    expect(findMagneticSnap([4.5], [{ value: 5, target: "grid" }], 0.2)).toEqual({ snapped: false, delta: 0 });
  });
  it("snaps the left outer bound of a moving group", () => {
    const result = findMagneticSnap([8.82, 16.82], [{ value: 9, target: "clip-end", clipId: "anchor" }], 0.25);
    expect(result).toMatchObject({ snapped: true, delta: 0.18, guideSec: 9, target: "clip-end" });
  });

  it("snaps the right outer bound of a moving group", () => {
    const result = findMagneticSnap([1.4, 12.82], [{ value: 13, target: "playhead" }], 0.25);
    expect(result).toMatchObject({ snapped: true, delta: 0.18, guideSec: 13, target: "playhead" });
  });});
