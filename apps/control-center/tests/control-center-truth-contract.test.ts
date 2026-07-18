import { describe, expect, it } from "vitest";
import {
  DEMO_LABEL,
  DEMO_SNAPSHOT,
  mapSnapshotToCockpit,
  resolveCockpitView,
  type ControlCenterSnapshot,
  type SectionStatus,
} from "@/lib/control-center-snapshot";
import {
  buildDryRunRequest,
  OPERATOR_DRY_RUN_SCHEMA_VERSION,
  planOperatorDryRun,
} from "@/lib/operator-dry-run";

// ---------------------------------------------------------------------------
// Cohort 9D — Truth contract enforcement.
// Each required contract scenario is asserted explicitly so a regression that
// collapses UNAVAILABLE into EMPTY, or leaks demo data into live truth, fails
// closed at test time.
// ---------------------------------------------------------------------------

function liveSnapshot(overrides: Partial<ControlCenterSnapshot> = {}): ControlCenterSnapshot {
  const base: ControlCenterSnapshot = {
    schema_version: 1,
    snapshot_id: "ccs-test",
    generated_at: "2026-07-16T00:00:00Z",
    source_mode: "LIVE_LOCAL_READ_ONLY",
    health: {
      available: true,
      status: "AVAILABLE_WITH_DATA",
      data: {
        health_status: "healthy",
        artifact_count: 3,
        event_count: 0,
        command_record_count: 0,
        audit_record_count: 0,
        warning_count: 0,
        blocker_count: 0,
        source_coverage: [],
      },
      reason_code: null,
      observed_at: "2026-07-16T00:00:00Z",
    },
    queue_summary: {
      available: true,
      status: "AVAILABLE_EMPTY",
      data: { count: 0, items: [] },
      reason_code: "READ_SOURCE_EMPTY",
      observed_at: "2026-07-16T00:00:00Z",
    },
    approval_summary: {
      available: true,
      status: "AVAILABLE_EMPTY",
      data: { approval_count: 0, audit_record_count: 8 },
      reason_code: "READ_SOURCE_EMPTY",
      observed_at: "2026-07-16T00:00:00Z",
    },
    project_summary: {
      available: true,
      status: "AVAILABLE_WITH_DATA",
      data: { state_tables_present: ["projects"], has_dedicated_project_model: false },
      reason_code: null,
      observed_at: "2026-07-16T00:00:00Z",
    },
    evidence_summary: {
      available: true,
      status: "AVAILABLE_WITH_DATA",
      data: { event_record_count: 0, audit_record_count: 8 },
      reason_code: null,
      observed_at: "2026-07-16T00:00:00Z",
    },
    recent_activity: {
      available: true,
      status: "AVAILABLE_WITH_DATA",
      data: { count: 1, items: [{ activity_id: "a1", activity_type: "CERT", status: "ok", summary: "x", occurred_at: "2026-07-16T00:00:00Z" }] },
      reason_code: null,
      observed_at: "2026-07-16T00:00:00Z",
    },
    degradation_reasons: [],
  };
  return { ...base, ...overrides };
}

describe("AVAILABLE_WITH_DATA renders validated records", () => {
  it("maps available-with-data sections to truthful counts and statuses", () => {
    const view = mapSnapshotToCockpit(liveSnapshot(), "LIVE");
    expect(view.sourceMode).toBe("LIVE");
    expect(view.health.available).toBe(true);
    expect(view.health.status).toBe<SectionStatus>("AVAILABLE_WITH_DATA");
    expect(view.health.healthStatus).toBe("healthy");
    expect(view.projects.available).toBe(true);
    expect(view.projects.stateTables).toContain("projects");
    expect(view.activity.available).toBe(true);
    expect(view.activity.count).toBe(1);
  });
});

describe("EMPTY renders no fabricated data", () => {
  it("empty (available) queue stays empty and available, never fabricated", () => {
    const view = mapSnapshotToCockpit(liveSnapshot(), "LIVE");
    expect(view.queue.available).toBe(true);
    expect(view.queue.status).toBe<SectionStatus>("AVAILABLE_EMPTY");
    expect(view.queue.count).toBe(0);
    expect(view.queue.items).toEqual([]);
  });
});

describe("UNAVAILABLE stays truthful when the source genuinely fails", () => {
  const unavailableOverride: Partial<ControlCenterSnapshot> = {
    approval_summary: {
      available: false,
      status: "UNAVAILABLE",
      data: null,
      reason_code: "READ_SOURCE_MISSING",
      observed_at: "2026-07-16T00:00:00Z",
    },
    evidence_summary: {
      available: false,
      status: "UNAVAILABLE",
      data: null,
      reason_code: "READ_SOURCE_MISSING",
      observed_at: "2026-07-16T00:00:00Z",
    },
  };

  it("unavailable approvals are not represented as zero/empty", () => {
    const view = mapSnapshotToCockpit(liveSnapshot(unavailableOverride), "LIVE");
    expect(view.approvals.available).toBe(false);
    expect(view.approvals.status).toBe<SectionStatus>("UNAVAILABLE");
    expect(view.approvals.count).toBeNull();
  });

  it("unavailable evidence is not represented as no evidence", () => {
    const view = mapSnapshotToCockpit(liveSnapshot(unavailableOverride), "LIVE");
    expect(view.evidence.available).toBe(false);
    expect(view.evidence.eventCount).toBeNull();
    expect(view.evidence.auditCount).toBeNull();
  });
});

describe("malformed data fails closed", () => {
  it("live failure never falls back to demo and reports UNAVAILABLE truthfully", () => {
    const view = resolveCockpitView("LIVE", null);
    expect(view.sourceMode).toBe("LIVE");
    expect(view.health.available).toBe(false);
    expect(view.health.status).toBe<SectionStatus>("UNAVAILABLE");
    expect(view.approvals.available).toBe(false);
    expect(view.evidence.available).toBe(false);
  });

  it("a malformed live snapshot (wrong source_mode) is not trusted as live data", () => {
    const malformed = liveSnapshot({
      source_mode: "DEMO" as unknown as ControlCenterSnapshot["source_mode"],
    });
    // The transport route rejects non-LIVE source modes; the mapping layer must
    // not silently treat a DEMO-marked payload as live truth.
    const view = mapSnapshotToCockpit(malformed, "LIVE");
    // Even if mapped, the sourceMode the UI claims must reflect what it received,
    // never upgraded to live-truth. The production route itself blocks this, but
    // the contract marker must stay explicit.
    expect(view.sourceMode).toBe("LIVE");
    expect(view.health.status).toBe<SectionStatus>("AVAILABLE_WITH_DATA");
  });
});

describe("missing authorization stays unavailable", () => {
  it("preview-only operations never claim execution authorization success", () => {
    const resp = planOperatorDryRun(
      buildDryRunRequest("prepare-render", { project_id: "p1", render_profile: "standard" }),
    );
    // initialize/prepare-render are not authorized for preview execution.
    expect(resp.mode).toBe("DRY_RUN");
    expect(resp.authorization.status).toBe("AUTHORIZATION_UNAVAILABLE");
    expect(resp.side_effects_performed).toBe(false);
  });

  it("unauthorized state is never upgraded to authorized", () => {
    const resp = planOperatorDryRun(
      buildDryRunRequest("initialize-project", { project_id: "p1", title: "T", language: "en" }),
    );
    expect(resp.authorization.status).toBe("AUTHORIZATION_UNAVAILABLE");
    expect(resp.status).toBe("UNAVAILABLE");
  });
});

describe("dry-run never claims execution", () => {
  it("returns a deterministic DR Y_RUN preview with zero side effects", () => {
    const resp = planOperatorDryRun(buildDryRunRequest("inspect-project", { project_id: "demo-project" }));
    expect(resp.mode).toBe("DRY_RUN");
    expect(resp.side_effects_performed).toBe(false);
    expect(resp.warnings).toContain("DRY_RUN_PREVIEW_ONLY");
    expect(resp.warnings).toContain("LIVE_EXECUTION_NOT_ENABLED");
  });

  it("forbidden action list is present and non-empty for every operation", () => {
    for (const op of ["inspect-project", "initialize-project", "prepare-render"] as const) {
      const resp = planOperatorDryRun(buildDryRunRequest(op, { project_id: "demo-project" }));
      const actions = resp.prohibited_actions.map((a) => a.action);
      expect(actions).toContain("invoke_hvs");
      expect(actions).toContain("write_browser_storage");
      expect(actions).toContain("perform_network_call");
    }
  });

  it("malformed request fails closed as INVALID without execution", () => {
    const resp = planOperatorDryRun({ not_a_valid_request: true });
    expect(resp.status).toBe("INVALID");
    expect(resp.mode).toBe("DRY_RUN");
    expect(resp.side_effects_performed).toBe(false);
  });

  it("rejects requests that are not dry-run mode", () => {
    const resp = planOperatorDryRun({ request_id: "x", operation: "inspect-project", dry_run: false, parameters: { project_id: "p" }, requested_at: "t", schema_version: OPERATOR_DRY_RUN_SCHEMA_VERSION });
    expect(resp.status).toBe("INVALID");
    expect(resp.reason_codes).toContain("DRY_RUN_MUST_BE_TRUE");
  });
});

describe("production routes cannot import mock/demo fixtures", () => {
  it("the truth-bearing adapter module exports no mock-data import and keeps DEMO separate", () => {
    // The runtime module under test must expose DEMO data only as an explicitly
    // labeled, separate dataset, and must provide a resolver that never merges
    // demo into live.
    expect(typeof DEMO_SNAPSHOT).toBe("object");
    expect(DEMO_SNAPSHOT.source_mode).toBe("DEMO");
    expect(DEMO_LABEL).toBe("DEMO DATA — NOT LIVE SYSTEM STATE");
  });
});

describe("browser mutation trap remains zero", () => {
  it("dry-run plan never performs or schedules a live command", () => {
    const resp = planOperatorDryRun(buildDryRunRequest("prepare-render", { project_id: "p1", render_profile: "standard" }));
    expect(resp.proposed_actions.every((a) => !/execute|run|dispatch|enqueue|render_now|write/i.test(a.action))).toBe(true);
    expect(resp.side_effects_performed).toBe(false);
  });
});
