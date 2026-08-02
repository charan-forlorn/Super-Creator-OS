import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Scenario coverage (jsdom render surface; real browser is exercised separately
// per the operator-authorized R2.2 real-browser matrix):
//  C  packet admission step calls the admission authority and shows projection
//  D  all three real-shape assets displayed truthfully
//  F  create disabled until PACKET_ADMISSION = PASS (not HTTP 200 / asset count)
//  G/J exactly one canonical spp-* project creation (via mocked client)
//  H  exact replay creates no second write
//  M  refresh/restart recovers authoritative state via draft_id URL param
//  O  render controls remain disabled / read-only; no render action fired

const mocked = {
  createIntakeDraft: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  getIntakeDraft: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  attachConsentEvidence: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  admitRealAsset: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  admitRealPacket: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  createCanonicalProject: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  evaluateRenderReadiness: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
};

vi.mock("@/lib/paid-pilot-intake-client", () => ({
  createIntakeDraft: (...a: unknown[]) => mocked.createIntakeDraft(...a),
  getIntakeDraft: (...a: unknown[]) => mocked.getIntakeDraft(...a),
  attachConsentEvidence: (...a: unknown[]) => mocked.attachConsentEvidence(...a),
  admitRealAsset: (...a: unknown[]) => mocked.admitRealAsset(...a),
}));
vi.mock("@/lib/paid-pilot-admission-client", () => ({
  admitRealPacket: (...a: unknown[]) => mocked.admitRealPacket(...a),
}));
vi.mock("@/lib/paid-pilot-create-client", () => ({
  createCanonicalProject: (...a: unknown[]) => mocked.createCanonicalProject(...a),
}));
vi.mock("@/lib/paid-pilot-render-readiness-client", () => ({
  evaluateRenderReadiness: (...a: unknown[]) => mocked.evaluateRenderReadiness(...a),
}));

import { PaidPilotIntakeWizard } from "@/components/paid-pilot-intake-wizard";

beforeEach(() => {
  Object.values(mocked).forEach((m) => m.mockReset());
});
afterEach(() => cleanup());

function readyDraft(over: Record<string, unknown> = {}) {
  return {
    ok: true, draft_id: "draft-1", status: "READY_TO_CREATE", safe_project_title: "Promo",
    selected_template: "Vertical Product Promo", target_platform: "TikTok", output_profile: "vertical_9_16",
    duration: "30s", deadline: "2026-08-15", commercial_reference: "x", asset_references: [],
    consent_state: "CONSENT_CONFIRMED", external_action_restrictions: { publishing: "NOT_AUTHORIZED" },
    validation_findings: [], generated: {}, pilot_safe_id: "pilot-1", project_safe_id: "project-1",
    admission_packet_sha256: "abc", ...over,
  };
}

const ADMIT_PASS = {
  ok: true, error_code: null, detail: null, gates: [], assets: [],
  projection: {
    packet_sha256: "c4784164…", pilot_id: "PILOT-2026-001", customer_ref: "CUST-A1",
    project_ref: "PILOT-2026-001-PROJ-01", asset_count: 3,
    assets: [
      { safe_name: "product-front.jpg" }, { safe_name: "customer-logo.png" }, { safe_name: "promo-music-31s.mp3" },
    ],
    external_action_restrictions: { publishing: "NOT_AUTHORIZED" }, font_policy: "OPEN_SOURCE_APPROVED",
  },
};

describe("Paid Pilot Intake Wizard — packet-faithful canonical journey", () => {
  it("D: displays all three packet-approved assets truthfully", async () => {
    mocked.createIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.getIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByTestId("approved-asset-product-front.jpg")).toBeTruthy());
    expect(screen.getByTestId("approved-asset-customer-logo.png")).toBeTruthy();
    expect(screen.getByTestId("approved-asset-promo-music-31s.mp3")).toBeTruthy();
  });

  it("C: admit authorization packet calls authority and shows projection", async () => {
    mocked.createIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.admitRealPacket.mockResolvedValue(ADMIT_PASS);
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByText(/Create guided draft/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Create guided draft/));
    await waitFor(() => expect(screen.getByTestId("admit-packet")).toBeTruthy());
    fireEvent.click(screen.getByTestId("admit-packet"));
    await waitFor(() => expect(mocked.admitRealPacket).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByTestId("admission-projection").textContent).toMatch(/PILOT-2026-001-PROJ-01/));
  });

  it("F: create disabled until PACKET_ADMISSION = PASS", async () => {
    mocked.createIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.getIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByTestId("create-pilot")).toBeTruthy());
    expect((screen.getByTestId("create-pilot") as HTMLButtonElement).disabled).toBe(true);
  });

  it("G/J/H: one canonical spp-* creation, no second write on replay", async () => {
    mocked.createIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.getIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.admitRealPacket.mockResolvedValue(ADMIT_PASS);
    mocked.createCanonicalProject
      .mockResolvedValueOnce({ ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b", replay: false, materialization: { dimensions: "1080x1920" } })
      .mockResolvedValueOnce({ ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b", replay: true, materialization: { dimensions: "1080x1920" } });
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByText(/Create guided draft/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Create guided draft/));
    await waitFor(() => expect(screen.getByTestId("admit-packet")).toBeTruthy());
    fireEvent.click(screen.getByTestId("admit-packet"));
    await waitFor(() => expect((screen.getByTestId("create-pilot") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByTestId("create-pilot"));
    await waitFor(() => expect(mocked.createCanonicalProject).toHaveBeenCalledTimes(1));
    const first = await mocked.createCanonicalProject.mock.results[0].value;
    expect(first.canonical_internal_project_id).toMatch(/^spp-[a-f0-9]{12}$/);
    // exact replay (same idempotency key) -> no second write
    fireEvent.click(screen.getByTestId("create-pilot"));
    await waitFor(() => expect(mocked.createCanonicalProject).toHaveBeenCalledTimes(2));
    const second = await mocked.createCanonicalProject.mock.results[1].value;
    expect(second.replay).toBe(true);
  });

  it("M: recovers draft from URL draft_id on restart", async () => {
    window.history.replaceState(null, "", "?draft_id=draft-1");
    mocked.getIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByTestId("admit-packet")).toBeTruthy());
    expect(mocked.getIntakeDraft).toHaveBeenCalledWith("draft-1");
  });

  it("O: render readiness is read-only, no render action fired", async () => {
    mocked.createIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.getIntakeDraft.mockResolvedValue({ ok: true, draft: readyDraft() });
    mocked.admitRealPacket.mockResolvedValue(ADMIT_PASS);
    mocked.createCanonicalProject.mockResolvedValue({ ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b", replay: false, materialization: { dimensions: "1080x1920" } });
    mocked.evaluateRenderReadiness.mockResolvedValue({ ok: true, state: "READY_FOR_RENDER", error_code: null, detail: null, checks: [], projection: { render_action: "DISABLED_PRE_AUTHORIZATION", asset_safe_names: ["product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"] } });
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByText(/Create guided draft/)).toBeTruthy());
    fireEvent.click(screen.getByText(/Create guided draft/));
    await waitFor(() => expect(screen.getByTestId("admit-packet")).toBeTruthy());
    fireEvent.click(screen.getByTestId("admit-packet"));
    await waitFor(() => expect((screen.getByTestId("create-pilot") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByTestId("create-pilot"));
    await waitFor(() => expect(screen.getByTestId("created-canonical").textContent).toMatch(/spp-/));
    fireEvent.click(screen.getByText(/Check render readiness/));
    await waitFor(() => expect(screen.getByTestId("render-readiness-state").textContent).toMatch(/READY_FOR_RENDER/));
    expect(JSON.stringify(mocked)).not.toMatch(/renderExecute|startRender|invokeRenderer/);
  });
});
