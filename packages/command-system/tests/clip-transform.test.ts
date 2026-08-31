import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { CommandBus, createStudioRegistry, SET_CLIP_TRANSFORM } from "../src/index.js";

function makeBus() {
  const p = createEmptyProject("transform", "p-transform");
  p.tracks = [{ id: "tv", kind: "video", captions: [], clips: [{
    id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "tv",
    transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false },
  }] }];
  return new CommandBus(createStudioRegistry(), p);
}

describe("clip.transform", () => {
  it("updates the complete transform and supports undo/redo", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_TRANSFORM, { clipId: "c", scale: 1.5, x: 0.25, y: -0.5, opacity: 0.6 });
    expect(bus.project.tracks[0].clips[0].transform).toEqual({ scale: 1.5, x: 0.25, y: -0.5, opacity: 0.6 });    bus.undo();
    expect(bus.project.tracks[0].clips[0].transform).toEqual({ scale: 1, x: 0, y: 0, opacity: 1 });
    bus.redo();
    expect(bus.project.tracks[0].clips[0].transform).toEqual({ scale: 1.5, x: 0.25, y: -0.5, opacity: 0.6 });
  });

  it("fails closed outside supported bounds", () => {
    const bus = makeBus();
    expect(() => bus.execute(SET_CLIP_TRANSFORM, { clipId: "c", scale: 5, x: 0, y: 0, opacity: 1 })).toThrow();
    expect(() => bus.execute(SET_CLIP_TRANSFORM, { clipId: "c", scale: 1, x: 1.1, y: 0, opacity: 1 })).toThrow();
    expect(bus.project.tracks[0].clips[0].transform).toEqual({ scale: 1, x: 0, y: 0, opacity: 1 });
  });
});