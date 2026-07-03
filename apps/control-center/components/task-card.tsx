import { cn, getAgentById } from "@/lib/utils";
import type { Task } from "@/lib/types";

const PRIORITY_META: Record<Task["priority"], { label: string; className: string }> =
  {
    high: { label: "High", className: "text-status-blocked" },
    medium: { label: "Med", className: "text-status-working" },
    low: { label: "Low", className: "text-ink-faint" },
  };

export function TaskCard({
  task,
  selected,
  onSelect,
}: {
  task: Task;
  selected: boolean;
  onSelect: (taskId: string) => void;
}) {
  const agent = getAgentById(task.assignee);
  const priority = PRIORITY_META[task.priority];
  const doneCount = task.checklist.filter((item) => item.done).length;

  return (
    <button
      type="button"
      onClick={() => onSelect(task.id)}
      aria-pressed={selected}
      className={cn(
        "w-full rounded-xl border bg-surface p-3 text-left transition-all",
        selected
          ? "border-accent/60 ring-1 ring-inset ring-accent/40 shadow-md shadow-accent/10"
          : "border-border hover:border-border/80 hover:bg-surface-2/60",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-ink-faint">{task.code}</span>
        <span className={cn("text-[11px] font-semibold", priority.className)}>
          {priority.label}
        </span>
      </div>

      <p className="mt-1 text-sm font-medium leading-snug text-ink">
        {task.title}
      </p>

      <div className="mt-3 flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-ink-faint" aria-hidden />
          {agent ? agent.name : task.assignee}
        </span>
        <span className="text-[11px] text-ink-faint">
          {doneCount}/{task.checklist.length}
        </span>
      </div>
    </button>
  );
}
