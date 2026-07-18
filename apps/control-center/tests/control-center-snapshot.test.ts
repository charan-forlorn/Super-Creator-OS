import { describe, expect, it } from "vitest";
import {
  DEMO_SNAPSHOT,
  DEMO_LABEL,
  mapSnapshotToCockpit,
  resolveCockpitView,
  type ControlCenterSnapshot,
} from "@/lib/control-center-snapshot";

function liveSnapshot(overrides: Partial<ControlCenterSnapshot> = {}): ControlCenterSnapshot {
  const base: ControlCenterSnapshot = {
    schema_version: 1,
    snapshot_id: "ccs-test",
    generated_at: "2026-07-16T00:00:00Z",
    source_mode: "LIVE_LOCAL_READ_ONLY",
    health: { available: true, status: "AVAILABLE_WITH_DATA", data: { health_status: "healthy", artifact_count: 1, event_count: 0, command_record_count: 0, audit_record_count: 0, warning_count: 0, blocker_count: 0, source_coverage: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    queue_summary: { available: true, status: "AVAILABLE_EMPTY", data: { count: 0, items: [] }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" },
    approval_summary: { available: true, status: "AVAILABLE_EMPTY", data: { approval_count: 0, audit_record_count: 8 }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" },
    project_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { state_tables_present: ["a", "b"], has_dedicated_project_model: false }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    evidence_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { event_record_count: 0, audit_record_count: 8 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    recent_activity: { available: true, status: "AVAILABLE_WITH_DATA", data: { count: 1, items: [{ activity_id: "a1", activity_type: "CERT", status: "ok", summary: "did a thing", occurred_at: "2026-07-16T00:00:00Z" }] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    degradation_reasons: [],
  };
  return { ...base, ...overrides };
}

describe("control-center-snapshot adapter", () => {
  it("maps live snapshot fields truthfully", () => {
    const view = mapSnapshotToCockpit(liveSnapshot(), "LIVE");
    expect(view.sourceMode).toBe("LIVE");
    expect(view.health.available).toBe(true);
    expect(view.health.healthStatus).toBe("healthy");
    // In a healthy repo the read surface holds records: approvals are
    // AVAILABLE_EMPTY (zero records), evidence AVAILABLE_WITH_DATA.
    expect(view.approvals.available).toBe(true);
    expect(view.approvals.count).toBe(0);
    // Empty queue is distinct from unavailable.
    expect(view.queue.available).toBe(true);
    expect(view.queue.count).toBe(0);
    expect(view.queue.status).toBe("AVAILABLE_EMPTY");
    // Evidence holds audit records in a healthy repo.
    expect(view.evidence.available).toBe(true);
    expect(view.evidence.eventCount).toBe(0);
    expect(view.evidence.auditCount).toBe(8);
  });

  it("demo mode uses the separate demo dataset and is labeled", () => {
    const view = resolveCockpitView("DEMO", null);
    expect(view.sourceMode).toBe("DEMO");
    // Demo provides populated counts (separate from live).
    expect(view.approvals.count).toBe(3);
    expect(view.queue.count).toBe(2);
  });

  it("live failure never falls back to demo and reports unavailable truthfully", () => {
    const view = resolveCockpitView("LIVE", null);
    expect(view.sourceMode).toBe("LIVE");
    expect(view.health.available).toBe(false);
    expect(view.health.status).toBe("UNAVAILABLE");
  });

  it("demo data is never merged with live data", () => {
    // Even when live is available, DEMO mode resolves to the demo snapshot only.
    const view = resolveCockpitView("DEMO", liveSnapshot());
    expect(view.approvals.count).toBe(DEMO_SNAPSHOT.approval_summary.data?.approval_count);
    expect(view.queue.count).toBe(DEMO_SNAPSHOT.queue_summary.data?.count);
    // Not the live approval count (which was null here anyway).
    expect(view.approvals.count).not.toBeNull();
  });

  it("DEMO_LABEL constant is explicit", () => {
    expect(DEMO_LABEL).toBe("DEMO DATA — NOT LIVE SYSTEM STATE");
  });
});
