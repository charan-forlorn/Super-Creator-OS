import { act } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PaidPilotIntakeWizard } from "@/components/paid-pilot-intake-wizard";
import * as client from "@/lib/paid-pilot-intake-client";
import * as admissionClient from "@/lib/paid-pilot-admission-client";
import * as createClient from "@/lib/paid-pilot-create-client";
import * as readinessClient from "@/lib/paid-pilot-render-readiness-client";
import type { GuidedIntakeDraft, IntakeStatus } from "@/lib/paid-pilot-intake-types";

type DraftExtra = Partial<GuidedIntakeDraft>;

function draft(status: IntakeStatus = "NEEDS_INPUT", extra: DraftExtra = {}): GuidedIntakeDraft {
  return {
    schema_version: "v",
    draft_id: "draft-1",
    status,
    safe_project_title: "Synthetic Product Promo",
    selected_template: "Vertical Product Promo",
    target_platform: "TikTok",
    output_profile: "vertical_9_16",
    duration: "30s",
    deadline: "2026-08-15",
    commercial_reference: "synthetic",
    asset_references: [],
    consent_state: "CONSENT_NOT_CONFIRMED",
    consent_evidence_reference: "",
    consent_evidence_sha256: "",
    explicit_consent_confirmed: false,
    rights_answers: {
      asset_owner: "Owned",
      identifiable_person: "No",
      voice_used: "Not used",
      music_used: "Not used",
      font_policy: "Licensed",
    },
    privacy_answers: {
      health_data: "No",
      financial_data: "No",
      government_identifiers: "No",
      child_information: "No",
    },
    derived_classification: "STANDARD_COMMERCIAL",
    retention_policy:
      "Retain customer assets for 30 days after operator handoff, then require review before deletion or extended retention.",
    external_action_restrictions: {
      customer_notification: "NOT_AUTHORIZED",
      external_delivery: "NOT_AUTHORIZED",
      publishing: "NOT_AUTHORIZED",
      upload: "NOT_AUTHORIZED",
      deployment: "NOT_AUTHORIZED",
    },
    validation_findings: [
      {
        field: "consent_evidence",
        status: "Blocked",
        message: "Consent evidence is missing.",
        why_required: "Required",
        operator_action: "Attach evidence.",
        blocked_effect: "The Pilot will not be created.",
      },
    ],
    generated: {},
    created_at: "t",
    updated_at: "t",
    revision: 1,
    pilot_safe_id: "pilot-1",
    project_safe_id: "project-1",
    admission_packet_sha256: "",
    ...extra,
  };
}

async function click(name: RegExp) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
}

describe("PaidPilotIntakeWizard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("defaults to Quick Setup, collapses advanced, shows no YAML/JSON fields, and locks restrictions", () => {
    render(<PaidPilotIntakeWizard />);
    expect(screen.getByRole("button", { name: /Quick Setup/i }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /Advanced Setup/i }).getAttribute("aria-expanded")).toBe("false");
    expect(document.body.textContent).not.toMatch(/YAML|JSON schema|SHA-256.*input/i);
    // External-action restrictions are locked (not authorized) and surfaced truthfully.
    expect(screen.getByTestId("external-action-restrictions").textContent).toMatch(/not authorized/i);
  });

  it("disables Create until authoritative PACKET_ADMISSION = PASS (not READY_TO_CREATE alone), then creates canonical spp-* project", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue({ ok: false, error_code: "DRAFT_NOT_FOUND", detail: null, draft: null });
    vi.spyOn(client, "createIntakeDraft").mockResolvedValue({ ok: true, error_code: null, detail: null, draft: draft() });
    vi.spyOn(admissionClient, "admitRealPacket").mockResolvedValue({
      ok: true, error_code: null, detail: null, gates: [], assets: [],
      projection: {
        packet_sha256: "c4784164…", pilot_id: "PILOT-2026-001", customer_ref: "CUST-A1",
        project_ref: "PILOT-2026-001-PROJ-01", asset_count: 3,
        assets: [
          { safe_name: "product-front.jpg" }, { safe_name: "customer-logo.png" }, { safe_name: "promo-music-31s.mp3" },
        ],
        external_action_restrictions: { publishing: "NOT_AUTHORIZED" }, font_policy: "OPEN_SOURCE_APPROVED",
      },
    });
    const createMock = vi.spyOn(createClient, "createCanonicalProject");
    createMock
      .mockResolvedValueOnce({ ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b", pilot_safe_id: null, project_safe_id: null, external_project_ref: null, admission_packet_sha256: null, replay: false, materialization: { dimensions: "1080x1920" }, next_safe_action: null })
      .mockResolvedValueOnce({ ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b", pilot_safe_id: null, project_safe_id: null, external_project_ref: null, admission_packet_sha256: null, replay: true, materialization: { dimensions: "1080x1920" }, next_safe_action: null });

    render(<PaidPilotIntakeWizard />);
    await click(/Create guided draft/i);
    // Before admission, Create is disabled even though the draft exists.
    expect(screen.getByTestId("create-pilot")).toBeDisabled();

    // READY_TO_CREATE alone must NOT enable Create: attach consent to reach
    // READY_TO_CREATE, then assert Create remains disabled without admission.
    vi.spyOn(client, "attachConsentEvidence").mockResolvedValue({
      ok: true, error_code: null, detail: null,
      draft: draft("READY_TO_CREATE", { validation_findings: [], consent_state: "CONSENT_CONFIRMED", explicit_consent_confirmed: true }),
    });
    await click(/Generate consent message/i);
    await act(async () => { fireEvent.click(screen.getByRole("checkbox", { name: /Confirm explicit consent/i })); });
    await click(/Attach consent evidence/i);
    await waitFor(() => expect(screen.getByText(/Create disabled until PACKET_ADMISSION/i)).toBeTruthy());
    expect(screen.getByTestId("create-pilot")).toBeDisabled();
    expect(createMock).not.toHaveBeenCalled();

    // Successful authoritative admission enables Create.
    await click(/Admit authorization packet/i);
    await waitFor(() => expect(screen.getByTestId("admission-projection").textContent).toMatch(/PILOT-2026-001-PROJ-01/));
    expect(screen.getByTestId("create-pilot")).not.toBeDisabled();

    // Create action calls the canonical-create client with a browser-safe payload.
    await click(/Create Pilot/i);
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    const [key] = createMock.mock.calls[0];
    expect(typeof key).toBe("string");
    expect(key).not.toMatch(/[\\/]|C:\\\\|packet_path|hvs_projects_root/);
    const first = await createMock.mock.results[0].value;
    expect(first.canonical_internal_project_id).toMatch(/^spp-[a-f0-9]{12}$/);
    expect(screen.getByText(/Canonical project created: spp-3f9a1c2d4e5b/)).toBeTruthy();

    // Exact replay creates no duplicate (no render action anywhere).
    await click(/Create Pilot/i);
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(2));
    const second = await createMock.mock.results[1].value;
    expect(second.replay).toBe(true);
    expect(JSON.stringify(createMock.mock.calls)).not.toMatch(/packet_path|hvs_projects_root|C:\\\\\\\\/);
  });

  it("passes the admitted external project_ref to readiness, never the spp-* id (§7.1/§7.2)", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue({ ok: false, error_code: "DRAFT_NOT_FOUND", detail: null, draft: null });
    vi.spyOn(client, "createIntakeDraft").mockResolvedValue({ ok: true, error_code: null, detail: null, draft: draft() });
    vi.spyOn(admissionClient, "admitRealPacket").mockResolvedValue({
      ok: true, error_code: null, detail: null, gates: [], assets: [],
      projection: {
        packet_sha256: "c4784164…", pilot_id: "PILOT-2026-001", customer_ref: "CUST-A1",
        project_ref: "PILOT-2026-001-PROJ-01", asset_count: 3,
        assets: [{ safe_name: "product-front.jpg" }, { safe_name: "customer-logo.png" }, { safe_name: "promo-music-31s.mp3" }],
        external_action_restrictions: { publishing: "NOT_AUTHORIZED" }, font_policy: "OPEN_SOURCE_APPROVED",
      },
    });
    vi.spyOn(createClient, "createCanonicalProject").mockResolvedValue({
      ok: true, error_code: null, detail: null, canonical_internal_project_id: "spp-3f9a1c2d4e5b",
      pilot_safe_id: null, project_safe_id: null, external_project_ref: null, admission_packet_sha256: null,
      replay: false, materialization: { dimensions: "1080x1920" }, next_safe_action: null,
    });
    const readinessMock = vi.spyOn(readinessClient, "evaluateRenderReadiness");
    readinessMock.mockResolvedValue({ ok: true, state: "READY_FOR_RENDER", error_code: null, detail: null, checks: [], projection: { schema_version: "scos-hvs.pilot-render-readiness.v1/1.0.0", canonical_internal_project_id: "spp-3f9a1c2d4e5b", external_project_ref: "PILOT-2026-001-PROJ-01", output_profile: "vertical_9_16", dimensions: "1080x1920", duration_seconds: 30, audio_duration_seconds: 30.974943, font_family: "Noto Sans Thai", asset_safe_names: ["product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"], render_action: "DISABLED_PRE_AUTHORIZATION" } });

    render(<PaidPilotIntakeWizard />);
    await click(/Create guided draft/i);
    await click(/Admit authorization packet/i);
    await waitFor(() => expect(screen.getByTestId("admission-projection")).toBeTruthy());
    await click(/Create Pilot/i);
    await waitFor(() => expect(screen.getByTestId("created-canonical")).toBeTruthy());
    await click(/Check render readiness/i);
    await waitFor(() => expect(readinessMock).toHaveBeenCalledTimes(1));
    // Must pass the external project_ref, NOT the spp-* canonical id.
    expect(readinessMock.mock.calls[0][0]).toBe("PILOT-2026-001-PROJ-01");
    expect(readinessMock.mock.calls[0][0]).not.toMatch(/^spp-/);
  });

  it("does not use browser storage and hydrates CREATED state from an authoritative URL draft id", async () => {
    const storageRead = vi.spyOn(Storage.prototype, "getItem");
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");
    const sessionRead = vi.spyOn(window.sessionStorage, "getItem");
    const sessionWrite = vi.spyOn(window.sessionStorage, "setItem");
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue({
      ok: true,
      error_code: null,
      detail: null,
      draft: draft("CREATED", { validation_findings: [], admission_packet_sha256: "d".repeat(64) }),
    });
    window.history.replaceState(null, "", "/?draft_id=draft-1");

    render(<PaidPilotIntakeWizard />);

    await waitFor(() => expect(screen.getByRole("heading", { name: /Start New Pilot/i })).toBeTruthy());
    expect(screen.getByText(/CREATED/)).toBeTruthy();
    expect(client.getIntakeDraft).toHaveBeenCalledWith("draft-1");
    expect(storageRead).not.toHaveBeenCalled();
    expect(storageWrite).not.toHaveBeenCalled();
    expect(sessionRead).not.toHaveBeenCalled();
    expect(sessionWrite).not.toHaveBeenCalled();
  });

  it("keeps a truthful new state with missing identity and fails invalid identity safely", async () => {
    const getDraft = vi.spyOn(client, "getIntakeDraft").mockResolvedValue({ ok: false, error_code: "DRAFT_NOT_FOUND", detail: null, draft: null });
    const { unmount } = render(<PaidPilotIntakeWizard />);
    expect(getDraft).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Create Pilot/i })).toBeDisabled();
    unmount();

    window.history.replaceState(null, "", "/?draft_id=invalid-draft");
    render(<PaidPilotIntakeWizard />);
    await waitFor(() => expect(screen.getByText(/Draft identity not found/i)).toBeTruthy());
    expect(getDraft).toHaveBeenCalledWith("invalid-draft");
    expect(screen.queryByRole("heading", { name: /Pilot created/i })).toBeNull();
    expect(screen.getByRole("button", { name: /Create Pilot/i })).toBeDisabled();
  });

});
