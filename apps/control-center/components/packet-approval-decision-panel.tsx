import type {
  OperatorPacketDecision,
  OperatorPacketReviewView,
} from "@/lib/operator-packet-review-types";

const ACTIONS: readonly { decision: OperatorPacketDecision; label: string }[] = [
  { decision: "approve", label: "Approve" },
  { decision: "reject", label: "Reject" },
  { decision: "request_changes", label: "Request Changes" },
  { decision: "manual_handoff", label: "Prepare Manual Handoff" },
  { decision: "blocked", label: "Mark Blocked" },
];

export function PacketApprovalDecisionPanel({
  review,
  selectedDecision,
  onDecision,
}: {
  review: OperatorPacketReviewView;
  selectedDecision: OperatorPacketDecision | null;
  onDecision: (decision: OperatorPacketDecision) => void;
}) {
  return (
    <section className="rounded-lg border border-border-soft bg-surface-2/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-semibold text-ink">Operator Decision</h3>
          <p className="mt-1 text-[11px] text-ink-faint">
            Local mock state only. No packet is dispatched or persisted.
          </p>
        </div>
        <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-[10px] font-semibold text-status-review ring-1 ring-inset ring-status-review/30">
          approval required
        </span>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {ACTIONS.map((action) => {
          const active = selectedDecision === action.decision;
          return (
            <button
              key={action.decision}
              type="button"
              onClick={() => onDecision(action.decision)}
              className={
                active
                  ? "rounded-lg border border-accent bg-accent/15 px-3 py-2 text-left text-xs font-semibold text-ink ring-1 ring-accent/30"
                  : "rounded-lg border border-border bg-surface px-3 py-2 text-left text-xs font-semibold text-ink-muted hover:bg-surface-2 hover:text-ink"
              }
            >
              {action.label}
            </button>
          );
        })}
      </div>

      <p className="mt-3 rounded bg-surface px-2 py-1 text-[11px] text-ink-muted">
        Recommended for this packet:{" "}
        <span className="font-semibold text-ink">
          {review.requiredDecision.replace(/_/g, " ")}
        </span>
        . Reason: {review.operatorNote}
      </p>
    </section>
  );
}
