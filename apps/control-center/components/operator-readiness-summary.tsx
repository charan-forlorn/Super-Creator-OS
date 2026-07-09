import { getReadinessTone } from "@/lib/operator-read-surface-projection";
import type { OperatorReadinessSummary } from "@/lib/operator-read-surface-types";

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg border border-border-soft bg-surface p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}

export function OperatorReadinessSummary({
  summary,
}: {
  summary: OperatorReadinessSummary;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">
            Operator Readiness Summary
          </h3>
          <p className="mt-1 text-[11px] text-ink-faint">
            Checked at {summary.checkedAt}
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${getReadinessTone(summary)}`}
        >
          {summary.goNoGo} - {summary.readinessScore}
        </span>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Health signals" value={summary.totalHealthSignals} />
        <Metric label="Blockers" value={summary.blockersCount} />
        <Metric label="Warnings" value={summary.warningsCount} />
        <Metric label="Degraded / stale" value={summary.degradedOrStaleCount} />
      </div>
    </div>
  );
}
