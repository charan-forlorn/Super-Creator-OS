import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "transport-nav",
  name: "Transport navigation",
  createdAt: "2026-09-01T00:00:00.000Z",
  updatedAt: "2026-09-01T00:00:00.000Z",
  assets: [
    { id: "a", name: "base.mp4", sourcePath: "C:/media/base.mp4", kind: "video" as const, durationSec: 12, width: 1920, height: 1080, fps: 25, hasAudio: true, createdAt: "2026-09-01T00:00:00.000Z" },
  ],
  tracks: [{ id: "v", kind: "video" as const, captions: [], clips: [
    { id: "c0", assetId: "a", inPoint: 0, duration: 12, start: 0, trackId: "v", playbackRate: 1 },
  ] }],
  durationSec: 12,
  aspectRatio: "1920x1080" as const,
};

describe("R2.14F precision transport/navigation runtime state", () => {
  beforeEach(() => {
    useStudio.getState().newProject();
    useStudio.getState().loadProject(project);
  });
  it("steps by active media frame rate and coarse seconds without dirtying project", () => {
    const beforeProject = JSON.stringify(useStudio.getState().project);
    useStudio.getState().setPlayhead(5);
    useStudio.getState().stepPlayhead(1, false);
    expect(useStudio.getState().playheadSec).toBeCloseTo(5.04);
    useStudio.getState().stepPlayhead(-1, false);
    expect(useStudio.getState().playheadSec).toBeCloseTo(5);
    useStudio.getState().stepPlayhead(1, true);
    expect(useStudio.getState().playheadSec).toBeCloseTo(6);
    expect(useStudio.getState().dirty).toBe(false);
    expect(JSON.stringify(useStudio.getState().project)).toBe(beforeProject);
  });

  it("clamps navigation to timeline start/end", () => {
    useStudio.getState().setPlayhead(0.01);
    useStudio.getState().stepPlayhead(-1, true);
    expect(useStudio.getState().playheadSec).toBe(0);
    useStudio.getState().jumpPlayhead("end");
    expect(useStudio.getState().playheadSec).toBe(12);
    useStudio.getState().stepPlayhead(1, true);
    expect(useStudio.getState().playheadSec).toBe(12);
    useStudio.getState().jumpPlayhead("start");
    expect(useStudio.getState().playheadSec).toBe(0);
  });
  it("controls runtime transport rate without creating project history", () => {
    const beforeProject = JSON.stringify(useStudio.getState().project);
    expect(useStudio.getState().transportRate).toBe(0);
    useStudio.getState().setTransportRate(1);
    expect(useStudio.getState().transportRate).toBe(1);
    useStudio.getState().setTransportRate(-1);
    expect(useStudio.getState().transportRate).toBe(-1);
    useStudio.getState().toggleTransport();
    expect(useStudio.getState().transportRate).toBe(0);
    useStudio.getState().toggleTransport();
    expect(useStudio.getState().transportRate).toBe(1);
    expect(useStudio.getState().dirty).toBe(false);
    expect(JSON.stringify(useStudio.getState().project)).toBe(beforeProject);
  });

  it("fits the whole timeline into the visible lane and resets scroll", () => {
    useStudio.setState({ zoom: 3, scrollSec: 4 });
    useStudio.getState().fitTimelineZoom(1024);
    const state = useStudio.getState();
    expect(state.zoom).toBeCloseTo((1024 - 64) / (17 * 80));
    expect(state.scrollSec).toBe(0);
    expect(state.dirty).toBe(false);
  });
});

// Runtime navigation must not erase diagnostics owned by another subsystem.
describe("R2.14F transport diagnostic isolation", () => {
  it("preserves unrelated lastError across transport and successful zoom-fit actions", () => {
    useStudio.getState().newProject();
    useStudio.getState().loadProject(project);
    useStudio.setState({ lastError: "KEEP_EXISTING_DIAGNOSTIC" });
    useStudio.getState().setTransportRate(1);
    expect(useStudio.getState().lastError).toBe("KEEP_EXISTING_DIAGNOSTIC");
    useStudio.getState().fitTimelineZoom(1024);
    expect(useStudio.getState().lastError).toBe("KEEP_EXISTING_DIAGNOSTIC");
  });
});
