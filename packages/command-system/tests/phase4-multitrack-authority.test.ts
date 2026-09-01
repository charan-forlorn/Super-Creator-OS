import { describe, expect, it } from "vitest";
import { createEmptyProject, type Clip, type MediaAsset, type Track } from "@haios/project-model";
import { createCommandBus } from "../src/index.js";

const asset: MediaAsset = {
  id: "a", name: "a.mp4", sourcePath: "/media/a.mp4", kind: "video",
  durationSec: 20, width: 1920, height: 1080, fps: 30, hasAudio: true,
  createdAt: "2026-01-01T00:00:00Z",
};
const insertAsset: MediaAsset = {
  ...asset, id: "b", name: "b.mp4", sourcePath: "/media/b.mp4", durationSec: 3,
};
function clip(id: string, trackId: string, start: number): Clip {
  return {
    id, assetId: "a", trackId, start, inPoint: 0, duration: 2, playbackRate: 1,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    effects: { brightness: 0, contrast: 1, saturation: 1 }, transitionIn: null,
    audio: { gainDb: 0, muted: false },
  };
}
function track(id: string, kind: Track["kind"] = "video", locked = false): Track {
  return { id, kind, clips: [], captions: [], visible: true, muted: false, locked };
}
function busWithTracks(tracks: Track[]) {
  const project = createEmptyProject("P4.2", "p42");
  project.assets = [asset, insertAsset];
  project.tracks = tracks;
  project.durationSec = Math.max(0, ...tracks.flatMap((t) => t.clips.map((c) => c.start + c.duration)));
  return createCommandBus(project);
}
describe("Phase 4 P4.2 multi-track command authority", () => {
  it("allows multiple video/audio tracks while keeping duplicate ids fail-closed", () => {
    const bus = busWithTracks([]);
    bus.execute("track.add", { track: track("v1") });
    bus.execute("track.add", { track: track("v2") });
    bus.execute("track.add", { track: track("a1", "audio") });
    bus.execute("track.add", { track: track("a2", "audio") });
    expect(bus.project.tracks.map((t) => t.id)).toEqual(["v1", "v2", "a1", "a2"]);
    expect(() => bus.execute("track.add", { track: track("v2") })).toThrow(/TRACK_DUPLICATE_ID/);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks.map((t) => t.id)).toEqual(["v1", "v2", "a1"]);
  });

  it("reorders canonical track order as one undoable command", () => {
    const bus = busWithTracks([track("back"), track("mid"), track("front")]);
    bus.execute("track.reorder", { trackId: "front", toIndex: 0 });
    expect(bus.project.tracks.map((t) => t.id)).toEqual(["front", "back", "mid"]);
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks.map((t) => t.id)).toEqual(["back", "mid", "front"]);
    expect(bus.redo()).toBe(true);
    expect(bus.project.tracks.map((t) => t.id)).toEqual(["front", "back", "mid"]);
  });

  it("sets persisted track controls and restores them exactly on undo", () => {
    const bus = busWithTracks([track("v")]);
    bus.execute("track.setControls", { trackId: "v", visible: false, muted: true, locked: true });
    expect(bus.project.tracks[0]).toMatchObject({ visible: false, muted: true, locked: true });
    expect(bus.undo()).toBe(true);
    expect(bus.project.tracks[0]).toMatchObject({ visible: true, muted: false, locked: false });
    bus.execute("track.setControls", { trackId: "v", locked: true });
    bus.execute("track.setControls", { trackId: "v", locked: false });
    expect(bus.project.tracks[0].locked).toBe(false);
  });
  it("requires explicit timeline target when more than one compatible track exists", () => {
    const v1 = track("v1"); v1.clips = [clip("c1", "v1", 0)];
    const v2 = track("v2");
    const bus = busWithTracks([v1, v2]);
    const before = structuredClone(bus.project);
    expect(() => bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 4 }))
      .toThrow(/TIMELINE_TARGET_TRACK_REQUIRED/);
    expect(bus.project).toEqual(before);
    expect(bus.canUndo).toBe(false);
  });

  it("routes insert/overwrite to an explicit compatible target track", () => {
    const v1 = track("v1"); v1.clips = [clip("c1", "v1", 0)];
    const v2 = track("v2");
    const bus = busWithTracks([v1, v2]);
    bus.execute("timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 4, targetTrackId: "v2" });
    expect(bus.project.tracks.find((t) => t.id === "v1")?.clips.map((c) => c.id)).toEqual(["c1"]);
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id)).toEqual(["ins"]);
    expect(bus.undo()).toBe(true);
    bus.execute("timeline.overwriteAsset", { assetId: "b", clipId: "ovr", atSec: 1, targetTrackId: "v2" });
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id)).toEqual(["ovr"]);
  });

  it("rejects missing and wrong-kind explicit timeline targets", () => {
    const bus = busWithTracks([track("v"), track("a", "audio")]);
    expect(() => bus.execute("timeline.insertAsset", { assetId: "b", clipId: "x", atSec: 0, targetTrackId: "missing" }))
      .toThrow(/TIMELINE_TARGET_TRACK_NOT_FOUND/);
    expect(() => bus.execute("timeline.insertAsset", { assetId: "b", clipId: "y", atSec: 0, targetTrackId: "a" }))
      .toThrow(/TIMELINE_TARGET_TRACK_KIND_MISMATCH/);
  });
  it("requires target track for ambiguous import placement and supports explicit placement", () => {
    const probe = {
      id: "imported", name: "imported.mp4", sourcePath: "/media/imported.mp4", kind: "video",
      durationSec: 2, width: 1280, height: 720, fps: 30, hasAudio: true,
      videoCodec: "h264", audioCodec: "aac", probeStatus: "ok",
    };
    const bus = busWithTracks([track("v1"), track("v2")]);
    expect(() => bus.execute("media.placeProbed", { probe, place: true }))
      .toThrow(/TIMELINE_TARGET_TRACK_REQUIRED/);
    expect(bus.project.assets.some((a) => a.id === "imported")).toBe(false);
    const result = bus.execute<{ clipId?: string }>("media.placeProbed", { probe, place: true, targetTrackId: "v2" });
    expect(result.clipId).toBe("imported-clip");
    expect(bus.project.tracks.find((t) => t.id === "v1")?.clips).toHaveLength(0);
    expect(bus.project.tracks.find((t) => t.id === "v2")?.clips.map((c) => c.id)).toEqual(["imported-clip"]);
  });

  it("allows import-to-bin without target even when media tracks are ambiguous", () => {
    const probe = {
      id: "bin-only", name: "bin.mp4", sourcePath: "/media/bin.mp4", kind: "video",
      durationSec: 2, width: 1280, height: 720, fps: 30, hasAudio: true,
      videoCodec: "h264", audioCodec: "aac", probeStatus: "ok",
    };
    const bus = busWithTracks([track("v1"), track("v2")]);
    const result = bus.execute<{ clipId?: string }>("media.placeProbed", { probe, place: false });
    expect(result.clipId).toBeUndefined();
    expect(bus.project.assets.some((a) => a.id === "bin-only")).toBe(true);
    expect(bus.project.tracks.every((t) => t.clips.length === 0)).toBe(true);
  });
  it("fails closed for every clip/timeline mutation targeting a locked track", () => {
    const locked = track("locked", "video", true);
    locked.clips = [clip("c0", "locked", 0), clip("c1", "locked", 2)];
    const cases: Array<[string, unknown]> = [
      ["clip.add", { clip: clip("c-new", "locked", 5) }],
      ["clip.delete", { clipId: "c0" }],
      ["clip.move", { clipId: "c0", newStart: 1 }],
      ["clip.trim", { clipId: "c0", newSourceEnd: 1.5 }],
      ["clip.audio", { clipId: "c0", gainDb: -3, muted: false }],
      ["clip.effects", { clipId: "c0", brightness: 0.1, contrast: 1, saturation: 1 }],
      ["clip.speed", { clipId: "c0", playbackRate: 2 }],
      ["clip.transition", { clipId: "c1", mode: "crossfade", duration: 0.5 }],
      ["clip.transform", { clipId: "c0", scale: 1.2, x: 0, y: 0, opacity: 1 }],
      ["clip.rippleDelete", { clipIds: ["c0"] }],
      ["clip.rippleTrim", { clipId: "c0", newSourceEnd: 1.5 }],
      ["clip.split", { clipId: "c0", t: 1 }],
      ["track.remove", { trackId: "locked" }],
      ["timeline.insertAsset", { assetId: "b", clipId: "ins", atSec: 5, targetTrackId: "locked" }],
      ["timeline.overwriteAsset", { assetId: "b", clipId: "ovr", atSec: 0, targetTrackId: "locked" }],
    ];
    for (const [type, payload] of cases) {
      const bus = busWithTracks([structuredClone(locked)]);
      const before = structuredClone(bus.project);
      expect(() => bus.execute(type, payload), type).toThrow(/TRACK_LOCKED/);
      expect(bus.project, type).toEqual(before);
      expect(bus.canUndo, type).toBe(false);
    }
  });
  it("rejects a mixed unlocked+locked batch atomically with no history entry", () => {
    const open = track("open"); open.clips = [clip("open-c", "open", 0)];
    const locked = track("locked", "video", true); locked.clips = [clip("locked-c", "locked", 4)];
    const bus = busWithTracks([open, locked]);
    const before = structuredClone(bus.project);
    expect(() => bus.batch([
      { commandType: "clip.delete", payload: { clipId: "open-c" } },
      { commandType: "clip.delete", payload: { clipId: "locked-c" } },
    ])).toThrow(/TRACK_LOCKED/);
    expect(bus.project).toEqual(before);
    expect(bus.canUndo).toBe(false);
  });
});

// P4.2 adversarial extension: lock authority also covers persisted caption edits.
describe("Phase 4 P4.2 locked caption authority", () => {
  it("rejects place/add/remove caption against a locked text track", () => {
    const text = track("text-locked", "text", true);
    text.captions = [{
      id: "cap-1", text: "locked", start: 0, duration: 1, trackId: text.id,
      style: { x: 0.5, y: 0.8, fontSizePx: 48, color: "#FFFFFF", backgroundColor: "#000000", backgroundOpacity: 0.6 },
    }];
    const caption = { ...text.captions[0], id: "cap-2", text: "new" };
    const cases: Array<[string, unknown]> = [
      ["caption.place", { text: "blocked", start: 1, duration: 1 }],
      ["caption.add", { caption }],
      ["caption.remove", { captionId: "cap-1", trackId: text.id }],
    ];
    for (const [type, payload] of cases) {
      const bus = busWithTracks([structuredClone(text)]);
      const before = structuredClone(bus.project);
      expect(() => bus.execute(type, payload), type).toThrow(/TRACK_LOCKED/);
      expect(bus.project, type).toEqual(before);
      expect(bus.canUndo, type).toBe(false);
    }
  });
});

describe("Phase 4 P4.2 caption target authority", () => {
  it("requires an explicit text target when multiple text tracks exist", () => {
    const bus = busWithTracks([track("text-a", "text"), track("text-b", "text")]);
    const before = structuredClone(bus.project);
    expect(() => bus.execute("caption.place", { text: "ambiguous", start: 0, duration: 1 }))
      .toThrow(/CAPTION_TARGET_TRACK_REQUIRED/);
    expect(bus.project).toEqual(before);
    expect(bus.canUndo).toBe(false);
    const result = bus.execute<{ trackId: string }>("caption.place", {
      text: "targeted", start: 0, duration: 1, targetTrackId: "text-b",
    });
    expect(result.trackId).toBe("text-b");
    expect(bus.project.tracks.find((t) => t.id === "text-a")?.captions).toHaveLength(0);
    expect(bus.project.tracks.find((t) => t.id === "text-b")?.captions).toHaveLength(1);
  });
});
