import { cn, TASK_STATUS_LABEL } from "@/lib/utils";
import type { LiveBadge, TaskStatus, Verdict } from "@/lib/types";

const STATUS_STYLES: Record<TaskStatus, string> = {
  backlog: "bg-status-idle/15 text-ink-muted ring-status-idle/25",
  "in-progress": "bg-status-working/15 text-status-working ring-status-working/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  "in-review": "bg-status-review/15 text-status-review ring-status-review/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  done: "bg-status-approved/10 text-status-approved/80 ring-status-approved/20",
};

export function StatusBadge({
  status,
  className,
}: {
  status: TaskStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        STATUS_STYLES[status],
        className,
      )}
    >
      {TASK_STATUS_LABEL[status]}
    </span>
  );
}

export function VerdictBadge({
  verdict,
  className,
}: {
  verdict: Verdict;
  className?: string;
}) {
  const pass = verdict === "PASS";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        pass
          ? "bg-status-approved/15 text-status-approved ring-status-approved/30"
          : "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          pass ? "bg-status-approved" : "bg-status-blocked",
        )}
      />
      {verdict}
    </span>
  );
}

const LIVE_BADGE_STYLES: Record<LiveBadge, string> = {
  New: "bg-accent/15 text-accent ring-accent/30",
  "Needs Review": "bg-status-review/15 text-status-review ring-status-review/30",
  "Fix Required": "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  "Ready to Merge":
    "bg-status-approved/15 text-status-approved ring-status-approved/30",
};

/** Notification pill driven by the deterministic live-updates simulation. */
export function LiveBadgePill({
  badge,
  className,
}: {
  badge: LiveBadge;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
        LIVE_BADGE_STYLES[badge],
        className,
      )}
    >
      {badge}
    </span>
  );
}
