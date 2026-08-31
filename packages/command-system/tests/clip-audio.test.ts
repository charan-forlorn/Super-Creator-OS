import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, ADD_ASSET, ADD_TRACK, ADD_CLIP, SET_CLIP_AUDIO } from "../src/index.js";

function makeBus() {
  const bus = createCommandBus(createEmptyProject("x", "p1"));
  bus.execute(ADD_ASSET, { asset: { id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 5, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" } });
  bus.execute(ADD_TRACK, { track: { id: "v", kind: "video", clips: [], captions: [] } });
  bus.execute(ADD_CLIP, { clip: { id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "v", transform: {} } });
  return bus;
}

describe("clip.audio", () => {
  it("updates gain/mute and supports undo/redo", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_AUDIO, { clipId: "c", gainDb: -12, muted: true });
    expect(bus.project.tracks[0].clips[0].audio).toEqual({ gainDb: -12, muted: true });
    bus.undo();
    expect(bus.project.tracks[0].clips[0].audio).toEqual({ gainDb: 0, muted: false });
    bus.redo();
    expect(bus.project.tracks[0].clips[0].audio).toEqual({ gainDb: -12, muted: true });
  });

  it("rejects gain outside the supported preview/export range", () => {
    const bus = makeBus();
    expect(() => bus.execute(SET_CLIP_AUDIO, { clipId: "c", gainDb: 1, muted: false })).toThrow();
    expect(bus.project.tracks[0].clips[0].audio).toEqual({ gainDb: 0, muted: false });
  });
});
