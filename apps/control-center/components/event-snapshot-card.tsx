import type { EventStreamSnapshotView } from "@/lib/event-stream-types";

function CountRow({ counts }: { counts: Record<string, number> }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {Object.entries(counts).map(([key, value]) => (
        <li
          key={key}
          className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-ink-faint"
        >
          {key}: {value}
        </li>
      ))}
    </ul>
  );
}

export function EventSnapshotCard({
  snapshot,
}: {
  snapshot: EventStreamSnapshotView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Snapshot Metadata</h3>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          schema v{snapshot.schemaVersion}
        </span>
      </div>

      <p className="mt-2 truncate text-[11px] text-ink-faint" title={snapshot.snapshotId}>
        {snapshot.snapshotId}
      </p>

      <div className="mt-3 space-y-2">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            By status
          </p>
          <div className="mt-1">
            <CountRow counts={snapshot.statusCounts} />
          </div>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            By source
          </p>
          <div className="mt-1">
            <CountRow counts={snapshot.sourceCounts} />
          </div>
        </div>
      </div>
    </div>
  );
}
