import type { ApprovalState } from "@/lib/operator-command-view-types";

const TONES: Record<ApprovalState, string> = {
  pending: "bg-status-review/15 text-status-review ring-status-review/40",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/40",
  denied: "bg-status-failed/15 text-status-failed ring-status-failed/40",
  missing_approval: "bg-status-failed/15 text-status-failed ring-status-failed/40",
  tampered: "bg-status-failed/20 text-status-failed ring-status-failed/50",
  executed: "bg-accent/15 text-accent ring-accent/40",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/40",
  unknown: "bg-surface-2 text-ink-faint ring-border",
};

export function ApprovalStateBadge({ state }: { state: ApprovalState }) {
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${TONES[state]}`}
    >
      {state.replace("_", " ")}
    </span>
  );
}
