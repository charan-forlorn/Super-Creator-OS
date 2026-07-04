import { cn } from "@/lib/utils";
import type { ProjectSnapshot } from "@/lib/types";

export function ProjectStateSnapshot({
  snapshot,
}: {
  snapshot: ProjectSnapshot;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-ink">Project State Snapshot</h2>
        <span className="text-[11px] text-ink-faint">
          Evidence-based current state
        </span>
      </div>

      <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        <SnapshotItem
          label="Current stage"
          value={snapshot.currentStage}
          accent
        />
        <SnapshotItem label="Latest completed stage" value={snapshot.latestCompletedStage} />
        <SnapshotItem label="Latest UI milestone" value={snapshot.latestUiMilestone} />
        <SnapshotItem
          label="Active blocker"
          value={snapshot.activeBlocker ?? "None"}
          accent={!snapshot.activeBlocker}
        />
        <SnapshotItem label="Repo state" value={snapshot.repoState} />
        <SnapshotItem label="Next action" value={snapshot.nextAction} accent />
      </div>
    </section>
  );
}

function SnapshotItem({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border-soft bg-surface-2/50 p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
        {label}
      </p>
      <p
        className={cn(
          "mt-1 text-sm font-medium",
          accent ? "text-ink" : "text-ink-muted",
        )}
      >
        {value}
      </p>
    </div>
  );
}
