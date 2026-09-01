import { describe, expect, it } from "vitest";
import * as projectModel from "../src/index";

const currentDocument = {
  schemaVersion: 2,
  id: "migration-current",
  name: "Current",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
  assets: [],
  tracks: [],
  durationSec: 0,
  aspectRatio: "1920x1080",
};

describe("project schema migration foundation", () => {
  it("exposes an explicit migration seam before schema v2 exists", () => {
    expect(typeof projectModel.migrateProjectDocument).toBe("function");
  });

  it("passes the current schema through without changing semantics", () => {
    const migrate = (projectModel as any).migrateProjectDocument;
    expect(migrate(currentDocument)).toEqual(currentDocument);
  });

  it("fails closed for future schema versions", () => {
    const migrate = (projectModel as any).migrateProjectDocument;
    expect(() => migrate({ ...currentDocument, schemaVersion: 3 })).toThrow(/newer than supported/i);
  });
});
