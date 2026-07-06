import type { ManualCommandRunbookView } from "@/lib/operator-execution-types";
import { RunbookStepCard } from "./runbook-step-card";

export function ManualCommandRunbookPanel({
  runbook,
}: {
  runbook: ManualCommandRunbookView;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-ink">
            Manual Command Runbook
          </h3>
          <p className="mt-1 text-xs text-ink-faint">
            Ordered steps for the operator to run manually, outside SCOS.
            Nothing here executes; every step must be copied and run by a human.
          </p>
        </div>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] font-semibold text-ink-faint ring-1 ring-inset ring-border">
          {runbook.runbookType}
        </span>
      </div>

      <ol className="mt-3 space-y-2">
        {runbook.commandSteps.map((step) => (
          <RunbookStepCard key={step.stepId} step={step} />
        ))}
      </ol>

      {runbook.expectedOutputs.length > 0 ? (
        <div className="mt-3 rounded-lg border border-border-soft bg-surface-2/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Expected outputs
          </p>
          <ul className="mt-1 space-y-0.5">
            {runbook.expectedOutputs.map((output) => (
              <li key={output} className="text-[11px] text-ink-muted">
                • {output}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {runbook.operatorNotes.length > 0 ? (
        <div className="mt-3 rounded-lg border border-dashed border-border-soft bg-surface-2/30 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Operator notes
          </p>
          <ul className="mt-1 space-y-0.5">
            {runbook.operatorNotes.map((note) => (
              <li key={note} className="text-[11px] text-ink-faint">
                • {note}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
