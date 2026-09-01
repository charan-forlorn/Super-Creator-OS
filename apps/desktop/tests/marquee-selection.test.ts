import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "marquee-ui",
  name: "Marquee UI",
  createdAt: "2026-09-01T00:00:00.000Z",
  updatedAt: "2026-09-01T00:00:00.000Z",
  assets: [],
  tracks: [{
    id: "v",
    kind: "video" as const,
    captions: [],
    clips: [
      { id: "c0", assetId: "a", inPoint: 0, duration: 4, start: 0, trackId: "v" },
      { id: "c1", assetId: "a", inPoint: 0, duration: 4, start: 5, trackId: "v" },
      { id: "c2", assetId: "a", inPoint: 0, duration: 4, start: 10, trackId: "v" },
    ],
  }],
  durationSec: 14,
  aspectRatio: "1920x1080" as const,
};
describe("R2.14C marquee selection state", () => {
  beforeEach(() => useStudio.getState().newProject());

  it("replaces selection atomically and ignores unknown clip ids", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectClip("c2");
    useStudio.getState().setClipSelection(["c1", "missing", "c0"]);
    const state = useStudio.getState();
    expect(state.selectedClipIds).toEqual(["c1", "c0"]);
    expect(state.selectedClipId).toBe("c0");
    expect(state.dirty).toBe(false);
  });

  it("extends an existing selection without duplicates", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().setClipSelection(["c2"]);
    useStudio.getState().setClipSelection(["c2", "c0", "c2"], true);
    const state = useStudio.getState();
    expect(state.selectedClipIds).toEqual(["c2", "c0"]);
    expect(state.selectedClipId).toBe("c0");
    expect(state.dirty).toBe(false);
  });
});
