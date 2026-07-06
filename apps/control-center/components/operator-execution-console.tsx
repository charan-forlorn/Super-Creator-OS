import type {
  OperatorExecutionConsoleRow,
  RunbookStatus,
} from "@/lib/operator-execution-types";
import { formatTimestamp } from "@/lib/utils";
import { CommandResultCapturePanel } from "./command-result-capture-panel";
import { ExecutionSafetyChecklist } from "./execution-safety-checklist";
import { ManualCommandRunbookPanel } from "./manual-command-runbook-panel";

const STATUS_STYLES: Record<RunbookStatus, string> = {
  drafted: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  ready_for_operator: "bg-status-review/15 text-status-review ring-status-review/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  executed_manually: "bg-status-working/15 text-status-working ring-status-working/30",
  result_captured: "bg-status-working/15 text-status-working ring-status-working/30",
  verified: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  failed: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  archived: "bg-surface-2 text-ink-faint ring-border",
};

function BoundaryBanner() {
  return (
    <div className="rounded-card border border-dashed border-status-review/40 bg-status-review/5 p-3">
      <p className="text-xs font-semibold text-status-review">
        SCOS is not executing these commands.
      </p>
      <ul className="mt-1 space-y-0.5 text-[11px] text-ink-muted">
        <li>• The operator runs every command manually, outside SCOS.</li>
        <li>• Approval is required before any command may be used.</li>
        <li>• Push approval is separate from commit approval.</li>
        <li>• Results must be pasted back manually to classify the outcome.</li>
        <li>• Blocked / failed results route back to review.</li>
      </ul>
    </div>
  );
}

function ConsoleRow({ row }: { row: OperatorExecutionConsoleRow }) {
  const { runbook, capture, outcome } = row;
  const passedChecks = runbook.safetyChecks.filter((c) => c.status === "passed").length;
  const source =
    runbook.sourceCommitProposalId ??
    runbook.sourcePushProposalId ??
    runbook.sourceApprovalId ??
    "none";

  return (
    <article className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">{runbook.title}</h3>
          <p className="mt-1 text-xs text-ink-muted">{runbook.objective}</p>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATUS_STYLES[runbook.status]}`}
        >
          {runbook.status}
        </span>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
        <div>
          <dt className="font-semibold uppercase tracking-wide text-ink-faint">Runbook</dt>
          <dd className="mt-0.5 truncate font-mono text-ink-muted">{runbook.runbookId}</dd>
        </div>
        <div>
          <dt className="font-semibold uppercase tracking-wide text-ink-faint">Source approval</dt>
          <dd className="mt-0.5 truncate font-mono text-ink-muted">{source}</dd>
        </div>
        <div>
          <dt className="font-semibold uppercase tracking-wide text-ink-faint">Safety</dt>
          <dd className="mt-0.5 text-ink-muted">
            {passedChecks}/{runbook.safetyChecks.length} passed
          </dd>
        </div>
        <div>
          <dt className="font-semibold uppercase tracking-wide text-ink-faint">Capture</dt>
          <dd className="mt-0.5 text-ink-muted">
            {capture ? capture.verdict : "not captured"}
          </dd>
        </div>
      </dl>

      <div className="mt-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
          Command summary
        </p>
        <pre className="mt-1 overflow-auto rounded border border-border-soft bg-surface-2/50 p-2 font-mono text-[11px] text-ink">
{runbook.commandSummary}
        </pre>
      </div>

      {runbook.blockedReasons.length > 0 ? (
        <div className="mt-2 rounded-lg border border-status-blocked/30 bg-status-blocked/5 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-status-blocked">
            Blocked — operator review required
          </p>
          <ul className="mt-1 space-y-0.5">
            {runbook.blockedReasons.map((reason) => (
              <li key={reason} className="text-[11px] text-ink-muted">
                • {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="mt-2 text-[10px] text-ink-faint">
        created {formatTimestamp(runbook.createdAt)}
        {outcome ? ` · outcome ${outcome.outcome}` : ""}
      </p>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <ManualCommandRunbookPanel runbook={runbook} />
        <ExecutionSafetyChecklist checks={runbook.safetyChecks} />
      </div>

      <div className="mt-3">
        <CommandResultCapturePanel capture={capture} outcome={outcome} />
      </div>
    </article>
  );
}

export function OperatorExecutionConsole({
  rows,
}: {
  rows: readonly OperatorExecutionConsoleRow[];
}) {
  return (
    <section className="space-y-3">
      <BoundaryBanner />
      {rows.map((row) => (
        <ConsoleRow key={row.runbook.runbookId} row={row} />
      ))}
    </section>
  );
}
