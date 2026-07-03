import { StatusBadge } from "./status-badge";
import { cn, formatTimestamp, getAgentById } from "@/lib/utils";
import type { Task } from "@/lib/types";

export function TaskDetailPanel({ task }: { task: Task | undefined }) {
  if (!task) {
    return (
      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink">Task Detail</h2>
        <p className="mt-6 rounded-xl border border-dashed border-border-soft px-4 py-8 text-center text-sm text-ink-faint">
          Select a task from the board to see its details here.
        </p>
      </section>
    );
  }

  const agent = getAgentById(task.assignee);

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Task Detail</h2>
        <StatusBadge status={task.status} />
      </div>

      <div className="mt-3">
        <p className="font-mono text-[11px] text-ink-faint">{task.code}</p>
        <p className="mt-0.5 text-base font-semibold leading-snug text-ink">
          {task.title}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          {task.summary}
        </p>
      </div>

      {task.status === "blocked" && task.blockedReason ? (
        <div className="mt-3 rounded-xl border border-status-blocked/30 bg-status-blocked/10 px-3 py-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-status-blocked">
            Blocked
          </p>
          <p className="mt-0.5 text-sm text-ink">{task.blockedReason}</p>
        </div>
      ) : null}

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[11px] text-ink-faint">Assignee</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {agent ? agent.name : task.assignee}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] text-ink-faint">Stage</dt>
          <dd className="mt-0.5 font-medium text-ink">{task.stage}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-[11px] text-ink-faint">Last updated</dt>
          <dd className="mt-0.5 font-medium text-ink">
            {formatTimestamp(task.updatedAt)}
          </dd>
        </div>
      </dl>

      <div className="mt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Checklist
        </p>
        <ul className="mt-2 space-y-1.5">
          {task.checklist.map((item) => (
            <li key={item.id} className="flex items-center gap-2.5 text-sm">
              <span
                className={cn(
                  "flex h-4 w-4 items-center justify-center rounded-[5px] text-[10px]",
                  item.done
                    ? "bg-status-approved/20 text-status-approved ring-1 ring-inset ring-status-approved/40"
                    : "border border-border-soft text-transparent",
                )}
                aria-hidden
              >
                ✓
              </span>
              <span
                className={cn(
                  item.done ? "text-ink-muted line-through" : "text-ink",
                )}
              >
                {item.label}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Operator checklist
        </p>
        <ul className="mt-2 space-y-1.5">
          {task.operatorChecklist.map((item) => (
            <li key={item.id} className="flex items-center gap-2.5 text-sm">
              <span
                className={cn(
                  "flex h-4 w-4 items-center justify-center rounded-[5px] text-[10px]",
                  item.done
                    ? "bg-status-approved/20 text-status-approved ring-1 ring-inset ring-status-approved/40"
                    : "border border-border-soft text-transparent",
                )}
                aria-hidden
              >
                ✓
              </span>
              <span
                className={cn(
                  item.done ? "text-ink-muted line-through" : "text-ink",
                )}
              >
                {item.label}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
