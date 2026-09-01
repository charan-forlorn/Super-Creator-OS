import { describe, expect, it } from "vitest";
import {
  applyRenderProgress,
  createRenderSession,
  isRenderTerminal,
  renderStatusText,
} from "../src/renderLifecycle";

const event = (status: string, progress: number, error: string | null = null) => ({
  jobId: "job-1",
  status,
  progress,
  outputPath: status === "COMPLETED" ? "C:/out.mp4" : null,
  error,
});

describe("R2.13 render lifecycle state", () => {
  it("keeps the export busy until a terminal backend event", () => {
    let state = createRenderSession("job-1", "C:/out.mp4");
    state = applyRenderProgress(state, event("RENDERING", 0.4));
    expect(state.busy).toBe(true);
    state = applyRenderProgress(state, event("VERIFYING", 0.9));
    expect(state.busy).toBe(true);
    state = applyRenderProgress(state, event("COMPLETED", 1));
    expect(state.busy).toBe(false);
    expect(state.status).toBe("COMPLETED");
  });

  it("ignores events for another render job and never regresses progress", () => {
    let state = createRenderSession("job-1", "C:/out.mp4");
    state = applyRenderProgress(state, event("RENDERING", 0.6));
    state = applyRenderProgress(state, { ...event("VERIFYING", 0.9), jobId: "job-2" });
    expect(state.status).toBe("RENDERING");
    expect(state.progress).toBe(0.6);
    state = applyRenderProgress(state, event("RENDERING", 0.2));
    expect(state.progress).toBe(0.6);
  });

  it("treats completed, failed, and cancelled as terminal states", () => {
    expect(isRenderTerminal("COMPLETED")).toBe(true);
    expect(isRenderTerminal("FAILED")).toBe(true);
    expect(isRenderTerminal("CANCELLED")).toBe(true);
    expect(isRenderTerminal("VERIFYING")).toBe(false);
    expect(renderStatusText(event("FAILED", 0.5, "ffmpeg failed"))).toContain("ffmpeg failed");
    expect(renderStatusText(event("CANCELLED", 0.5))).toContain("cancelled");
  });
});
