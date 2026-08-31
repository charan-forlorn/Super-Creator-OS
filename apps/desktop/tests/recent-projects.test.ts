import { describe, expect, it } from "vitest";
import { mergeRecentProjects, projectFileLabel } from "../src/projectLifecycle";

describe("recent project helpers", () => {
  it("deduplicates Windows paths case-insensitively and moves the latest to the front", () => {
    expect(mergeRecentProjects(["C:/Edits/A.haip.json", "D:/B.haip.json"], "c:/edits/a.haip.json"))
      .toEqual(["c:/edits/a.haip.json", "D:/B.haip.json"]);
  });

  it("bounds the recent list to eight entries", () => {
    const current = Array.from({ length: 8 }, (_, i) => `C:/p${i}.json`);
    const next = mergeRecentProjects(current, "C:/latest.json");
    expect(next).toHaveLength(8);
    expect(next[0]).toBe("C:/latest.json");
    expect(next).not.toContain("C:/p7.json");
  });

  it("renders a portable file label for Windows and POSIX separators", () => {
    expect(projectFileLabel("C:\\Projects\\demo.haip.json")).toBe("demo.haip.json");
    expect(projectFileLabel("/tmp/demo.haip.json")).toBe("demo.haip.json");
  });
});
