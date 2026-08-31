import { describe, expect, it } from "vitest";
import { clipSchema, sourceEnd, splitClip, trimLeft, trimRight, validateClipAgainstAsset } from "../src/index.js";

const legacy = {
  id: "c1",
  assetId: "a1",
  inPoint: 2,
  duration: 2,
  start: 0,
  trackId: "v1",
  transform: {},
};

function rateOf(value: unknown): unknown {
  return (value as Record<string, unknown>).playbackRate;
}

describe("clip playback rate", () => {
  it("backfills playbackRate=1 for legacy clips", () => {
    const parsed = clipSchema.parse(legacy);
    expect(rateOf(parsed)).toBe(1);
  });

  it("uses timeline duration times playback rate as the consumed source span", () => {
    const clip = clipSchema.parse({ ...legacy, playbackRate: 2 });
    expect(sourceEnd(clip)).toBe(6);
    expect(validateClipAgainstAsset(clip, { durationSec: 5.9 })).toMatch(/only 5.9s/);
    expect(validateClipAgainstAsset(clip, { durationSec: 6 })).toBeNull();
  });

  it("splits a retimed clip without changing its consumed source range", () => {
    const clip = clipSchema.parse({ ...legacy, playbackRate: 2 });
    const { left, right } = splitClip(clip, 0.75);
    expect(left.duration).toBe(0.75);
    expect(sourceEnd(left)).toBe(3.5);
    expect(right.inPoint).toBe(3.5);
    expect(right.start).toBe(0.75);
    expect(right.duration).toBe(1.25);
    expect(sourceEnd(right)).toBe(6);
    expect(rateOf(left)).toBe(2);
    expect(rateOf(right)).toBe(2);
  });

  it("trims retimed clips in source-time while keeping timeline duration rate-aware", () => {
    const clip = clipSchema.parse({ ...legacy, playbackRate: 2 });
    const left = trimLeft(clip, 3);
    expect(left.duration).toBe(1.5);
    expect(sourceEnd(left)).toBe(6);
    const right = trimRight(clip, 5);
    expect(right.duration).toBe(1.5);
    expect(sourceEnd(right)).toBe(5);
  });
});
