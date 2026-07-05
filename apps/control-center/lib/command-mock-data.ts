// SCOS Control Center — Stage 5.1 command bridge mock data.
// Static, deterministic display data only. Nothing here is executed and
// nothing is generated at runtime (no Date.now / Math.random / randomUUID);
// ids and timestamps are fixed literals shaped like the Python bridge output.

import type {
  CommandDraftView,
  CommandEventView,
  OperatorApprovalView,
} from "./command-types";

/** A valid draft that passed validate_command_draft and was approved. */
export const COMMAND_DRAFT_APPROVED: CommandDraftView = {
  commandId: "cmd-001",
  commandType: "RUN_SMOKE_CHECK",
  requestedBy: "operator-a",
  createdAt: "2026-07-05T10:00:00Z",
  summary: "Run the Tier 1 smoke check before starting Stage 5.1 review",
  args: [],
  metadata: [["origin", "control-center"]],
  validation: { verdict: "valid", errors: [] },
};

/** An invalid draft: unknown command type, rejected by the operator. */
export const COMMAND_DRAFT_REJECTED: CommandDraftView = {
  commandId: "cmd-002",
  commandType: "RUN_FULL_PIPELINE",
  requestedBy: "operator-a",
  createdAt: "2026-07-05T10:02:00Z",
  summary: "Run the whole pipeline end to end",
  args: [],
  metadata: [],
  validation: {
    verdict: "invalid",
    errors: ["unknown command_type: 'RUN_FULL_PIPELINE'"],
  },
};

export const COMMAND_DRAFTS: readonly CommandDraftView[] = [
  COMMAND_DRAFT_APPROVED,
  COMMAND_DRAFT_REJECTED,
];

export const OPERATOR_APPROVALS: readonly OperatorApprovalView[] = [
  {
    approvalId: "apr-4f2c9d1a7b3e5081",
    commandId: "cmd-001",
    approved: true,
    approvedBy: "operator-a",
    approvedAt: "2026-07-05T10:05:00Z",
    reason: "Allowlisted local check; validation clean; safe to queue.",
  },
  {
    approvalId: "apr-8e6b0c3d5a19f742",
    commandId: "cmd-002",
    approved: false,
    approvedBy: "operator-a",
    approvedAt: "2026-07-05T10:06:00Z",
    reason: "Unknown command type — not on the Stage 5.1 allowlist.",
  },
];

export const COMMAND_EVENTS: readonly CommandEventView[] = [
  {
    eventId: "evt-1a2b3c4d5e6f7081",
    commandId: "cmd-001",
    eventType: "COMMAND_DRAFTED",
    createdAt: "2026-07-05T10:00:00Z",
    status: "pending",
    message: "Draft created by operator-a",
  },
  {
    eventId: "evt-2b3c4d5e6f708192",
    commandId: "cmd-001",
    eventType: "COMMAND_VALIDATED",
    createdAt: "2026-07-05T10:01:00Z",
    status: "success",
    message: "validate_command_draft: 0 errors",
  },
  {
    eventId: "evt-3c4d5e6f70819203",
    commandId: "cmd-002",
    eventType: "COMMAND_REJECTED",
    createdAt: "2026-07-05T10:06:00Z",
    status: "blocked",
    message: "unknown command_type: 'RUN_FULL_PIPELINE'",
  },
  {
    eventId: "evt-4d5e6f7081920314",
    commandId: "cmd-001",
    eventType: "COMMAND_APPROVED",
    createdAt: "2026-07-05T10:05:00Z",
    status: "success",
    message: "Approved by operator-a",
  },
  {
    eventId: "evt-5e6f708192031425",
    commandId: "cmd-001",
    eventType: "COMMAND_QUEUED",
    createdAt: "2026-07-05T10:07:00Z",
    status: "pending",
    message: "Appended to local JSONL queue",
  },
  {
    eventId: "evt-6f70819203142536",
    commandId: "cmd-001",
    eventType: "COMMAND_STARTED",
    createdAt: "2026-07-05T10:20:00Z",
    status: "pending",
    message: "RUN_SMOKE_CHECK started",
  },
  {
    eventId: "evt-7081920314253647",
    commandId: "cmd-001",
    eventType: "COMMAND_COMPLETED",
    createdAt: "2026-07-05T10:21:00Z",
    status: "success",
    message: "RUN_SMOKE_CHECK exit_code=0",
  },
];
