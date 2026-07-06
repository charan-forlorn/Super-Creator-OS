import type { UIStateSyncSnapshotView } from "@/lib/ui-state-sync-types";

export function SyncHealthPanel({
  snapshot,
}: {
  snapshot: UIStateSyncSnapshotView;
}) {
  const healthy = snapshot.blockers.length === 0 && snapshot.syncStatus === "ready";

  return (
    <div
      className={`rounded-card border p-3 ${
        healthy
          ? "border-dashed border-status-approved/40 bg-status-approved/5"
          : "border-dashed border-status-rejected/40 bg-status-rejected/5"
      }`}
    >
      <p
        className={`text-xs font-semibold ${
          healthy ? "text-status-approved" : "text-status-rejected"
        }`}
      >
        {healthy ? "Sync healthy" : "Sync blocked or stale"}
      </p>
      <p className="mt-1 text-[11px] text-ink-muted">
        Stage 6.4 foundation only -- this reads a static local snapshot, never
        a live connection. Disabled until a later stage: WebSocket, SSE,
        polling, real adapter dispatch.
      </p>

      {snapshot.blockers.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {snapshot.blockers.map((blocker) => (
            <li
              key={blocker}
              className="rounded-md bg-status-rejected/10 px-2 py-1 text-[11px] text-status-rejected"
            >
              {blocker}
            </li>
          ))}
        </ul>
      )}

      {snapshot.warnings.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {snapshot.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-md bg-status-review/10 px-2 py-1 text-[11px] text-status-review"
            >
              {warning}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
