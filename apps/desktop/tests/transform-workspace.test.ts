import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1, id: "p", name: "transform", createdAt: "2026-08-31T00:00:00Z", updatedAt: "2026-08-31T00:00:00Z",
  assets: [{ id: "a", name: "a.mp4", sourcePath: "C:/a.mp4", kind: "video", durationSec: 5, hasAudio: false, createdAt: "2026-08-31T00:00:00Z" }],
  tracks: [{ id: "tv", kind: "video", captions: [], clips: [{ id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "tv", transform: { scale: 1, x: 0, y: 0, opacity: 1 }, audio: { gainDb: 0, muted: false } }] }],
  durationSec: 5, aspectRatio: "1920x1080",
} as const;

describe("R2.6 transform workspace store", () => {
  beforeEach(() => { useStudio.getState().loadProject(project); useStudio.getState().selectClip("c"); });
  it("updates selected transform through CommandBus and undo restores defaults", () => {
    expect(useStudio.getState().setSelectedTransform(1.25, 0.2, -0.3, 0.7)).toBe(true);
    expect(useStudio.getState().project.tracks[0].clips[0].transform).toEqual({ scale: 1.25, x: 0.2, y: -0.3, opacity: 0.7 });    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks[0].clips[0].transform).toEqual({ scale: 1, x: 0, y: 0, opacity: 1 });
  });
});