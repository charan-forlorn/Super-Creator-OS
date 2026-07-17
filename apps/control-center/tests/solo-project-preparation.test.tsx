import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SoloProjectPreparationPanel } from "@/components/solo-project-preparation-panel";
import {
  approvePreparationRequest,
  generatePreparationPreview,
  prepareProjectDraft,
  validateProjectDraft,
  type SoloProjectDraftInput,
} from "@/lib/solo-project-preparation";
import type {
  ProjectPreparationRecord,
  ProjectPreparationState,
  ReadEnvelope,
} from "@/lib/project-preparation-client";

const validDraft: SoloProjectDraftInput = {
  projectTitle: "Launch Reel",
  clientOrBrand: "Northstar Studio",
  projectPurpose: "Announce the new creator workflow",
  contentBrief: "A crisp launch video showing the operator cockpit, approval moment, and dry-run preparation preview.",
  targetDurationSeconds: 45,
  outputProfiles: ["vertical_9_16", "square_1_1"],
  operatorNotes: "Keep it energetic but truthful.",
};

// ---------------------------------------------------------------------------
// Preserved client-domain regression (Cohort 10B functions still exist).
// ---------------------------------------------------------------------------

describe("solo project preparation domain", () => {
  it("normalizes a valid draft and creates stable approval-required identity", () => {
    const first = prepareProjectDraft(validDraft);
    const second = prepareProjectDraft({ ...validDraft, projectTitle: "  Launch   Reel  " });

    expect(first.ok).toBe(true);
    expect(first.state).toBe("APPROVAL_REQUIRED");
    expect(first.project?.projectIdentity).toBe(second.project?.projectIdentity);
    expect(first.project?.plannedRenditionCount).toBe(2);
    expect(first.project?.outputProfiles.map((profile) => profile.id)).toEqual(["vertical_9_16", "square_1_1"]);
  });

  it("fails closed for required fields, duration, profiles, identity, URLs, paths, and shell content", () => {
    const errors = validateProjectDraft({
      ...validDraft,
      projectTitle: "../bad",
      contentBrief: "Render this from https://example.com/source.mp4 && publish it",
      targetDurationSeconds: 601,
      outputProfiles: ["vertical_9_16", "vertical_9_16", "bad_profile"],
    } as SoloProjectDraftInput);

    expect(errors).toEqual([
      "BRIEF_LIVE_EXECUTION_REQUEST_UNSUPPORTED",
      "BRIEF_PATH_TRAVERSAL_UNSUPPORTED",
      "BRIEF_REMOTE_ASSET_UNSUPPORTED",
      "BRIEF_SHELL_COMMAND_UNSUPPORTED",
      "DURATION_OUT_OF_RANGE",
      "OUTPUT_PROFILE_DUPLICATE",
      "OUTPUT_PROFILE_UNSUPPORTED",
      "PROJECT_TITLE_MALFORMED",
      "TITLE_PATH_TRAVERSAL_UNSUPPORTED",
    ]);
  });

  it("does not issue a project identity for invalid drafts", () => {
    const result = prepareProjectDraft({ ...validDraft, projectTitle: "", contentBrief: "" });

    expect(result.ok).toBe(false);
    expect(result.state).toBe("VALIDATION_FAILED");
    expect(result.project).toBeNull();
    expect(result.errors).toEqual(["BRIEF_REQUIRED", "PROJECT_TITLE_REQUIRED"]);
  });

  it("requires exact approval before deterministic preparation preview", () => {
    const prepared = prepareProjectDraft(validDraft);
    const projectIdentity = prepared.project?.projectIdentity ?? "";

    const wrongApproval = approvePreparationRequest(prepared, "spp-000000000000");
    const approved = approvePreparationRequest(prepared, projectIdentity);
    const duplicateApproval = approvePreparationRequest(approved, projectIdentity);
    const preview = generatePreparationPreview(approved, projectIdentity);
    const repeatedPreview = generatePreparationPreview(preview, projectIdentity);
    const stalePreview = generatePreparationPreview(approved, "spp-111111111111");

    expect(wrongApproval.state).toBe("APPROVAL_REQUIRED");
    expect(wrongApproval.errors).toEqual(["APPROVAL_PROJECT_ID_MISMATCH"]);
    expect(approved.state).toBe("APPROVED");
    expect(duplicateApproval.approvalCount).toBe(1);
    expect(preview.state).toBe("PREPARATION_PREVIEW_READY");
    expect(repeatedPreview).toEqual(preview);
    expect(stalePreview.errors).toEqual(["PREVIEW_PROJECT_ID_MISMATCH"]);
    expect(preview.preview).toMatchObject({
      side_effects_performed: false,
      render_started: false,
      hvs_project_created: false,
      approval_status: "approved",
      planned_rendition_count: 2,
    });
  });

  it("rejects approval and preview for unknown, malformed, or unapproved identities", () => {
    const emptyApproval = approvePreparationRequest(prepareProjectDraft({ ...validDraft, projectTitle: "" }), "spp-abc");
    const prepared = prepareProjectDraft(validDraft);
    const beforeApproval = generatePreparationPreview(prepared, prepared.project?.projectIdentity ?? "");
    const malformed = approvePreparationRequest(prepared, "../bad");

    expect(emptyApproval.errors).toContain("APPROVAL_REQUIRES_VALIDATED_DRAFT");
    expect(beforeApproval.errors).toEqual(["PREVIEW_REQUIRES_APPROVAL"]);
    expect(malformed.errors).toEqual(["APPROVAL_PROJECT_ID_MALFORMED"]);
  });
});

// ---------------------------------------------------------------------------
// Cohort 10C — authoritative client transport + truth-state UI behavior.
// The panel now reads from the same-origin authorative API and never trusts
// browser storage. We mock fetch to a controllable same-origin handler and
// assert the five truth states resolve without any demo fallback.
// ---------------------------------------------------------------------------

type FetchPlan = {
  read: () => unknown;
  create?: (body: unknown) => unknown;
  approve?: (body: unknown) => unknown;
  preview?: (body: unknown) => unknown;
};

// Single shared plan, mutated per-test, read by the fetch mock at call time.
let activePlan: FetchPlan = { read: () => EMPTY_STATUS };

beforeEach(() => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage read");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage write");
  });
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new Error("Unexpected browser storage remove");
  });
  vi.spyOn(Storage.prototype, "clear").mockImplementation(() => {
    throw new Error("Unexpected browser storage clear");
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: unknown) => {
      const url = String(input);
      // External egress must never happen.
      if (/^https?:\/\//i.test(url) || url.startsWith("//")) {
        throw new Error(`Unexpected external fetch: ${url}`);
      }
      const method = (init as { method?: string } | undefined)?.method ?? "GET";
      let payload: unknown = activePlan.read();
      if (url === "/api/project-preparation" && method === "POST") {
        payload = activePlan.create ? activePlan.create((init as { body?: string }).body) : activePlan.read();
      } else if (url.includes("/approve") && method === "POST") {
        payload = activePlan.approve ? activePlan.approve((init as { body?: string }).body) : activePlan.read();
      } else if (url.includes("/preview") && method === "POST") {
        payload = activePlan.preview ? activePlan.preview((init as { body?: string }).body) : activePlan.read();
      }
      return {
        ok: true,
        status: 200,
        json: async () => payload,
      };
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  activePlan = { read: () => EMPTY_STATUS };
});

function setPlan(plan: FetchPlan) {
  activePlan = plan;
}

const EMPTY_STATUS: ReadEnvelope = { status: "EMPTY", schema_version: 1, error_code: null, detail: null, records: [] };
const UNAVAILABLE_STATUS: ReadEnvelope = { status: "UNAVAILABLE", schema_version: 1, error_code: "READ_FAILED", detail: "boom", records: [] };
const CORRUPT_STATUS: ReadEnvelope = { status: "CORRUPT", schema_version: 1, error_code: "STORE_CORRUPT", detail: "malformed", records: [] };

function sampleRecord(state: ProjectPreparationState, revision: number): ProjectPreparationRecord {
  return {
    project_id: "spp-502e92236edd",
    schema_version: 1,
    revision,
    created_at: "2026-07-17T00:00:00Z",
    updated_at: "2026-07-17T00:00:00Z",
    state,
    normalized: {
      project_title: "Launch Reel",
      client_or_brand: "Northstar Studio",
      project_purpose: "Announce the new creator workflow",
      normalized_brief_summary: "A crisp launch video.",
      target_duration_seconds: 45,
      output_profiles: [{ id: "square_1_1", label: "square 1:1", aspectRatio: "1:1" }, { id: "vertical_9_16", label: "vertical 9:16", aspectRatio: "9:16" }],
      planned_rendition_count: 2,
      operator_notes: "Keep it energetic but truthful.",
    },
    approval: { status: "approved", approved_at: "2026-07-17T00:00:01Z", approval_count: 1, approved_by: "local-solo-operator" },
    preparation_preview:
      state === "PREPARATION_PREVIEW_READY"
        ? {
            schema_version: 1,
            project_identity: "spp-502e92236edd",
            project_title: "Launch Reel",
            client_or_brand: "Northstar Studio",
            normalized_brief_summary: "A crisp launch video.",
            selected_output_profiles: ["square_1_1", "vertical_9_16"],
            planned_rendition_count: 2,
            expected_preparation_stages: ["validate specification", "prepare script inputs"],
            approval_status: "approved",
          }
        : null,
    side_effect_flags: { side_effects_performed: false, render_started: false, hvs_project_created: false },
  };
}

describe("SoloProjectPreparationPanel — authoritative truth states", () => {
  it("shows loading then EMPTY (no demo record) when the store is empty", async () => {
    setPlan({ read: () => EMPTY_STATUS });
    render(<SoloProjectPreparationPanel />);
    expect(screen.getByText(/Reading authoritative local SCOS state/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Authoritative store · empty/i)).toBeInTheDocument());
    expect(screen.queryByText(/spp-/)).not.toBeInTheDocument();
  });

  it("represents UNAVAILABLE as unavailable (never as EMPTY, never fabricated)", async () => {
    setPlan({ read: () => UNAVAILABLE_STATUS });
    render(<SoloProjectPreparationPanel />);
    await waitFor(() =>
      expect(screen.getAllByText(/Authoritative store unavailable/i).length).toBeGreaterThan(0),
    );
    expect(screen.queryByText(/spp-/)).not.toBeInTheDocument();
  });

  it("represents CORRUPT without rewrite and disables transitions", async () => {
    setPlan({ read: () => CORRUPT_STATUS });
    render(<SoloProjectPreparationPanel />);
    await waitFor(() => expect(screen.getAllByText(/Authoritative store corrupt/i).length).toBeGreaterThan(0));
    expect(screen.getByRole("button", { name: /Validate and create draft/i })).toBeDisabled();
  });

  it("creates a draft through the authoritative API and shows approval-required", async () => {
    let store: ReadEnvelope = { ...EMPTY_STATUS };
    setPlan({
      read: () => store,
      create: () => {
        const rec = sampleRecord("APPROVAL_REQUIRED", 1);
        store = { status: "AVAILABLE_WITH_DATA", schema_version: 1, error_code: null, detail: null, records: [rec] };
        return { ok: true, error_code: null, detail: null, record: rec };
      },
    });
    render(<SoloProjectPreparationPanel />);
    await waitFor(() => expect(screen.getByText(/Authoritative store · empty/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: validDraft.projectTitle } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: validDraft.clientOrBrand } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: validDraft.projectPurpose } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: validDraft.contentBrief } });
    fireEvent.click(screen.getByRole("button", { name: /Validate and create draft/i }));
    await waitFor(() => expect(screen.getByText("APPROVAL_REQUIRED")).toBeInTheDocument());
    expect(screen.getByText("spp-502e92236edd")).toBeInTheDocument();
    expect(screen.getByText(/revision = 1/)).toBeInTheDocument();
  });

  it("approves and previews via the authoritative API, keeping side-effect flags false", async () => {
    let store = { status: "AVAILABLE_WITH_DATA", schema_version: 1, error_code: null, detail: null, records: [sampleRecord("APPROVAL_REQUIRED", 1)] };
    setPlan({
      read: () => store,
      approve: () => {
        const rec = sampleRecord("APPROVED", 2);
        store = { status: "AVAILABLE_WITH_DATA", schema_version: 1, error_code: null, detail: null, records: [rec] };
        return { ok: true, error_code: null, detail: null, record: rec };
      },
      preview: () => {
        const rec = sampleRecord("PREPARATION_PREVIEW_READY", 3);
        store = { status: "AVAILABLE_WITH_DATA", schema_version: 1, error_code: null, detail: null, records: [rec] };
        return { ok: true, error_code: null, detail: null, record: rec };
      },
    });
    render(<SoloProjectPreparationPanel />);
    await waitFor(() => expect(screen.getByText("APPROVAL_REQUIRED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Record local approval/i }));
    await waitFor(() => expect(screen.getByText("APPROVED")).toBeInTheDocument());
    expect(screen.getByText(/revision = 2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Generate dry-run preparation preview/i }));
    await waitFor(() => expect(screen.getByText("PREPARATION_PREVIEW_READY")).toBeInTheDocument());
    expect(screen.getByText("side_effects_performed = false")).toBeInTheDocument();
    expect(screen.getByText("render_started = false")).toBeInTheDocument();
    expect(screen.getByText("hvs_project_created = false")).toBeInTheDocument();
    expect(screen.getByText(/revision = 3/)).toBeInTheDocument();
  });

  it("never renders a demo or fabricated project when the store is empty", async () => {
    setPlan({ read: () => EMPTY_STATUS });
    render(<SoloProjectPreparationPanel />);
    await waitFor(() => expect(screen.getByText(/Authoritative store · empty/i)).toBeInTheDocument());
    expect(screen.queryByText("Launch Reel")).not.toBeInTheDocument();
    expect(screen.queryByText("PREPARATION_PREVIEW_READY")).not.toBeInTheDocument();
  });
});
