import type { OperatorActivityRecord } from "@/lib/operator-read-surface-types";
import { getSignalTone } from "@/lib/operator-read-surface-projection";

export function OperatorActivityFeed({
  records,
}: {
  records: OperatorActivityRecord[];
}) {
  if (records.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-ink">Recent Activity</h3>
        <p className="mt-2 text-xs text-ink-muted">
          No operator read surface activity is present in this deterministic
          projection.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">Recent Activity</h3>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink-faint">
          {records.length} records
        </span>
      </div>

      <ol className="mt-3 space-y-2">
        {records.map((record) => (
          <li
            key={record.activityId}
            className="rounded-lg border border-border-soft bg-surface p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-ink">
                  {record.activityType}
                </p>
                <p className="text-[11px] text-ink-faint">
                  {record.occurredAt} - {record.sourceStage}
                </p>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${getSignalTone(record.status)}`}
              >
                {record.status}
              </span>
            </div>
            <p className="mt-2 text-xs text-ink-muted">{record.summary}</p>
            <p className="mt-1 text-[11px] text-ink-faint">
              Reference: {record.referenceLabel}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}
