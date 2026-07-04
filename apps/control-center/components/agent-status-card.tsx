import { cn, getTaskById } from "@/lib/utils";
import type { Agent, AgentLiveMeta, AgentLiveState } from "@/lib/types";

const ACCENT_RING: Record<Agent["accent"], string> = {
  emerald: "ring-agent-emerald/30",
  violet: "ring-agent-violet/30",
  sky: "ring-agent-sky/30",
  amber: "ring-agent-amber/30",
};

const ACCENT_BG: Record<Agent["accent"], string> = {
  emerald: "bg-agent-emerald/15 text-agent-emerald",
  violet: "bg-agent-violet/15 text-agent-violet",
  sky: "bg-agent-sky/15 text-agent-sky",
  amber: "bg-agent-amber/15 text-agent-amber",
};

const STATUS_META: Record<Agent["status"], { label: string; dot: string }> = {
  active: { label: "Active", dot: "bg-status-approved" },
  idle: { label: "Idle", dot: "bg-status-idle" },
  waiting: { label: "Waiting", dot: "bg-status-review" },
  blocked: { label: "Blocked", dot: "bg-status-blocked" },
};

const LIVE_STATE_META: Record<AgentLiveState, { label: string; badge: string }> = {
  idle: { label: "idle", badge: "bg-status-idle/15 text-status-idle ring-status-idle/30" },
  working: {
    label: "working",
    badge: "bg-status-working/15 text-status-working ring-status-working/30",
  },
  reviewing: {
    label: "reviewing",
    badge: "bg-status-review/15 text-status-review ring-status-review/30",
  },
  blocked: {
    label: "blocked",
    badge: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  },
  result_ready: {
    label: "result ready",
    badge: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  },
  waiting_for_operator: {
    label: "waiting for operator",
    badge: "bg-accent/15 text-accent ring-accent/30",
  },
};

export function AgentStatusCard({
  agent,
  live,
  onSelectTask,
}: {
  agent: Agent;
  live: AgentLiveMeta;
  onSelectTask: (taskId: string) => void;
}) {
  const status = STATUS_META[agent.status];
  const liveState = LIVE_STATE_META[live.liveState];
  const task = getTaskById(live.currentTaskId ?? agent.currentTaskId);
  const initials = agent.name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div
      className={cn(
        "rounded-card border border-border bg-surface p-4 ring-1 ring-inset shadow-sm shadow-black/10",
        ACCENT_RING[agent.accent],
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold",
            ACCENT_BG[agent.accent],
          )}
          aria-hidden
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-sm font-semibold text-ink">
              {agent.name}
            </p>
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-ink-muted">
              <span
                className={cn("h-1.5 w-1.5 rounded-full", status.dot)}
                aria-hidden
              />
              {status.label}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            <p className="text-[11px] text-ink-faint">{agent.role}</p>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                liveState.badge,
              )}
            >
              {liveState.label}
            </span>
          </div>
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-muted">
        {agent.activity}
      </p>

      {task ? (
        <button
          type="button"
          onClick={() => onSelectTask(task.id)}
          className="mt-3 flex w-full items-center justify-between rounded-lg border border-border-soft bg-surface-2 px-3 py-2 text-left transition-colors hover:border-border hover:bg-surface-2/70"
        >
          <span className="min-w-0">
            <span className="block text-[11px] text-ink-faint">
              Current task
            </span>
            <span className="block truncate text-xs font-medium text-ink">
              {task.code} · {task.title}
            </span>
          </span>
          <span className="ml-2 text-ink-faint" aria-hidden>
            →
          </span>
        </button>
      ) : (
        <p className="mt-3 rounded-lg border border-dashed border-border-soft px-3 py-2 text-[11px] text-ink-faint">
          No task attached.
        </p>
      )}

      <div className="mt-3 space-y-0.5 border-t border-border-soft pt-2 text-[11px] text-ink-faint">
        <p>
          <span className="font-medium text-ink-muted">Last update:</span>{" "}
          {live.lastUpdateLabel}
        </p>
        {live.waitingOn ? (
          <p>
            <span className="font-medium text-ink-muted">Waiting on:</span>{" "}
            {live.waitingOn}
          </p>
        ) : null}
      </div>
    </div>
  );
}
