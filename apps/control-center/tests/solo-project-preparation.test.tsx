import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { SoloProjectPreparationPanel } from "@/components/solo-project-preparation-panel";
import {
  approvePreparationRequest,
  generatePreparationPreview,
  prepareProjectDraft,
  validateProjectDraft,
  type SoloProjectDraftInput,
} from "@/lib/solo-project-preparation";

const validDraft: SoloProjectDraftInput = {
  projectTitle: "Launch Reel",
  clientOrBrand: "Northstar Studio",
  projectPurpose: "Announce the new creator workflow",
  contentBrief: "A crisp launch video showing the operator cockpit, approval moment, and dry-run preparation preview.",
  targetDurationSeconds: 45,
  outputProfiles: ["vertical_9_16", "square_1_1"],
  operatorNotes: "Keep it energetic but truthful.",
};

function installBrowserSideEffectTraps() {
  const blocked = (name: string) =>
    vi.fn(() => {
      throw new Error(`Unexpected browser side effect: ${name}`);
    });

  beforeEach(() => {
    const xhrGlobal = ["XML", "Http", "Request"].join("");
    const socketGlobal = ["Web", "Socket"].join("");

    vi.stubGlobal("fetch", blocked("fetch"));
    vi.stubGlobal(
      xhrGlobal,
      vi.fn(() => {
        throw new Error(`Unexpected browser side effect: ${xhrGlobal}`);
      }),
    );
    vi.stubGlobal(
      socketGlobal,
      vi.fn(() => {
        throw new Error(`Unexpected browser side effect: ${socketGlobal}`);
      }),
    );
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(blocked("storage.getItem"));
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(blocked("storage.setItem"));
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(blocked("storage.removeItem"));
    vi.spyOn(Storage.prototype, "clear").mockImplementation(blocked("storage.clear"));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
}

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

describe("SoloProjectPreparationPanel", () => {
  installBrowserSideEffectTraps();

  it("labels runtime-only state truthfully and resets after remount", () => {
    const { unmount } = render(<SoloProjectPreparationPanel />);

    expect(screen.getByRole("region", { name: "Project draft and render-preparation preview" })).toBeInTheDocument();
    expect(screen.getByText("Runtime memory only")).toBeInTheDocument();
    expect(screen.getByText(/Refresh, remount, a fresh browser context, or server restart resets this draft/i)).toBeInTheDocument();
    expect(screen.queryByText(/Project initialized|Render started|Published|Uploaded/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: validDraft.projectTitle } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: validDraft.clientOrBrand } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: validDraft.projectPurpose } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: validDraft.contentBrief } });
    fireEvent.click(screen.getByRole("button", { name: "Validate project draft" }));
    expect(screen.getByText("APPROVAL_REQUIRED")).toBeInTheDocument();

    unmount();
    render(<SoloProjectPreparationPanel />);

    expect(screen.getByText("DRAFT")).toBeInTheDocument();
    expect(screen.getByText("No dry-run preview generated")).toBeInTheDocument();
  });

  it("runs validation, approval, and preview without browser side effects", () => {
    render(<SoloProjectPreparationPanel />);

    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: validDraft.projectTitle } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: validDraft.clientOrBrand } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: validDraft.projectPurpose } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: validDraft.contentBrief } });
    fireEvent.change(screen.getByLabelText("Target duration seconds"), { target: { value: "45" } });
    fireEvent.click(screen.getByLabelText("square 1:1"));

    fireEvent.click(screen.getByRole("button", { name: "Validate project draft" }));
    const identity = screen.getByTestId("preparation-project-identity").textContent ?? "";

    fireEvent.change(screen.getByLabelText("Approval project identity"), { target: { value: identity } });
    fireEvent.click(screen.getByRole("button", { name: "Record local approval" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate dry-run preparation preview" }));

    expect(screen.getByText("PREPARATION_PREVIEW_READY")).toBeInTheDocument();
    expect(screen.getByText("side_effects_performed = false")).toBeInTheDocument();
    expect(screen.getByText("render_started = false")).toBeInTheDocument();
    expect(screen.getByText("hvs_project_created = false")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Expected preparation stages")).getAllByRole("listitem")).toHaveLength(6);
  });

  it("contains duplicate approval, repeated preview, and mismatched identity", () => {
    render(<SoloProjectPreparationPanel />);

    fireEvent.change(screen.getByLabelText("Project title"), { target: { value: validDraft.projectTitle } });
    fireEvent.change(screen.getByLabelText("Client or brand"), { target: { value: validDraft.clientOrBrand } });
    fireEvent.change(screen.getByLabelText("Project purpose"), { target: { value: validDraft.projectPurpose } });
    fireEvent.change(screen.getByLabelText("Content brief"), { target: { value: validDraft.contentBrief } });
    fireEvent.click(screen.getByRole("button", { name: "Validate project draft" }));

    const identity = screen.getByTestId("preparation-project-identity").textContent ?? "";
    fireEvent.change(screen.getByLabelText("Approval project identity"), { target: { value: "spp-000000000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Record local approval" }));
    expect(screen.getByRole("alert")).toHaveTextContent("APPROVAL_PROJECT_ID_MISMATCH");

    fireEvent.change(screen.getByLabelText("Approval project identity"), { target: { value: identity } });
    fireEvent.click(screen.getByRole("button", { name: "Record local approval" }));
    fireEvent.click(screen.getByRole("button", { name: "Record local approval" }));
    expect(screen.getByText("approval_count = 1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Generate dry-run preparation preview" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate dry-run preparation preview" }));
    expect(screen.getByText("preview_count = 1")).toBeInTheDocument();
  });
});
