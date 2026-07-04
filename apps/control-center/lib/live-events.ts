// Deterministic "simulated realtime" engine for the Live Work Updates feature.
// A fixed, ordered event list is replayed up to an index held in React state.
// Pure module: no clocks, no randomness, no network, no storage, no side effects.

import { TASKS } from "./mock-data";
import type {
  AgentId,
  AgentLiveMeta,
  EvidenceCard,
  LiveAgentName,
  LiveBadge,
  LiveWorkEvent,
  ProjectSnapshot,
  CommitEvidence,
  ReviewArchiveEntry,
  TaskCommitEvidenceLink,
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
    message: "SCOS-409 handoff fixture (simulated) — pending source proof, not verified in repository history.",
    severity: "info",
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
    liveState: "idle",
    currentTaskId: "task-01",
    lastUpdateLabel: "Stage 4.17 recommended next (planned)",
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
export function labelFor(event: LiveWorkEvent): string {
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

export const PROJECT_SNAPSHOT: ProjectSnapshot = {
  currentStage: "Stage 4.17 (planned — recommended next, no implementation evidence yet)",
  latestCompletedStage: "Stage 4.16",
  latestUiMilestone: "Control Center v0.1.4.1 — current-state sync complete",
  activeBlocker: null,
  repoState: "v0.2 working draft · uncommitted apps/control-center/ changes pending review",
  nextAction: "Prepare Stage 4.17 conversion handoff plan",
};

export const COMMIT_EVIDENCE: CommitEvidence[] = [
  {
    shortHash: "145d4d6",
    message: "chore(ui): sync control center current state data",
    category: "Current State",
    relatedTaskOrStage: "Control Center v0.1.4.1",
    status: "pushed",
    proofSummary: "Real UI-data-sync commit. Its mock content is simulated and does not assert SCOS-409 closure or Stage 4.17 implementation in repository history.",
  },
  {
    shortHash: "f70e133",
    message: "feat(ui): add deterministic live work updates",
    category: "Live Simulation",
    relatedTaskOrStage: "Control Center v0.1.3",
    status: "pushed",
    proofSummary: "Added deterministic index-driven updates with static evidence transitions.",
  },
  {
    shortHash: "28c2eaf",
    message: "test(commercial): add Stage 4.14 handoff fixture",
    category: "Commercial Evidence",
    relatedTaskOrStage: "Stage 4.14",
    status: "pushed",
    proofSummary: "Handoff fixture test passthrough supports staged handoff readiness.",
  },
  {
    shortHash: "8e520e7",
    message: "feat(commercial): add Stage 4.16 first prospect outcome review",
    category: "Commercial Evidence",
    relatedTaskOrStage: "Stage 4.16",
    status: "pushed",
    proofSummary: "First prospect outcome review is complete and supports downstream conversion planning.",
  },
  {
    shortHash: "72ab3fe",
    message: "fix(ui): update Next.js for Vercel deployment",
    category: "Deployment Evidence",
    relatedTaskOrStage: "Control Center v0.1.x",
    status: "deployed",
    proofSummary: "Updated for Vercel deployment compatibility and verifiable build output.",
  },
  {
    shortHash: "63ef243",
    message: "feat(ui): clarify control center operator workflow",
    category: "Workflow Evidence",
    relatedTaskOrStage: "Control Center v0.1.x",
    status: "pushed",
    proofSummary: "Operator review gates, merge decision guidance, and static review flow added.",
  },
];

export const EVIDENCE_CARDS: EvidenceCard[] = [
  {
    id: "evd-1",
    title: "SCOS-409 Closure (Simulated)",
    sourceType: "Simulated Evidence",
    relatedTaskOrStage: "SCOS-409",
    status: "simulated",
    proofSummary: "Simulated / pending source proof. Not verified in repository history. Operator review required before treating as closed.",
    nextAction: "Obtain repository source proof for SCOS-409 before treating it as closed.",
  },
  {
    id: "evd-2",
    title: "Stage 4.16 Completion Evidence",
    sourceType: "Stage Complete",
    relatedTaskOrStage: "Stage 4.16",
    status: "pushed",
    proofSummary: "First prospect outcome review is complete and pushed.",
    nextAction: "Prepare Stage 4.17 customer conversion handoff plan.",
  },
  {
    id: "evd-3",
    title: "Control Center v0.1.3 Completion Evidence",
    sourceType: "UI Milestone",
    relatedTaskOrStage: "Control Center v0.1.3",
    status: "pushed",
    proofSummary: "Deterministic live work updates were added and deployed.",
    nextAction: "Retain evidence for v0.1.5 archive review.",
  },
  {
    id: "evd-4",
    title: "Control Center v0.1.4.1 Current-State Sync Evidence",
    sourceType: "UI Milestone",
    relatedTaskOrStage: "Control Center v0.1.4.1",
    status: "pushed",
    proofSummary: "Static mock data now syncs the current SCOS project state.",
    nextAction: "Use current-state snapshot as the v0.2 evidence baseline.",
  },
  {
    id: "evd-5",
    title: "Vercel Deployment Evidence",
    sourceType: "Deployment Evidence",
    relatedTaskOrStage: "Control Center v0.1.x / v0.1.4",
    status: "deployed",
    proofSummary: "Next.js app builds and deploys to Vercel.",
    nextAction: "Treat deployment export evidence as commit-readiness validation.",
  },
  {
    id: "evd-6",
    title: "Repo State — v0.2 Working Draft",
    sourceType: "Draft Evidence",
    relatedTaskOrStage: "Control Center v0.2",
    status: "draft",
    proofSummary: "v0.2 working draft: uncommitted apps/control-center/ UI changes pending review. Clean/synced state applies only after commit/push verification. Commit pending.",
    nextAction: "Commit pending — verify clean/synced state only after the v0.2 commit and push.",
  },
];

export const TASK_COMMIT_EVIDENCE_LINKS: TaskCommitEvidenceLink[] = [
  {
    taskId: "task-04",
    result: "SCOS-409 handoff fixture is simulated / pending source proof — not verified in repository history.",
    commit: null,
    evidence: EVIDENCE_CARDS[0],
    nextAction: "Obtain repository source proof for SCOS-409 before treating it as closed.",
  },
  {
    taskId: "task-03",
    result: "Stage 4.16 is complete and pushed.",
    commit: COMMIT_EVIDENCE[3],
    evidence: EVIDENCE_CARDS[1],
    nextAction: "Prepare Stage 4.17 customer conversion handoff plan.",
  },
  {
    taskId: "task-06",
    result: "Current-state sync is complete for Control Center v0.1.4.1.",
    commit: COMMIT_EVIDENCE[0],
    evidence: EVIDENCE_CARDS[3],
    nextAction: "Use current-state snapshot as the v0.2 evidence baseline.",
  },
  {
    taskId: "task-05",
    result: "Review gate flow is complete, committed, and deployed.",
    commit: COMMIT_EVIDENCE[4],
    evidence: EVIDENCE_CARDS[4],
    nextAction: "Keep deployment evidence visible for commit-readiness.",
  },
];

export const REVIEW_ARCHIVE: ReviewArchiveEntry[] = [
  {
    id: "arc-1",
    label: "SCOS-409 handoff fixture (simulated)",
    sourceType: "Simulated Evidence",
    relatedTaskOrStage: "SCOS-409",
    status: "simulated",
    proofSummary: "Simulated / pending source proof. Not verified in repository history; operator review required before treating as closed.",
    nextAction: "Obtain repository source proof for SCOS-409 before archiving it as closed.",
  },
  {
    id: "arc-2",
    label: "Stage 4.16 complete",
    sourceType: "Stage Archive",
    relatedTaskOrStage: "Stage 4.16",
    status: "archived",
    proofSummary: "First prospect outcome review was committed and pushed.",
    nextAction: "Use Stage 4.16 as the latest completed stage.",
  },
  {
    id: "arc-3",
    label: "Control Center v0.1.3 pushed",
    sourceType: "UI Archive",
    relatedTaskOrStage: "Control Center v0.1.3",
    status: "archived",
    proofSummary: "Deterministic live updates were merged and deployed.",
    nextAction: "Use as the baseline live-update evidence for v0.2.",
  },
  {
    id: "arc-4",
    label: "Control Center v0.1.4.1 data sync pushed",
    sourceType: "UI Archive",
    relatedTaskOrStage: "Control Center v0.1.4.1",
    status: "archived",
    proofSummary: "Current-state mock sync was committed and visible in the operator UI.",
    nextAction: "Treat v0.1.4.1 as the current UI milestone evidence.",
  },
  {
    id: "arc-5",
    label: "Stale Stage 4.15 blocked state replaced",
    sourceType: "State Replace",
    relatedTaskOrStage: "Stage 4.15",
    status: "archived",
    proofSummary: "Old Stage 4.15 planning state was replaced with the archived done state.",
    nextAction: "Use archived state for Stage 4.15 evidence review.",
  },
];
