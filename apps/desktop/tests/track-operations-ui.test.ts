import { beforeEach, describe, expect, it } from "vitest";
import { createEmptyProject, type MediaAsset, type Track } from "@haios/project-model";
import { useStudio } from "../src/store.js";

const asset: MediaAsset = {
  id: "asset-v", name: "v.mp4", sourcePath: "C:/v.mp4", kind: "video",
  durationSec: 10, width: 320, height: 180, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00.000Z",
};
function track(id: string, kind: Track["kind"] = "video"): Track {
  return { id, kind, clips: [], captions: [], visible: true, muted: false, locked: false };
}
function projectWithTracks() {
  const p = createEmptyProject("P4.5", "p45");
  p.assets = [asset];
  p.tracks = [track("v1"), track("v2"), track("t1", "text")];
  return p;
}

beforeEach(() => useStudio.getState().loadProject(projectWithTracks()));

describe("P4.5 track operations store wiring", () => {
  it("exposes runtime target-track selection and validates ids", () => {
    const s = useStudio.getState() as any;
    expect(typeof s.selectTrack).toBe("function");
    s.selectTrack("v2");
    expect(useStudio.getState().selectedTrackId).toBe("v2");
    s.selectTrack("missing");
    expect(useStudio.getState().selectedTrackId).toBe("v2");
    expect(useStudio.getState().lastError).toMatch(/TRACK_NOT_FOUND/);
  });
  it("adds, reorders, controls, and removes tracks through CommandBus wrappers", () => {
    const s = useStudio.getState() as any;
    const id = s.addTrack("audio");
    expect(id).toMatch(/^track-audio-/);
    expect(useStudio.getState().project.tracks.at(-1)?.id).toBe(id);
    s.selectTrack(id);
    expect(s.moveSelectedTrack(-1)).toBe(true);
    expect(useStudio.getState().project.tracks.at(-2)?.id).toBe(id);
    expect(s.setSelectedTrackControls({ visible: false, muted: true, locked: true })).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === id)).toMatchObject({ visible: false, muted: true, locked: true });
    expect(s.setSelectedTrackControls({ locked: false })).toBe(true);
    expect(s.removeSelectedTrack()).toBe(true);
    expect(useStudio.getState().project.tracks.some((t) => t.id === id)).toBe(false);
    expect(useStudio.getState().selectedTrackId).toBeNull();
  });

  it("routes insert and overwrite to the selected compatible track", () => {
    const s = useStudio.getState() as any;
    s.selectAsset("asset-v");
    s.selectTrack("v2");
    expect(s.insertSelectedAssetAtPlayhead()).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v1")?.clips).toHaveLength(0);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v2")?.clips).toHaveLength(1);
    useStudio.getState().undo();
    expect(s.overwriteSelectedAssetAtPlayhead()).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v2")?.clips).toHaveLength(1);
  });
  it("routes caption placement to selected text track and import placement to selected media track", () => {
    const s = useStudio.getState() as any;
    s.selectTrack("t1");
    expect(s.placeCaption("Targeted", 1, 2)).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "t1")?.captions).toHaveLength(1);

    s.selectTrack("v2");
    const clipId = s.importProbedMedia({
      id: "import-v", name: "import.mp4", sourcePath: "C:/import.mp4", kind: "video",
      durationSec: 2, width: 320, height: 180, fps: 30, hasAudio: true,
      videoCodec: "h264", audioCodec: "aac", probeStatus: "ok",
    });
    expect(clipId).toBe("import-v-clip");
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v1")?.clips).toHaveLength(0);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id)).toContain("import-v-clip");
  });
});
