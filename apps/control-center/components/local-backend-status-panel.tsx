import type { BackendHealthSnapshotView } from "@/lib/local-backend-types";

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

export function LocalBackendStatusPanel({
  snapshot,
}: {
  snapshot: BackendHealthSnapshotView;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
        <p className="text-xs font-semibold text-status-review">
          Stage 6.2 Foundation Ready
        </p>
        <p className="mt-1 text-[11px] text-ink-muted">
          This panel displays a static, deterministic mock of the local
          backend health snapshot. No fetch, socket, or timer is used here --
          the real boundary lives in scos/control_center/local_backend.py.
        </p>
      </div>

      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-ink">Local Backend</h3>
          <span className="rounded-full bg-status-approved/15 px-3 py-1 text-xs font-semibold text-status-approved ring-1 ring-inset ring-status-approved/30">
            {snapshot.backendStatus}
          </span>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <StatusRow label="Stage" value={snapshot.stage} />
          <StatusRow label="Active store" value={snapshot.activeStore} />
          <StatusRow label="Event stream" value={snapshot.eventStreamStatus} />
          <StatusRow
            label="Real adapter dispatch"
            value={snapshot.adapterDispatchStatus}
          />
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Enabled
            </p>
            <ul className="mt-1 space-y-1">
              {snapshot.capabilities.map((capability) => (
                <li
                  key={capability}
                  className="rounded-md bg-status-approved/10 px-2 py-1 text-[11px] text-status-approved"
                >
                  {capability}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Disabled
            </p>
            <ul className="mt-1 space-y-1">
              {snapshot.disabledCapabilities.map((capability) => (
                <li
                  key={capability}
                  className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-ink-faint"
                >
                  {capability}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
