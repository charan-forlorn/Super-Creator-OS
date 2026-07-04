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
import { deriveLiveState, LIVE_EVENTS } from "@/lib/live-events";
import { cn, deriveMascotView } from "@/lib/utils";
import type { AgentId, Stage } from "@/lib/types";

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
  // Default selection: the blocked task, so the operator immediately sees what needs attention.
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>("task-04");
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [targetAgentId, setTargetAgentId] = useState<AgentId>("claude-code");

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
  const mascotView = useMemo(() => {
    const view = deriveMascotView(selectedTask);
    if (!live.orbitMessageOverride) return view;
    return {
      ...view,
      message: live.orbitMessageOverride,
      nextAction: live.recommendedActionOverride ?? view.nextAction,
    };
  }, [selectedTask, live]);

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
