import { cn, getTaskById } from "@/lib/utils";
import type { EvidenceCard } from "@/lib/types";

const STATUS_STYLES: Record<EvidenceCard["status"], string> = {
  done: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  pushed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  deployed: "bg-agent-sky/15 text-agent-sky ring-agent-sky/30",
  clean: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  archived: "bg-surface-2 text-ink-muted ring-border",
  // Evidence classes for unproven / not-yet-committed items.
  simulated: "bg-status-working/15 text-status-working ring-status-working/30",
  planned: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  draft: "bg-status-review/15 text-status-review ring-status-review/30",
};

export function EvidenceCards({ items }: { items: EvidenceCard[] }) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Evidence Cards</h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            Static proof for review, merge, and deploy decisions.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => {
          const task = getTaskById(
            item.relatedTaskOrStage?.toLowerCase().startsWith("task-")
              ? item.relatedTaskOrStage
              : null,
          );
          return (
            <div
              key={item.id}
              className="rounded-xl border border-border-soft bg-surface-2/60 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink">{item.title}</p>
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

              <p className="mt-2 text-xs leading-relaxed text-ink-muted">
                {item.proofSummary}
              </p>

              <div className="mt-3 rounded-lg border border-border-soft bg-surface p-2.5">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                  Next action
                </p>
                <p className="mt-1 text-xs text-ink">{item.nextAction}</p>
              </div>

              <div className="mt-2 text-[11px] text-ink-faint">
                {task ? (
                  <>
                    Related task:{" "}
                    <button
                      type="button"
                      onClick={() => {
                        const el = document.getElementById(
                          task.stage.toLowerCase().replace(/\./g, "-"),
                        );
                        if (el) el.scrollIntoView({ behavior: "smooth" });
                      }}
                      className="text-accent/80 hover:text-accent"
                    >
                      {task.code}
                    </button>
                  </>
                ) : (
                  <>Related task: {item.relatedTaskOrStage}</>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
