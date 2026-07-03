import { cn, getTaskById } from "@/lib/utils";
import type { Agent } from "@/lib/types";

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

export function AgentStatusCard({
  agent,
  onSelectTask,
}: {
  agent: Agent;
  onSelectTask: (taskId: string) => void;
}) {
  const status = STATUS_META[agent.status];
  const task = getTaskById(agent.currentTaskId);
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
          <p className="text-[11px] text-ink-faint">{agent.role}</p>
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
    </div>
  );
}
