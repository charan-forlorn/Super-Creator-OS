import { describe, expect, it } from "vitest";
import { BoundedTaskQueue, analyzeMediaSource } from "../src/mediaAnalysis";

const okProbe = {
  id: "p", name: "sample.mp4", sourcePath: "C:/sample.mp4", kind: "video", durationSec: 10,
  width: 1920, height: 1080, fps: 30, hasAudio: true, videoCodec: "h264", audioCodec: "aac",
  audioSampleRate: 48000, probeStatus: "ok", error: null,
};

describe("R2.3 media analysis", () => {
  it("bounds background work to two concurrent tasks", async () => {
    const q = new BoundedTaskQueue(2);
    let active = 0;
    let maxActive = 0;
    const task = () => q.enqueue(async () => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 20));
      active -= 1;
      return true;
    });
    await Promise.all([task(), task(), task(), task(), task()]);
    expect(maxActive).toBe(2);
  });

  it("returns metadata, thumbnail and waveform without generating an unnecessary proxy", async () => {
    const calls: string[] = [];
    const result = await analyzeMediaSource("C:/sample.mp4", {
      probeMedia: async () => okProbe,
      ensureThumbnail: async () => { calls.push("thumb"); return "C:/thumb.png"; },
      ensurePreviewProxy: async () => { calls.push("proxy"); return "C:/proxy.mp4"; },
      ensureWaveform: async () => { calls.push("wave"); return "C:/wave.png"; },
      previewNeedsProxy: () => false,
    });
    expect(result.status).toBe("ready");
    expect(result.probe?.width).toBe(1920);
    expect(result.thumbnailPath).toBe("C:/thumb.png");
    expect(result.waveformPath).toBe("C:/wave.png");
    expect(result.proxyPath).toBeUndefined();
    expect(calls).toEqual(["thumb", "wave"]);
  });

  it("classifies a missing source without attempting derived media", async () => {
    const missing = { ...okProbe, probeStatus: "missing", error: "file not found" };
    const result = await analyzeMediaSource("C:/missing.mp4", {
      probeMedia: async () => missing,
      ensureThumbnail: async () => { throw new Error("must not run"); },
      ensurePreviewProxy: async () => { throw new Error("must not run"); },
      ensureWaveform: async () => { throw new Error("must not run"); },
      previewNeedsProxy: () => false,
    });
    expect(result.status).toBe("missing");
    expect(result.error).toMatch(/file not found/);
  });
});
