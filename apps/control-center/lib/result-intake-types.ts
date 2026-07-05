// SCOS Control Center - Stage 5.7 AI Result Intake & ChatGPT Status Update
// Loop types. Static frontend mirror only. No backend calls, persistence,
// AI dispatch, clipboard, or network behavior is implemented here.

export type SourceAgent = "chatgpt" | "claude_code" | "codex" | "hermes" | "operator";

export type ResultVerdict =
  | "PASS"
  | "FAIL"
  | "BLOCKED"
  | "NEEDS_FIX"
  | "NEEDS_REVIEW"
  | "PARTIAL"
  | "UNKNOWN";

export type ResultConfidence = "low" | "medium" | "high";

export type IntakeStatus =
  | "drafted"
  | "intake_recorded"
  | "normalized"
  | "review_required"
  | "ready_for_chatgpt_update"
  | "sent_to_chatgpt_packet_ready"
  | "project_state_updated"
  | "next_action_ready"
  | "blocked";

export type ArtifactType =
  | "implementation_report"
  | "review_report"
  | "audit_report"
  | "test_report"
  | "changed_files"
  | "command_output"
  | "git_status"
  | "build_result"
  | "lint_result"
  | "screenshot_note"
  | "operator_note"
  | "unknown";

export type RequestedChatGPTAction =
  | "summarize_status"
  | "decide_next_action"
  | "update_stage_plan"
  | "prepare_review_prompt"
  | "prepare_fix_prompt"
  | "prepare_commit_recommendation"
  | "mark_blocked"
  | "request_operator_decision";

export type TaskStatus =
  | "planning"
  | "implementation_done"
  | "review_required"
  | "needs_fix"
  | "blocked"
  | "approved"
  | "ready_for_commit"
  | "done";

export type StageStatus =
  | "active"
  | "blocked"
  | "needs_review"
  | "ready_for_next_stage"
  | "complete";

export type RecommendedNextAction =
  | "send_to_chatgpt_status_update"
  | "send_to_claude_fix"
  | "send_to_codex_review"
  | "send_to_hermes_audit"
  | "request_operator_review"
  | "prepare_commit_gate"
  | "mark_stage_complete"
  | "hold_blocked"
  | "no_action";

export type NextActionPriority = "low" | "normal" | "high" | "urgent";

export interface ResultIntakeArtifactView {
  artifactId: string;
  artifactType: ArtifactType;
  title: string;
  path: string | null;
  summary: string;
  required: boolean;
}

export interface AIResultIntakeRecordView {
  intakeId: string;
  sessionId: string;
  taskId: string;
  sourceAgent: SourceAgent;
  sourceRuntimeId: string;
  title: string;
  normalizedSummary: string;
  verdict: ResultVerdict;
  confidence: ResultConfidence;
  artifacts: readonly ResultIntakeArtifactView[];
  blockers: readonly string[];
  warnings: readonly string[];
  testsSummary: string;
  changedFilesSummary: string;
  operatorReviewRequired: boolean;
  createdAt: string;
  status: IntakeStatus;
}

export interface ChatGPTStatusUpdatePacketView {
  updatePacketId: string;
  intakeId: string;
  sessionId: string;
  taskId: string;
  targetRuntimeId: string;
  title: string;
  statusUpdateBody: string;
  resultVerdict: ResultVerdict;
  resultSummary: string;
  evidenceRefs: readonly string[];
  requestedChatGPTAction: RequestedChatGPTAction;
  createdAt: string;
  status: IntakeStatus;
}

export interface ProjectStateUpdateView {
  stateUpdateId: string;
  intakeId: string;
  sessionId: string;
  taskId: string;
  previousStage: string;
  currentStage: string;
  taskStatus: TaskStatus;
  stageStatus: StageStatus;
  latestAgent: SourceAgent;
  latestVerdict: ResultVerdict;
  summary: string;
  updatedAt: string;
  evidenceRefs: readonly string[];
}

export interface NextActionDecisionView {
  nextActionId: string;
  intakeId: string;
  sessionId: string;
  taskId: string;
  recommendedAction: RecommendedNextAction;
  targetAgent: SourceAgent | null;
  targetRuntimeId: string | null;
  priority: NextActionPriority;
  reason: string;
  requiresOperatorApproval: boolean;
  createdAt: string;
}
