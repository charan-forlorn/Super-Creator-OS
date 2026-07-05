import { cn } from "@/lib/utils";
import type { OperatorApprovalView } from "@/lib/command-types";

const DECISION_STYLES: Record<"approved" | "rejected", string> = {
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  rejected: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

export function OperatorApprovalPanel({
  approvals,
}: {
  approvals: readonly OperatorApprovalView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Operator Approval Gate</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · no auto-approval
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Every command needs an explicit human decision. Approval ids are
        deterministic (sha256 of command + operator + timestamp + decision).
      </p>

      <ul className="mt-3 space-y-3">
        {approvals.map((approval) => {
          const decision = approval.approved ? "approved" : "rejected";
          return (
            <li
              key={approval.approvalId}
              className="rounded-lg border border-border-soft bg-surface/70 p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-ink-faint">
                  {approval.approvalId}
                </span>
                <span className="font-mono text-[11px] text-ink-muted">
                  → {approval.commandId}
                </span>
                <span
                  className={cn(
                    "ml-auto rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
                    DECISION_STYLES[decision],
                  )}
                >
                  {decision}
                </span>
              </div>
              <p className="mt-2 text-sm text-ink-muted">{approval.reason}</p>
              <p className="mt-1 text-[11px] text-ink-faint">
                {approval.approvedBy} · {approval.approvedAt}
              </p>
            </li>
          );
        })}
      </ul>

      <p className="mt-3 rounded bg-surface-2 px-3 py-2 text-[11px] text-ink-faint">
        No command executes without a granting approval whose command id
        matches the draft. Rejected drafts never reach the queue.
      </p>
    </section>
  );
}
