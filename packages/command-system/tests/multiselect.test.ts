import { describe, it, expect, beforeEach } from "vitest";
import { createEmptyProject, type MediaAsset, type Clip } from "@haios/project-model";
import {
  createCommandBus,
  ADD_CLIP,
  MOVE_CLIP,
  DELETE_CLIP,
  SPLIT_CLIP,
} from "../src/index.js";

const asset: MediaAsset = {
  id: "a1",
  name: "src.mp4",
  sourcePath: "/media/src.mp4",
  kind: "video",
  durationSec: 30,
  width: 1920,
  height: 1080,
  fps: 30,
  hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};

function freshBus() {
  const p = createEmptyProject("P", "p1");
  p.assets = [asset];
  p.tracks = [{ id: "tv", kind: "video", clips: [] }];
  const bus = createCommandBus(p);
  for (let i = 0; i < 3; i++) {
    const clip: Clip = {
      id: `c${i}`,
      assetId: "a1",
      inPoint: 0,
      duration: 4,
      start: i * 4,
      trackId: "tv",
    };
    bus.execute(ADD_CLIP, { clip });
  }
  return bus;
}

// Mirror the store's group operations using bus.batch (single undo unit per group).
function groupDelete(bus: ReturnType<typeof freshBus>, ids: string[]) {
  bus.batch(ids.map((id) => ({ commandType: DELETE_CLIP, payload: { clipId: id } })));
}
function groupMove(bus: ReturnType<typeof freshBus>, ids: string[], deltaSec: number) {
  const clips = bus.project.tracks.flatMap((t) => t.clips);
  const found = ids.map((id) => clips.find((x) => x.id === id)).filter(Boolean) as Clip[];
  const rawStarts = found.map((c) => c.start + deltaSec);
  const minRaw = Math.min(...rawStarts);
  const shift = minRaw < 0 ? -minRaw : 0;
  const moves = found.map((c) => ({ clipId: c.id, newStart: c.start + deltaSec + shift }));
  bus.batch(moves.map((m) => ({ commandType: MOVE_CLIP, payload: m })));
}
function groupSplit(bus: ReturnType<typeof freshBus>, ids: string[], localT: number) {
  const clips = bus.project.tracks.flatMap((t) => t.clips);
  const splits = ids
    .map((id) => {
      const c = clips.find((x) => x.id === id);
      return c && localT > 0 && localT < c.duration ? { clipId: id, t: localT } : null;
    })
    .filter((s): s is { clipId: string; t: number } => s !== null);
  bus.batch(splits.map((s) => ({ commandType: SPLIT_CLIP, payload: s })));
}

describe("R2.1 multi-selection group operations (exact undo/redo)", () => {
  let bus: ReturnType<typeof freshBus>;
  beforeEach(() => {
    bus = freshBus();
  });

  it("group delete of 2 clips collapses to ONE undo restoring both", () => {
    groupDelete(bus, ["c0", "c2"]);
    expect(bus.project.tracks[0].clips.map((c) => c.id)).toEqual(["c1"]);
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.id).sort()).toEqual(["c0", "c1", "c2"]);
  });

  it("group move shifts all selected clips by delta and collapses to ONE undo", () => {
    groupMove(bus, ["c0", "c1", "c2"], 2);
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([2, 6, 10]);
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
  });

  it("group split of 3 clips collapses to ONE undo restoring 3 clips", () => {
    groupSplit(bus, ["c0", "c1", "c2"], 2);
    // each 4s clip -> 2s + 2s => 6 clips
    expect(bus.project.tracks[0].clips).toHaveLength(6);
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.id).sort()).toEqual(["c0", "c1", "c2"]);
    expect(bus.project.tracks[0].clips.every((c) => c.duration === 4)).toBe(true);
  });

  it("group move keeps relative spacing and does not cross below 0", () => {
    groupMove(bus, ["c0", "c1", "c2"], -100);
    // whole group is lifted so the minimum start is 0, preserving 4s spacing
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
  });

  it("group delete is fail-closed: a missing id rejects the whole batch", () => {
    const before = bus.project.tracks[0].clips.map((c) => c.id);
    expect(() => groupDelete(bus, ["c0", "c9"])).toThrow();
    expect(bus.project.tracks[0].clips.map((c) => c.id)).toEqual(before);
  });

  it("undo then redo of a group move is byte-exact", () => {
    const before = JSON.parse(JSON.stringify(bus.project.tracks[0].clips));
    groupMove(bus, ["c0", "c1"], 1.5);
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([1.5, 5.5, 8]);
    bus.undo();
    expect(JSON.parse(JSON.stringify(bus.project.tracks[0].clips))).toEqual(before);
    bus.redo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([1.5, 5.5, 8]);
  });
});
