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
 * Fixed simulation script. One coherent story: current-state evidence lands,
 * v0.1.4 is committed/deployed, then the next Stage 4.17 and v0.1.5 planning
 * targets become ready.
 */
export const LIVE_EVENTS: LiveWorkEvent[] = [
  {
    id: "live-01",
    timestamp: "2026-07-04T11:44:00Z",
    agent: "Claude Code",
    taskId: "task-04",
    eventType: "implementation_result_ready",
    message: "SCOS-409 fixture handoff_sample.json added and pushed.",
    severity: "success",
    route: "Result Inbox",
  },
  {
    id: "live-02",
    timestamp: "2026-07-04T11:50:00Z",
    agent: "Hermes",
    taskId: "task-03",
    eventType: "review_passed",
    message: "Stage 4.16 completed and pushed.",
    severity: "success",
    route: "Task Detail",
  },
  {
    id: "live-03",
    timestamp: "2026-07-04T11:58:00Z",
    agent: "Codex",
    taskId: "task-05",
    eventType: "review_passed",
    message:
      "Control Center v0.1.4 committed as 798c88b feat(ui): add operator review and commit gate flow.",
    severity: "success",
    route: "Operator Review Gate",
  },
  {
    id: "live-04",
    timestamp: "2026-07-04T12:00:00Z",
    agent: "Claude Code",
    taskId: "task-05",
    eventType: "merge_queue_updated",
    message: "Control Center v0.1.4 deployed to Vercel.",
    severity: "success",
    route: "Merge Queue",
  },
  {
    id: "live-05",
    timestamp: "2026-07-04T12:14:00Z",
    agent: "ChatGPT",
    taskId: "task-02",
    eventType: "push_decision_ready",
    message: "Control Center v0.1.5 archive feature is ready for planning.",
    severity: "info",
    route: "Prompt Builder",
  },
  {
    id: "live-06",
    timestamp: "2026-07-04T12:16:00Z",
    agent: "ChatGPT",
    taskId: "task-01",
    eventType: "next_action_generated",
    message: "Stage 4.17 planning is ready for the conversion handoff.",
    severity: "info",
    route: "Prompt Builder",
  },
];

/** "2026-07-04T11:12:00Z" -> "11:12 UTC" (pure string slicing, no Date). */
function shortTime(iso: string): string {
  const timePart = iso.split("T")[1] ?? "";
  return `${timePart.slice(0, 5)} UTC`;
}

/** Baseline live metadata before any simulated event, mirroring the static AGENTS mock. */
const BASELINE_AGENT_LIVE: Record<AgentId, AgentLiveMeta> = {
  chatgpt: {
    liveState: "working",
    currentTaskId: "task-01",
    lastUpdateLabel: "Preparing Stage 4.17 plan",
    waitingOn: null,
  },
  "claude-code": {
    liveState: "idle",
    currentTaskId: "task-02",
    lastUpdateLabel: "Ready for v0.1.5 archive slice",
    waitingOn: null,
  },
  codex: {
    liveState: "idle",
    currentTaskId: "task-05",
    lastUpdateLabel: "v0.1.4 review evidence archived",
    waitingOn: null,
  },
  hermes: {
    liveState: "idle",
    currentTaskId: "task-03",
    lastUpdateLabel: "Repo health clear",
    waitingOn: null,
  },
};

/** What each event type means for the affected task's board status, if anything. */
const STATUS_EFFECT: Partial<
  Record<LiveWorkEvent["eventType"], { current: TaskStatus; next: TaskStatus | null }>
> = {
  implementation_started: { current: "in-progress", next: "in-review" },
  implementation_result_ready: { current: "done", next: null },
  review_passed: { current: "done", next: null },
  merge_queue_updated: { current: "done", next: null },
};

/** Fallback next-expected status per event type when the status itself does not change. */
const NEXT_EXPECTED: Record<LiveWorkEvent["eventType"], TaskStatus | null> = {
  next_action_generated: "in-progress",
  implementation_started: "in-review",
  implementation_result_ready: null,
  review_requested: "approved",
  review_passed: null,
  review_failed: "in-review",
  repo_warning: "in-progress",
  merge_queue_updated: null,
  operator_decision_required: "approved",
  changed_files_scope_validated: "approved",
  commit_checklist_completed: "approved",
  remote_safety_checked: "approved",
  push_decision_ready: "backlog",
};

export interface DerivedLiveState {
  /** Applied events, newest first. */
  feedEvents: LiveWorkEvent[];
  agentLive: Record<AgentId, AgentLiveMeta>;
  /** taskId -> live board status override. */
  taskStatusOverrides: Record<string, TaskStatus>;
  /** taskId -> latest transition info for the Task Detail panel. */
  transitionHistory: Record<string, TaskTransitionInfo>;
  inboxBadge: LiveBadge | null;
  mergeBadge: LiveBadge | null;
  orbitMessageOverride: string | null;
  recommendedActionOverride: string | null;
}

/**
 * Pure fold over LIVE_EVENTS.slice(0, eventIndex).
 * Same index in -> same state out, always. Refresh resets the index to 0.
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

    actor.lastUpdateLabel = `${labelFor(event)} - ${shortTime(event.timestamp)}`;

    const previousStatus = currentStatusOf(event.taskId);
    const effect = STATUS_EFFECT[event.eventType];
    const currentStatus = effect ? effect.current : previousStatus;
    if (effect) taskStatusOverrides[event.taskId] = effect.current;
    transitionHistory[event.taskId] = {
      previousStatus,
      currentStatus,
      nextExpectedStatus: effect?.next ?? NEXT_EXPECTED[event.eventType],
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
        actor.waitingOn = "Archive review";
        inboxBadge = "New";
        break;
      case "review_requested":
        agentLive.codex.liveState = "reviewing";
        agentLive.codex.currentTaskId = event.taskId;
        inboxBadge = "Needs Review";
        break;
      case "review_passed":
        actor.liveState = "idle";
        actor.currentTaskId = event.taskId;
        actor.waitingOn = null;
        mergeBadge = "Ready to Merge";
        break;
      case "review_failed":
        inboxBadge = "Fix Required";
        if (assigneeId) {
          agentLive[assigneeId].liveState = "working";
          agentLive[assigneeId].currentTaskId = event.taskId;
          agentLive[assigneeId].waitingOn = null;
        }
        break;
      case "repo_warning":
        agentLive.hermes.liveState = "waiting_for_operator";
        agentLive.hermes.currentTaskId = event.taskId;
        agentLive.hermes.waitingOn = "Operator acknowledgement";
        break;
      case "merge_queue_updated":
        actor.liveState = "idle";
        actor.currentTaskId = event.taskId;
        mergeBadge = "Ready to Merge";
        break;
      case "operator_decision_required":
        actor.liveState = "waiting_for_operator";
        actor.waitingOn = "Operator merge decision";
        agentLive.codex.liveState = "waiting_for_operator";
        agentLive.codex.waitingOn = "Operator merge decision";
        orbitMessageOverride =
          "The latest item is queued at the operator gate. The crew is waiting on your merge decision.";
        recommendedActionOverride =
          "Open Merge Queue, check the Decision Guidance evidence, then Approve or Hold.";
        break;
      case "changed_files_scope_validated":
      case "commit_checklist_completed":
      case "remote_safety_checked":
      case "push_decision_ready":
        actor.liveState = "working";
        actor.currentTaskId = event.taskId;
        actor.waitingOn = null;
        orbitMessageOverride =
          "The commit gate evidence is ready for operator review. The UI remains display-only.";
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
