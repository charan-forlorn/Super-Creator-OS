import { describe, it, expect } from "vitest";
import { PlaybackDiagnostics, type PlaybackEvent } from "../src/previewDiagnostics.js";

function makeErrorEvent(code: number, message: string): PlaybackEvent {
  return { type: "error", code, message, mediaError: { code, message } };
}

describe("TEST3 — playback diagnostics must not swallow media errors", () => {
  it("records loadedmetadata / canplay / play / pause lifecycle", () => {
    const d = new PlaybackDiagnostics();
    d.record({ type: "loadedmetadata" });
    d.record({ type: "canplay" });
    d.record({ type: "play" });
    d.record({ type: "pause" });
    const log = d.log();
    expect(log.map((e) => e.type)).toEqual(["loadedmetadata", "canplay", "play", "pause"]);
    expect(d.lastEvent?.type).toBe("pause");
  });

  it("captures MediaError with a code and a human-readable reason", () => {
    const d = new PlaybackDiagnostics();
    d.record(makeErrorEvent(4, "MEDIA_ELEMENT_ERROR: Format error"));
    const last = d.lastEvent!;
    expect(last.type).toBe("error");
    expect(last.mediaError?.code).toBe(4);
    expect(last.mediaError?.message).toBeDefined();
    expect(last.mediaError?.message.length).toBeGreaterThan(0);
  });

  it("classifies the failure as a decode/source problem (not ignored)", () => {
    const d = new PlaybackDiagnostics();
    d.record(makeErrorEvent(4, "no supported source"));
    expect(d.hasError).toBe(true);
    expect(d.isDecodeError).toBe(true);
    expect(d.summary()).toMatch(/error|decode|source/i);
  });

  it("exposes a stable JSON snapshot for review/debug", () => {
    const d = new PlaybackDiagnostics();
    d.record({ type: "loadedmetadata" });
    const snap = JSON.parse(JSON.stringify(d.toJSON()));
    expect(snap.events).toHaveLength(1);
    expect(snap.hasError).toBe(false);
  });
});
