import type { EventStreamSnapshotView } from "@/lib/event-stream-types";

const STATUS_TONE: Record<string, string> = {
  queued: "bg-surface-2 text-ink-faint",
  working: "bg-status-review/15 text-status-review",
  ready: "bg-status-approved/15 text-status-approved",
  blocked: "bg-status-rejected/15 text-status-rejected",
  approved: "bg-status-approved/15 text-status-approved",
  rejected: "bg-status-rejected/15 text-status-rejected",
  completed: "bg-status-approved/15 text-status-approved",
  failed: "bg-status-rejected/15 text-status-rejected",
  stale: "bg-status-review/15 text-status-review",
  unknown: "bg-surface-2 text-ink-faint",
};

export function EventStreamPanel({
  snapshot,
}: {
  snapshot: EventStreamSnapshotView;
}) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">Event Stream (local snapshot)</h3>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          cursor {snapshot.cursor}
        </span>
      </div>

      <p className="mt-1 text-[11px] text-ink-faint">
        Deterministic cursor-based batch of {snapshot.eventCount} local
        event{snapshot.eventCount === 1 ? "" : "s"}, generated {snapshot.generatedAt}.
        No WebSocket, SSE, or polling is used here -- the real projection lives
        in scos/control_center/event_stream_snapshot.py.
      </p>

      <ol className="mt-3 space-y-1.5">
        {snapshot.events.map((event) => (
          <li
            key={`${event.sequence}-${event.eventId}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border-soft bg-surface p-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium text-ink">
                #{event.sequence} · {event.eventType}
              </p>
              <p className="truncate text-[11px] text-ink-faint">
                {event.entityType}:{event.entityId} · {event.occurredAt}
              </p>
            </div>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                STATUS_TONE[event.status] ?? STATUS_TONE.unknown
              }`}
            >
              {event.status}
            </span>
          </li>
        ))}
      </ol>

      {snapshot.warnings.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Warnings
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {snapshot.warnings.map((warning) => (
              <li
                key={warning}
                className="rounded-md bg-status-review/10 px-2 py-1 text-[11px] text-status-review"
              >
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
