import { describe, it, expect, beforeEach } from "vitest";
import { createEmptyProject, parseProject, type MediaAsset, type Clip } from "@haios/project-model";
import {
  createCommandBus,
  CommandBusValidationError,
  ADD_CLIP,
  MOVE_CLIP,
  DELETE_CLIP,
  SPLIT_CLIP,
} from "../src/index.js";

const asset: MediaAsset = {
  id: "a1",
  name: "src.mp4",
  sourcePath: "/media/src.mp4",
  kind: "video",
  durationSec: 20,
  width: 1920,
  height: 1080,
  fps: 30,
  hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};

function freshBus() {
  const p = createEmptyProject("P", "p1");
  p.assets = [asset];
  p.tracks = [{ id: "tv", kind: "video", clips: [] }];
  const bus = createCommandBus(p);
  // place three clips on the same video track
  for (let i = 0; i < 3; i++) {
    const id = `c${i}`;
    const clip: Clip = { id, assetId: "a1", inPoint: 0, duration: 4, start: i * 4, trackId: "tv" };
    bus.execute(ADD_CLIP, { clip });
  }
  // baseline: 3 ADD_CLIP entries recorded.
  return bus;
}

describe("CommandBus.batch — atomic group undo/redo", () => {
  let bus: ReturnType<typeof freshBus>;
  beforeEach(() => {
    bus = freshBus();
  });

  it("executes every sub-command and adds EXACTLY ONE undo entry", () => {
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    // Undo all 3 adds to measure pre-batch depth on a sibling state.
    const probe = freshBus();
    let depthBefore = 0;
    while (probe.canUndo) {
      probe.undo();
      depthBefore++;
    }
    expect(depthBefore).toBe(3);

    bus.batch([
      { commandType: MOVE_CLIP, payload: { clipId: "c0", newStart: 1 } },
      { commandType: MOVE_CLIP, payload: { clipId: "c1", newStart: 5 } },
      { commandType: MOVE_CLIP, payload: { clipId: "c2", newStart: 9 } },
    ]);
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([1, 5, 9]);

    // Undo exactly once -> whole group reverts; the 3 adds remain.
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    expect(bus.canUndo).toBe(true); // the 3 adds are still undoable
    bus.redo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([1, 5, 9]);
  });

  it("redo re-applies the entire group exactly once", () => {
    bus.batch([
      { commandType: MOVE_CLIP, payload: { clipId: "c0", newStart: 2 } },
      { commandType: MOVE_CLIP, payload: { clipId: "c1", newStart: 6 } },
    ]);
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    bus.redo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([2, 6, 8]);
  });

  it("fails closed: a bad sub-command leaves state UNCHANGED and adds no undo entry", () => {
    const before = JSON.parse(JSON.stringify(parseProject(bus.project).tracks));
    // Probe depth on a sibling to avoid mutating the subject.
    const probe = freshBus();
    let depthBefore = 0;
    while (probe.canUndo) {
      probe.undo();
      depthBefore++;
    }
    expect(() =>
      bus.batch([
        { commandType: MOVE_CLIP, payload: { clipId: "c0", newStart: 2 } },
        { commandType: MOVE_CLIP, payload: { clipId: "c9", newStart: 2 } },
      ]),
    ).toThrow();
    expect(JSON.parse(JSON.stringify(bus.project.tracks))).toEqual(before);
    // No batch entry was pushed; undoing the subject should still match the probe depth.
    let d = 0;
    while (bus.canUndo) {
      bus.undo();
      d++;
    }
    expect(d).toBe(depthBefore);
  });

  it("fails closed: an invalid payload (schema) never applies partial state", () => {
    expect(() =>
      bus.batch([
        { commandType: MOVE_CLIP, payload: { clipId: "c0", newStart: -3 } },
      ]),
    ).toThrow(CommandBusValidationError);
    expect(bus.project.tracks[0].clips[0].start).toBe(0);
  });

  it("batch of deletes collapses to one undo restoring all clips", () => {
    bus.batch([
      { commandType: DELETE_CLIP, payload: { clipId: "c0" } },
      { commandType: DELETE_CLIP, payload: { clipId: "c2" } },
    ]);
    expect(bus.project.tracks[0].clips).toHaveLength(1);
    expect(bus.project.tracks[0].clips[0].id).toBe("c1");
    bus.undo();
    expect(bus.project.tracks[0].clips).toHaveLength(3);
    expect(bus.project.tracks[0].clips.map((c) => c.id).sort()).toEqual(["c0", "c1", "c2"]);
  });

  it("batch of splits collapses to one undo restoring original clips", () => {
    bus.batch([
      { commandType: SPLIT_CLIP, payload: { clipId: "c0", t: 2 } },
      { commandType: SPLIT_CLIP, payload: { clipId: "c1", t: 2 } },
    ]);
    expect(bus.project.tracks[0].clips).toHaveLength(5);
    bus.undo();
    expect(bus.project.tracks[0].clips).toHaveLength(3);
    expect(bus.project.tracks[0].clips.map((c) => c.id).sort()).toEqual(["c0", "c1", "c2"]);
  });

  it("a new edit after undo clears the redo future (branching semantics preserved)", () => {
    bus.batch([
      { commandType: MOVE_CLIP, payload: { clipId: "c0", newStart: 1 } },
      { commandType: MOVE_CLIP, payload: { clipId: "c1", newStart: 5 } },
    ]);
    bus.undo(); // undo the group (c0,c1 back to original)
    expect(bus.canRedo).toBe(true);
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    // A branching edit invalidates the redo future.
    bus.execute(MOVE_CLIP, { clipId: "c2", newStart: 12 });
    expect(bus.canRedo).toBe(false);
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 12]);
    // Undo the new single move -> c2 returns to 8.
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.start)).toEqual([0, 4, 8]);
    // The group was already consumed by the earlier undo + branching, so no stale
    // group remains; undoing continues into the original 3 adds (c2 removed).
    bus.undo();
    expect(bus.project.tracks[0].clips.map((c) => c.id)).toEqual(["c0", "c1"]);
  });
});
