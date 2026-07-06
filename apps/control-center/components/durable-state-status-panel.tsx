import type { DurableStateStatusView } from "@/lib/durable-state-types";

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

export function DurableStateStatusPanel({
  status,
}: {
  status: DurableStateStatusView;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
        <p className="text-xs font-semibold text-status-review">
          Stage 6.3 Durable State Foundation
        </p>
        <p className="mt-1 text-[11px] text-ink-muted">
          This panel displays a static, deterministic mock of the local
          SQLite WAL state store status. No fetch, socket, or timer is used
          here -- the real store lives in
          scos/control_center/sqlite_state_store.py.
        </p>
      </div>

      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">Durable State Store</h3>
          <span className="rounded-full bg-status-approved/15 px-3 py-1 text-xs font-semibold text-status-approved ring-1 ring-inset ring-status-approved/30">
            {status.storeStatus}
          </span>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <StatusRow label="Stage" value={status.stage} />
          <StatusRow label="Database path" value={status.dbPath} />
          <StatusRow label="WAL mode" value={status.walMode} />
          <StatusRow label="Event stream" value={status.eventStreamStatus} />
          <StatusRow
            label="Real adapter dispatch"
            value={status.adapterDispatchStatus}
          />
          <StatusRow
            label="Backend socket server"
            value={status.backendSocketServerStatus}
          />
        </div>
      </div>
    </div>
  );
}
