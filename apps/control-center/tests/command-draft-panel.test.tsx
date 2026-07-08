import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CommandDraftPanel } from "@/components/command-draft-panel";
import {
  COMMAND_DRAFTS,
  COMMAND_DRAFT_APPROVED,
  COMMAND_DRAFT_REJECTED,
} from "@/lib/command-mock-data";

// Stage 6.7 — command draft panel test.
// Covers render + validated (enabled) vs validation-failed (blocked) state,
// and the approval-gated "approval required before queueing" contract.
describe("Command Draft panel", () => {
  it("renders the panel heading", () => {
    render(<CommandDraftPanel drafts={COMMAND_DRAFTS} />);
    expect(screen.getByText("Command Drafts")).toBeInTheDocument();
  });

  it("shows VALIDATED for an approved draft and requires operator approval", () => {
    render(<CommandDraftPanel drafts={[COMMAND_DRAFT_APPROVED]} />);
    expect(screen.getByText("VALIDATED")).toBeInTheDocument();
    expect(
      screen.getByText(/approval required before queueing/i),
    ).toBeInTheDocument();
  });

  it("shows VALIDATION FAILED for a rejected draft with its error", () => {
    render(<CommandDraftPanel drafts={[COMMAND_DRAFT_REJECTED]} />);
    expect(screen.getByText("VALIDATION FAILED")).toBeInTheDocument();
    expect(screen.getByText(/unknown command_type/i)).toBeInTheDocument();
  });

  it("renders both a valid and an invalid draft in one panel", () => {
    render(
      <CommandDraftPanel
        drafts={[COMMAND_DRAFT_APPROVED, COMMAND_DRAFT_REJECTED]}
      />,
    );
    expect(screen.getByText("VALIDATED")).toBeInTheDocument();
    expect(screen.getByText("VALIDATION FAILED")).toBeInTheDocument();
  });
});
