import type {
  RunbookCommandStepView,
  RunbookRiskLevel,
} from "@/lib/operator-execution-types";

const RISK_STYLES: Record<RunbookRiskLevel, string> = {
  low: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  medium: "bg-status-review/15 text-status-review ring-status-review/30",
  high: "bg-status-working/15 text-status-working ring-status-working/30",
  critical: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function RunbookStepCard({ step }: { step: RunbookCommandStepView }) {
  return (
    <li className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-ink">
          <span className="mr-1.5 font-mono text-ink-faint">
            {step.stepOrder}.
          </span>
          {step.title}
        </p>
        <div className="flex items-center gap-1.5 text-[10px] font-semibold">
          <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-ink-faint ring-1 ring-inset ring-border">
            {step.commandType}
          </span>
          <span
            className={`rounded-full px-2 py-0.5 ring-1 ring-inset ${RISK_STYLES[step.riskLevel]}`}
          >
            {step.riskLevel}
          </span>
        </div>
      </div>

      <pre className="mt-2 overflow-auto rounded border border-border-soft bg-surface p-2 font-mono text-[11px] text-ink">
{step.command}
      </pre>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] font-medium text-ink-faint">
        <span className="rounded bg-surface px-1.5 py-0.5 ring-1 ring-inset ring-border">
          shell: {step.shell}
        </span>
        <span className="rounded bg-surface px-1.5 py-0.5 font-mono ring-1 ring-inset ring-border">
          cwd: {step.workingDirectory}
        </span>
        {step.requiresManualCopy ? (
          <span className="rounded bg-status-review/15 px-1.5 py-0.5 text-status-review ring-1 ring-inset ring-status-review/30">
            Manual copy required
          </span>
        ) : null}
        {step.requiresOperatorConfirmation ? (
          <span className="rounded bg-status-review/15 px-1.5 py-0.5 text-status-review ring-1 ring-inset ring-status-review/30">
            Operator confirmation required
          </span>
        ) : null}
      </div>

      {step.expectedResultHint ? (
        <p className="mt-2 text-[11px] text-ink-muted">
          <span className="font-semibold text-ink-faint">Expected: </span>
          {step.expectedResultHint}
        </p>
      ) : null}

      {/* Inert. SCOS never copies to the clipboard; the operator copies the
          command block above manually and runs it outside SCOS. */}
      <p className="mt-2 text-[10px] text-ink-faint">
        Copy manually from the command block above — SCOS does not touch your
        clipboard or run this command.
      </p>
    </li>
  );
}
