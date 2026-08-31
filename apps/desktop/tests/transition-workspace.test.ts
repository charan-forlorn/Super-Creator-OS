import { describe, beforeEach, it, expect } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1, id: "p", name: "transition", createdAt: "2026-08-31T00:00:00Z", updatedAt: "2026-08-31T00:00:00Z",
  assets: [{ id: "a", name: "a.mp4", sourcePath: "C:/a.mp4", kind: "video", durationSec: 8, hasAudio: true, createdAt: "2026-08-31T00:00:00Z" }],
  tracks: [{ id: "tv", kind: "video", captions: [], clips: [
    { id: "c0", assetId: "a", inPoint: 0, duration: 2, start: 0, trackId: "tv", transform: {}, audio: {}, effects: {} },
    { id: "c1", assetId: "a", inPoint: 2, duration: 2, start: 2, trackId: "tv", transform: {}, audio: {}, effects: {} },
  ] }], durationSec: 4, aspectRatio: "1920x1080",
} as const;

describe("R2.10 transition workspace store", () => {
  beforeEach(() => { useStudio.getState().loadProject(project); useStudio.getState().selectClip("c1"); });
  it("applies crossfade through CommandBus and undo restores exact adjacency", () => {
    expect(useStudio.getState().setSelectedTransition("crossfade", 0.5)).toBe(true);
    expect(useStudio.getState().project.tracks[0].clips[1].start).toBe(1.5);
    expect(useStudio.getState().project.tracks[0].clips[1].transitionIn).toEqual({ type: "crossfade", duration: 0.5 });
    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks[0].clips[1].start).toBe(2);
    expect(useStudio.getState().project.tracks[0].clips[1].transitionIn).toBeNull();
  });
});
