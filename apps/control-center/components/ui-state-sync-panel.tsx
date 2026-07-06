import type { UIStateSyncSnapshotView } from "@/lib/ui-state-sync-types";

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border-soft bg-surface p-2.5">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
        {value}
      </span>
    </div>
  );
}

export function UIStateSyncPanel({
  snapshot,
}: {
  snapshot: UIStateSyncSnapshotView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">UI State Sync</h3>
        <span className="rounded-full bg-status-approved/15 px-3 py-1 text-xs font-semibold text-status-approved ring-1 ring-inset ring-status-approved/30">
          {snapshot.syncStatus}
        </span>
      </div>

      <p className="mt-1 text-[11px] text-ink-faint">
        Static local sync summary generated {snapshot.generatedAt} from{" "}
        {snapshot.stateSource}. No fetch, socket, or timer -- the real
        builder lives in scos/control_center/ui_state_sync.py.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <StatusRow label="Active stage" value={snapshot.activeStage} />
        <StatusRow label="Active task" value={snapshot.activeTask} />
        <StatusRow label="Backend status" value={snapshot.backendStatus} />
        <StatusRow
          label="Durable state status"
          value={snapshot.durableStateStatus}
        />
        <StatusRow label="Latest event" value={snapshot.latestEventId} />
        <StatusRow
          label="Latest sequence"
          value={String(snapshot.latestEventSequence)}
        />
      </div>

      {snapshot.pendingOperatorActions.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Pending operator actions
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {snapshot.pendingOperatorActions.map((action) => (
              <li
                key={action}
                className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-ink-faint"
              >
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
