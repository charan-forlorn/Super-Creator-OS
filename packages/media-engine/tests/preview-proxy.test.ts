import { describe, it, expect } from "vitest";
import { previewNeedsProxy } from "../src/index.js";

describe("preview proxy compatibility — ROOT_CAUSE_3 (WebVie2 decode gaps)", () => {
  it("direct-plays widely supported codecs", () => {
    expect(previewNeedsProxy({ kind: "video", videoCodec: "h264", audioCodec: "aac" })).toBe(false);
    expect(previewNeedsProxy({ kind: "video", videoCodec: "avc1", audioCodec: "aac" })).toBe(false);
  });

  it("needs a proxy for unsupported / exotic codecs", () => {
    expect(previewNeedsProxy({ kind: "video", videoCodec: "hevc", audioCodec: "aac" })).toBe(true);
    expect(previewNeedsProxy({ kind: "video", videoCodec: "prores", audioCodec: "aac" })).toBe(true);
    expect(previewNeedsProxy({ kind: "video", videoCodec: "h264", audioCodec: "amr" })).toBe(true);
  });

  it("non-av media never needs a proxy", () => {
    expect(previewNeedsProxy({ kind: "image" })).toBe(false);
    expect(previewNeedsProxy({ kind: "audio", audioCodec: "mp3" })).toBe(false);
  });

  it("unknown codecs are treated conservatively (proxy)", () => {
    expect(previewNeedsProxy({ kind: "video", videoCodec: null, audioCodec: null })).toBe(false);
  });
});
