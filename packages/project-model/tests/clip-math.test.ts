import { describe, it, expect } from "vitest";
import {
  splitClip,
  trimLeft,
  trimRight,
  validateClipAgainstAsset,
  sourceEnd,
  ClipMathError,
} from "../src/clip-math.js";
import type { Clip, MediaAsset } from "../src/schema.js";

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

const baseClip: Clip = {
  id: "c1",
  assetId: "a1",
  inPoint: 2,
  duration: 4, // consumes source [2,6]
  start: 0,
  trackId: "t1",
};

describe("clip math", () => {
  it("sourceEnd = inPoint + duration", () => {
    expect(sourceEnd(baseClip)).toBe(6);
  });

  it("validateClipAgainstAsset passes for a valid clip", () => {
    expect(validateClipAgainstAsset(baseClip, asset)).toBeNull();
  });

  it("rejects a clip that overshoots the source asset", () => {
    const bad = { ...baseClip, duration: 9 }; // ends at 11 > 10
    expect(validateClipAgainstAsset(bad, asset)).toMatch(/only 10s/);
  });

  it("split produces two clips covering the same source range", () => {
    const { left, right } = splitClip(baseClip, 1.5);
    expect(left.inPoint).toBe(2);
    expect(left.duration).toBe(1.5);
    expect(right.inPoint).toBe(3.5);
    expect(right.start).toBe(1.5);
    expect(right.duration).toBe(2.5);
    // source coverage preserved: left covers [2,3.5), right covers [3.5,6)
    expect(sourceEnd(left)).toBeCloseTo(3.5);
    expect(sourceEnd(right)).toBeCloseTo(6);
    expect(left.duration + right.duration).toBeCloseTo(baseClip.duration);
  });

  it("split throws on an invalid split point (0 or >= duration)", () => {
    expect(() => splitClip(baseClip, 0)).toThrow(ClipMathError);
    expect(() => splitClip(baseClip, 4)).toThrow(ClipMathError);
    expect(() => splitClip(baseClip, -1)).toThrow(ClipMathError);
  });

  it("trimLeft keeps the source end fixed", () => {
    const t = trimLeft(baseClip, 3); // start consuming at 3, end stays 6
    expect(t.inPoint).toBe(3);
    expect(t.duration).toBe(3);
    expect(sourceEnd(t)).toBeCloseTo(6);
  });

  it("trimLeft rejects a point that yields non-positive duration", () => {
    expect(() => trimLeft(baseClip, 6)).toThrow(ClipMathError);
  });

  it("trimRight keeps the in-point fixed", () => {
    const t = trimRight(baseClip, 5); // end at 5, inPoint stays 2
    expect(t.inPoint).toBe(2);
    expect(t.duration).toBe(3);
  });

  it("trimRight rejects an end <= inPoint", () => {
    expect(() => trimRight(baseClip, 2)).toThrow(ClipMathError);
  });
});
