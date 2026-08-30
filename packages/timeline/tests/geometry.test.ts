import { createEmptyProject, type Clip } from "@haios/project-model";
import {
  pxToSec,
  secToPx,
  pxPerSec,
  snap,
  collectSnapPoints,
  clipAtTime,
  clamp,
  type TimelineView,
} from "../src/geometry.js";

const view: TimelineView = {
  pxPerSecBase: 100,
  zoom: 2,
  scrollSec: 5,
  playheadSec: 10,
  snapInterval: 1,
};

const proj = createEmptyProject("P", "p");
const clip: Clip = {
  id: "c1",
  assetId: "a1",
  inPoint: 0,
  duration: 4,
  start: 2,
  trackId: "tv",
};
proj.tracks = [{ id: "tv", kind: "video", clips: [clip] }];

describe("timeline geometry", () => {
  it("pxPerSec scales with zoom", () => {
    expect(pxPerSec(view)).toBe(200);
  });

  it("secToPx / pxToSec are inverse within scroll offset", () => {
    const px = secToPx(view, 12);
    expect(px).toBe((12 - 5) * 200);
    expect(pxToSec(view, px)).toBeCloseTo(12);
  });

  it("collectSnapPoints includes clip edges, playhead and grid", () => {
    const pts = collectSnapPoints(proj, view);
    expect(pts).toContain(2); // clip start
    expect(pts).toContain(6); // clip end (2+4)
    expect(pts).toContain(10); // playhead
    expect(pts).toContain(5); // grid
  });

  it("snap returns the nearest point within tolerance", () => {
    const pts = collectSnapPoints(proj, view);
    const r = snap(6.05, pts, 0.2);
    expect(r.snapped).toBe(true);
    expect(r.value).toBeCloseTo(6);
  });

  it("snap returns original value when nothing is close", () => {
    const r = snap(6.5, collectSnapPoints(proj, view), 0.1);
    expect(r.snapped).toBe(false);
    expect(r.value).toBeCloseTo(6.5);
  });

  it("clipAtTime finds the clip covering the time", () => {
    expect(clipAtTime(proj, "tv", 3)?.id).toBe("c1");
    expect(clipAtTime(proj, "tv", 7)).toBeUndefined();
  });

  it("clamp bounds values", () => {
    expect(clamp(5, 0, 3)).toBe(3);
    expect(clamp(-1, 0, 3)).toBe(0);
    expect(clamp(2, 0, 3)).toBe(2);
  });
});
