import { cn } from "@/lib/utils";
import type {
  ProjectStateUpdateView,
  StageStatus,
  TaskStatus,
} from "@/lib/result-intake-types";

const TASK_STATUS_STYLES: Record<TaskStatus, string> = {
  planning: "bg-status-idle/15 text-ink-muted ring-status-idle/25",
  implementation_done: "bg-accent/15 text-accent ring-accent/30",
  review_required: "bg-status-review/15 text-status-review ring-status-review/30",
  needs_fix: "bg-status-working/15 text-status-working ring-status-working/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  ready_for_commit: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  done: "bg-status-approved/10 text-status-approved/80 ring-status-approved/20",
};

const STAGE_STATUS_STYLES: Record<StageStatus, string> = {
  active: "bg-accent/15 text-accent ring-accent/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  needs_review: "bg-status-review/15 text-status-review ring-status-review/30",
  ready_for_next_stage: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  complete: "bg-status-approved/10 text-status-approved/80 ring-status-approved/20",
};

export function ProjectStateUpdatePanel({ update }: { update: ProjectStateUpdateView }) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Project State Update</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Derived from the selected intake — local bookkeeping only, never mutates Stage
            4/5.1-5.6 records directly.
          </p>
        </div>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
          {update.stateUpdateId}
        </span>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Stage
          </p>
          <p className="mt-1 text-xs text-ink">
            {update.previousStage} <span className="text-ink-faint">→</span> {update.currentStage}
          </p>
          <span
            className={cn(
              "mt-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
              STAGE_STATUS_STYLES[update.stageStatus],
            )}
          >
            {update.stageStatus.replace(/_/g, " ")}
          </span>
        </div>

        <div className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Task Status
          </p>
          <p className="mt-1 text-xs text-ink">{update.taskId}</p>
          <span
            className={cn(
              "mt-2 inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
              TASK_STATUS_STYLES[update.taskStatus],
            )}
          >
            {update.taskStatus.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      <p className="mt-3 rounded bg-surface-2/40 px-3 py-2 text-xs text-ink-muted">
        {update.summary}
      </p>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
        <span>
          Latest agent: <span className="font-semibold text-ink">{update.latestAgent}</span>
        </span>
        <span>·</span>
        <span>
          Latest verdict: <span className="font-semibold text-ink">{update.latestVerdict}</span>
        </span>
      </div>

      {update.evidenceRefs.length ? (
        <div className="mt-3 rounded bg-surface-2/40 px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Evidence references
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] text-ink-muted">
            {update.evidenceRefs.map((ref) => (
              <li key={ref}>{ref}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
