import { getSignalTone } from "@/lib/operator-read-surface-projection";
import type { ReadSurfaceCoherenceSummary } from "@/lib/operator-read-surface-types";

export function ReadSurfaceCoherenceCard({
  coherence,
}: {
  coherence: ReadSurfaceCoherenceSummary;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">
            Read Surface Coherence
          </h3>
          <p className="mt-1 text-[11px] text-ink-faint">
            Checked at {coherence.checkedAt}
          </p>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${getSignalTone(coherence.status)}`}
        >
          {coherence.status}
        </span>
      </div>

      <div className="mt-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Inspected sources
        </p>
        <ul className="mt-1 flex flex-wrap gap-1.5">
          {coherence.inspectedSources.map((source) => (
            <li
              key={source}
              className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-ink-muted"
            >
              {source}
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Blockers
          </p>
          <ul className="mt-1 space-y-1">
            {(coherence.blockers.length > 0 ? coherence.blockers : ["None"]).map(
              (blocker) => (
                <li
                  key={blocker}
                  className="rounded-md bg-status-rejected/10 px-2 py-1 text-[11px] text-status-rejected"
                >
                  {blocker}
                </li>
              ),
            )}
          </ul>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Warnings
          </p>
          <ul className="mt-1 space-y-1">
            {(coherence.warnings.length > 0 ? coherence.warnings : ["None"]).map(
              (warning) => (
                <li
                  key={warning}
                  className="rounded-md bg-status-review/10 px-2 py-1 text-[11px] text-status-review"
                >
                  {warning}
                </li>
              ),
            )}
          </ul>
        </div>
      </div>

      <p className="mt-3 rounded-lg border border-dashed border-status-review/40 bg-status-review/5 p-3 text-[11px] text-ink-muted">
        {coherence.fallbackModeNote}
      </p>
    </div>
  );
}
