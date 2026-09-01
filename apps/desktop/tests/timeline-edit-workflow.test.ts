import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "timeline-edit-ui",
  name: "Timeline edit UI",
  createdAt: "2026-09-01T00:00:00.000Z",
  updatedAt: "2026-09-01T00:00:00.000Z",
  assets: [
    { id: "a", name: "base.mp4", sourcePath: "C:/media/base.mp4", kind: "video" as const, durationSec: 20, width: 1920, height: 1080, fps: 30, hasAudio: true, createdAt: "2026-09-01T00:00:00.000Z" },
    { id: "b", name: "edit.mp4", sourcePath: "C:/media/edit.mp4", kind: "video" as const, durationSec: 3, width: 1920, height: 1080, fps: 30, hasAudio: true, createdAt: "2026-09-01T00:00:00.000Z" },
  ],
  tracks: [{ id: "v", kind: "video" as const, captions: [], clips: [
    { id: "c0", assetId: "a", inPoint: 0, duration: 6, start: 0, trackId: "v", playbackRate: 1 },
    { id: "c1", assetId: "a", inPoint: 6, duration: 4, start: 8, trackId: "v", playbackRate: 1 },
  ] }],
  durationSec: 12,
  aspectRatio: "1920x1080" as const,
};
describe("R2.14D timeline edit workflow store integration", () => {
  beforeEach(() => useStudio.getState().newProject());

  it("selects a media asset as runtime-only state", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectAsset("b");
    const state = useStudio.getState();
    expect(state.selectedAssetId).toBe("b");
    expect(state.dirty).toBe(false);
  });

  it("inserts the selected asset at playhead through one undoable command", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectAsset("b");
    useStudio.getState().setPlayhead(4);
    expect(useStudio.getState().insertSelectedAssetAtPlayhead()).toBe(true);
    let state = useStudio.getState();
    expect(state.project.tracks[0].clips.some((c) => c.assetId === "b" && c.start === 4)).toBe(true);
    expect(state.dirty).toBe(true);
    state.undo();
    state = useStudio.getState();
    expect(state.project.tracks[0].clips.some((c) => c.assetId === "b")).toBe(false);
  });
  it("overwrites at playhead and selects the newly placed clip", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().selectAsset("b");
    useStudio.getState().setPlayhead(4);
    expect(useStudio.getState().overwriteSelectedAssetAtPlayhead()).toBe(true);
    const state = useStudio.getState();
    const placed = state.project.tracks[0].clips.find((c) => c.assetId === "b");
    expect(placed?.start).toBe(4);
    expect(state.selectedClipId).toBe(placed?.id);
    expect(state.lastError).toBeNull();
  });

  it("fails closed when no media asset is selected", () => {
    useStudio.getState().loadProject(project);
    expect(useStudio.getState().insertSelectedAssetAtPlayhead()).toBe(false);
    expect(useStudio.getState().project.tracks[0].clips).toHaveLength(2);
    expect(useStudio.getState().lastError).toMatch(/SELECT_MEDIA_ASSET/);
  });
});
