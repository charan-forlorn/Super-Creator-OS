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
