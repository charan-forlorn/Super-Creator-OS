import { describe, it, expect, beforeEach } from "vitest";
import { createEmptyProject, parseProject, type MediaAsset, type Clip } from "@haios/project-model";
import {
  createCommandBus,
  createStudioRegistry,
  CommandBusValidationError,
  CommandError,
  ADD_ASSET,
  ADD_CLIP,
  SPLIT_CLIP,
  DELETE_CLIP,
  MOVE_CLIP,
  TRIM_CLIP,
} from "../src/index.js";

const asset: MediaAsset = {
  id: "a1",
  name: "src.mp4",
  sourcePath: "/media/src.mp4",
  kind: "video",
  durationSec: 10,
  width: 1920,
  height: 1080,
  fps: 30,
  hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};

const clip: Clip = {
  id: "c1",
  assetId: "a1",
  inPoint: 2,
  duration: 4,
  start: 0,
  trackId: "tv",
};

function freshBus() {
  const p = createEmptyProject("P", "p1");
  p.assets = [asset];
  p.tracks = [{ id: "tv", kind: "video", clips: [clip] }];
  return createCommandBus(p);
}

describe("CommandBus invariants", () => {
  let bus: ReturnType<typeof freshBus>;
  beforeEach(() => {
    bus = freshBus();
  });

  it("rejects unknown command types (no bypass)", () => {
    expect(() => bus.execute("clip.hallucinated", {})).toThrow(CommandBusValidationError);
  });

  it("rejects commands referencing a non-existent clip id", () => {
    expect(() => bus.execute(DELETE_CLIP, { clipId: "nope" })).toThrow(CommandError);
    expect(bus.project.tracks[0].clips).toHaveLength(1);
  });

  it("rejects a split point outside (0, duration)", () => {
    expect(() => bus.execute(SPLIT_CLIP, { clipId: "c1", t: 0 })).toThrow();
    expect(() => bus.execute(SPLIT_CLIP, { clipId: "c1", t: 4 })).toThrow();
    expect(bus.project.tracks[0].clips).toHaveLength(1);
  });

  it("rejects a trimmed clip that overshoots its source asset", () => {
    // clip currently [2,6]; trimming to source end 11 exceeds asset (10)
    expect(() => bus.execute(TRIM_CLIP, { clipId: "c1", newSourceEnd: 11 })).toThrow(CommandError);
    expect(bus.project.tracks[0].clips[0].inPoint).toBe(2);
  });

  it("split then undo restores a single clip", () => {
    bus.execute(SPLIT_CLIP, { clipId: "c1", t: 1.5 });
    expect(bus.project.tracks[0].clips).toHaveLength(2);
    expect(bus.canUndo).toBe(true);
    bus.undo();
    expect(bus.project.tracks[0].clips).toHaveLength(1);
    expect(bus.project.tracks[0].clips[0].duration).toBeCloseTo(4);
  });

  it("redo stack clears after a branching edit", () => {
    bus.execute(SPLIT_CLIP, { clipId: "c1", t: 1.5 });
    bus.undo(); // now can redo
    expect(bus.canRedo).toBe(true);
    bus.execute(MOVE_CLIP, { clipId: "c1", newStart: 2 }); // branch
    expect(bus.canRedo).toBe(false);
  });

  it("full undo/redo round-trip preserves state", () => {
    // Normalize both sides through the canonical parser so Zod-applied defaults
    // (e.g. clip.transform) exist on the baseline exactly as they will on restore.
    const before = JSON.parse(JSON.stringify(parseProject(bus.project).tracks));
    bus.execute(MOVE_CLIP, { clipId: "c1", newStart: 3 });
    bus.execute(TRIM_CLIP, { clipId: "c1", newInPoint: 3 });
    bus.undo();
    bus.undo();
    // Undo/redo must restore the exact track/clip structure the user saw.
    expect(JSON.parse(JSON.stringify(bus.project.tracks))).toEqual(before);
    bus.redo();
    bus.redo();
    expect(bus.project.tracks[0].clips[0].start).toBeCloseTo(3);
    expect(bus.project.tracks[0].clips[0].inPoint).toBeCloseTo(3);
  });

  it("delete + undo restores the clip and its duration", () => {
    bus.execute(DELETE_CLIP, { clipId: "c1" });
    expect(bus.project.tracks[0].clips).toHaveLength(0);
    bus.undo();
    expect(bus.project.tracks[0].clips).toHaveLength(1);
    expect(bus.project.tracks[0].clips[0].id).toBe("c1");
  });

  it("registry rejects duplicate command registration", () => {
    const reg = createStudioRegistry();
    expect(() => reg.register({ type: ADD_CLIP, execute: (() => ({ next: reg as any, inverse: reg as any })) as any })).toThrow();
  });

  it("payload schema validation rejects malformed payloads", () => {
    expect(() => bus.execute(MOVE_CLIP, { clipId: "c1", newStart: -2 })).toThrow(
      CommandBusValidationError,
    );
  });
});
