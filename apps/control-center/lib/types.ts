// SCOS Agent Control Center — shared domain types.
// Frontend prototype only: these describe static mock data, no backend contracts.

export type AgentId = "chatgpt" | "claude-code" | "codex" | "hermes";

export type AgentRole =
  | "Orchestrator"
  | "Builder"
  | "Reviewer / Verifier"
  | "Repo Health / Workflow Auditor";

export type AgentStatus = "active" | "idle" | "waiting" | "blocked";

export type TaskStatus =
  | "backlog"
  | "in-progress"
  | "blocked"
  | "in-review"
  | "approved"
  | "done";

export type MascotMood = "idle" | "working" | "blocked" | "approved" | "review";

export type Verdict = "PASS" | "FAIL";

export type MergeAction = "Approve" | "Request Fix" | "Reject" | "Hold";

export type WorkflowState =
  | "ready"
  | "working"
  | "waiting_result"
  | "needs_review"
  | "blocked"
  | "approved";

export type ResultRouteStatus = "PASS" | "FAIL" | "BLOCKED" | "NEEDS_REVIEW";

export type RiskLevel = "low" | "medium" | "high";

export interface Agent {
  id: AgentId;
  name: string;
  role: AgentRole;
  status: AgentStatus;
  /** One-line description of what this agent is doing right now. */
  activity: string;
  /** Id of the task this agent is currently attached to, if any. */
  currentTaskId: string | null;
  /** Short accent token used for theming (maps to a CSS class, not inline color). */
  accent: "emerald" | "violet" | "sky" | "amber";
}

export interface ChecklistItem {
  id: string;
  label: string;
  done: boolean;
}

export interface OperatorChecklistItem {
  id: string;
  label: string;
  done: boolean;
}

export interface Task {
  id: string;
  /** Human ticket code, e.g. "SCOS-412". */
  code: string;
  title: string;
  stage: string;
  status: TaskStatus;
  assignee: AgentId;
  priority: "low" | "medium" | "high";
  summary: string;
  /** Optional reason a task is blocked (only meaningful when status === "blocked"). */
  blockedReason?: string;
  checklist: ChecklistItem[];
  operatorChecklist: OperatorChecklistItem[];
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  updatedAt: string;
}

export interface NextAction {
  title: string;
  owner: AgentId;
  reason: string;
  sourceItem: string;
  urgency: "low" | "medium" | "high";
  recommendedAction: string;
}

export interface HandoffStep {
  id: string;
  name: string;
  role: string;
  state: WorkflowState;
  message: string;
}

export interface ResultRoute {
  status: ResultRouteStatus;
  label: string;
  destination: string;
  guidance: string;
}

export interface DecisionGuidance {
  recommendedDecision: MergeAction;
  reason: string;
  requiredEvidence: string;
  riskLevel: RiskLevel;
}

export interface TimelineEvent {
  id: string;
  /** Deterministic ISO-8601 timestamp. */
  at: string;
  agent: AgentId;
  taskId: string | null;
  message: string;
  kind: "info" | "success" | "warning" | "review";
}

export interface MergeItem {
  id: string;
  taskId: string;
  title: string;
  branch: string;
  author: AgentId;
  /** Codex verdict summary attached to the change set. */
  verdict: Verdict;
  additions: number;
  deletions: number;
  filesChanged: number;
  decisionGuidance: DecisionGuidance;
  submittedAt: string;
}

export interface ResultItem {
  id: string;
  taskId: string;
  title: string;
  producedBy: AgentId;
  verdict: Verdict;
  summary: string;
  /** e.g. "18/18 checks" or "2 failing gates". */
  metric: string;
  route: ResultRoute;
  at: string;
}

export interface Stage {
  id: string;
  label: string;
  status: "done" | "current" | "upcoming";
}

export interface StageProgress {
  /** The stage the operator is actively working on. */
  currentStageLabel: string;
  percentComplete: number;
  stages: Stage[];
}

// ── Live Work Updates (deterministic simulated realtime) ──
// Driven only by a fixed ordered event list + an index in React state.
// No clocks, no randomness, no network, no storage.

export type LiveAgentName = "ChatGPT" | "Claude Code" | "Codex" | "Hermes";

export type LiveEventType =
  | "next_action_generated"
  | "implementation_started"
  | "implementation_result_ready"
  | "review_requested"
  | "review_passed"
  | "review_failed"
  | "repo_warning"
  | "merge_queue_updated"
  | "operator_decision_required";

export type LiveSeverity = "info" | "success" | "warning" | "error";

export type LiveRoute =
  | "Prompt Builder"
  | "Result Inbox"
  | "Merge Queue"
  | "Task Detail";

export type AgentLiveState =
  | "idle"
  | "working"
  | "reviewing"
  | "blocked"
  | "result_ready"
  | "waiting_for_operator";

export interface LiveWorkEvent {
  id: string;
  /** Deterministic ISO-8601 timestamp — never generated at runtime. */
  timestamp: string;
  agent: LiveAgentName;
  taskId: string;
  eventType: LiveEventType;
  message: string;
  severity: LiveSeverity;
  /** UI area the operator should look at next. */
  route: LiveRoute;
}

export interface AgentLiveMeta {
  liveState: AgentLiveState;
  currentTaskId: string | null;
  /** e.g. "Started implementation · 11:12 UTC". */
  lastUpdateLabel: string;
  /** What the agent is waiting on, if anything. */
  waitingOn: string | null;
}

export interface TaskTransitionInfo {
  previousStatus: TaskStatus;
  currentStatus: TaskStatus;
  nextExpectedStatus: TaskStatus | null;
  latestEvent: LiveWorkEvent;
  responsibleAgent: LiveAgentName;
}

export type LiveBadge = "New" | "Needs Review" | "Fix Required" | "Ready to Merge";
