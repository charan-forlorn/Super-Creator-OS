import { describe, expect, it } from "vitest";
import { compileCompositionPlan, parseProject } from "../src/index.js";

const asset = (id: string, kind: "video" | "audio", hasAudio: boolean) => ({
  id, name: `${id}.mp4`, sourcePath: `C:/${id}.mp4`, kind,
  durationSec: 10, fps: kind === "video" ? 30 : undefined,
  hasAudio, createdAt: "2026-01-01T00:00:00.000Z",
});

const clip = (id: string, assetId: string, trackId: string, start = 0) => ({
  id, assetId, trackId, start, inPoint: 0, duration: 2,
  playbackRate: 1,
  transform: { scale: 1, x: 0, y: 0, opacity: 1 },
  effects: { brightness: 0, contrast: 1, saturation: 1 },
  transitionIn: null,
  audio: { gainDb: -6, muted: false },
});

function project() {
  return parseProject({
    schemaVersion: 2,
    id: "composition-v2", name: "Composition",
    createdAt: "2026-01-01T00:00:00.000Z", updatedAt: "2026-01-01T00:00:00.000Z",
    assets: [asset("video-a", "video", true), asset("video-silent", "video", false), asset("music", "audio", true)],
    tracks: [
      { id: "video-back", kind: "video", visible: true, muted: false, locked: false, clips: [clip("c-back", "video-a", "video-back")], captions: [] },
      { id: "video-hidden", kind: "video", visible: false, muted: false, locked: false, clips: [clip("c-hidden", "video-a", "video-hidden")], captions: [] },
      { id: "video-front", kind: "video", visible: true, muted: false, locked: true, clips: [clip("c-front", "video-silent", "video-front")], captions: [] },
      { id: "music-muted", kind: "audio", visible: true, muted: true, locked: false, clips: [clip("c-mute", "music", "music-muted")], captions: [] },
      { id: "music-live", kind: "audio", visible: true, muted: false, locked: false, clips: [clip("c-live", "music", "music-live", 1)], captions: [] },
      { id: "captions", kind: "text", visible: true, muted: false, locked: false, clips: [], captions: [] },
    ],
    durationSec: 10, aspectRatio: "1920x1080",
  });
}

describe("Phase 4 derived CompositionPlan", () => {
  it("preserves canonical track order as back-to-front visual z-order", () => {
    const p = project();
    const plan = compileCompositionPlan(p);
    expect(plan.visualLayers.map((layer) => [layer.trackId, layer.zIndex])).toEqual([
      ["video-back", 0],
      ["video-front", 2],
      ["captions", 5],
    ]);
  });

  it("derives audio contributions from unmuted tracks and audible clips", () => {
    const p = project();
    const plan = compileCompositionPlan(p);
    expect(plan.audioLayers.map((layer) => layer.trackId)).toEqual(["video-back", "video-hidden", "music-live"]);
    expect(plan.audioLayers[0].clips[0]).toMatchObject({ clipId: "c-back", gainDb: -6 });
    expect(plan.audioLayers[2].clips[0]).toMatchObject({ clipId: "c-live", gainDb: -6 });
  });

  it("is a pure derived view and does not mutate the persisted project", () => {
    const p = project();
    const before = JSON.stringify(p);
    const plan = compileCompositionPlan(p);
    expect(JSON.stringify(p)).toBe(before);
    expect(plan.schemaVersion).toBe(2);
    expect(plan.durationSec).toBe(10);
    expect(plan.aspectRatio).toBe("1920x1080");
    plan.visualLayers[0].clips[0].start = 99;
    expect(p.tracks[0].clips[0].start).toBe(0);
  });
});
