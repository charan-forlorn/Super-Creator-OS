import type { OperatorCommandViewSnapshot } from "@/lib/operator-command-view-types";

export function ExecutionEvidenceSurfacePanel({
  snapshot,
}: {
  snapshot: OperatorCommandViewSnapshot;
}) {
  const blocked = snapshot.views.filter((view) =>
    view.execution.executionState.startsWith("blocked_"),
  );
  const terminal = snapshot.views.filter((view) => view.approval.terminal);

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-ink">Execution Evidence Surface</h3>
          <p className="mt-1 text-xs text-ink-muted">
            Terminal and blocked command instances stay visible without offering bypass actions.
          </p>
        </div>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          {terminal.length} terminal
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-border-soft bg-surface p-3">
          <h4 className="text-xs font-semibold text-ink">Blocked Evidence</h4>
          {blocked.length > 0 ? (
            <ul className="mt-2 space-y-1.5">
              {blocked.map((view) => (
                <li key={view.viewId} className="text-[11px] text-ink-muted">
                  <span className="font-medium text-ink">{view.commandId}</span>: {view.execution.executionState}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[11px] text-ink-faint">No blocked evidence in this fixture.</p>
          )}
        </div>

        <div className="rounded-lg border border-border-soft bg-surface p-3">
          <h4 className="text-xs font-semibold text-ink">Snapshot Notes</h4>
          <ul className="mt-2 space-y-1.5">
            {[...snapshot.blockers, ...snapshot.warnings].map((item) => (
              <li key={item} className="text-[11px] text-ink-muted">
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
