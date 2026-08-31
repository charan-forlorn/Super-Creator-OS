import { describe, beforeEach, it, expect } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1, id: "p", name: "speed", createdAt: "2026-08-31T00:00:00Z", updatedAt: "2026-08-31T00:00:00Z",
  assets: [{ id: "a", name: "a.mp4", sourcePath: "C:/a.mp4", kind: "video", durationSec: 8, hasAudio: true, createdAt: "2026-08-31T00:00:00Z" }],
  tracks: [{ id: "tv", kind: "video", captions: [], clips: [
    { id: "c", assetId: "a", inPoint: 0, duration: 4, start: 1, trackId: "tv", transform: {}, audio: {}, effects: {}, transitionIn: null },
  ] }], durationSec: 5, aspectRatio: "1920x1080",
} as const;

describe("R2.11 speed workspace store", () => {
  beforeEach(() => { useStudio.getState().loadProject(project); useStudio.getState().selectClip("c"); });
  it("changes selected speed through CommandBus and undo restores duration/rate", () => {
    expect(useStudio.getState().setSelectedSpeed(2)).toBe(true);
    let clip = useStudio.getState().project.tracks[0].clips[0];
    expect(clip.playbackRate).toBe(2);
    expect(clip.duration).toBe(2);
    useStudio.getState().undo();
    clip = useStudio.getState().project.tracks[0].clips[0];
    expect(clip.playbackRate).toBe(1);
    expect(clip.duration).toBe(4);
  });
});
