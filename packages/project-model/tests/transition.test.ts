import { parseProject } from "../src/index.js";

describe("clip transition", () => {
  it("backfills no transition for legacy clips", () => {
    const p = parseProject({
      schemaVersion: 1, id: "p", name: "x",
      createdAt: "2026-01-01T00:00:00.000Z", updatedAt: "2026-01-01T00:00:00.000Z",
      assets: [{ id: "a", name: "x.mp4", sourcePath: "C:/x.mp4", kind: "video", durationSec: 5, hasAudio: true, createdAt: "2026-01-01T00:00:00.000Z" }],
      tracks: [{ id: "v", kind: "video", captions: [], clips: [{ id: "c", assetId: "a", inPoint: 0, duration: 5, start: 0, trackId: "v", transform: {} }] }],
      durationSec: 5, aspectRatio: "1920x1080",
    });
    expect(p.tracks[0].clips[0].transitionIn).toBeNull();
  });
});
