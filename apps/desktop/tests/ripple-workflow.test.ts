import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "ripple-ui",
  name: "Ripple UI",
  createdAt: "2026-09-01T00:00:00.000Z",
  updatedAt: "2026-09-01T00:00:00.000Z",
  assets: [{
    id: "a", name: "src.mp4", sourcePath: "C:/media/src.mp4", kind: "video" as const,
    durationSec: 20, width: 1920, height: 1080, fps: 30, hasAudio: true,
    createdAt: "2026-09-01T00:00:00.000Z",
  }],
  tracks: [{
    id: "v", kind: "video" as const, captions: [],
    clips: [
      { id: "c0", assetId: "a", inPoint: 0, duration: 4, start: 0, trackId: "v", playbackRate: 1 },
      { id: "c1", assetId: "a", inPoint: 4, duration: 4, start: 5, trackId: "v", playbackRate: 1 },
    ],
  }],
  durationSec: 9,
  aspectRatio: "1920x1080" as const,
};

describe("R2.14 ripple workflow store integration", () => {
  beforeEach(() => useStudio.getState().newProject());
  it("routes ripple delete through the canonical command bus", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectClip("c0");
    useStudio.getState().rippleDeleteSelected();
    const state = useStudio.getState();
    expect(state.project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([["c1", 1]]);
    expect(state.selectedClipIds).toEqual([]);
    expect(state.dirty).toBe(true);
    state.undo();
    expect(useStudio.getState().project.tracks[0].clips.map((c) => [c.id, c.start])).toEqual([["c0", 0], ["c1", 5]]);
  });

  it("routes ripple trim through one undoable command", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectClip("c0");
    useStudio.getState().rippleTrimSelected(undefined, 3);
    let clips = useStudio.getState().project.tracks[0].clips;
    expect(clips.map((c) => [c.id, c.start, c.duration])).toEqual([["c0", 0, 3], ["c1", 4, 4]]);
    useStudio.getState().undo();
    clips = useStudio.getState().project.tracks[0].clips;
    expect(clips.map((c) => [c.id, c.start, c.duration])).toEqual([["c0", 0, 4], ["c1", 5, 4]]);
  });
});