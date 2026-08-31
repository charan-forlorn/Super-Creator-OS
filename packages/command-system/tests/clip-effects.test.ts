import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, ADD_ASSET, ADD_TRACK, ADD_CLIP, SET_CLIP_EFFECTS } from "../src/index.js";

function makeBus() {
  const bus = createCommandBus(createEmptyProject("x", "p1"));
  bus.execute(ADD_ASSET, { asset: { id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 5, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" } });
  bus.execute(ADD_TRACK, { track: { id: "v", kind: "video", clips: [], captions: [] } });
  bus.execute(ADD_CLIP, { clip: { id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "v", transform: {}, audio: {} } });
  return bus;
}

describe("clip.effects", () => {
  it("updates visual effects and supports undo/redo", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_EFFECTS, { clipId: "c", brightness: 0.25, contrast: 1.4, saturation: 0.5 });
    expect(bus.project.tracks[0].clips[0].effects).toEqual({ brightness: 0.25, contrast: 1.4, saturation: 0.5 });
    bus.undo();
    expect(bus.project.tracks[0].clips[0].effects).toEqual({ brightness: 0, contrast: 1, saturation: 1 });
    bus.redo();
    expect(bus.project.tracks[0].clips[0].effects).toEqual({ brightness: 0.25, contrast: 1.4, saturation: 0.5 });
  });

  it("rejects values outside the shared preview/export contract", () => {
    const bus = makeBus();
    expect(() => bus.execute(SET_CLIP_EFFECTS, { clipId: "c", brightness: 1.1, contrast: 1, saturation: 1 })).toThrow();
    expect(() => bus.execute(SET_CLIP_EFFECTS, { clipId: "c", brightness: 0, contrast: 2.1, saturation: 1 })).toThrow();
    expect(() => bus.execute(SET_CLIP_EFFECTS, { clipId: "c", brightness: 0, contrast: 1, saturation: 3.1 })).toThrow();
  });
});
