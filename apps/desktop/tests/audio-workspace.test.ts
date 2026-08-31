import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1, id: "p", name: "audio",
  createdAt: "2026-01-01T00:00:00.000Z", updatedAt: "2026-01-01T00:00:00.000Z",
  assets: [{ id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 5, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" }],
  tracks: [{ id: "v", kind: "video", captions: [], clips: [{ id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "v", transform: {} }] }],
  durationSec: 5, aspectRatio: "1920x1080",
};

describe("R2.5 audio workspace store", () => {
  beforeEach(() => { useStudio.getState().loadProject(project); useStudio.getState().selectClip("c"); });
  it("updates selected clip audio through CommandBus and undo restores defaults", () => {
    expect(useStudio.getState().setSelectedAudio(-18, true)).toBe(true);
    expect(useStudio.getState().project.tracks[0].clips[0].audio).toEqual({ gainDb: -18, muted: true });
    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks[0].clips[0].audio).toEqual({ gainDb: 0, muted: false });
  });
});
