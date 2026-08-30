import { describe, it, expect } from "vitest";
import { parseProject, PROJECT_SCHEMA_VERSION, createEmptyProject } from "../src/index.js";

describe("project schema versioning", () => {
  it("accepts a well-formed current-version project", () => {
    const p = createEmptyProject("Test", "pid-1");
    expect(p.schemaVersion).toBe(PROJECT_SCHEMA_VERSION);
    const round = parseProject(JSON.parse(JSON.stringify(p)));
    expect(round.id).toBe("pid-1");
  });

  it("rejects a project with an unsupported schemaVersion", () => {
    const p = { ...createEmptyProject("X", "x"), schemaVersion: 999 };
    expect(() => parseProject(p)).toThrow(/Unsupported project schemaVersion/);
  });

  it("rejects a malformed project document", () => {
    expect(() => parseProject({ foo: "bar" })).toThrow(/Invalid project document/);
  });

  it("rejects negative-ish structural corruption", () => {
    const p = createEmptyProject("X", "x");
    // @ts-expect-error intentional corruption
    p.durationSec = "not-a-number";
    expect(() => parseProject(p)).toThrow();
  });
});
