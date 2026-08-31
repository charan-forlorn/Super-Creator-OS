import { describe, expect, it } from "vitest";
import { sourceTimeForClip, timelineTimeForClip } from "../src/components/Preview";

const clip = { start: 3, inPoint: 2, playbackRate: 2 };

describe("R2.11 preview speed mapping", () => {
  it("maps timeline seconds to source seconds using playbackRate", () => {
    expect(sourceTimeForClip(clip, 3)).toBe(2);
    expect(sourceTimeForClip(clip, 4)).toBe(4);
    expect(sourceTimeForClip(clip, 5)).toBe(6);
  });

  it("maps source media time back to timeline time", () => {
    expect(timelineTimeForClip(clip, 2)).toBe(3);
    expect(timelineTimeForClip(clip, 4)).toBe(4);
    expect(timelineTimeForClip(clip, 6)).toBe(5);
  });

  it("preserves legacy 1x behavior when playbackRate is absent", () => {
    const legacy = { start: 3, inPoint: 2 };
    expect(sourceTimeForClip(legacy, 4)).toBe(3);
    expect(timelineTimeForClip(legacy, 3)).toBe(4);
  });
});
