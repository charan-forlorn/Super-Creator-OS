import { cn } from "@/lib/utils";
import type { ReviewArchiveEntry } from "@/lib/types";

const STATUS_STYLES: Record<ReviewArchiveEntry["status"], string> = {
  archived: "bg-surface-2 text-ink-muted ring-border",
  done: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  pushed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  // Evidence classes for unproven / not-yet-committed items.
  simulated: "bg-status-working/15 text-status-working ring-status-working/30",
  planned: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  draft: "bg-status-review/15 text-status-review ring-status-review/30",
};

export function ReviewArchive({ items }: { items: ReviewArchiveEntry[] }) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Review Archive</h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            Archived blockers, completion states, and replaced stale states.
          </p>
        </div>
        <span className="text-[11px] text-ink-faint">
          {items.length} archived entries
        </span>
      </div>

      <ul className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <li
            key={item.id}
            className="rounded-xl border border-border-soft bg-surface-2/60 p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">{item.label}</p>
                <p className="text-[11px] text-ink-faint">
                  {item.sourceType} · {item.relatedTaskOrStage}
                </p>
              </div>
              <span
                className={cn(
                  "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                  STATUS_STYLES[item.status] ?? STATUS_STYLES.archived,
                )}
              >
                {item.status}
              </span>
            </div>

            <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
              {item.proofSummary}
            </p>

            <div className="mt-2 rounded-lg border border-border-soft bg-surface p-2.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                Next action
              </p>
              <p className="mt-1 text-xs text-ink">{item.nextAction}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
