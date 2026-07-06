import type { DurableStateSnapshotView } from "@/lib/durable-state-types";

function CountTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border-soft bg-surface p-2.5 text-center">
      <p className="text-lg font-semibold text-ink">{value}</p>
      <p className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</p>
    </div>
  );
}

export function StateSnapshotPanel({
  snapshot,
}: {
  snapshot: DurableStateSnapshotView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">State Snapshot</h3>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          checked {snapshot.checkedAt}
        </span>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border-soft bg-surface p-2.5">
          <span className="text-xs text-ink-muted">DB mode</span>
          <span className="rounded-full bg-status-approved/15 px-2 py-0.5 text-[10px] font-medium text-status-approved">
            {snapshot.dbMode}
          </span>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-border-soft bg-surface p-2.5">
          <span className="text-xs text-ink-muted">WAL enabled</span>
          <span className="rounded-full bg-status-approved/15 px-2 py-0.5 text-[10px] font-medium text-status-approved">
            {snapshot.walEnabled ? "true" : "false"}
          </span>
        </div>
      </div>

      <p className="mt-3 truncate text-[11px] text-ink-faint" title={snapshot.dbPath}>
        {snapshot.dbPath}
      </p>

      <div className="mt-3 grid grid-cols-5 gap-2">
        <CountTile label="Commands" value={snapshot.counts.commands} />
        <CountTile label="Sessions" value={snapshot.counts.sessions} />
        <CountTile label="Events" value={snapshot.counts.events} />
        <CountTile label="Approvals" value={snapshot.counts.approvals} />
        <CountTile label="Results" value={snapshot.counts.results} />
      </div>

      <div className="mt-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Disabled until later stages
        </p>
        <ul className="mt-1 flex flex-wrap gap-1.5">
          {Object.entries(snapshot.disabledCapabilities).map(([capability]) => (
            <li
              key={capability}
              className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-ink-faint"
            >
              {capability}
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-3 text-[11px] text-ink-muted">
        Next stage: {snapshot.nextStage}
      </p>
    </div>
  );
}
