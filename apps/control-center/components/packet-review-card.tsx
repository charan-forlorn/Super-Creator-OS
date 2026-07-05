import { cn } from "@/lib/utils";
import type {
  OperatorPacketReviewView,
  ReviewQueueStatus,
} from "@/lib/operator-packet-review-types";

const STATUS_STYLES: Record<ReviewQueueStatus, string> = {
  pending: "bg-status-review/15 text-status-review ring-status-review/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  rejected: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  changes_requested: "bg-status-working/15 text-status-working ring-status-working/30",
  manual_handoff_prepared: "bg-accent/15 text-accent ring-accent/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

const SEVERITY_STYLES = {
  info: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  warning: "bg-status-working/15 text-status-working ring-status-working/30",
  error: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  critical: "bg-status-blocked/20 text-status-blocked ring-status-blocked/40",
};

export function PacketReviewCard({
  review,
  selected,
  onSelect,
}: {
  review: OperatorPacketReviewView;
  selected: boolean;
  onSelect: (reviewId: string) => void;
}) {
  const failures = review.checks.filter((check) => check.status === "failure");
  const warnings = review.checks.filter((check) => check.severity === "warning");

  return (
    <button
      type="button"
      onClick={() => onSelect(review.reviewId)}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        selected
          ? "border-accent bg-accent/10 ring-1 ring-accent/30"
          : "border-border-soft bg-surface-2/40 hover:border-border hover:bg-surface-2",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] text-ink-faint">{review.packetId}</span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            STATUS_STYLES[review.status],
          )}
        >
          {review.status.replace(/_/g, " ")}
        </span>
        <span className="ml-auto text-[10px] text-ink-faint">
          decision: {review.requiredDecision.replace(/_/g, " ")}
        </span>
      </div>

      <p className="mt-2 text-xs font-semibold text-ink">{review.title}</p>
      <p className="mt-1 text-[11px] text-ink-faint">
        {review.sourceAgent} -&gt; {review.targetAgent} / {review.targetRuntimeId}
      </p>
      <p className="mt-2 text-xs text-ink-muted">{review.routingReason}</p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
            failures.length
              ? "bg-status-blocked/15 text-status-blocked ring-status-blocked/30"
              : "bg-status-approved/15 text-status-approved ring-status-approved/30",
          )}
        >
          {failures.length ? `${failures.length} failure` : "checks pass"}
        </span>
        {warnings.length ? (
          <span className="rounded-full bg-status-working/15 px-2 py-0.5 text-[10px] font-semibold text-status-working ring-1 ring-inset ring-status-working/30">
            {warnings.length} warning
          </span>
        ) : null}
        {review.checks.slice(0, 3).map((check) => (
          <span
            key={`${review.reviewId}-${check.checkName}`}
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] ring-1 ring-inset",
              SEVERITY_STYLES[check.severity],
            )}
          >
            {check.checkName.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </button>
  );
}
