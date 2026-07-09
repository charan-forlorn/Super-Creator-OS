"use client";

import { useMemo, useState } from "react";

import { Sidebar, TopNav } from "./sidebar";
import { Topbar } from "./topbar";
import { AgentStatusCard } from "./agent-status-card";
import { TaskBoard } from "./task-board";
import { TaskDetailPanel } from "./task-detail-panel";
import { PromptBuilder } from "./prompt-builder";
import { ResultInbox } from "./result-inbox";
import { MergeQueue } from "./merge-queue";
import { Timeline } from "./timeline";
import { MascotAssistant } from "./mascot-assistant";
import { NextActionPanel } from "./next-action-panel";
import { HandoffStatusStrip } from "./handoff-status-strip";
import { LiveWorkUpdates } from "./live-work-updates";
import { OperatorReviewGate } from "./operator-review-gate";
import { CommandDraftPanel } from "./command-draft-panel";
import { OperatorApprovalPanel } from "./operator-approval-panel";
import { CommandEventLog } from "./command-event-log";
import { AIWorkSessionPanel } from "./ai-work-session-panel";
import { AgentRoutingPanel } from "./agent-routing-panel";
import { AgentResultStatusPanel } from "./agent-result-status-panel";
import { AgentAdapterPanel } from "./agent-adapter-panel";
import { AdapterSimulationPanel } from "./adapter-simulation-panel";
import { PromptResultPacketPanel } from "./prompt-result-packet-panel";
import { OperatorPacketReviewPanel } from "./operator-packet-review-panel";
import { WorkflowRouterPanel } from "./workflow-router-panel";
import { ResultIntakePanel } from "./result-intake-panel";
import { ChatGPTStatusUpdatePanel } from "./chatgpt-status-update-panel";
import { ProjectStateUpdatePanel } from "./project-state-update-panel";
import { NextActionDecisionPanel } from "./next-action-decision-panel";
import { GitApprovalPanel } from "./git-approval-panel";
import { OperatorExecutionConsole } from "./operator-execution-console";
import { Stage5CertificationPanel } from "./stage5-certification-panel";
import { LocalBackendStatusPanel } from "./local-backend-status-panel";
import { CommandApiPanel } from "./command-api-panel";
import { DurableStateStatusPanel } from "./durable-state-status-panel";
import { StateSnapshotPanel } from "./state-snapshot-panel";
import { CommandRecordCard, ApprovalRecordCard } from "./state-record-card";
import { EventStreamPanel } from "./event-stream-panel";
import { EventSnapshotCard } from "./event-snapshot-card";
import { UIStateSyncPanel } from "./ui-state-sync-panel";
import { SyncHealthPanel } from "./sync-health-panel";
import { OperatorReadSurfacePanel } from "./operator-read-surface-panel";
import { OperatorCommandViewsPanel } from "./operator-command-views-panel";
import { ExecutionEvidenceSurfacePanel } from "./execution-evidence-surface-panel";

import {
  AGENTS,
  HANDOFF_STEPS,
  MERGE_QUEUE,
  PRIMARY_NEXT_ACTION,
  RESULT_INBOX,
  STAGE_PROGRESS,
  TASKS,
  TIMELINE,
} from "@/lib/mock-data";
import {
  deriveLiveState,
  LIVE_EVENTS,
  PROJECT_SNAPSHOT,
  COMMIT_EVIDENCE,
  EVIDENCE_CARDS,
  TASK_COMMIT_EVIDENCE_LINKS,
  REVIEW_ARCHIVE,
} from "@/lib/live-events";
import {
  deriveCommitGateAdvisor,
  OPERATOR_REVIEW_GATE,
} from "@/lib/review-gates";
import {
  COMMAND_DRAFTS,
  COMMAND_EVENTS,
  OPERATOR_APPROVALS,
} from "@/lib/command-mock-data";
import { AGENT_RUNTIMES, AI_WORK_SESSIONS } from "@/lib/ai-work-session-mock-data";
import {
  AGENT_ADAPTER_CARDS,
  AGENT_ADAPTER_SIMULATION_EVENTS,
  AGENT_ADAPTER_SIMULATION_REQUEST,
} from "@/lib/agent-adapter-mock-data";
import {
  PACKET_ROUTING_FLOW,
  PACKET_SCENARIOS,
} from "@/lib/prompt-result-packet-mock-data";
import { OPERATOR_PACKET_REVIEWS } from "@/lib/operator-packet-review-mock-data";
import {
  CHATGPT_STATUS_UPDATE,
  NEXT_ACTION_DECISION,
  PROJECT_STATE_UPDATE,
  RESULT_INTAKES,
} from "@/lib/result-intake-mock-data";
import {
  COMMIT_APPROVAL_DECISION,
  COMMIT_PROPOSAL,
  GIT_APPROVAL_EVENTS,
  GIT_EVIDENCE_SNAPSHOT,
  PUSH_APPROVAL_DECISION,
  PUSH_PROPOSAL,
  PUSH_READINESS_SNAPSHOT,
} from "@/lib/git-approval-mock-data";
import { OPERATOR_EXECUTION_ROWS } from "@/lib/operator-execution-mock-data";
import { STAGE5_FINAL_CERTIFICATION_RESULT } from "@/lib/stage5-certification-mock-data";
import {
  BACKEND_HEALTH_SNAPSHOT,
  COMMAND_API_ACTIONS,
  REJECTED_COMMAND_EXAMPLE,
} from "@/lib/local-backend-mock-data";
import {
  DURABLE_STATE_STATUS,
  EXAMPLE_STATE_SNAPSHOT,
  EXAMPLE_COMMAND_RECORD,
  EXAMPLE_APPROVAL_RECORD,
} from "@/lib/durable-state-mock-data";
import {
  EXAMPLE_EVENT_STREAM_SNAPSHOT,
  EXAMPLE_UI_STATE_SYNC_SNAPSHOT,
} from "@/lib/event-stream-mock-data";
import { populatedOperatorReadSurfaceProjection } from "@/lib/operator-read-surface-mock-data";
import { operatorCommandViewSnapshot } from "@/lib/operator-command-view-mock-data";
import { cn, deriveMascotView } from "@/lib/utils";
import type { MascotView } from "@/lib/utils";
import type { AgentId, Stage } from "@/lib/types";
import { ProjectStateSnapshot } from "@/components/project-state-snapshot";
import { CommitEvidenceList } from "@/components/commit-evidence-list";
import { EvidenceCards } from "@/components/evidence-cards";
import { TaskCommitEvidenceTimeline } from "@/components/task-commit-evidence-timeline";
import { ReviewArchive } from "@/components/review-archive";

const STAGE_META: Record<Stage["status"], { dot: string; text: string }> = {
  done: { dot: "bg-status-approved", text: "text-ink-muted" },
  current: { dot: "bg-accent", text: "text-ink" },
  upcoming: { dot: "bg-border", text: "text-ink-faint" },
};

function StageOverview() {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Stage Progress</h2>
        <span className="text-[11px] text-ink-faint">
          {STAGE_PROGRESS.currentStageLabel} · {STAGE_PROGRESS.percentComplete}%
        </span>
      </div>

      {/* progress bar */}
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${STAGE_PROGRESS.percentComplete}%` }}
        />
      </div>

      <ol className="mt-4 space-y-2">
        {STAGE_PROGRESS.stages.map((stage) => {
          const meta = STAGE_META[stage.status];
          return (
            <li key={stage.id} className="flex items-center gap-2.5">
              <span
                className={cn("h-2 w-2 shrink-0 rounded-full", meta.dot)}
                aria-hidden
              />
              <span className={cn("text-xs", meta.text)}>{stage.label}</span>
              {stage.status === "current" ? (
                <span className="ml-auto rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent">
                  current
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function SectionHeading({ id, title }: { id: string; title: string }) {
  return (
    <h2
      id={id}
      className="scroll-mt-6 text-xs font-semibold uppercase tracking-wider text-ink-faint"
    >
      {title}
    </h2>
  );
}

export function AppShell() {
  // Default selection: the recommended-next (planned) Stage 4.17 target.
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>("task-01");
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [targetAgentId, setTargetAgentId] = useState<AgentId>("claude-code");
  const [selectedIntakeId, setSelectedIntakeId] = useState<string>(
    RESULT_INTAKES[0]?.intakeId ?? "",
  );

  // Deterministic simulated realtime: the only state is an index into LIVE_EVENTS.
  const [eventIndex, setEventIndex] = useState(0);
  const live = useMemo(() => deriveLiveState(eventIndex), [eventIndex]);

  const liveTasks = useMemo(
    () =>
      TASKS.map((task) =>
        live.taskStatusOverrides[task.id]
          ? { ...task, status: live.taskStatusOverrides[task.id] }
          : task,
      ),
    [live],
  );

  const selectedTask = selectedTaskId
    ? liveTasks.find((task) => task.id === selectedTaskId)
    : undefined;
  const selectedTransition = selectedTask
    ? live.transitionHistory[selectedTask.id]
    : undefined;
  const mascotView = useMemo<MascotView>(() => {
    const view = deriveMascotView(selectedTask);
    if (eventIndex >= 11) {
      const advisor = deriveCommitGateAdvisor(OPERATOR_REVIEW_GATE);
      return {
        ...view,
        mood: advisor.mood,
        message: advisor.message,
        nextAction: advisor.nextAction,
        taskSummary: advisor.summary,
      };
    }
    if (!live.orbitMessageOverride) return view;
    return {
      ...view,
      message: live.orbitMessageOverride,
      nextAction: live.recommendedActionOverride ?? view.nextAction,
    };
  }, [selectedTask, live, eventIndex]);

  const activeAgent = AGENTS.find((agent) => agent.status === "active");

  function handleAdvanceLive() {
    setEventIndex((index) => Math.min(index + 1, LIVE_EVENTS.length));
  }

  function handleResetLiveUpdates() {
    setEventIndex(0);
  }

  function handleSelectTask(taskId: string) {
    setSelectedTaskId(taskId);
  }

  function handleSelectSection(id: string) {
    setActiveSection(id);
    if (typeof document !== "undefined") {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar activeSection={activeSection} onSelect={handleSelectSection} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar stage={STAGE_PROGRESS} activeAgent={activeAgent} />

        {/* Compact horizontal nav replaces the sidebar below lg. */}
        <div className="lg:hidden">
          <TopNav activeSection={activeSection} onSelect={handleSelectSection} />
        </div>

        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Main scrollable column */}
          <main className="min-w-0 flex-1 space-y-8 overflow-y-auto p-6">
            <section id="next-action" className="scroll-mt-6">
              <NextActionPanel action={PRIMARY_NEXT_ACTION} />
            </section>

            <section id="handoff" className="scroll-mt-6">
              <HandoffStatusStrip steps={HANDOFF_STEPS} />
            </section>

            <section id="evidence-identity" className="scroll-mt-6 space-y-3">
              <div className="rounded-card border border-border bg-surface p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h1 className="text-sm font-semibold text-ink">
                      Evidence Command Center
                    </h1>
                    <p className="mt-1 text-xs text-ink-faint">
                      This dashboard organizes project evidence, task state, commit proof,
                      review status, and next actions for deterministic operator review.
                    </p>
                  </div>
                  <span className="text-[11px] text-ink-faint">Control Center v0.2</span>
                </div>
              </div>
              <ProjectStateSnapshot snapshot={PROJECT_SNAPSHOT} />
            </section>

            <section id="evidence" className="scroll-mt-6 space-y-3">
              <CommitEvidenceList
                commits={COMMIT_EVIDENCE}
                activeTaskId={selectedTaskId || undefined}
                selectedTaskId={selectedTaskId || undefined}
                onSelectTask={handleSelectTask}
              />
            </section>

            <section id="evidence-cards" className="scroll-mt-6 space-y-3">
              <EvidenceCards items={EVIDENCE_CARDS} />
            </section>

            <section id="task-timeline" className="scroll-mt-6 space-y-3">
              <TaskCommitEvidenceTimeline
                items={TASK_COMMIT_EVIDENCE_LINKS}
                onSelectTask={handleSelectTask}
              />
            </section>

            <section id="review-archive" className="scroll-mt-6 space-y-3">
              <ReviewArchive items={REVIEW_ARCHIVE} />
            </section>

            {/* 1 + 2: Agent status + stage overview */}
            <section id="overview" className="scroll-mt-6 space-y-3">
              <SectionHeading id="overview-h" title="Agent Status" />
              <div className="grid gap-3 lg:grid-cols-3 xl:grid-cols-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:col-span-2 xl:col-span-3">
                  {AGENTS.map((agent) => (
                    <AgentStatusCard
                      key={agent.id}
                      agent={agent}
                      live={live.agentLive[agent.id]}
                      onSelectTask={handleSelectTask}
                    />
                  ))}
                </div>
                <StageOverview />
              </div>
            </section>

            {/* Live Work Updates: deterministic simulated feed. Single placement —
                below the command/agent sections and above the board at every
                breakpoint (the main column order is shared across breakpoints). */}
            <section id="live" className="scroll-mt-6 space-y-3">
              <SectionHeading id="live-h" title="Live Work Updates" />
              <LiveWorkUpdates
                events={live.feedEvents}
                appliedCount={eventIndex}
                totalCount={LIVE_EVENTS.length}
                onAdvance={handleAdvanceLive}
                onReset={handleResetLiveUpdates}
                onSelectTask={handleSelectTask}
              />
            </section>

            <section id="operator-review" className="scroll-mt-6">
              <OperatorReviewGate gate={OPERATOR_REVIEW_GATE} />
            </section>

            {/* Stage 5.1: local command bridge (static deterministic mock —
                the UI never executes commands; execution lives in
                scos/control_center behind the operator approval gate). */}
            <section id="command-bridge" className="scroll-mt-6 space-y-3">
              <SectionHeading id="command-bridge-h" title="Command Bridge (Stage 5.1)" />
              <div className="grid gap-4 xl:grid-cols-2">
                <CommandDraftPanel drafts={COMMAND_DRAFTS} />
                <OperatorApprovalPanel approvals={OPERATOR_APPROVALS} />
              </div>
              <CommandEventLog events={COMMAND_EVENTS} />
            </section>

            {/* Stage 5.2: AI Work Session Manager (static deterministic mock —
                the UI never dispatches AI work itself; state modeling lives in
                scos/control_center/work_session_manager.py, no execution). */}
            <section id="ai-work-sessions" className="scroll-mt-6 space-y-3">
              <SectionHeading id="ai-work-sessions-h" title="AI Work Sessions (Stage 5.2)" />
              <AIWorkSessionPanel sessions={AI_WORK_SESSIONS} />
              <div className="grid gap-4 xl:grid-cols-2">
                <AgentRoutingPanel runtimes={AGENT_RUNTIMES} sessions={AI_WORK_SESSIONS} />
                <AgentResultStatusPanel sessions={AI_WORK_SESSIONS} />
              </div>
            </section>

            {/* Stage 5.3: AI Agent Adapter Contract Layer (static deterministic
                mock — no adapter here calls an API, opens an app, or
                automates anything; contracts live in
                scos/control_center/agent_adapter_*.py). */}
            <section id="agent-adapters" className="scroll-mt-6 space-y-3">
              <SectionHeading id="agent-adapters-h" title="AI Agent Adapters (Stage 5.3)" />
              <AgentAdapterPanel adapters={AGENT_ADAPTER_CARDS} />
              <AdapterSimulationPanel
                request={AGENT_ADAPTER_SIMULATION_REQUEST}
                events={AGENT_ADAPTER_SIMULATION_EVENTS}
              />
            </section>

            {/* Stage 5.4: Unified Prompt & Result Packet (static deterministic
                mock — no packet here is sent, no routing decision is
                executed; contracts live in
                scos/control_center/prompt_result_packet_*.py). */}
            <section id="prompt-packets" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="prompt-packets-h"
                title="Unified Prompt & Result Packets (Stage 5.4)"
              />
              <PromptResultPacketPanel scenarios={PACKET_SCENARIOS} flow={PACKET_ROUTING_FLOW} />
            </section>

            {/* Stage 5.5: Operator Packet Review & Manual Handoff Flow
                (static deterministic mock - decisions update React local
                state only; no backend, clipboard, dispatch, or app control). */}
            <section id="packet-review" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="packet-review-h"
                title="Operator Packet Review (Stage 5.5)"
              />
              <OperatorPacketReviewPanel reviews={OPERATOR_PACKET_REVIEWS} />
            </section>

            {/* Stage 5.6: Cross-Agent Workflow Router (static deterministic
                mock - routing decisions are display-only; no packet is
                dispatched or routed automatically. Contracts live in
                scos/control_center/workflow_router*.py). */}
            <section id="workflow-router" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="workflow-router-h"
                title="Cross-Agent Router (Stage 5.6)"
              />
              <WorkflowRouterPanel />
            </section>

            {/* Stage 5.7: AI Result Intake & ChatGPT Status Update Loop
                (static deterministic mock — results are pasted/imported by
                the operator; no clipboard, network, or AI dispatch happens
                here. Contracts live in scos/control_center/result_intake_*.py,
                chatgpt_status_update.py, and project_state_update.py). */}
            <section id="result-intake" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="result-intake-h"
                title="AI Result Intake & ChatGPT Status Update Loop (Stage 5.7)"
              />
              <ResultIntakePanel
                intakes={RESULT_INTAKES}
                selectedIntakeId={selectedIntakeId}
                onSelectIntake={setSelectedIntakeId}
              />
              <div className="grid gap-4 xl:grid-cols-2">
                <ChatGPTStatusUpdatePanel packet={CHATGPT_STATUS_UPDATE} />
                <div className="space-y-4">
                  <ProjectStateUpdatePanel update={PROJECT_STATE_UPDATE} />
                  <NextActionDecisionPanel decision={NEXT_ACTION_DECISION} />
                </div>
              </div>
            </section>

            {/* Stage 5.8: Git Commit / Push Approval Gate (static
                deterministic mock — no git command is ever read or run here;
                contracts live in scos/control_center/git_approval_*.py and
                git_evidence_snapshot.py). */}
            <section id="git-approval" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="git-approval-h"
                title="Git Commit / Push Approval Gate (Stage 5.8)"
              />
              <GitApprovalPanel
                snapshot={GIT_EVIDENCE_SNAPSHOT}
                proposal={COMMIT_PROPOSAL}
                commitDecision={COMMIT_APPROVAL_DECISION}
                pushReadiness={PUSH_READINESS_SNAPSHOT}
                pushProposal={PUSH_PROPOSAL}
                pushDecision={PUSH_APPROVAL_DECISION}
                events={GIT_APPROVAL_EVENTS}
              />
            </section>

            {/* Stage 5.9: Local Operator Execution Console / Manual Command
                Runbook. Static deterministic mock. SCOS does not execute any
                command, open a terminal, or touch the clipboard; the operator
                runs each step manually and pastes the result back. Real
                contracts live in scos/control_center/operator_execution_*.py. */}
            <section id="operator-execution" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="operator-execution-h"
                title="Operator Execution Console (Stage 5.9)"
              />
              <OperatorExecutionConsole rows={OPERATOR_EXECUTION_ROWS} />
            </section>

            {/* Stage 5.10: Stage 5 Final AI Command Center Certification.
                Static deterministic mock. This is a read-only certification
                mirror - SCOS does not dispatch AI work, execute a command, or
                fix any finding here. Real contracts live in
                scos/control_center/stage5_final_certification.py. */}
            <section id="stage5-certification" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="stage5-certification-h"
                title="Stage 5 Final Certification (Stage 5.10)"
              />
              <Stage5CertificationPanel result={STAGE5_FINAL_CERTIFICATION_RESULT} />
            </section>

            {/* Stage 6.2: Local Control Center Backend & Command API.
                Static deterministic mock. No fetch, socket, WebSocket, SSE,
                polling, timer, real clock/random/uuid, or browser storage is
                used anywhere in this section. Real contracts live in
                scos/control_center/{backend_models,backend_validation,
                command_api,local_backend,backend_response_builder}.py. */}
            <section id="local-backend" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="local-backend-h"
                title="Local Backend / Command API (Stage 6.2)"
              />
              <LocalBackendStatusPanel snapshot={BACKEND_HEALTH_SNAPSHOT} />
              <CommandApiPanel
                actions={COMMAND_API_ACTIONS}
                rejectedExample={REJECTED_COMMAND_EXAMPLE}
              />
            </section>

            {/* Stage 6.3: Durable Local State Store (SQLite WAL).
                Static deterministic mock. No fetch, socket, WebSocket, SSE,
                polling, timer, real clock/random/uuid, or browser storage is
                used anywhere in this section. Real contracts live in
                scos/control_center/{state_models,sqlite_state_schema,
                sqlite_state_store,state_repository,state_snapshot}.py. */}
            <section id="durable-state" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="durable-state-h"
                title="Durable Local State (Stage 6.3)"
              />
              <DurableStateStatusPanel status={DURABLE_STATE_STATUS} />
              <StateSnapshotPanel snapshot={EXAMPLE_STATE_SNAPSHOT} />
              <div className="grid gap-3 sm:grid-cols-2">
                <CommandRecordCard record={EXAMPLE_COMMAND_RECORD} />
                <ApprovalRecordCard record={EXAMPLE_APPROVAL_RECORD} />
              </div>
            </section>

            {/* Stage 6.4: Local Event Stream & UI State Sync Foundation.
                Static deterministic mock. No fetch, socket, WebSocket, SSE,
                polling, timer, real clock/random/uuid, or browser storage is
                used anywhere in this section. Real contracts live in
                scos/control_center/{event_stream_models,event_stream_builder,
                event_stream_snapshot,ui_state_sync}.py. */}
            <section id="event-stream" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="event-stream-h"
                title="Event Stream & UI State Sync (Stage 6.4)"
              />
              <SyncHealthPanel snapshot={EXAMPLE_UI_STATE_SYNC_SNAPSHOT} />
              <UIStateSyncPanel snapshot={EXAMPLE_UI_STATE_SYNC_SNAPSHOT} />
              <div className="grid gap-3 lg:grid-cols-2">
                <EventStreamPanel snapshot={EXAMPLE_EVENT_STREAM_SNAPSHOT} />
                <EventSnapshotCard snapshot={EXAMPLE_EVENT_STREAM_SNAPSHOT} />
              </div>
            </section>

            {/* Stage 7.4: Operator Read Surface UI Projection.
                Static deterministic fixture only. No live sync transport,
                backend route, browser request, direct SQLite read, or adapter
                dispatch exists here; Stage 7.5 owns any future transport
                decision. */}
            <section id="operator-read-surface" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="operator-read-surface-h"
                title="Operator Read Surface (Stage 7.4)"
              />
              <OperatorReadSurfacePanel projection={populatedOperatorReadSurfaceProjection} />
            </section>

            {/* Stage 7.6: Approval-aware operator command views.
                Static deterministic fixture only. This read-only evidence
                surface does not change approval, command, audit, event,
                queue, state, or adapter behavior. */}
            <section id="operator-command-views" className="scroll-mt-6 space-y-3">
              <SectionHeading
                id="operator-command-views-h"
                title="Operator Command Views (Stage 7.6)"
              />
              <OperatorCommandViewsPanel snapshot={operatorCommandViewSnapshot} />
              <ExecutionEvidenceSurfacePanel snapshot={operatorCommandViewSnapshot} />
            </section>

            {/* 3: Kanban board */}
            <section id="board" className="scroll-mt-6 space-y-3">
              <SectionHeading id="board-h" title="Task Board" />
              <TaskBoard
                tasks={liveTasks}
                selectedTaskId={selectedTaskId}
                onSelectTask={handleSelectTask}
              />
            </section>

            {/* 7 + 9 (below xl): in-flow Selected Task + Orbit, so selection feedback
                stays visible when the right rail is hidden. The rail copy below is the
                xl+ equivalent; only one is display:rendered per breakpoint (the CSS-hidden
                copy is display:none, so it is excluded from the accessibility tree too). */}
            <section id="selected" className="scroll-mt-6 space-y-3 xl:hidden">
              <SectionHeading id="selected-h" title="Selected Task & Orbit" />
              <div className="grid gap-4 md:grid-cols-2">
                <TaskDetailPanel task={selectedTask} transition={selectedTransition} />
                <MascotAssistant view={mascotView} compact />
              </div>
            </section>

            {/* 4: Prompt builder */}
            <section id="prompt" className="scroll-mt-6 space-y-3">
              <SectionHeading id="prompt-h" title="Prompt Builder" />
              <PromptBuilder
                selectedTask={selectedTask}
                targetAgentId={targetAgentId}
                onChangeTargetAgent={setTargetAgentId}
              />
            </section>

            {/* 5 + 6: Result inbox + merge queue */}
            <div className="grid gap-6 xl:grid-cols-2">
              <section id="inbox" className="scroll-mt-6 space-y-3">
                <SectionHeading id="inbox-h" title="Result Inbox" />
                <ResultInbox
                  results={RESULT_INBOX}
                  selectedTaskId={selectedTaskId}
                  onSelectTask={handleSelectTask}
                  badge={live.inboxBadge}
                />
              </section>

              <section id="merge" className="scroll-mt-6 space-y-3">
                <SectionHeading id="merge-h" title="Merge Queue" />
                <MergeQueue
                  items={MERGE_QUEUE}
                  selectedTaskId={selectedTaskId}
                  onSelectTask={handleSelectTask}
                  badge={live.mergeBadge}
                />
              </section>
            </div>

            {/* 8: Timeline */}
            <section id="timeline" className="scroll-mt-6 space-y-3">
              <SectionHeading id="timeline-h" title="Timeline" />
              <Timeline
                events={TIMELINE}
                selectedTaskId={selectedTaskId}
                onSelectTask={handleSelectTask}
              />
            </section>
          </main>

          {/* Right rail: task detail + mascot (7 + 9) */}
          <aside className="hidden w-80 shrink-0 space-y-6 overflow-y-auto border-l border-border bg-surface/40 p-5 xl:block">
            <TaskDetailPanel task={selectedTask} transition={selectedTransition} />
            <MascotAssistant view={mascotView} />
          </aside>
        </div>
      </div>
    </div>
  );
}
