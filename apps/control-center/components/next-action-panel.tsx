import { cn, getAgentById } from "@/lib/utils";
import type { NextAction } from "@/lib/types";

const URGENCY_STYLES: Record<NextAction["urgency"], string> = {
  low: "bg-status-idle/15 text-ink-muted ring-status-idle/25",
  medium: "bg-status-working/15 text-status-working ring-status-working/30",
  high: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

const ACTIONS = ["Copy Prompt", "Paste Result", "Send to Review", "Hold"];

export function NextActionPanel({ action }: { action: NextAction }) {
  const owner = getAgentById(action.owner);

  return (
    <section className="rounded-card border border-accent/35 bg-gradient-to-br from-surface-2 to-surface p-5 shadow-lg shadow-accent/5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-ink">Next Action</h2>
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ring-inset",
                URGENCY_STYLES[action.urgency],
              )}
            >
              {action.urgency} urgency
            </span>
          </div>

          <p className="mt-2 text-lg font-semibold leading-tight text-ink">
            {action.title}
          </p>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-muted">
            {action.recommendedAction}
          </p>
        </div>

        <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[28rem]">
          {ACTIONS.map((label) => (
            <button
              key={label}
              type="button"
              disabled
              aria-disabled
              title="Disabled in prototype"
              className="cursor-not-allowed rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs font-medium text-ink-muted opacity-60"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <dl className="mt-5 grid gap-3 text-sm md:grid-cols-3">
        <div className="rounded-xl border border-border-soft bg-surface/70 p-3">
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Owning agent
          </dt>
          <dd className="mt-1 font-medium text-ink">
            {owner ? owner.name : action.owner}
          </dd>
        </div>
        <div className="rounded-xl border border-border-soft bg-surface/70 p-3">
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Source item
          </dt>
          <dd className="mt-1 font-medium text-ink">{action.sourceItem}</dd>
        </div>
        <div className="rounded-xl border border-border-soft bg-surface/70 p-3">
          <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Reason
          </dt>
          <dd className="mt-1 text-ink-muted">{action.reason}</dd>
        </div>
      </dl>
    </section>
  );
}
