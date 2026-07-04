// Deterministic "simulated realtime" engine for the Live Work Updates feature.
// A fixed, ordered event list is replayed up to an index held in React state.
// Pure module: no clocks, no randomness, no network, no storage, no side effects.

import { TASKS } from "./mock-data";
import type {
  AgentId,
  AgentLiveMeta,
  LiveAgentName,
  LiveBadge,
  LiveWorkEvent,
  TaskStatus,
  TaskTransitionInfo,
} from "./types";

export const AGENT_NAME_TO_ID: Record<LiveAgentName, AgentId> = {
  ChatGPT: "chatgpt",
  "Claude Code": "claude-code",
  Codex: "codex",
  Hermes: "hermes",
};

/**
 * Fixed simulation script. One coherent story:
 * SCOS-412 (task-06) runs the full build → review → merge-gate lifecycle,
 * with a Hermes repo-hygiene warning on SCOS-409 (task-04) mid-stream.
 * Timestamps are hardcoded and continue after the latest mock-data event (11:02Z).
 */
export const LIVE_EVENTS: LiveWorkEvent[] = [
  {
    id: "live-01",
    timestamp: "2026-07-04T11:08:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "next_action_generated",
    message: "ChatGPT generated the next action for SCOS-412: draft the delivery-log contract doc.",
    severity: "info",
    route: "Prompt Builder",
  },
  {
    id: "live-02",
    timestamp: "2026-07-04T11:12:00Z",
    agent: "Claude Code",
    taskId: "task-06",
    eventType: "implementation_started",
    message: "Claude Code started implementation of SCOS-412.",
    severity: "info",
    route: "Task Detail",
  },
  {
    id: "live-03",
    timestamp: "2026-07-04T11:18:00Z",
    agent: "Claude Code",
    taskId: "task-06",
    eventType: "implementation_result_ready",
    message: "Claude Code returned a result for SCOS-412 — draft ready for review.",
    severity: "success",
    route: "Result Inbox",
  },
  {
    id: "live-04",
    timestamp: "2026-07-04T11:20:00Z",
    agent: "Codex",
    taskId: "task-06",
    eventType: "review_requested",
    message: "Codex review requested for SCOS-412.",
    severity: "info",
    route: "Result Inbox",
  },
  {
    id: "live-05",
    timestamp: "2026-07-04T11:24:00Z",
    agent: "Codex",
    taskId: "task-06",
    eventType: "review_failed",
    message: "Codex returned FAIL on SCOS-412 — invariants section is missing two gates.",
    severity: "error",
    route: "Result Inbox",
  },
  {
    id: "live-06",
    timestamp: "2026-07-04T11:27:00Z",
    agent: "Hermes",
    taskId: "task-04",
    eventType: "repo_warning",
    message: "Hermes detected a repo hygiene warning on SCOS-409 — fixture handoff_sample.json still missing.",
    severity: "warning",
    route: "Task Detail",
  },
  {
    id: "live-07",
    timestamp: "2026-07-04T11:31:00Z",
    agent: "Claude Code",
    taskId: "task-06",
    eventType: "implementation_result_ready",
    message: "Claude Code returned a fixed result for SCOS-412 — missing gates added.",
    severity: "success",
    route: "Result Inbox",
  },
  {
    id: "live-08",
    timestamp: "2026-07-04T11:35:00Z",
    agent: "Codex",
    taskId: "task-06",
    eventType: "review_passed",
    message: "Codex returned PASS on SCOS-412 — all checks green.",
    severity: "success",
    route: "Merge Queue",
  },
  {
    id: "live-09",
    timestamp: "2026-07-04T11:37:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "merge_queue_updated",
    message: "Merge Queue updated — SCOS-412 queued for the operator gate.",
    severity: "info",
    route: "Merge Queue",
  },
  {
    id: "live-10",
    timestamp: "2026-07-04T11:40:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "operator_decision_required",
    message: "Operator decision required — approve or hold the SCOS-412 merge.",
    severity: "warning",
    route: "Merge Queue",
  },
  {
    id: "live-11",
    timestamp: "2026-07-04T11:44:00Z",
    agent: "Codex",
    taskId: "task-06",
    eventType: "review_passed",
    message: "Codex review returned PASS for the operator commit gate.",
    severity: "success",
    route: "Operator Review Gate",
  },
  {
    id: "live-12",
    timestamp: "2026-07-04T11:47:00Z",
    agent: "Hermes",
    taskId: "task-06",
    eventType: "changed_files_scope_validated",
    message: "Changed files scope validated â€” one forbidden Stage 4 path blocks commit.",
    severity: "warning",
    route: "Operator Review Gate",
  },
  {
    id: "live-13",
    timestamp: "2026-07-04T11:51:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "commit_checklist_completed",
    message: "Commit readiness checklist completed with HOLD verdict.",
    severity: "warning",
    route: "Operator Review Gate",
  },
  {
    id: "live-14",
    timestamp: "2026-07-04T11:55:00Z",
    agent: "Hermes",
    taskId: "task-06",
    eventType: "remote_safety_checked",
    message: "Remote safety check passed branch review, then blocked push on remote-only commits.",
    severity: "error",
    route: "Operator Review Gate",
  },
  {
    id: "live-15",
    timestamp: "2026-07-04T11:58:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "operator_decision_required",
    message: "Operator approval required for commit gate disposition.",
    severity: "warning",
    route: "Operator Review Gate",
  },
  {
    id: "live-16",
    timestamp: "2026-07-04T12:02:00Z",
    agent: "ChatGPT",
    taskId: "task-06",
    eventType: "push_decision_ready",
    message: "Push decision ready, but Approve Push remains blocked until remote safety is clean.",
    severity: "warning",
    route: "Operator Review Gate",
  },
];

/** "2026-07-04T11:12:00Z" → "11:12 UTC" (pure string slicing, no Date). */
function shortTime(iso: string): string {
  const timePart = iso.split("T")[1] ?? "";
  return `${timePart.slice(0, 5)} UTC`;
}

/** Baseline live metadata before any simulated event, mirroring the static AGENTS mock. */
const BASELINE_AGENT_LIVE: Record<AgentId, AgentLiveMeta> = {
  chatgpt: {
    liveState: "working",
    currentTaskId: "task-01",
    lastUpdateLabel: "Sequencing Stage 4.15 tasks",
    waitingOn: null,
  },
  "claude-code": {
    liveState: "working",
    currentTaskId: "task-02",
    lastUpdateLabel: "Implementing delivery log module",
    waitingOn: null,
  },
  codex: {
    liveState: "reviewing",
    currentTaskId: "task-03",
    lastUpdateLabel: "Verifying decision gate change set",
    waitingOn: null,
  },
  hermes: {
    liveState: "blocked",
    currentTaskId: "task-04",
    lastUpdateLabel: "Audit paused",
    waitingOn: "Fixture handoff_sample.json from the builder",
  },
};

/** What each event type means for the affected task's board status, if anything. */
const STATUS_EFFECT: Partial<
  Record<LiveWorkEvent["eventType"], { current: TaskStatus; next: TaskStatus | null }>
> = {
  implementation_started: { current: "in-progress", next: "in-review" },
  implementation_result_ready: { current: "in-review", next: "approved" },
  review_failed: { current: "in-progress", next: "in-review" },
};

/** Fallback next-expected status per event type when the status itself does not change. */
const NEXT_EXPECTED: Record<LiveWorkEvent["eventType"], TaskStatus | null> = {
  next_action_generated: "in-progress",
  implementation_started: "in-review",
  implementation_result_ready: "approved",
  review_requested: "approved",
  review_passed: "approved",
  review_failed: "in-review",
  repo_warning: "in-progress",
  merge_queue_updated: "approved",
  operator_decision_required: "approved",
  changed_files_scope_validated: "approved",
  commit_checklist_completed: "approved",
  remote_safety_checked: "approved",
  push_decision_ready: "approved",
};

export interface DerivedLiveState {
  /** Applied events, newest first. */
  feedEvents: LiveWorkEvent[];
  agentLive: Record<AgentId, AgentLiveMeta>;
  /** taskId → live board status override. */
  taskStatusOverrides: Record<string, TaskStatus>;
  /** taskId → latest transition info for the Task Detail panel. */
  transitionHistory: Record<string, TaskTransitionInfo>;
  inboxBadge: LiveBadge | null;
  mergeBadge: LiveBadge | null;
  orbitMessageOverride: string | null;
  recommendedActionOverride: string | null;
}

/**
 * Pure fold over LIVE_EVENTS.slice(0, eventIndex).
 * Same index in → same state out, always. Refresh resets the index to 0.
 */
export function deriveLiveState(eventIndex: number): DerivedLiveState {
  const applied = LIVE_EVENTS.slice(0, Math.max(0, Math.min(eventIndex, LIVE_EVENTS.length)));

  const agentLive: Record<AgentId, AgentLiveMeta> = {
    chatgpt: { ...BASELINE_AGENT_LIVE.chatgpt },
    "claude-code": { ...BASELINE_AGENT_LIVE["claude-code"] },
    codex: { ...BASELINE_AGENT_LIVE.codex },
    hermes: { ...BASELINE_AGENT_LIVE.hermes },
  };
  const taskStatusOverrides: Record<string, TaskStatus> = {};
  const transitionHistory: Record<string, TaskTransitionInfo> = {};
  let inboxBadge: LiveBadge | null = null;
  let mergeBadge: LiveBadge | null = null;
  let orbitMessageOverride: string | null = null;
  let recommendedActionOverride: string | null = null;

  const baseStatusOf = (taskId: string): TaskStatus =>
    TASKS.find((task) => task.id === taskId)?.status ?? "backlog";
  const currentStatusOf = (taskId: string): TaskStatus =>
    taskStatusOverrides[taskId] ?? baseStatusOf(taskId);

  for (const event of applied) {
    const actorId = AGENT_NAME_TO_ID[event.agent];
    const actor = agentLive[actorId];
    const assigneeId = TASKS.find((task) => task.id === event.taskId)?.assignee;

    // Every event stamps the acting agent's last-update label.
    actor.lastUpdateLabel = `${labelFor(event)} · ${shortTime(event.timestamp)}`;

    // Task status transition, when the event implies one.
    const previousStatus = currentStatusOf(event.taskId);
    const effect = STATUS_EFFECT[event.eventType];
    const currentStatus = effect ? effect.current : previousStatus;
    if (effect) taskStatusOverrides[event.taskId] = effect.current;
    transitionHistory[event.taskId] = {
      previousStatus,
      currentStatus,
      nextExpectedStatus: NEXT_EXPECTED[event.eventType],
      latestEvent: event,
      responsibleAgent: event.agent,
    };

    switch (event.eventType) {
      case "next_action_generated":
        actor.liveState = "working";
        actor.currentTaskId = event.taskId;
        break;
      case "implementation_started":
        actor.liveState = "working";
        actor.currentTaskId = event.taskId;
        actor.waitingOn = null;
        break;
      case "implementation_result_ready":
        actor.liveState = "result_ready";
        actor.currentTaskId = event.taskId;
        actor.waitingOn = "Codex review";
        inboxBadge = "New";
        break;
      case "review_requested":
        agentLive.codex.liveState = "reviewing";
        agentLive.codex.currentTaskId = event.taskId;
        inboxBadge = "Needs Review";
        break;
      case "review_passed":
        agentLive.codex.liveState = "idle";
        agentLive.codex.waitingOn = null;
        mergeBadge = "Ready to Merge";
        break;
      case "review_failed":
        inboxBadge = "Fix Required";
        // The builder picks the task back up for a fix pass.
        if (assigneeId) {
          agentLive[assigneeId].liveState = "working";
          agentLive[assigneeId].currentTaskId = event.taskId;
          agentLive[assigneeId].waitingOn = null;
        }
        break;
      case "repo_warning":
        agentLive.hermes.liveState = "waiting_for_operator";
        agentLive.hermes.currentTaskId = event.taskId;
        agentLive.hermes.waitingOn = "Operator ack of the hygiene warning";
        break;
      case "merge_queue_updated":
        mergeBadge = "Ready to Merge";
        break;
      case "operator_decision_required":
        actor.liveState = "waiting_for_operator";
        actor.waitingOn = "Operator merge decision";
        agentLive.codex.liveState = "waiting_for_operator";
        agentLive.codex.waitingOn = "Operator merge decision";
        orbitMessageOverride =
          "SCOS-412 passed review and is queued at the operator gate. The crew is waiting on your merge decision.";
        recommendedActionOverride =
          "Open Merge Queue, check the Decision Guidance evidence for SCOS-412, then Approve or Hold.";
        break;
      case "changed_files_scope_validated":
      case "commit_checklist_completed":
      case "remote_safety_checked":
      case "push_decision_ready":
        actor.liveState = "waiting_for_operator";
        actor.currentTaskId = event.taskId;
        actor.waitingOn = "Operator review gate decision";
        orbitMessageOverride =
          "The commit gate is under operator review. Do not commit or push from the UI.";
        recommendedActionOverride =
          "Use Operator Review Gate to inspect scope, evidence, commit plan, and remote safety before deciding.";
        break;
    }
  }

  return {
    feedEvents: [...applied].reverse(),
    agentLive,
    taskStatusOverrides,
    transitionHistory,
    inboxBadge,
    mergeBadge,
    orbitMessageOverride,
    recommendedActionOverride,
  };
}

/** Short verb phrase for agent-card footers. */
function labelFor(event: LiveWorkEvent): string {
  switch (event.eventType) {
    case "next_action_generated":
      return "Generated next action";
    case "implementation_started":
      return "Started implementation";
    case "implementation_result_ready":
      return "Returned result";
    case "review_requested":
      return "Review requested";
    case "review_passed":
      return "Returned PASS";
    case "review_failed":
      return "Returned FAIL";
    case "repo_warning":
      return "Raised repo warning";
    case "merge_queue_updated":
      return "Updated merge queue";
    case "operator_decision_required":
      return "Escalated to operator";
    case "changed_files_scope_validated":
      return "Validated file scope";
    case "commit_checklist_completed":
      return "Completed checklist";
    case "remote_safety_checked":
      return "Checked remote safety";
    case "push_decision_ready":
      return "Prepared push decision";
  }
}
