import { describe, expect, it } from "vitest";
import {
  buildOperatorReadSurfaceProjection,
  countBlockersAndWarnings,
  filterActivityByLimit,
  getReadinessTone,
  getSignalTone,
} from "@/lib/operator-read-surface-projection";
import {
  degradedOperatorReadSurfaceProjection,
  errorOperatorReadSurfaceProjection,
  populatedOperatorReadSurfaceProjection,
} from "@/lib/operator-read-surface-mock-data";

describe("operator read surface projection", () => {
  it("builds deterministic projections for identical input", () => {
    const first = buildOperatorReadSurfaceProjection(populatedOperatorReadSurfaceProjection);
    const second = buildOperatorReadSurfaceProjection(populatedOperatorReadSurfaceProjection);

    expect(first).toEqual(second);
    expect(first.healthSignals.map((signal) => signal.signalType)).toEqual([
      "BACKEND",
      "STATE_STORE",
      "EVENT_STREAM",
      "APPROVAL",
      "AUDIT",
      "SECURITY_BASELINE",
      "DRIFT",
      "HOST_METRICS",
    ]);
  });

  it("applies activity limits deterministically", () => {
    const limited = filterActivityByLimit(
      populatedOperatorReadSurfaceProjection.recentActivity,
      2,
    );

    expect(limited).toHaveLength(2);
    expect(limited.map((record) => record.activityId)).toEqual([
      "act-stage74",
      "act-stage73",
    ]);
  });

  it("counts blockers and warnings from coherence and health signals", () => {
    expect(countBlockersAndWarnings(degradedOperatorReadSurfaceProjection)).toEqual({
      blockers: 0,
      warnings: 4,
    });
    expect(countBlockersAndWarnings(errorOperatorReadSurfaceProjection).blockers).toBe(2);
  });

  it("maps tones without runtime side effects", () => {
    expect(getReadinessTone({ goNoGo: "GO", readinessScore: 94 })).toContain(
      "status-approved",
    );
    expect(getSignalTone("error")).toContain("status-rejected");
  });

  it("projects missing required arrays as empty or degraded-safe, never healthy", () => {
    const projection = buildOperatorReadSurfaceProjection({
      projectionId: "missing-arrays",
    });

    expect(projection.state).toBe("empty");
    expect(projection.coherence.status).toBe("unknown");
    expect(projection.healthSignals).toEqual([]);
    expect(projection.recentActivity).toEqual([]);
  });
});
