// SCOS Control Center - Stage 5.9 Local Operator Execution Console /
// Manual Command Runbook types. Static frontend mirror only. SCOS never
// executes a command here: no backend calls, no persistence, no git
// execution, no terminal, no clipboard, and no network behavior.

export type RunbookCommandType =
  | "git_status"
  | "git_diff"
  | "git_add"
  | "git_commit"
  | "git_fetch"
  | "git_push"
  | "test"
  | "build"
  | "lint"
  | "security_scan"
  | "verification"
  | "informational"
  | "unknown";

export type RunbookShell = "powershell" | "cmd" | "bash" | "python" | "manual";

export type RunbookRiskLevel = "low" | "medium" | "high" | "critical";

export type SafetyCheckStatus =
  | "pending"
  | "passed"
  | "failed"
  | "skipped"
  | "requires_review";

export type SafetyCheckSeverity = "info" | "warning" | "error" | "critical";

export type RunbookType =
  | "commit_runbook"
  | "push_runbook"
  | "verification_runbook"
  | "release_check_runbook"
  | "recovery_runbook"
  | "general_manual_command";

export type RunbookStatus =
  | "drafted"
  | "ready_for_operator"
  | "blocked"
  | "executed_manually"
  | "result_captured"
  | "verified"
  | "failed"
  | "archived";

export type CaptureVerdict =
  | "PASS"
  | "PASS_WITH_WARNINGS"
  | "NEEDS_REVIEW"
  | "NEEDS_FIX"
  | "BLOCKED"
  | "FAIL"
  | "UNKNOWN";

export type ExecutionOutcome =
  | "command_succeeded"
  | "command_succeeded_with_warnings"
  | "command_failed"
  | "command_blocked"
  | "command_needs_review"
  | "command_needs_fix"
  | "command_unknown";

export type NextAgent =
  | "chatgpt"
  | "claude_code"
  | "codex"
  | "hermes"
  | "operator";

export interface RunbookCommandStepView {
  stepId: string;
  stepOrder: number;
  title: string;
  command: string;
  commandType: RunbookCommandType;
  shell: RunbookShell;
  workingDirectory: string;
  requiresManualCopy: boolean;
  requiresOperatorConfirmation: boolean;
  expectedResultHint: string;
  riskLevel: RunbookRiskLevel;
}

export interface ExecutionSafetyCheckView {
  checkId: string;
  title: string;
  description: string;
  status: SafetyCheckStatus;
  severity: SafetyCheckSeverity;
  required: boolean;
  operatorInstruction: string;
}

export interface ManualCommandRunbookView {
  runbookId: string;
  sourceApprovalId: string | null;
  sourceCommitProposalId: string | null;
  sourcePushProposalId: string | null;
  sessionId: string;
  taskId: string;
  title: string;
  objective: string;
  commandSummary: string;
  runbookType: RunbookType;
  createdAt: string;
  status: RunbookStatus;
  safetyChecks: readonly ExecutionSafetyCheckView[];
  commandSteps: readonly RunbookCommandStepView[];
  expectedOutputs: readonly string[];
  blockedReasons: readonly string[];
  operatorNotes: readonly string[];
}

export interface CommandExecutionCaptureView {
  captureId: string;
  runbookId: string;
  sessionId: string;
  taskId: string;
  operatorReportedCommand: string;
  pastedOutputSummary: string;
  rawOutputExcerpt: string;
  exitStatusText: string;
  verdict: CaptureVerdict;
  capturedAt: string;
  evidencePaths: readonly string[];
  warnings: readonly string[];
  blockers: readonly string[];
}

export interface OperatorExecutionOutcomeView {
  outcomeId: string;
  runbookId: string;
  captureId: string;
  sessionId: string;
  taskId: string;
  outcome: ExecutionOutcome;
  summary: string;
  recommendedNextAction: string;
  recommendedNextAgent: NextAgent | null;
  operatorReviewRequired: boolean;
  createdAt: string;
}

// A console row binds one runbook to its (optional) capture + outcome so the
// UI can render the full lifecycle for one approved command.
export interface OperatorExecutionConsoleRow {
  runbook: ManualCommandRunbookView;
  capture: CommandExecutionCaptureView | null;
  outcome: OperatorExecutionOutcomeView | null;
}
