import { beforeEach, describe, expect, it } from "vitest";
import { useStudio } from "../src/store";

const project = {
  schemaVersion: 1,
  id: "p-lifecycle",
  name: "Lifecycle",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-01T00:00:00.000Z",
  assets: [],
  tracks: [],
  durationSec: 0,
  aspectRatio: "1920x1080",
};

describe("production project lifecycle state", () => {
  beforeEach(() => useStudio.getState().newProject());

  it("records the opened project path and starts clean", () => {
    useStudio.getState().loadProject(project, "C:/projects/demo.haip.json");
    const state = useStudio.getState();
    expect(state.projectPath).toBe("C:/projects/demo.haip.json");
    expect(state.dirty).toBe(false);
  });

  it("records a Save As path when marking the project saved", () => {
    useStudio.getState().loadProject(project);
    useStudio.getState().markSaved("D:/edits/demo.haip.json");
    const state = useStudio.getState();
    expect(state.projectPath).toBe("D:/edits/demo.haip.json");
    expect(state.dirty).toBe(false);
  });

  it("does not clear dirty state when a stale save finishes after a newer edit", () => {
    useStudio.getState().loadProject(
      { ...project, updatedAt: "2026-01-01T00:01:00.000Z" },
      "C:/projects/demo.haip.json",
      true,
    );
    useStudio.getState().markSaved("C:/projects/demo.haip.json", project.updatedAt);
    const state = useStudio.getState();
    expect(state.projectPath).toBe("C:/projects/demo.haip.json");
    expect(state.dirty).toBe(true);
  });

  it("clears the project path for a new unsaved project", () => {
    useStudio.getState().loadProject(project, "C:/projects/demo.haip.json");
    useStudio.getState().newProject();
    const state = useStudio.getState();
    expect(state.projectPath).toBeNull();
    expect(state.dirty).toBe(false);
  });
});
