import type {
  CaptureVerdict,
  CommandExecutionCaptureView,
  OperatorExecutionOutcomeView,
} from "@/lib/operator-execution-types";
import { formatTimestamp } from "@/lib/utils";

const VERDICT_STYLES: Record<CaptureVerdict, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  PASS_WITH_WARNINGS: "bg-status-review/15 text-status-review ring-status-review/30",
  NEEDS_REVIEW: "bg-status-review/15 text-status-review ring-status-review/30",
  NEEDS_FIX: "bg-status-working/15 text-status-working ring-status-working/30",
  BLOCKED: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  UNKNOWN: "bg-surface-2 text-ink-faint ring-border",
};

export function CommandResultCapturePanel({
  capture,
  outcome,
}: {
  capture: CommandExecutionCaptureView | null;
  outcome: OperatorExecutionOutcomeView | null;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">
            Command Result Capture
          </h3>
          <p className="mt-1 text-xs text-ink-faint">
            The operator pastes the command output back here manually. SCOS does
            not read the terminal, the clipboard, or the process exit code.
          </p>
        </div>
        {capture ? (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${VERDICT_STYLES[capture.verdict]}`}
          >
            {capture.verdict}
          </span>
        ) : null}
      </div>

      {capture ? (
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Operator-reported command
            </p>
            <pre className="mt-1 overflow-auto rounded border border-border-soft bg-surface-2/50 p-2 font-mono text-[11px] text-ink">
{capture.operatorReportedCommand}
            </pre>
          </div>

          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Pasted output summary
            </p>
            <p className="mt-1 text-[11px] text-ink-muted">
              {capture.pastedOutputSummary}
            </p>
          </div>

          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Raw output excerpt
            </p>
            <pre className="mt-1 max-h-40 overflow-auto rounded border border-border-soft bg-surface-2/50 p-2 font-mono text-[11px] text-ink-muted">
{capture.rawOutputExcerpt}
            </pre>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[10px] font-medium text-ink-faint">
            <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono ring-1 ring-inset ring-border">
              {capture.exitStatusText}
            </span>
            <span className="rounded bg-surface-2 px-1.5 py-0.5 ring-1 ring-inset ring-border">
              captured {formatTimestamp(capture.capturedAt)}
            </span>
          </div>

          {capture.warnings.length > 0 ? (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-status-review">
                Warnings
              </p>
              <ul className="mt-1 space-y-0.5">
                {capture.warnings.map((w) => (
                  <li key={w} className="text-[11px] text-ink-muted">
                    • {w}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {capture.blockers.length > 0 ? (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-status-blocked">
                Blockers
              </p>
              <ul className="mt-1 space-y-0.5">
                {capture.blockers.map((b) => (
                  <li key={b} className="text-[11px] text-ink-muted">
                    • {b}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {capture.evidencePaths.length > 0 ? (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
                Evidence paths
              </p>
              <ul className="mt-1 space-y-0.5">
                {capture.evidencePaths.map((p) => (
                  <li key={p} className="truncate font-mono text-[11px] text-ink-muted">
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 rounded-lg bg-surface-2/40 px-3 py-2 text-[11px] text-ink-faint">
          No result has been captured yet. Run the runbook manually, then paste
          the output back to classify the outcome.
        </p>
      )}

      {outcome ? (
        <div className="mt-3 rounded-lg border border-border-soft bg-surface-2/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Next action
          </p>
          <p className="mt-1 text-xs text-ink">
            <span className="font-semibold">{outcome.recommendedNextAction}</span>
            {outcome.recommendedNextAgent ? (
              <>
                {" "}→ <span className="font-mono">{outcome.recommendedNextAgent}</span>
              </>
            ) : null}
          </p>
          {outcome.operatorReviewRequired ? (
            <p className="mt-1 text-[11px] text-status-review">
              Operator review required before proceeding.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
