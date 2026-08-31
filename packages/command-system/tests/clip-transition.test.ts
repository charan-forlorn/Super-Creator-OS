import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, ADD_ASSET, ADD_TRACK, ADD_CLIP, SET_CLIP_TRANSITION } from "../src/index.js";

function makeBus() {
  const bus = createCommandBus(createEmptyProject("x", "p1"));
  bus.execute(ADD_ASSET, { asset: { id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 8, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" } });
  bus.execute(ADD_TRACK, { track: { id: "v", kind: "video", clips: [], captions: [] } });
  bus.execute(ADD_CLIP, { clip: { id: "c0", assetId: "a", inPoint: 0, duration: 2, start: 0, trackId: "v", transform: {} } });
  bus.execute(ADD_CLIP, { clip: { id: "c1", assetId: "a", inPoint: 2, duration: 2, start: 2, trackId: "v", transform: {} } });
  return bus;
}

describe("clip.transition", () => {
  it("creates exact crossfade overlap and undo/redo restores both start and metadata", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_TRANSITION, { clipId: "c1", mode: "crossfade", duration: 0.5 });
    let c = bus.project.tracks[0].clips.find((x) => x.id === "c1")!;
    expect(c.start).toBe(1.5);
    expect(c.transitionIn).toEqual({ type: "crossfade", duration: 0.5 });
    bus.undo();
    c = bus.project.tracks[0].clips.find((x) => x.id === "c1")!;
    expect(c.start).toBe(2);
    expect(c.transitionIn).toBeNull();
    bus.redo();
    c = bus.project.tracks[0].clips.find((x) => x.id === "c1")!;
    expect(c.start).toBe(1.5);
  });

  it("rejects a first-clip crossfade and an excessive duration", () => {
    const bus = makeBus();
    expect(() => bus.execute(SET_CLIP_TRANSITION, { clipId: "c0", mode: "crossfade", duration: 0.5 })).toThrow();
    expect(() => bus.execute(SET_CLIP_TRANSITION, { clipId: "c1", mode: "crossfade", duration: 3 })).toThrow();
  });

  it("removes a crossfade by restoring hard-cut adjacency", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_TRANSITION, { clipId: "c1", mode: "crossfade", duration: 0.5 });
    bus.execute(SET_CLIP_TRANSITION, { clipId: "c1", mode: "none" });
    const c = bus.project.tracks[0].clips.find((x) => x.id === "c1")!;
    expect(c.start).toBe(2);
    expect(c.transitionIn).toBeNull();
  });
});
