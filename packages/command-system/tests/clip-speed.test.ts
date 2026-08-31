import { createEmptyProject } from "@haios/project-model";
import { createCommandBus, ADD_ASSET, ADD_TRACK, ADD_CLIP, SET_CLIP_SPEED } from "../src/index.js";

function makeBus() {
  const bus = createCommandBus(createEmptyProject("speed", "p1"));
  bus.execute(ADD_ASSET, { asset: { id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 10, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" } });
  bus.execute(ADD_TRACK, { track: { id: "v", kind: "video", clips: [], captions: [] } });
  bus.execute(ADD_CLIP, { clip: { id: "c0", assetId: "a", inPoint: 2, duration: 4, start: 1, trackId: "v", transform: {} } });
  return bus;
}

describe("clip.speed", () => {
  it("changes timeline duration while preserving the exact consumed source range and undo/redo", () => {
    const bus = makeBus();
    bus.execute(SET_CLIP_SPEED, { clipId: "c0", playbackRate: 2 });
    let clip = bus.project.tracks[0].clips[0];
    expect(clip.playbackRate).toBe(2);
    expect(clip.duration).toBe(2);
    expect(bus.project.durationSec).toBe(3);
    bus.undo();
    clip = bus.project.tracks[0].clips[0];
    expect(clip.playbackRate).toBe(1);
    expect(clip.duration).toBe(4);
    bus.redo();
    expect(bus.project.tracks[0].clips[0].duration).toBe(2);
  });

  it("reflows a following crossfade when the outgoing clip speed changes", () => {
    const bus = makeBus();
    bus.execute(ADD_CLIP, { clip: { id: "c1", assetId: "a", inPoint: 6, duration: 2, start: 4.5, trackId: "v", playbackRate: 1, transform: {}, transitionIn: { type: "crossfade", duration: 0.5 } } });
    bus.execute(SET_CLIP_SPEED, { clipId: "c0", playbackRate: 2 });
    expect(bus.project.tracks[0].clips.find((c) => c.id === "c1")!.start).toBe(2.5);
    bus.undo();
    expect(bus.project.tracks[0].clips.find((c) => c.id === "c1")!.start).toBe(4.5);
  });

  it("rejects out-of-range speed without mutating the project", () => {
    expect(SET_CLIP_SPEED).toBe("clip.speed");
    const bus = makeBus();
    const before = JSON.stringify(bus.project);
    expect(() => bus.execute(SET_CLIP_SPEED, { clipId: "c0", playbackRate: 0.1 })).toThrow();
    expect(() => bus.execute(SET_CLIP_SPEED, { clipId: "c0", playbackRate: 5 })).toThrow();
    expect(JSON.stringify(bus.project)).toBe(before);
  });
});
