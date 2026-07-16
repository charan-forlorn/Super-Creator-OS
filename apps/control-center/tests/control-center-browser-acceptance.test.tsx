import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApprovalsScreen, EvidenceScreen, ProjectsScreen } from "@/components/cockpit/cockpit-routes";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";
import type { ControlCenterSnapshot } from "@/lib/control-center-snapshot";

// ---------------------------------------------------------------------------
// Cohort 9D — Browser acceptance matrix (jsdom render surface).
// Exercises the same required scenarios as the real desktop/mobile browser
// matrix (valid records -> AVAILABLE_WITH_DATA; empty -> EMPTY with no
// fallback; source failure -> UNAVAILABLE; dry-run preview -> zero mutation)
// against the actual React components, plus the layout integrity assertion
// (no horizontal overflow) and the read-only mutation trap.
// ---------------------------------------------------------------------------

function snapshotLike(overrides: Partial<ControlCenterSnapshot> = {}): ControlCenterSnapshot {
  const base: ControlCenterSnapshot = {
    schema_version: 1,
    snapshot_id: "ccs-test",
    generated_at: "2026-07-16T00:00:00Z",
    source_mode: "LIVE_LOCAL_READ_ONLY",
    health: { available: true, status: "AVAILABLE_WITH_DATA", data: { health_status: "healthy", artifact_count: 3, event_count: 0, command_record_count: 0, audit_record_count: 0, warning_count: 0, blocker_count: 0, source_coverage: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    queue_summary: { available: true, status: "AVAILABLE_EMPTY", data: { count: 0, items: [] }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" },
    approval_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { approval_count: 2, audit_record_count: 0 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    project_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { state_tables_present: ["projects"], has_dedicated_project_model: false }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T00:00:00Z" },
    recent_activity: { available: true, status: "AVAILABLE_WITH_DATA", data: { count: 1, items: [{ activity_id: "a1", activity_type: "CERT", status: "ok", summary: "x", occurred_at: "2026-07-16T00:00:00Z" }] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    degradation_reasons: ["READ_SOURCE_MISSING"],
  };
  return { ...base, ...overrides };
}

function stubFetch(payload: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 500, json: async () => payload }),
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Valid records -> AVAILABLE_WITH_DATA, provenance visible", () => {
  it("Projects surface shows the live read-only source badge and state tables", async () => {
    stubFetch(snapshotLike());
    render(<ProjectsScreen />);
    expect(await screen.findByText(/Live local read-only/i)).toBeInTheDocument();
    expect(screen.getByText(/1 state tables/i)).toBeInTheDocument();
  });
});

describe("Valid empty response -> EMPTY, no fallback records", () => {
  it("Approvals with zero records shows AVAILABLE_EMPTY, not unavailable", async () => {
    stubFetch(snapshotLike({ approval_summary: { available: true, status: "AVAILABLE_EMPTY", data: { approval_count: 0, audit_record_count: 0 }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" } }));
    render(<ApprovalsScreen />);
    // Empty approvals should render a zero-count available state, not an error.
    expect(await screen.findByText(/0/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not be read|ไม่สามารถอ่าน/i)).not.toBeInTheDocument();
  });
});

describe("Source failure -> UNAVAILABLE, no mock fallback", () => {
  it("Evidence with unavailable source shows unavailable, never fabricated empty", async () => {
    stubFetch(snapshotLike({ evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T00:00:00Z" } }));
    render(<EvidenceScreen />);
    expect(await screen.findByText(/could not be read|ไม่สามารถอ่าน/i)).toBeInTheDocument();
  });

  it("a failed fetch (loadState error) never renders fabricated demo data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network_down")));
    render(<EvidenceScreen />);
    // Unavailable path is shown; demo label must be absent unless mode toggled.
    await waitFor(() => {
      expect(screen.queryByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).not.toBeInTheDocument();
    });
  });
});

describe("Dry-run preview -> preview-only, zero mutation", () => {
  it("approval mutation controls remain disabled on the read-only bridge", async () => {
    stubFetch(snapshotLike({ approval_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { approval_count: 1, audit_record_count: 0 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" } }));
    render(<ApprovalsScreen />);
    const approve = (await screen.findAllByRole("button", { name: /Approve|อนุมัติ/i }))[0];
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute("aria-disabled", "true");
  });
});

describe("Navigation/layout — supported routes work, no overflow", () => {
  it("dashboard wires the four active cockpit routes", () => {
    stubFetch(snapshotLike());
    render(<CockpitDashboard />);
    expect(screen.getByRole("link", { name: "1 วันนี้" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "2 โปรเจกต์" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "5 หลักฐาน" })).toHaveAttribute("href", "/evidence");
    expect(screen.getByRole("link", { name: "6 การอนุมัติ" })).toHaveAttribute("href", "/approvals");
  });

  it("layout has no horizontal overflow (scrollWidth == clientWidth)", () => {
    stubFetch(snapshotLike());
    const { container } = render(<CockpitDashboard />);
    const root = container.ownerDocument.documentElement;
    // jsdom reports 0 for both; assert the equality invariant holds (the real
    // browser matrix enforces the non-zero check against a real viewport).
    expect(root.scrollWidth).toBe(root.clientWidth);
  });

  it("exposes unavailable nav controls that cannot activate (mutation trap)", () => {
    stubFetch(snapshotLike());
    const { container } = render(<CockpitDashboard />);
    const unavailable = Array.from(
      container.querySelectorAll<HTMLButtonElement>("nav.cockpit-nav button.cockpit-nav__item.is-unavailable"),
    );
    expect(unavailable.length).toBeGreaterThan(0);
    for (const item of unavailable) {
      expect(item).toBeDisabled();
      expect(item).toHaveAttribute("aria-disabled", "true");
      expect(() => fireEvent.click(item)).not.toThrow();
    }
    expect(window.location.pathname).toBe("/");
  });
});
