import { cn } from "@/lib/utils";
import type { CommitEvidence } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  pushed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  deployed: "bg-agent-sky/15 text-agent-sky ring-agent-sky/30",
  archived: "bg-surface-2 text-ink-muted ring-border",
  clean: "bg-status-approved/15 text-status-approved ring-status-approved/30",
};

export function CommitEvidenceList({
  commits,
  onSelectTask,
  activeTaskId,
  selectedTaskId,
}: {
  commits: CommitEvidence[];
  onSelectTask?: (taskId: string) => void;
  activeTaskId?: string | null;
  selectedTaskId?: string | null;
}) {
  const active = selectedTaskId != null && activeTaskId === selectedTaskId;

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <h2 className="text-sm font-semibold text-ink">Commit Evidence History</h2>
      <p className="mt-1 text-xs text-ink-faint">
        Static commit proof for completed stages. Stage 4.17 is planned (recommended next) with no implementation evidence yet.
      </p>
      <ol className="mt-3 space-y-2.5">
        {commits.map((commit) => {
          const statusKey =
            (commit.status as keyof typeof STATUS_STYLES) ??
            ("archived" as keyof typeof STATUS_STYLES);
          return (
            <li
              key={commit.shortHash}
              className={cn(
                "rounded-xl border p-3",
                active
                  ? "border-accent/50 bg-accent/5"
                  : "border-border-soft",
              )}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-ink">
                    {commit.shortHash}
                  </span>
                  <span className="text-xs text-ink-muted">{commit.category}</span>
                </div>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                    STATUS_STYLES[statusKey] ?? STATUS_STYLES.archived,
                  )}
                >
                  {commit.status}
                </span>
              </div>
              <p className="mt-1 text-sm font-medium text-ink">{commit.message}</p>
              <p className="mt-1 text-xs text-ink-faint">
                {commit.relatedTaskOrStage}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                {commit.proofSummary}
              </p>
              {onSelectTask && activeTaskId ? (
                <button
                  type="button"
                  onClick={() => onSelectTask(activeTaskId)}
                  className="mt-2 text-[11px] font-medium text-accent/80 hover:text-accent"
                >
                  View related task
                </button>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
