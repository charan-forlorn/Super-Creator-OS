import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { AppShell } from "@/components/app-shell";
import { SoloOperatorWorkflowPanel } from "@/components/solo-operator-workflow-panel";
import {
  approveSoloProjection,
  dispatchSoloProjection,
  initialSoloProjection,
  rejectSoloProjection,
} from "@/lib/solo-operator-workflow";

describe("solo operator workflow contract", () => {
  const request = {
    workflow: "video-production" as const,
    project_id: "demo-project",
    title: "Demo Project",
    language: "en" as const,
    render_profile: "vertical" as const,
    idempotency_key: "idem-1",
  };

  it("keeps command identity stable for duplicate submissions", () => {
    const first = initialSoloProjection(request);
    const second = initialSoloProjection(request);

    expect(first.command_id).toBe(second.command_id);
    expect(first.status).toBe("approval_required");
    expect(first.side_effects_performed).toBe(false);
  });

  it("requires approval before fake HVS dry-run dispatch", () => {
    const pending = initialSoloProjection(request);
    const blocked = dispatchSoloProjection(pending);
    const approved = approveSoloProjection(pending);
    const dispatched = dispatchSoloProjection(approved);
    const duplicate = dispatchSoloProjection(dispatched);

    expect(blocked.status).toBe("blocked");
    expect(blocked.errors).toContain("DISPATCH_REQUIRES_APPROVAL");
    expect(dispatched.status).toBe("dry_run_succeeded");
    expect(dispatched.safe_result_summary).toMatch(/no live render/i);
    expect(duplicate.result_count).toBe(1);
  });

  it("treats rejection as terminal", () => {
    const rejected = rejectSoloProjection(initialSoloProjection(request));
    const approvedAfterReject = approveSoloProjection(rejected);

    expect(rejected.status).toBe("rejected");
    expect(approvedAfterReject.status).toBe("rejected");
  });
});

describe("SoloOperatorWorkflowPanel", () => {
  it("renders validation, explicit approval, rejection, and dry-run dispatch controls", () => {
    render(<SoloOperatorWorkflowPanel />);

    expect(screen.getByRole("button", { name: "Submit request" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Dispatch dry run" })).toBeDisabled();
    expect(screen.getByText("approval_required")).toBeInTheDocument();
  });

  it("prevents invalid submission and shows validation before dispatch", () => {
    render(<SoloOperatorWorkflowPanel />);

    fireEvent.change(screen.getByLabelText("Cohort 10A project id"), { target: { value: "../bad" } });

    expect(screen.getByRole("alert")).toHaveTextContent("PROJECT_ID_UNSAFE");
    expect(screen.getByRole("button", { name: "Submit request" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Dispatch dry run" })).toBeDisabled();
  });

  it("runs the user-visible approval to fake dry-run result flow", () => {
    render(<SoloOperatorWorkflowPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Submit request" }));
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByText("approved")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dispatch dry run" }));

    expect(screen.getByText("dry_run_succeeded")).toBeInTheDocument();
    expect(screen.getByText(/Fake HVS dry-run succeeded/i)).toBeInTheDocument();
    expect(screen.getByText("side_effects_performed = false")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dispatch dry run" })).toBeDisabled();
  });

  it("keeps the panel wired into the main app shell", () => {
    render(<AppShell />);

    expect(screen.getByText("Solo Operator Workflow (Cohort 10A)")).toBeInTheDocument();
    expect(screen.getByText("Video-production request")).toBeInTheDocument();
  });
});
