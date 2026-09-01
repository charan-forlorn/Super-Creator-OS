import { describe, expect, it } from "vitest";
import {
  PROJECT_SCHEMA_VERSION,
  createEmptyProject,
  migrateProjectDocument,
  parseProject,
} from "../src/index.js";

const v1Document = {
  schemaVersion: 1,
  id: "legacy-v1",
  name: "Legacy",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
  assets: [],
  tracks: [
    { id: "v1", kind: "video", clips: [], captions: [] },
    { id: "a1", kind: "audio", clips: [], captions: [] },
    { id: "t1", kind: "text", clips: [], captions: [] },
  ],
  durationSec: 0,
  aspectRatio: "1920x1080",
};

describe("Phase 4 project schema v2", () => {
  it("migrates v1 tracks with explicit neutral controls without mutating input", () => {
    const before = JSON.stringify(v1Document);
    const migrated = migrateProjectDocument(v1Document) as any;
    expect(migrated.schemaVersion).toBe(2);
    expect(migrated.tracks).toEqual([
      { ...v1Document.tracks[0], visible: true, muted: false, locked: false },
      { ...v1Document.tracks[1], visible: true, muted: false, locked: false },
      { ...v1Document.tracks[2], visible: true, muted: false, locked: false },
    ]);
    expect(JSON.stringify(v1Document)).toBe(before);
  });

  it("creates and parses v2 documents with explicit track controls", () => {
    expect(PROJECT_SCHEMA_VERSION).toBe(2);
    const empty = createEmptyProject("P4", "p4");
    expect(empty.schemaVersion).toBe(2);
    const parsed = parseProject({
      ...empty,
      tracks: [{
        id: "video-main", kind: "video", clips: [], captions: [],
        visible: false, muted: true, locked: true,
      }],
    });
    expect(parsed.tracks[0]).toMatchObject({ visible: false, muted: true, locked: true });
  });

  it("continues to fail closed for future schema versions", () => {
    expect(() => parseProject({ ...v1Document, schemaVersion: 3 })).toThrow(/newer than supported/i);
  });
});
