import { act } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PaidPilotIntakeWizard } from "@/components/paid-pilot-intake-wizard";
import * as client from "@/lib/paid-pilot-intake-client";
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
    expect(screen.getByText(/Customer notification/i)).toBeTruthy();
    expect(screen.getAllByText(/NOT AUTHORIZED|Not authorized/i).length).toBeGreaterThan(0);
  });

  it("blocks create while missing consent, then creates after authoritative READY_TO_CREATE", async () => {
    vi.spyOn(client, "getIntakeDraft").mockResolvedValue({ ok: false, error_code: "DRAFT_NOT_FOUND", detail: null, draft: null });
    vi.spyOn(client, "createIntakeDraft").mockResolvedValue({ ok: true, error_code: null, detail: null, draft: draft() });
    vi.spyOn(client, "refreshAssetInventory").mockResolvedValue({
      ok: true,
      error_code: null,
      detail: null,
      draft: draft("NEEDS_INPUT", {
        asset_references: [
          {
            asset_id: "a",
            safe_name: "x.png",
            sha256: "a".repeat(64),
            size_bytes: 2,
            status: "Ready",
            rights_required: true,
            safe_reference: "x.png",
          },
        ],
      }),
    });
    vi.spyOn(client, "attachConsentEvidence").mockResolvedValue({
      ok: true,
      error_code: null,
      detail: null,
      draft: draft("READY_TO_CREATE", {
        validation_findings: [],
        asset_references: [
          {
            asset_id: "a",
            safe_name: "x.png",
            sha256: "a".repeat(64),
            size_bytes: 2,
            status: "Ready",
            rights_required: true,
            safe_reference: "x.png",
          },
        ],
        consent_state: "CONSENT_CONFIRMED",
        explicit_consent_confirmed: true,
        consent_evidence_sha256: "b".repeat(64),
      }),
    });
    vi.spyOn(client, "createPilotFromDraft").mockResolvedValue({
      ok: true,
      error_code: null,
      detail: null,
      pilot_safe_id: "pilot-1",
      project_safe_id: "project-1",
      admission_packet_sha256: "c".repeat(64),
      draft: draft("CREATED", { validation_findings: [], admission_packet_sha256: "c".repeat(64) }),
    });

    render(<PaidPilotIntakeWizard />);
    await click(/Create guided draft/i);
    await waitFor(() => expect(screen.getByText(/Consent evidence is missing/i)).toBeTruthy());
    expect(screen.getByRole("button", { name: /Create Pilot/i })).toBeDisabled();

    await click(/Refresh asset inventory/i);
    await click(/Generate consent message/i);
    await act(async () => {
      fireEvent.click(screen.getByRole("checkbox", { name: /Confirm explicit consent/i }));
    });
    await click(/Attach redacted consent evidence/i);
    await waitFor(() => expect(screen.getByRole("button", { name: /Create Pilot/i })).not.toBeDisabled());

    await click(/Create Pilot/i);
    await waitFor(() => expect(screen.getByRole("heading", { name: /Pilot created/i })).toBeTruthy());
    expect(screen.getByText(/Admission packet sealed/i)).toBeTruthy();
    expect(screen.getAllByText(/Technical evidence/i).length).toBeGreaterThan(0);
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

    await waitFor(() => expect(screen.getByRole("heading", { name: /Pilot created/i })).toBeTruthy());
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
