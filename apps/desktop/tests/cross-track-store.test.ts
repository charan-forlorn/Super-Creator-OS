import { beforeEach, describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { useStudio } from "../src/store.js";

describe("Phase 5 cross-track store transaction", () => {
  beforeEach(() => {
    const project = createEmptyProject("P5", "p5");
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "c", assetId: "a", inPoint: 0, duration: 2, start: 1, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [], captions: [] },
    ];
    useStudio.getState().loadProject(project);
    useStudio.getState().selectTrack("v1");
    useStudio.getState().selectClip("c");
    useStudio.getState().setPlayhead(3);
  });

  it("moves selection atomically and currentizes its destination only after success", () => {
    expect(useStudio.getState().moveSelected(4, "v2")).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v2")?.clips[0]).toMatchObject({ id: "c", trackId: "v2", start: 4 });
    expect(useStudio.getState().selectedTrackId).toBe("v2");
    expect(useStudio.getState().selectedClipIds).toEqual(["c"]);
    expect(useStudio.getState().playheadSec).toBe(3);
  });

  it("moves same-kind multi-selection as one atomic command and preserves state on rejected targets", () => {
    const state = useStudio.getState();
    const project = state.project;
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "a", assetId: "a", inPoint: 0, duration: 2, start: 1, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [{ id: "b", assetId: "a", inPoint: 0, duration: 2, start: 4, trackId: "v2" }], captions: [] },
      { id: "v3", kind: "video", clips: [], captions: [] },
      { id: "a1", kind: "audio", clips: [], captions: [] },
    ];
    state.loadProject(project);
    state.setClipSelection(["a", "b"]);
    state.selectTrack("v1");
    state.setPlayhead(7);
    expect(useStudio.getState().commitGroupMove(2, "a", "v2")).toBe(true);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v2")?.clips.find((c) => c.id === "a")?.start).toBe(3);
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v3")?.clips.find((c) => c.id === "b")?.start).toBe(6);
    expect(useStudio.getState().selectedClipId).toBe("b");
    expect(useStudio.getState().selectedTrackId).toBe("v3");
    useStudio.getState().undo();
    expect(useStudio.getState().project.tracks.find((t) => t.id === "v1")?.clips.find((c) => c.id === "a")?.start).toBe(1);
    useStudio.getState().redo();

    const before = structuredClone(useStudio.getState().project);
    const selection = [...useStudio.getState().selectedClipIds];
    expect(useStudio.getState().commitGroupMove(0, "a", "a1")).toBe(false);
    expect(useStudio.getState().project).toEqual(before);
    expect(useStudio.getState().selectedClipIds).toEqual(selection);
    expect(useStudio.getState().selectedTrackId).toBe("v3");
    expect(useStudio.getState().playheadSec).toBe(7);
    expect(useStudio.getState().lastError).toMatch(/CROSS_TRACK_TARGET_TRACK_KIND_MISMATCH/);
  });
});

describe("Phase 5 undo/redo runtime projection", () => {
  it("keeps selection/playhead and currentizes target track across undo and redo", () => {
    const project = createEmptyProject("P5", "p5-undo-projection");
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "c", assetId: "a", inPoint: 0, duration: 2, start: 1, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [], captions: [] },
    ];
    useStudio.getState().loadProject(project);
    useStudio.getState().selectTrack("v1");
    useStudio.getState().selectClip("c");
    useStudio.getState().setPlayhead(3);
    const s = useStudio.getState();
    expect(s.moveSelected(4, "v2")).toBe(true);
    expect(useStudio.getState().selectedTrackId).toBe("v2");
    useStudio.getState().undo();
    expect(useStudio.getState().selectedClipIds).toEqual(["c"]);
    expect(useStudio.getState().selectedClipId).toBe("c");
    expect(useStudio.getState().selectedTrackId).toBe("v1");
    expect(useStudio.getState().playheadSec).toBe(3);
    useStudio.getState().redo();
    expect(useStudio.getState().selectedClipIds).toEqual(["c"]);
    expect(useStudio.getState().selectedClipId).toBe("c");
    expect(useStudio.getState().selectedTrackId).toBe("v2");
    expect(useStudio.getState().playheadSec).toBe(3);
  });
});
