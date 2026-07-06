import type { CommandApiActionView } from "@/lib/local-backend-types";
import { BackendResponseCard } from "./backend-response-card";

function ActionCard({ action }: { action: CommandApiActionView }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <p className="text-sm font-semibold text-ink">{action.label}</p>
      <p className="mt-1 text-[11px] text-ink-muted">{action.description}</p>

      <div className="mt-3 rounded-md bg-surface-2 p-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
          Request
        </p>
        <p className="mt-1 text-[11px] text-ink-muted">
          {action.request.requestType} · operator: {action.request.operatorId}
        </p>
        {Object.keys(action.request.payload).length > 0 ? (
          <p className="mt-0.5 text-[11px] text-ink-faint">
            payload:{" "}
            {Object.entries(action.request.payload)
              .map(([key, value]) => `${key}=${value}`)
              .join(", ")}
          </p>
        ) : null}
      </div>

      <div className="mt-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
          Response
        </p>
        <div className="mt-1">
          <BackendResponseCard response={action.response} />
        </div>
      </div>
    </div>
  );
}

export function CommandApiPanel({
  actions,
  rejectedExample,
}: {
  actions: CommandApiActionView[];
  rejectedExample: CommandApiActionView;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
        <p className="text-xs font-semibold text-status-review">
          Operator approval required for real execution.
        </p>
        <ul className="mt-1 space-y-0.5 text-[11px] text-ink-muted">
          <li>• These four actions preview, validate, or dry-run only -- none execute a command.</li>
          <li>• Real queueing/execution still requires the Stage 5.1 draft -&gt; validate -&gt; operator approval -&gt; queue -&gt; runner pipeline.</li>
          <li>• Contracts live in scos/control_center/command_api.py and local_backend.py.</li>
        </ul>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {actions.map((action) => (
          <ActionCard key={action.id} action={action} />
        ))}
      </div>

      <div>
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Rejected example
        </p>
        <div className="mt-2">
          <ActionCard action={rejectedExample} />
        </div>
      </div>
    </div>
  );
}
