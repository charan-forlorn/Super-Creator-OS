import type { CommitPlan } from "@/lib/types";

export function CommitPlanPreview({ plan }: { plan: CommitPlan }) {
  return (
    <section className="rounded-xl border border-border-soft bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">Commit Plan Preview</h3>

      <div className="mt-3 rounded-lg border border-border-soft bg-surface-2/50 p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Recommended commit message
        </p>
        <p className="mt-1 font-mono text-sm text-ink">{plan.recommendedMessage}</p>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Would-be staged files
          </p>
          <ul className="mt-2 space-y-1">
            {plan.stagedFiles.map((file) => (
              <li key={file} className="truncate font-mono text-xs text-ink-muted">
                {file}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Scope and risk
          </p>
          <p className="mt-2 text-sm text-ink-muted">{plan.scope}</p>
          <ul className="mt-2 space-y-1">
            {plan.riskNotes.map((note) => (
              <li key={note} className="text-xs text-ink-faint">
                {note}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="mt-3 rounded-lg border border-status-working/30 bg-status-working/10 px-3 py-2 text-xs font-medium text-status-working">
        {plan.reminder}
      </p>
    </section>
  );
}
