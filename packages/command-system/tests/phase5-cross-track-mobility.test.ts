import { describe, expect, it } from "vitest";
import { createEmptyProject, type Clip, type Project, type Track } from "@haios/project-model";
import { createCommandBus, MOVE_CLIP_ACROSS_TRACKS } from "../src/index.js";

function track(id: string, kind: Track["kind"] = "video", locked = false, clips: Clip[] = []): Track {
  return { id, kind, locked, clips, captions: [], visible: true, muted: false };
}

function clip(id: string, trackId: string, start: number, transitionIn: Clip["transitionIn"] = null): Clip {
  return { id, assetId: "asset", inPoint: 0, duration: 4, start, trackId, transitionIn };
}

function busWith(tracks: Track[]) {
  const project: Project = { ...createEmptyProject("P5", "p5"), tracks, durationSec: 20 };
  const bus = createCommandBus(project);
  bus.load(project);
  return bus;
}

function move(clipId: string, sourceTrackId: string, targetTrackId: string, newStart: number) {
  return { clipId, sourceTrackId, targetTrackId, newStart };
}

describe("Phase 5 cross-track editorial mobility command authority", () => {
  it("moves video and audio selections atomically with exact undo/redo containment", () => {
    const bus = busWith([
      track("v1", "video", false, [clip("v", "v1", 1)]), track("v2"),
      track("a1", "audio", false, [clip("a", "a1", 3)]), track("a2", "audio"),
    ]);
    const before = structuredClone(bus.project);
    bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("v", "v1", "v2", 4)] });
    expect(bus.project.tracks.find((t) => t.id === "v1")?.clips).toEqual([]);
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips).toMatchObject([{ id: "v", trackId: "v2", start: 4 }]);
    expect(bus.undo()).toBe(true);
    expect({ ...bus.project, updatedAt: before.updatedAt }).toEqual(before);
    expect(bus.redo()).toBe(true);
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips[0]).toMatchObject({ id: "v", trackId: "v2", start: 4 });

    const audio = busWith([track("a1", "audio", false, [clip("a", "a1", 3)]), track("a2", "audio")]);
    audio.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("a", "a1", "a2", 6)] });
    expect(audio.project.tracks.find((t) => t.id === "a2")?.clips).toMatchObject([{ id: "a", trackId: "a2", start: 6 }]);
  });

  it("preserves an existing project tail and unrelated late captions", () => {
    const bus = busWith([
      track("v1", "video", false, [clip("v", "v1", 1)]),
      track("v2"),
      { ...track("t1", "text"), captions: [{ id: "cap", text: "late", start: 14, duration: 2, trackId: "t1", style: {} }] },
    ]);
    bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("v", "v1", "v2", 1)] });
    expect(bus.project.durationSec).toBe(20);
    expect(bus.project.tracks.find((t) => t.id === "t1")?.captions[0]).toMatchObject({ id: "cap", start: 14, duration: 2 });
  });

  it("fails closed when a referenced track id is ambiguous", () => {
    const bus = busWith([
      track("v1", "video", false, [clip("v", "v1", 1)]),
      track("v2"),
      track("v2", "video", true),
    ]);
    const before = structuredClone(bus.project);
    expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("v", "v1", "v2", 3)] }))
      .toThrow(/CROSS_TRACK_TRACK_ID_AMBIGUOUS: v2/);
    expect(bus.project).toEqual(before);
    expect(bus.canUndo).toBe(false);
  });

  it("fails closed for duplicate or missing ids, source drift, missing/wrong/locked targets, mixed kinds, and no-op", () => {
    const cases: Array<{ moves: unknown[]; error: RegExp }> = [
      { moves: [move("v", "v1", "v2", 2), move("v", "v1", "v2", 3)], error: /CROSS_TRACK_DUPLICATE_CLIP_ID/ },
      { moves: [move("missing", "v1", "v2", 2)], error: /CROSS_TRACK_CLIP_NOT_FOUND/ },
      { moves: [move("v", "wrong", "v2", 2)], error: /CROSS_TRACK_SOURCE_TRACK_DRIFT/ },
      { moves: [move("v", "v1", "missing", 2)], error: /CROSS_TRACK_TARGET_TRACK_NOT_FOUND/ },
      { moves: [move("v", "v1", "a1", 2)], error: /CROSS_TRACK_TARGET_TRACK_KIND_MISMATCH/ },
      { moves: [move("v", "v1", "v1", 1)], error: /CROSS_TRACK_NO_OP/ },
      { moves: [move("v", "v1", "v2", 1), move("a", "a1", "a2", 3)], error: /CROSS_TRACK_SELECTION_KIND_MISMATCH/ },
    ];
    for (const { moves, error } of cases) {
      const bus = busWith([track("v1", "video", false, [clip("v", "v1", 1)]), track("v2"), track("a1", "audio", false, [clip("a", "a1", 3)]), track("a2")]);
      const before = structuredClone(bus.project);
      expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves })).toThrow(error);
      expect(bus.project).toEqual(before);
      expect(bus.canUndo).toBe(false);
    }
    for (const locked of ["source", "target"] as const) {
      const bus = busWith([track("v1", "video", locked === "source", [clip("v", "v1", 1)]), track("v2", "video", locked === "target")]);
      const before = structuredClone(bus.project);
      expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("v", "v1", "v2", 2)] })).toThrow(/TRACK_LOCKED/);
      expect(bus.project).toEqual(before);
    }
  });

  it("rejects an orphaned crossfade endpoint and moves a complete linked pair only when its canonical predecessor remains valid", () => {
    const pair = [clip("lead", "v1", 0), clip("fade", "v1", 3.5, { type: "crossfade", duration: 0.5 })];
    const bus = busWith([track("v1", "video", false, pair), track("v2")]);
    const before = structuredClone(bus.project);
    expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("fade", "v1", "v2", 3.5)] })).toThrow(/CROSS_TRACK_TRANSITION_CONFLICT/);
    expect(bus.project).toEqual(before);
    bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("lead", "v1", "v2", 4), move("fade", "v1", "v2", 7.5)] });
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id)).toEqual(["lead", "fade"]);
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.find((c) => c.id === "fade")?.transitionIn).toEqual({ type: "crossfade", duration: 0.5 });

    const conflicted = busWith([track("v1", "video", false, pair), track("v2", "video", false, [clip("intruder", "v2", 5)])]);
    expect(() => conflicted.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [move("lead", "v1", "v2", 4), move("fade", "v1", "v2", 7.5)] }))
      .toThrow(/CROSS_TRACK_TRANSITION_CONFLICT/);
  });
});

describe("Phase 5 ambiguous identity hardening", () => {
  it("rejects a clip id that resolves to more than one source containment", () => {
    const project = createEmptyProject("P5", "p5-ambiguous");
    project.tracks = [
      track("v1", "video", false, [clip("dup", "v1", 1)]),
      track("v2", "video", false, [clip("dup", "v2", 4)]),
      track("v3"),
    ];
    const bus = createCommandBus(project);
    const before = structuredClone(bus.project);
    expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, {
      moves: [move("dup", "v1", "v3", 2)],
    })).toThrow(/CROSS_TRACK_CLIP_ID_AMBIGUOUS/);
    expect(bus.project).toEqual(before);
    expect(bus.canUndo).toBe(false);
  });
});

describe("Phase 5 transition ordering currentness", () => {
  it("uses Unicode code-point ordering for same-start transition topology", () => {
    const lead = { ...clip("z", "v1", 0), duration: 2 };
    const fade = { ...clip("\u00e4", "v1", 0, { type: "crossfade", duration: 2 }), duration: 2 };
    const bus = busWith([track("v1", "video", false, [fade, lead]), track("v2")]);
    expect(() => bus.execute(MOVE_CLIP_ACROSS_TRACKS, { moves: [
      move("z", "v1", "v2", 3), move("\u00e4", "v1", "v2", 3),
    ] })).not.toThrow();
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id).sort()).toHaveLength(2);
  });
});
