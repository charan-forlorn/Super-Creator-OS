import { createEmptyProject, type Clip, type MediaAsset } from "@haios/project-model";
import { ADD_CLIP, createCommandBus } from "../src/index.js";

const baseAsset: MediaAsset = {
  id: "a", name: "base.mp4", sourcePath: "/media/base.mp4", kind: "video",
  durationSec: 40, width: 1920, height: 1080, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};
const editAsset: MediaAsset = {
  id: "b", name: "edit.mp4", sourcePath: "/media/edit.mp4", kind: "video",
  durationSec: 3, width: 1920, height: 1080, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};
function clip(id: string, start: number, duration: number, extra: Partial<Clip> = {}): Clip {
  return { id, assetId: "a", inPoint: 0, duration, start, trackId: "v", playbackRate: 1, transitionIn: null, ...extra };
}
function busWith(clips: Clip[]) {
  const project = createEmptyProject("Timeline edit", "timeline-edit-p");
  project.assets = [baseAsset, editAsset];
  project.tracks = [{ id: "v", kind: "video", clips: [] }];
  const bus = createCommandBus(project);
  for (const c of clips) bus.execute(ADD_CLIP, { clip: c });
  return bus;
}
describe("R2.14D insert / overwrite editing", () => {
  it("inserts at playhead, splits a covering clip, and shifts downstream as one undo unit", () => {
    const bus = busWith([clip("c0", 0, 6), clip("c1", 8, 4)]);
    const before = structuredClone(bus.project.tracks[0].clips);
    bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 4 });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start, c.duration, c.inPoint])).toEqual([
      ["c0", 0, 4, 0], ["ins", 4, 3, 0], ["c0__insert_r_ins", 7, 2, 4], ["c1", 11, 4, 0],
    ]);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0].clips).toEqual(before);
    expect(bus.redo()).toBe(true);
    expect(bus.project.tracks[0].clips.find((c) => c.id === "ins")?.start).toBe(4);
  });

  it("inserts into an empty media-kind track without mutating the asset", () => {
    const bus = busWith([]);
    bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 2 });
    const placed = bus.project.tracks[0].clips[0];
    expect([placed.id, placed.assetId, placed.start, placed.duration]).toEqual(["ins", "b", 2, 3]);
    expect(bus.project.assets.find((a) => a.id === "b")).toEqual(editAsset);
  });
  it("overwrites a range by trimming, removing, and splitting clips without shifting later material", () => {
    const bus = busWith([clip("c0", 0, 5), clip("c1", 5, 2), clip("c2", 7, 6), clip("c3", 15, 2)]);
    const before = structuredClone(bus.project.tracks[0].clips);
    bus.execute("timeline.overwriteAsset", { assetId: "b", clipId: "ovr", atSec: 4 });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start, c.duration, c.inPoint])).toEqual([
      ["c0", 0, 4, 0], ["ovr", 4, 3, 0], ["c2", 7, 6, 0], ["c3", 15, 2, 0],
    ]);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0].clips).toEqual(before);
  });

  it("splits one clip that spans the entire overwrite window and keeps rate-aware source offsets", () => {
    const bus = busWith([clip("c0", 0, 10, { playbackRate: 2 })]);
    bus.execute("timeline.overwriteAsset", { assetId: "b", clipId: "ovr", atSec: 3 });
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start, c.duration, c.inPoint])).toEqual([
      ["c0", 0, 3, 0], ["ovr", 3, 3, 0], ["c0__overwrite_r_ovr", 6, 4, 12],
    ]);
  });

  it("creates the target media-kind track deterministically when none exists", () => {
    const project = createEmptyProject("No track", "no-track");
    project.assets = [editAsset];
    const bus = createCommandBus(project);
    bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 2 });
    expect(bus.project.tracks.map((t) => [t.id, t.kind])).toEqual([["timeline-video", "video"]]);
    expect(bus.project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([["ins", 2]]);
  });

  it("fails closed when a derived split clip id would collide", () => {
    const bus = busWith([clip("c0", 0, 6), clip("c0__insert_r_ins", 20, 2)]);
    const before = structuredClone(bus.project);
    expect(() => bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 4 })).toThrow(/TIMELINE_CLIP_ID_DUPLICATE/);
    expect(bus.project).toEqual(before);
  });

  it("fails closed when insert or overwrite would reinterpret a transition boundary", () => {
    const transitioned = clip("c1", 4, 4, { transitionIn: { type: "crossfade", duration: 0.5 } });
    expect(() => busWith([clip("c0", 0, 4), transitioned]).execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 4 })).toThrow(/TIMELINE_TRANSITION_CONFLICT/);
    expect(() => busWith([clip("c0", 0, 4), transitioned]).execute("timeline.overwriteAsset", { assetId: "b", clipId: "ovr", atSec: 3 })).toThrow(/TIMELINE_TRANSITION_CONFLICT/);
  });
});
