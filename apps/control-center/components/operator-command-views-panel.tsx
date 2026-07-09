import { OperatorCommandEvidenceCard } from "./operator-command-evidence-card";
import type { OperatorCommandViewSnapshot } from "@/lib/operator-command-view-types";

export function OperatorCommandViewsPanel({
  snapshot,
}: {
  snapshot: OperatorCommandViewSnapshot;
}) {
  const totalItems = [
    ["pending", snapshot.totals.pending],
    ["approved", snapshot.totals.approved],
    ["denied", snapshot.totals.denied],
    ["missing", snapshot.totals.missingApproval],
    ["executed", snapshot.totals.executed],
    ["blocked", snapshot.totals.blocked],
    ["audited", snapshot.totals.audited],
  ];

  return (
    <div className="space-y-4">
      <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
        <p className="text-xs font-semibold text-status-review">Read-Only Evidence Surface</p>
        <p className="mt-1 text-[11px] text-ink-muted">
          Static deterministic Stage 7.6 data. Operator decisions and command running remain outside this panel.
        </p>
      </div>

      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-ink">Approval-Aware Command Views</h3>
            <p className="mt-1 text-[11px] text-ink-faint">
              {snapshot.checkedAt} · {snapshot.goNoGo} · readiness {snapshot.readinessScore}
            </p>
          </div>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
            {snapshot.views.length} views
          </span>
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-4 xl:grid-cols-7">
          {totalItems.map(([label, value]) => (
            <div key={label} className="rounded-lg border border-border-soft bg-surface p-2">
              <p className="text-[10px] uppercase text-ink-faint">{label}</p>
              <p className="mt-1 text-lg font-semibold text-ink">{value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {snapshot.views.map((view) => (
          <OperatorCommandEvidenceCard key={view.viewId} view={view} />
        ))}
      </div>
    </div>
  );
}
