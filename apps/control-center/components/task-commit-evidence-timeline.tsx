import { cn, getTaskById } from "@/lib/utils";
import type { TaskCommitEvidenceLink } from "@/lib/types";

const RESULT_STYLES: Record<string, string> = {
  done: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  pushed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  deployed: "bg-agent-sky/15 text-agent-sky ring-agent-sky/30",
  archived: "bg-surface-2 text-ink-muted ring-border",
  // Evidence classes for unproven / not-yet-committed items.
  simulated: "bg-status-working/15 text-status-working ring-status-working/30",
  planned: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  draft: "bg-status-review/15 text-status-review ring-status-review/30",
};

export function TaskCommitEvidenceTimeline({
  items,
  onSelectTask,
}: {
  items: TaskCommitEvidenceLink[];
  onSelectTask?: (taskId: string) => void;
}) {
  if (items.length === 0) {
    return (
      <section className="rounded-card border border-border bg-surface p-5">
        <h2 className="text-sm font-semibold text-ink">
          Task · Commit · Evidence Timeline
        </h2>
        <p className="mt-1 text-xs text-ink-faint">
          Static evidence timelines are empty.
        </p>
        <div className="mt-4 rounded-xl border border-dashed border-border-soft px-4 py-6 text-center text-xs text-ink-faint">
          No task-to-commit evidence links are defined yet.
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">
            Task · Commit · Evidence Timeline
          </h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            Why a task is done or ready, with commit proof and next action.
          </p>
        </div>
      </div>

      <ol className="mt-4 space-y-3">
        {items.map((item, index) => {
          const task = getTaskById(item.taskId);
          const isLast = index === items.length - 1;
          return (
            <li key={item.taskId} className="relative flex gap-3">
              {!isLast ? (
                <span
                  className="absolute left-[7px] top-5 h-full w-px bg-border"
                  aria-hidden
                />
              ) : null}

              <span
                className="relative mt-1 h-3.5 w-3.5 shrink-0 rounded-full ring-4 ring-surface bg-status-approved"
                aria-hidden
              />

              <div className="min-w-0 flex-1 rounded-xl border border-border-soft bg-surface-2/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-ink">
                      {task ? `${task.code} · ${task.title}` : item.taskId}
                    </span>
                    <span className="text-xs text-ink-muted">
                      {item.result}
                    </span>
                  </div>
                  {onSelectTask && (
                    <button
                      type="button"
                      onClick={() => onSelectTask(item.taskId)}
                      className="text-[11px] font-medium text-accent/80 hover:text-accent"
                    >
                      View task
                    </button>
                  )}
                </div>

                {item.commit ? (
                  <div className="mt-2 rounded-lg border border-border-soft bg-surface p-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-ink">
                        {item.commit.shortHash}
                      </span>
                      <span className="text-xs text-ink-muted">
                        {item.commit.category}
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                          RESULT_STYLES[item.commit.status] ??
                            RESULT_STYLES.archived,
                        )}
                      >
                        {item.commit.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-ink">{item.commit.message}</p>
                    <p className="mt-0.5 text-xs text-ink-faint">
                      {item.commit.relatedTaskOrStage}
                    </p>
                  </div>
                ) : null}

                {item.evidence ? (
                  <div className="mt-2 rounded-lg border border-border-soft bg-surface p-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-xs font-semibold text-ink">
                          {item.evidence.title}
                        </p>
                        <p className="text-[11px] text-ink-faint">
                          {item.evidence.sourceType} ·{" "}
                          {item.evidence.relatedTaskOrStage}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                          RESULT_STYLES[item.evidence.status] ??
                            RESULT_STYLES.archived,
                        )}
                      >
                        {item.evidence.status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-ink-muted">
                      {item.evidence.proofSummary}
                    </p>
                  </div>
                ) : null}

                <div className="mt-2 rounded-lg border border-border-soft bg-surface p-2.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                    Next action
                  </p>
                  <p className="mt-1 text-xs text-ink">{item.nextAction}</p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
