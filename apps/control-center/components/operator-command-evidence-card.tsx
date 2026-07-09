import { ApprovalStateBadge } from "./approval-state-badge";
import type { OperatorCommandView } from "@/lib/operator-command-view-types";

function EvidenceList({ view }: { view: OperatorCommandView }) {
  const refs = view.approval.evidenceReferences;
  if (refs.length === 0) {
    return <p className="text-[11px] text-ink-faint">No evidence references in this fixture.</p>;
  }
  return (
    <ul className="mt-2 space-y-1.5">
      {refs.map((ref) => (
        <li key={ref.referenceId} className="rounded-md bg-surface-2 px-2 py-1.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] font-medium text-ink">{ref.referenceType}</span>
            <span className="text-[10px] text-ink-faint">
              {ref.exists && ref.readable ? "readable" : "missing"}
            </span>
          </div>
          <p className="mt-1 break-all text-[10px] text-ink-faint">{ref.path}</p>
        </li>
      ))}
    </ul>
  );
}

export function OperatorCommandEvidenceCard({ view }: { view: OperatorCommandView }) {
  const hints = [...view.blockers, ...view.warnings];
  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate text-sm font-semibold text-ink">{view.commandId}</h4>
          <p className="mt-1 text-[11px] text-ink-faint">{view.commandType}</p>
        </div>
        <ApprovalStateBadge state={view.approval.approvalState} />
      </div>

      <div className="mt-3 grid gap-2 text-[11px] text-ink-muted sm:grid-cols-3">
        <div className="rounded-md bg-surface-2 px-2 py-1.5">
          <span className="block text-ink-faint">execution</span>
          <span className="font-medium text-ink">{view.execution.executionState}</span>
        </div>
        <div className="rounded-md bg-surface-2 px-2 py-1.5">
          <span className="block text-ink-faint">audit</span>
          <span className="font-medium text-ink">{view.execution.auditState}</span>
        </div>
        <div className="rounded-md bg-surface-2 px-2 py-1.5">
          <span className="block text-ink-faint">terminal</span>
          <span className="font-medium text-ink">{view.approval.terminal ? "yes" : "no"}</span>
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-ink-muted">
        {view.execution.summary}
      </p>
      <p className="mt-2 rounded-md border border-border-soft bg-surface px-2 py-1.5 text-[11px] text-ink-muted">
        {view.nextManualAction}
      </p>

      {hints.length > 0 ? (
        <ul className="mt-3 space-y-1">
          {hints.map((hint) => (
            <li key={hint} className="rounded-md bg-status-review/10 px-2 py-1 text-[11px] text-status-review">
              {hint}
            </li>
          ))}
        </ul>
      ) : null}

      <EvidenceList view={view} />
    </article>
  );
}
