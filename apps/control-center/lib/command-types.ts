// SCOS Control Center — Stage 5.1 command bridge types.
// Frontend prototype only: these mirror the Python models in
// scos/control_center/command_models.py for static mock display.
// No backend contracts, no execution from the UI.

export type CommandType =
  | "RUN_SMOKE_CHECK"
  | "RUN_RELEASE_CHECK"
  | "RUN_SECURITY_SCAN"
  | "RUN_STAGE4_FINAL_GATE"
  | "OPEN_STAGE5_HANDOFF"
  | "GENERATE_STATUS_SNAPSHOT";

export type CommandEventType =
  | "COMMAND_DRAFTED"
  | "COMMAND_VALIDATED"
  | "COMMAND_REJECTED"
  | "COMMAND_APPROVED"
  | "COMMAND_QUEUED"
  | "COMMAND_STARTED"
  | "COMMAND_COMPLETED"
  | "COMMAND_FAILED"
  | "COMMAND_BLOCKED";

export type CommandEventStatus =
  | "success"
  | "failure"
  | "skipped"
  | "blocked"
  | "pending";

export type CommandValidationVerdict = "valid" | "invalid";

/** [key, value] string pair, mirroring the Python tuple-of-pairs shape. */
export type StringPair = readonly [string, string];

export interface CommandDraftView {
  commandId: string;
  commandType: CommandType | string;
  requestedBy: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  summary: string;
  args: readonly StringPair[];
  metadata: readonly StringPair[];
  /** Result of validate_command_draft for this mock draft. */
  validation: {
    verdict: CommandValidationVerdict;
    errors: readonly string[];
  };
}

export interface OperatorApprovalView {
  approvalId: string;
  commandId: string;
  approved: boolean;
  approvedBy: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  approvedAt: string;
  reason: string;
}

export interface CommandEventView {
  eventId: string;
  commandId: string;
  eventType: CommandEventType;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  status: CommandEventStatus;
  message: string;
}
