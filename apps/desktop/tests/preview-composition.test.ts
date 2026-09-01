import { describe, expect, it } from "vitest";
import { compileCompositionPlan, parseProject, type Clip, type MediaAsset, type Track } from "@haios/project-model";
import { compilePreviewFrame } from "../src/previewComposition.js";

const asset = (id: string, kind: "video" | "audio" | "image", hasAudio = kind !== "image"): MediaAsset => ({
  id, name: `${id}.mp4`, sourcePath: `/media/${id}.mp4`, kind,
  durationSec: 20, width: 1920, height: 1080, fps: kind === "video" ? 30 : undefined,
  hasAudio, createdAt: "2026-01-01T00:00:00Z",
});
function clip(id: string, assetId: string, trackId: string, start: number, duration = 4, extra: Partial<Clip> = {}): Clip {
  return {
    id, assetId, trackId, start, inPoint: 0, duration, playbackRate: 1,
    transform: { scale: 1, x: 0, y: 0, opacity: 1 },
    effects: { brightness: 0, contrast: 1, saturation: 1 },
    transitionIn: null, audio: { gainDb: 0, muted: false }, ...extra,
  };
}
function track(id: string, kind: Track["kind"], clips: Clip[] = [], visible = true, muted = false): Track {
  return { id, kind, clips, captions: [], visible, muted, locked: false };
}
function project(tracks: Track[], assets: MediaAsset[]) {
  return parseProject({
    schemaVersion: 2, id: "preview-p4.3", name: "Preview P4.3",
    createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
    assets, tracks, durationSec: 12, aspectRatio: "1920x1080",
  });
}

const captionStyle = {
  x: 0.5, y: 0.85, fontSizePx: 48, color: "#FFFFFF",
  backgroundColor: "#000000", backgroundOpacity: 0.6,
};

describe("P4.3 preview composition frame", () => {
  it("returns active visual layers in canonical back-to-front order and excludes hidden tracks", () => {
    const assets = [asset("back", "video"), asset("hidden", "video"), asset("front", "video")];
    const tracks = [
      track("v-back", "video", [clip("c-back", "back", "v-back", 0)]),
      track("v-hidden", "video", [clip("c-hidden", "hidden", "v-hidden", 0)], false),
      track("v-front", "video", [clip("c-front", "front", "v-front", 0)]),
    ];
    const frame = compilePreviewFrame(compileCompositionPlan(project(tracks, assets)), 1);
    expect(frame.visualLayers.map((layer) => layer.trackId)).toEqual(["v-back", "v-front"]);
    expect(frame.visualLayers.map((layer) => layer.zIndex)).toEqual([0, 2]);
    expect(frame.visualLayers.flatMap((layer) => layer.clips.map((entry) => entry.clip.id)))
      .toEqual(["c-back", "c-front"]);
  });
  it("computes an independent crossfade for each active visual track", () => {
    const assets = [asset("base", "video"), asset("out", "video"), asset("in", "video")];
    const base = track("base-track", "video", [clip("base-c", "base", "base-track", 0, 8)]);
    const upper = track("upper-track", "video", [
      clip("out-c", "out", "upper-track", 0, 4),
      clip("in-c", "in", "upper-track", 3, 4, { transitionIn: { type: "crossfade", duration: 2 } }),
    ]);
    const frame = compilePreviewFrame(compileCompositionPlan(project([base, upper], assets)), 4);
    expect(frame.visualLayers[0].clips.map((entry) => [entry.clip.id, entry.opacity])).toEqual([["base-c", 1]]);
    expect(frame.visualLayers[1].clips.map((entry) => entry.clip.id)).toEqual(["out-c", "in-c"]);
    expect(frame.visualLayers[1].clips[0].opacity).toBeCloseTo(0.5);
    expect(frame.visualLayers[1].clips[1].opacity).toBeCloseTo(0.5);
  });

  it("emits only active captions from visible text tracks in canonical z-order", () => {
    const low = track("text-low", "text");
    low.captions = [{ id: "cap-low", text: "LOW", start: 0, duration: 4, trackId: low.id, style: captionStyle }];
    const hidden = track("text-hidden", "text", [], false);
    hidden.captions = [{ id: "cap-hidden", text: "HIDDEN", start: 0, duration: 4, trackId: hidden.id, style: captionStyle }];
    const high = track("text-high", "text");
    high.captions = [{ id: "cap-high", text: "HIGH", start: 1, duration: 3, trackId: high.id, style: captionStyle }];
    const frame = compilePreviewFrame(compileCompositionPlan(project([low, hidden, high], [])), 2);
    expect(frame.captions.map((entry) => [entry.caption.id, entry.zIndex])).toEqual([
      ["cap-low", 0], ["cap-high", 2],
    ]);
  });
  it("emits active audio entries from every unmuted audio-producing layer", () => {
    const assets = [asset("video-a", "video", true), asset("audio-a", "audio", true), asset("audio-b", "audio", true)];
    const video = track("video-track", "video", [clip("video-c", "video-a", "video-track", 0, 5)]);
    const audio = track("audio-track", "audio", [clip("audio-c", "audio-a", "audio-track", 1, 4)]);
    const mutedTrack = track("muted-track", "audio", [clip("muted-c", "audio-b", "muted-track", 0, 5)], true, true);
    const frame = compilePreviewFrame(compileCompositionPlan(project([video, audio, mutedTrack], assets)), 2);
    expect(frame.audio.map((entry) => [entry.trackId, entry.clip.clipId])).toEqual([
      ["video-track", "video-c"], ["audio-track", "audio-c"],
    ]);
    expect(frame.audio[0].sourceTimeSec).toBeCloseTo(2);
    expect(frame.audio[1].sourceTimeSec).toBeCloseTo(1);
  });

  it("preserves single-track preview semantics", () => {
    const a = asset("solo", "video", true);
    const c = clip("solo-c", "solo", "solo-track", 2, 5, { inPoint: 3, playbackRate: 2 });
    const frame = compilePreviewFrame(compileCompositionPlan(project([track("solo-track", "video", [c])], [a])), 3);
    expect(frame.visualLayers).toHaveLength(1);
    expect(frame.visualLayers[0].clips).toHaveLength(1);
    expect(frame.visualLayers[0].clips[0]).toMatchObject({ opacity: 1, sourceTimeSec: 5 });
    expect(frame.visualLayers[0].clips[0].asset.id).toBe("solo");
    expect(frame.audio).toHaveLength(1);
    expect(frame.audio[0].sourceTimeSec).toBeCloseTo(5);
  });
});

describe("P4.3 preview transition audio parity", () => {
  it("applies visual crossfade gain to matching video-track audio entries", () => {
    const assets = [asset("out-a", "video", true), asset("in-a", "video", true)];
    const video = track("video-x", "video", [
      clip("out-x", "out-a", "video-x", 0, 4),
      clip("in-x", "in-a", "video-x", 3, 4, { transitionIn: { type: "crossfade", duration: 2 } }),
    ]);
    const frame = compilePreviewFrame(compileCompositionPlan(project([video], assets)), 4);
    expect(frame.audio.map((entry) => [entry.clip.clipId, entry.gainScale])).toEqual([
      ["out-x", 0.5], ["in-x", 0.5],
    ]);
  });
});
