// SCOS Control Center — Stage 5.2 AI Work Session Manager types.
// Frontend prototype only: these mirror the Python models in
// scos/control_center/work_session_models.py for static mock display.
// No backend contracts, no execution from the UI, no agent dispatch.

export type AgentName = "chatgpt" | "claude_code" | "codex" | "hermes";

export type RuntimeType =
  | "chatgpt_app"
  | "chatgpt_web"
  | "manual_clipboard"
  | "claude_code_cli"
  | "claude_code_vscode"
  | "codex_cli"
  | "codex_app"
  | "hermes_cli";

export type TaskType =
  | "planning"
  | "implementation"
  | "review"
  | "audit"
  | "status_update"
  | "prompt_build"
  | "result_summary"
  | "release_gate"
  | "manual_handoff";

export type TaskPriority = "low" | "normal" | "high" | "urgent";

export type WorkSessionStatus =
  | "draft"
  | "queued"
  | "assigned"
  | "waiting_for_operator"
  | "sent_to_agent"
  | "agent_working"
  | "result_ready"
  | "review_required"
  | "needs_fix"
  | "approved"
  | "blocked"
  | "cancelled"
  | "done";

/** [key, value] string pair, mirroring the Python tuple-of-pairs shape. */
export type StringPair = readonly [string, string];

export interface AgentRuntimeView {
  runtimeId: string;
  agentName: AgentName;
  runtimeType: RuntimeType;
  displayName: string;
  supportedTaskTypes: readonly TaskType[];
  enabled: boolean;
}

export interface AIWorkTaskView {
  taskId: string;
  title: string;
  taskType: TaskType;
  objective: string;
  inputSummary: string;
  sourceStage: string;
  priority: TaskPriority;
}

export interface AgentAssignmentView {
  assignmentId: string;
  taskId: string;
  agentName: AgentName;
  runtimeId: string;
  reason: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  assignedAt: string;
}

export interface AIWorkSessionView {
  sessionId: string;
  task: AIWorkTaskView;
  assignment: AgentAssignmentView | null;
  status: WorkSessionStatus;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  updatedAt: string;
  resultSummary: string | null;
  nextAction: string | null;
}
