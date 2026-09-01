import { createEmptyProject, type Clip, type MediaAsset } from "@haios/project-model";
import {
  ADD_CLIP,
  RIPPLE_DELETE_CLIPS,
  RIPPLE_TRIM_CLIP,
  TRIM_CLIP,
  createCommandBus,
} from "../src/index.js";

const asset: MediaAsset = {
  id: "a", name: "src.mp4", sourcePath: "/media/src.mp4", kind: "video",
  durationSec: 40, width: 1920, height: 1080, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};

function clip(id: string, start: number, duration = 4, extra: Partial<Clip> = {}): Clip {
  return {
    id, assetId: "a", inPoint: 0, duration, start, trackId: "v",
    playbackRate: 1, transitionIn: null, ...extra,
  };
}

function busWith(clips: Clip[]) {
  const project = createEmptyProject("Ripple", "ripple-p");
  project.assets = [asset];
  project.tracks = [{ id: "v", kind: "video", clips: [] }];
  const bus = createCommandBus(project);
  for (const c of clips) bus.execute(ADD_CLIP, { clip: c });
  return bus;
}
describe("R2.14 practical ripple editing kernel", () => {
  it("ripple-deletes occupied time while preserving pre-existing gaps", () => {
    const bus = busWith([clip("c0", 0), clip("c1", 6), clip("c2", 10)]);
    bus.execute(RIPPLE_DELETE_CLIPS, { clipIds: ["c0"] });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([
      ["c1", 2], ["c2", 6],
    ]);
    expect(bus.project.durationSec).toBe(10);
  });

  it("ripple delete is one exact undo/redo unit for contiguous selection", () => {
    const bus = busWith([clip("c0", 0), clip("c1", 4), clip("c2", 8), clip("c3", 12)]);
    const before = structuredClone(bus.project.tracks[0].clips);
    bus.execute(RIPPLE_DELETE_CLIPS, { clipIds: ["c1", "c2"] });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([["c0", 0], ["c3", 4]]);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0].clips).toEqual(before);
    expect(bus.redo()).toBe(true);
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([["c0", 0], ["c3", 4]]);
  });

  it("rejects ripple delete across a transition boundary", () => {
    const bus = busWith([clip("c0", 0), clip("c1", 3.5, 4, { transitionIn: { type: "crossfade", duration: 0.5 } })]);
    expect(() => bus.execute(RIPPLE_DELETE_CLIPS, { clipIds: ["c0"] })).toThrow(/RIPPLE_TRANSITION_CONFLICT/);
  });
  it("ripple-trims the right edge and shifts every later clip by the duration delta", () => {
    const bus = busWith([clip("c0", 0), clip("c1", 5), clip("c2", 9)]);
    bus.execute(RIPPLE_TRIM_CLIP, { clipId: "c0", newSourceEnd: 3 });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start, c.duration])).toEqual([
      ["c0", 0, 3], ["c1", 4, 4], ["c2", 8, 4],
    ]);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start, c.duration])).toEqual([
      ["c0", 0, 4], ["c1", 5, 4], ["c2", 9, 4],
    ]);
  });

  it("uses playbackRate when converting source trim to timeline duration", () => {
    const bus = busWith([clip("c0", 0, 4, { playbackRate: 2 }), clip("c1", 5)]);
    bus.execute(RIPPLE_TRIM_CLIP, { clipId: "c0", newSourceEnd: 6 });
    const [first, second] = bus.project.tracks[0].clips;
    expect(first.duration).toBe(3);
    expect(second.start).toBe(4);
  });

  it("keeps an incoming transition aligned when ripple trim changes the previous clip", () => {
    const bus = busWith([clip("c0", 0), clip("c1", 3.5, 4, { transitionIn: { type: "crossfade", duration: 0.5 } })]);
    bus.execute(RIPPLE_TRIM_CLIP, { clipId: "c0", newSourceEnd: 3 });
    expect(bus.project.tracks[0].clips.find((c) => c.id === "c1")?.start).toBe(2.5);
  });

  it("keeps normal trim source math rate-aware for speed-adjusted clips", () => {
    const bus = busWith([clip("c0", 0, 4, { playbackRate: 2 })]);
    bus.execute(TRIM_CLIP, { clipId: "c0", newSourceEnd: 6 });
    expect(bus.project.tracks[0].clips[0].duration).toBe(3);
    expect(bus.project.durationSec).toBe(3);
  });

  it("undoes a normal right trim back to the exact source end", () => {
    const bus = busWith([clip("c0", 0, 4, { playbackRate: 2 })]);
    bus.execute(TRIM_CLIP, { clipId: "c0", newSourceEnd: 6 });
    expect(bus.project.tracks[0].clips[0].duration).toBe(3);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0].clips[0].duration).toBe(4);
    expect(bus.redo()).toBe(true);
    expect(bus.project.tracks[0].clips[0].duration).toBe(3);
  });
});