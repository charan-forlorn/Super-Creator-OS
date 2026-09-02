import { describe, expect, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { buildCrossTrackMovePlan, resolveTrackAtClientY } from "../src/crossTrackMove.js";

describe("Phase 5 cross-track move planning", () => {
  it("resolves real track rectangles and maps same-kind lanes while clamping the whole group", () => {
    expect(resolveTrackAtClientY([{ trackId: "v1", top: 10, bottom: 40 }, { trackId: "v2", top: 40, bottom: 70 }], 40)).toBe("v2");
    const project = createEmptyProject("P5", "p5");
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "a", assetId: "x", inPoint: 0, duration: 2, start: 1, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [{ id: "b", assetId: "x", inPoint: 0, duration: 2, start: 5, trackId: "v2" }], captions: [] },
      { id: "v3", kind: "video", clips: [], captions: [] },
    ];
    expect(buildCrossTrackMovePlan(project, ["a", "b"], "a", -10, "v2").moves).toEqual([
      { clipId: "a", sourceTrackId: "v1", targetTrackId: "v2", newStart: 0 },
      { clipId: "b", sourceTrackId: "v2", targetTrackId: "v3", newStart: 4 },
    ]);
  });

  it("rejects ambiguous referenced track ids before producing a pointer plan", () => {
    const project = createEmptyProject("P5", "p5-ambiguous-track");
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "v", assetId: "x", inPoint: 0, duration: 2, start: 0, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [], captions: [] },
      { id: "v2", kind: "video", clips: [], captions: [], locked: true },
    ];
    expect(() => buildCrossTrackMovePlan(project, ["v"], "v", 0, "v2"))
      .toThrow(/CROSS_TRACK_TRACK_ID_AMBIGUOUS: v2/);
  });

  it("fails closed for mixed-kind and out-of-range vertical mappings without producing partial plans", () => {
    const project = createEmptyProject("P5", "p5-invalid");
    project.tracks = [
      { id: "v1", kind: "video", clips: [{ id: "v", assetId: "x", inPoint: 0, duration: 2, start: 0, trackId: "v1" }], captions: [] },
      { id: "v2", kind: "video", clips: [], captions: [] },
      { id: "a1", kind: "audio", clips: [{ id: "a", assetId: "x", inPoint: 0, duration: 2, start: 0, trackId: "a1" }], captions: [] },
    ];
    expect(() => buildCrossTrackMovePlan(project, ["v", "a"], "v", 0, "v2")).toThrow(/CROSS_TRACK_SELECTION_KIND_MISMATCH/);
    expect(() => buildCrossTrackMovePlan(project, ["v"], "v", 0, "v2")).not.toThrow();
    expect(() => buildCrossTrackMovePlan(project, ["v"], "v", 0, "missing")).toThrow(/CROSS_TRACK_TARGET_TRACK_NOT_FOUND/);
  });
});
