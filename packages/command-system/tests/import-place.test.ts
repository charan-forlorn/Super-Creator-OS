import { describe, it, expect } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import {
  createCommandBus,
  ADD_TRACK,
  PLACE_PROBED_MEDIA,
} from "../src/index.js";

// A video probe exactly as the Tauri bridge returns it (see bridge.ts MediaProbe).
const videoProbe = {
  id: "asset-1",
  name: "sample.mp4",
  sourcePath: "C:\\Videos\\sample.mp4",
  kind: "video",
  durationSec: 5,
  width: 1920,
  height: 1080,
  fps: 30,
  hasAudio: true,
  videoCodec: "h264",
  audioCodec: "aac",
  audioSampleRate: 48000,
  probeStatus: "ok",
  error: null,
};

describe("R1 import placement — ROOT_CAUSE_1 (stale React snapshot race)", () => {
  it("places asset + suitable track + clip atomically on a fresh project", () => {
    const bus = createCommandBus(createEmptyProject("P", "p1"));
    const res = bus.execute(PLACE_PROBED_MEDIA, { probe: videoProbe, place: true });
    const p = bus.project;

    expect(p.assets).toHaveLength(1);
    expect(p.assets[0].id).toBe("asset-1");

    const vTrack = p.tracks.find((t) => t.kind === "video");
    expect(vTrack).toBeDefined();

    const clip = vTrack!.clips[0];
    expect(clip).toBeDefined();
    expect(clip.assetId).toBe("asset-1");

    expect(p.durationSec).toBeGreaterThan(0);
    expect(res.clipId).toBe(clip.id);
  });

  it("undo fully restores the fresh project (no asset / track / clip)", () => {
    const bus = createCommandBus(createEmptyProject("P", "p1"));
    bus.execute(PLACE_PROBED_MEDIA, { probe: videoProbe, place: true });
    expect(bus.project.assets).toHaveLength(1);

    bus.undo();
    expect(bus.project.assets).toHaveLength(0);
    expect(bus.project.tracks).toHaveLength(0);
    expect(bus.project.durationSec).toBe(0);
  });

  it("PLACE_PROBED_MEDIA on an already-populated project reuses the existing track", () => {
    const bus = createCommandBus(createEmptyProject("P", "p1"));
    bus.execute(PLACE_PROBED_MEDIA, { probe: videoProbe, place: true });
    const afterFirst = bus.project.tracks.length;

    const probe2 = { ...videoProbe, id: "asset-2", name: "clip2.mp4" };
    bus.execute(PLACE_PROBED_MEDIA, { probe: probe2, place: true });

    // Track count must NOT grow — one video track is reused.
    expect(bus.project.tracks).toHaveLength(afterFirst);
    expect(bus.project.assets).toHaveLength(2);
    expect(bus.project.tracks[0].clips).toHaveLength(2);
  });

  it("ADD_TRACK rejects a duplicate media-kind track (single-track-per-kind invariant)", () => {
    const bus = createCommandBus(createEmptyProject("P", "p1"));
    bus.execute(ADD_TRACK, { track: { id: "tv1", kind: "video" } });
    expect(() => bus.execute(ADD_TRACK, { track: { id: "tv2", kind: "video" } })).toThrow();
    // text tracks may be multiple
    expect(() => bus.execute(ADD_TRACK, { track: { id: "tt1", kind: "text" } })).not.toThrow();
    expect(() => bus.execute(ADD_TRACK, { track: { id: "tt2", kind: "text" } })).not.toThrow();
  });

  it("ADD_TRACK then undo removes the track it created", () => {
    const bus = createCommandBus(createEmptyProject("P", "p1"));
    bus.execute(ADD_TRACK, { track: { id: "ta1", kind: "audio" } });
    expect(bus.project.tracks).toHaveLength(1);
    bus.undo();
    expect(bus.project.tracks).toHaveLength(0);
  });
});
