import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

const LIVE_PAYLOAD = {
  schema_version: 1,
  snapshot_id: "ccs-test",
  generated_at: "2026-07-16T01:02:03Z",
  source_mode: "LIVE_LOCAL_READ_ONLY",
  health: { available: true, status: "AVAILABLE_WITH_DATA", data: { health_status: "healthy", artifact_count: 1, event_count: 0, command_record_count: 0, audit_record_count: 0, warning_count: 0, blocker_count: 0, source_coverage: [] }, reason_code: null, observed_at: "2026-07-16T01:02:03Z" },
  queue_summary: { available: true, status: "AVAILABLE_EMPTY", data: { count: 0, items: [] }, reason_code: "READ_SOURCE_EMPTY", observed_at: "2026-07-16T01:02:03Z" },
  approval_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T01:02:03Z" },
  project_summary: { available: true, status: "AVAILABLE_WITH_DATA", data: { state_tables_present: ["projects"], has_dedicated_project_model: false }, reason_code: null, observed_at: "2026-07-16T01:02:03Z" },
  evidence_summary: { available: false, status: "UNAVAILABLE", data: null, reason_code: "READ_SOURCE_MISSING", observed_at: "2026-07-16T01:02:03Z" },
  recent_activity: { available: true, status: "AVAILABLE_WITH_DATA", data: { count: 1, items: [{ activity_id: "a1", activity_type: "CERT", status: "ok", summary: "certified", occurred_at: "2026-07-16T01:02:03Z" }] }, reason_code: null, observed_at: "2026-07-16T01:02:03Z" },
  degradation_reasons: ["READ_SOURCE_MISSING"],
};

describe("cockpit bridge behavior (mocked transport)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads live state via the read-only transport and shows source mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => LIVE_PAYLOAD,
      }),
    );
    render(<CockpitDashboard />);
    expect(await screen.findByText(/Live local read-only/i)).toBeInTheDocument();
    // Truthful observed-at timestamp from the live payload.
    expect(screen.getByText(/2026-07-16T01:02:03Z/)).toBeInTheDocument();
  });

  it("shows an error state on live transport failure and does NOT switch to demo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) }),
    );
    render(<CockpitDashboard />);
    expect(await screen.findByText(/Could not read live SCOS state|ไม่สามารถอ่านสถานะ SCOS สดได้/i)).toBeInTheDocument();
    // Demo must never be auto-activated on failure.
    expect(screen.queryByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).not.toBeInTheDocument();
  });

  it("explicitly switches to demo mode and shows the demo badge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => LIVE_PAYLOAD }),
    );
    render(<CockpitDashboard />);
    await screen.findByText(/Live local read-only/i);
    fireEvent.click(screen.getByRole("button", { name: /View demo data|ดูข้อมูลจำลอง/i }));
    expect(await screen.findAllByText(/DEMO DATA — NOT LIVE SYSTEM STATE/i)).toBeTruthy();
  });

  it("refresh re-reads the live transport without external egress", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => LIVE_PAYLOAD });
    vi.stubGlobal("fetch", fetchMock);
    render(<CockpitDashboard />);
    await screen.findByText(/Live local read-only/i);
    const callsBefore = fetchMock.mock.calls.length;
    // The cockpit's own refresh affordance is the Thai "เรียกข้อมูลใหม่"
    // control; target it specifically so the re-read assertion holds against
    // the snapshot route (the solo project preparation panel renders its own
    // separate "Refresh authoritative state" control).
    fireEvent.click(screen.getByRole("button", { name: /เรียกข้อมูลใหม่/i }));
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore));
    // Every fetch stays same-origin (no external egress). The dashboard refresh
    // re-reads /api/control-center-snapshot; the mounted solo project
    // preparation panel independently reads its own same-origin route, so we
    // assert local-only egress rather than a single hard-coded path.
    const urls = fetchMock.mock.calls.map((c) => c[0]);
    expect(urls.every((u) => typeof u === "string" && u.startsWith("/api/"))).toBe(true);
  });
});
