import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "p-relink",
  name: "Relink",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
  assets: [{ id: "a1", name: "old.mp4", sourcePath: "C:/old.mp4", kind: "video", durationSec: 10, width: 640, height: 360, fps: 30, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" }],
  tracks: [{ id: "v1", kind: "video", clips: [{ id: "c1", assetId: "a1", inPoint: 0, duration: 5, start: 0, trackId: "v1", transform: { scale: 1, x: 0, y: 0, opacity: 1 } }], captions: [] }],
  durationSec: 5,
  aspectRatio: "1920x1080",
};

const replacement = {
  id: "probe-new", name: "new.mp4", sourcePath: "D:/new.mp4", kind: "video", durationSec: 12,
  width: 1920, height: 1080, fps: 60, hasAudio: true, videoCodec: "h264", audioCodec: "aac",
  audioSampleRate: 48000, probeStatus: "ok", error: null,
};

function seedDerivedState() {
  useStudio.getState().setThumbnail("a1", "D:/new-thumb.png");
  useStudio.getState().setPreviewProxy("a1", "D:/new-proxy.mp4");
  useStudio.getState().setMediaAnalysis("a1", {
    sourcePath: "D:/new.mp4", status: "ready", probe: replacement, waveformPath: "D:/new-wave.png",
  });
}

describe("R2.3 store relink derived-state reconciliation", () => {
  beforeEach(() => useStudio.getState().loadProject(project));

  it("clears derived analysis on undo after relink", () => {
    expect(useStudio.getState().relinkMedia("a1", replacement)).toBe(true);
    seedDerivedState();
    useStudio.getState().undo();

    const state = useStudio.getState();
    expect(state.project.assets[0].sourcePath).toBe("C:/old.mp4");
    expect(state.mediaAnalysis).toEqual({});
    expect(state.thumbnails).toEqual({});
    expect(state.previewProxies).toEqual({});
  });

  it("reapplies replacement on redo without reviving stale derived artifacts", () => {
    expect(useStudio.getState().relinkMedia("a1", replacement)).toBe(true);
    seedDerivedState();
    useStudio.getState().undo();
    useStudio.getState().redo();

    const state = useStudio.getState();
    expect(state.project.assets[0].sourcePath).toBe("D:/new.mp4");
    expect(state.mediaAnalysis).toEqual({});
    expect(state.thumbnails).toEqual({});
    expect(state.previewProxies).toEqual({});
  });
});
