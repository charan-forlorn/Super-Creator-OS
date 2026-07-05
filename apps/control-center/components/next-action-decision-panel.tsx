import { cn } from "@/lib/utils";
import type { NextActionDecisionView, NextActionPriority } from "@/lib/result-intake-types";

const PRIORITY_STYLES: Record<NextActionPriority, string> = {
  low: "bg-status-idle/15 text-ink-muted ring-status-idle/25",
  normal: "bg-accent/15 text-accent ring-accent/30",
  high: "bg-status-working/15 text-status-working ring-status-working/30",
  urgent: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function NextActionDecisionPanel({ decision }: { decision: NextActionDecisionView }) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Next Action Decision</h2>
          <p className="mt-1 text-xs text-ink-faint">
            A conservative recommendation only — nothing is dispatched automatically.
          </p>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
            PRIORITY_STYLES[decision.priority],
          )}
        >
          {decision.priority}
        </span>
      </div>

      <p className="mt-3 rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2 text-sm font-semibold text-ink">
        {decision.recommendedAction.replace(/_/g, " ")}
      </p>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <p className="rounded bg-surface-2/40 px-3 py-2 text-[11px] text-ink-muted">
          <span className="font-semibold text-ink">Target Agent:</span>{" "}
          {decision.targetAgent ?? "None"}
        </p>
        <p className="rounded bg-surface-2/40 px-3 py-2 text-[11px] text-ink-muted">
          <span className="font-semibold text-ink">Target Runtime:</span>{" "}
          {decision.targetRuntimeId ?? "None"}
        </p>
      </div>

      <p className="mt-2 rounded bg-surface-2/40 px-3 py-2 text-xs text-ink-muted">
        {decision.reason}
      </p>

      <div
        className={cn(
          "mt-3 flex items-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold ring-1 ring-inset",
          decision.requiresOperatorApproval
            ? "bg-status-review/15 text-status-review ring-status-review/30"
            : "bg-status-idle/15 text-ink-muted ring-status-idle/25",
        )}
      >
        <span aria-hidden>{decision.requiresOperatorApproval ? "⚠" : "—"}</span>
        {decision.requiresOperatorApproval
          ? "Operator approval required before this action is taken."
          : "No dispatch is recommended; no approval needed."}
      </div>
    </section>
  );
}
