import type {
  ExecutionSafetyCheckView,
  SafetyCheckSeverity,
  SafetyCheckStatus,
} from "@/lib/operator-execution-types";

const STATUS_STYLES: Record<SafetyCheckStatus, string> = {
  pending: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  passed: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  failed: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  skipped: "bg-surface-2 text-ink-faint ring-border",
  requires_review: "bg-status-review/15 text-status-review ring-status-review/30",
};

const SEVERITY_STYLES: Record<SafetyCheckSeverity, string> = {
  info: "text-ink-faint",
  warning: "text-status-review",
  error: "text-status-working",
  critical: "text-status-blocked",
};

export function ExecutionSafetyChecklist({
  checks,
}: {
  checks: readonly ExecutionSafetyCheckView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <h3 className="text-sm font-semibold text-ink">Execution Safety Checklist</h3>
      <p className="mt-1 text-xs text-ink-faint">
        Pre-checks the operator must confirm before running any step. These are
        instructions only — no check runs a command.
      </p>

      <ol className="mt-3 space-y-2">
        {checks.map((check) => (
          <li
            key={check.checkId}
            className="rounded-lg border border-border-soft bg-surface-2/40 p-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-semibold text-ink">
                {check.title}
                {check.required ? (
                  <span className="ml-2 text-[10px] font-medium text-ink-faint">
                    (required)
                  </span>
                ) : null}
              </p>
              <div className="flex items-center gap-1.5 text-[10px] font-semibold">
                <span className={`uppercase ${SEVERITY_STYLES[check.severity]}`}>
                  {check.severity}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 ring-1 ring-inset ${STATUS_STYLES[check.status]}`}
                >
                  {check.status}
                </span>
              </div>
            </div>
            {check.description ? (
              <p className="mt-1 text-[11px] text-ink-muted">{check.description}</p>
            ) : null}
            {check.operatorInstruction ? (
              <p className="mt-1 text-[11px] text-ink-faint">
                <span className="font-semibold">Instruction: </span>
                {check.operatorInstruction}
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
