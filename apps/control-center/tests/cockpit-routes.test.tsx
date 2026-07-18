import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";
import { ApprovalsScreen, EvidenceScreen, ProjectsScreen } from "@/components/cockpit/cockpit-routes";

function defaultSnapshotLike() {
  return {
    schema_version: 1,
    snapshot_id: "ccs-test",
    generated_at: "2026-07-16T00:00:00Z",
    source_mode: "LIVE_LOCAL_READ_ONLY",
    health: { available: true, status: "AVAILABLE_WITH_DATA", data: { health_status: "healthy", artifact_count: 1, event_count: 0, command_record_count: 0, audit_record_count: 0, warning_count: 0, blocker_count: 0, source_coverage: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    queue_summary: { available: true, status: "AVAILABLE_EMPTY", data: { count: 0, items: [] }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T00:00:00Z" },
    approval_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { approval_count: 2, audit_record_count: 0 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    project_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { state_tables_present: ["projects"], has_dedicated_project_model: false }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    evidence_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { event_record_count: 0, audit_record_count: 8 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    recent_activity: { available: true, status: "AVAILABLE_WITH_DATA", data: { count: 0, items: [] }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
    degradation_reasons: [],
  };
}

describe("Cockpit V0.2 routes — truthful read-only bridge", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    // Provide a working read-only transport stub (jsdom has no fetch origin).
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => defaultSnapshotLike(),
      }),
    );
  });

  it("wires Today, Projects, Approvals, and Evidence to their App Router paths", () => {
    render(<CockpitDashboard />);
    expect(screen.getByRole("link", { name: "1 วันนี้" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "2 โปรเจกต์" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "5 หลักฐาน" })).toHaveAttribute("href", "/evidence");
    expect(screen.getByRole("link", { name: "6 การอนุมัติ" })).toHaveAttribute("href", "/approvals");
  });

  it("renders the Projects screen with the read-only bridge source badge", async () => {
    render(<ProjectsScreen />);
    expect(screen.getByText(/Live local read-only/i)).toBeInTheDocument();
    // Bridge label renders after the live snapshot resolves (also echoed in the
    // live note), so assert at least one occurrence.
    expect((await screen.findAllByText(/bridge|สะพาน/i)).length).toBeGreaterThan(0);
  });

  it("keeps approval mutation controls disabled (read-only bridge)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ...defaultSnapshotLike(),
          approval_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { approval_count: 2, audit_record_count: 0 }, reason_code: null, observed_at: "2026-07-16T00:00:00Z" },
        }),
      }),
    );
    render(<ApprovalsScreen />);
    const approve = (await screen.findAllByRole("button", { name: /Approve|อนุมัติ/i }))[0];
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute("aria-disabled", "true");
  });

  it("shows a truthful unavailable state for evidence when the source cannot be read", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          ...defaultSnapshotLike(),
          evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T00:00:00Z" },
        }),
      }),
    );
    render(<EvidenceScreen />);
    // When the evidence read surface genuinely cannot be read, the UI must
    // not claim "no evidence" as a zero count.
    expect(await screen.findByText(/could not be read|ไม่สามารถอ่าน/i)).toBeInTheDocument();
  });

  it("exposes Agents, Workflows, Activity, and Settings as unavailable controls that cannot activate", () => {
    const { container } = render(<CockpitDashboard />);
    const unavailable = Array.from(
      container.querySelectorAll<HTMLButtonElement>("nav.cockpit-nav button.cockpit-nav__item.is-unavailable"),
    );
    expect(unavailable.length).toBe(4);

    for (const item of unavailable) {
      expect(item).toBeDisabled();
      expect(item).toHaveAttribute("aria-disabled", "true");
      expect(() => fireEvent.click(item)).not.toThrow();
    }
    expect(window.location.pathname).toBe("/");
  });
});
