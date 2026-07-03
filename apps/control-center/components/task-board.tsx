import { TaskCard } from "./task-card";
import { BOARD_COLUMNS, TASK_STATUS_LABEL } from "@/lib/utils";
import type { Task, TaskStatus } from "@/lib/types";

const COLUMN_ACCENT: Record<TaskStatus, string> = {
  backlog: "bg-status-idle",
  "in-progress": "bg-status-working",
  "in-review": "bg-status-review",
  blocked: "bg-status-blocked",
  approved: "bg-status-approved",
  done: "bg-status-approved/60",
};

export function TaskBoard({
  tasks,
  selectedTaskId,
  onSelectTask,
}: {
  tasks: Task[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
      {BOARD_COLUMNS.map((status) => {
        const columnTasks = tasks.filter((task) => task.status === status);
        return (
          <div
            key={status}
            className="flex min-h-40 flex-col rounded-xl border border-border-soft bg-surface/50 p-2.5"
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-muted">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${COLUMN_ACCENT[status]}`}
                  aria-hidden
                />
                {TASK_STATUS_LABEL[status]}
              </span>
              <span className="text-[11px] text-ink-faint">
                {columnTasks.length}
              </span>
            </div>
            <div className="flex flex-1 flex-col gap-2">
              {columnTasks.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border-soft px-2 py-4 text-center text-[11px] text-ink-faint">
                  Empty
                </p>
              ) : (
                columnTasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    selected={task.id === selectedTaskId}
                    onSelect={onSelectTask}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
