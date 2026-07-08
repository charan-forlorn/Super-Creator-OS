import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OperatorApprovalPanel } from "@/components/operator-approval-panel";
import { OPERATOR_APPROVALS } from "@/lib/command-mock-data";
import type { OperatorApprovalView } from "@/lib/command-types";

// Stage 6.7 — operator approval panel test.
// The panel renders approved (approved=true) and denied/rejected
// (approved=false) decisions; an empty list represents the pending /
// awaiting-operator state. All three are asserted at render level with no
// component rewrite and no backend import.

const APPROVED: OperatorApprovalView = {
  approvalId: "apr-test-approved",
  commandId: "cmd-001",
  approved: true,
  approvedBy: "operator-a",
  approvedAt: "2026-07-05T10:05:00Z",
  reason: "Allowlisted local check; validation clean; safe to queue.",
};

const DENIED: OperatorApprovalView = {
  approvalId: "apr-test-denied",
  commandId: "cmd-002",
  approved: false,
  approvedBy: "operator-a",
  approvedAt: "2026-07-05T10:06:00Z",
  reason: "Unknown command type — not on the allowlist.",
};

describe("Operator Approval panel", () => {
  it("renders the gate heading and the no-auto-approval notice", () => {
    render(<OperatorApprovalPanel approvals={OPERATOR_APPROVALS} />);
    expect(screen.getByText("Operator Approval Gate")).toBeInTheDocument();
    expect(screen.getByText(/no auto-approval/i)).toBeInTheDocument();
  });

  it("renders an APPROVED decision", () => {
    render(<OperatorApprovalPanel approvals={[APPROVED]} />);
    // Component renders the decision lowercase ("approved") and uppercases via CSS.
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText(/Allowlisted local check/i)).toBeInTheDocument();
  });

  it("renders a REJECTED decision (denied state)", () => {
    render(<OperatorApprovalPanel approvals={[DENIED]} />);
    expect(screen.getByText("rejected")).toBeInTheDocument();
  });

  it("renders the gate with no decisions (pending / awaiting operator)", () => {
    render(<OperatorApprovalPanel approvals={[]} />);
    expect(screen.getByText("Operator Approval Gate")).toBeInTheDocument();
    expect(
      screen.getByText(/no command executes without a granting approval/i),
    ).toBeInTheDocument();
  });
});
