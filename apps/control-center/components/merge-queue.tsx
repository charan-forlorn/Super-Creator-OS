"use client";

import { LiveBadgePill, VerdictBadge } from "./status-badge";
import { cn, formatTimestamp, getAgentById } from "@/lib/utils";
import type { LiveBadge, MergeAction, MergeItem, RiskLevel } from "@/lib/types";

const ACTIONS: { label: MergeAction; className: string }[] = [
  {
    label: "Approve",
    className:
      "bg-status-approved/15 text-status-approved ring-status-approved/30",
  },
  {
    label: "Request Fix",
    className: "bg-status-working/15 text-status-working ring-status-working/30",
  },
  {
    label: "Reject",
    className: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  },
  { label: "Hold", className: "bg-surface-2 text-ink-muted ring-border" },
];

const RISK_STYLES: Record<RiskLevel, string> = {
  low: "text-status-approved",
  medium: "text-status-working",
  high: "text-status-blocked",
};

const MERGE_STATE_STYLES: Record<string, string> = {
  "ready-for-review":
    "bg-status-review/15 text-status-review ring-status-review/30",
  queued: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  merged: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  archived: "bg-surface-2 text-ink-muted ring-border",
};

const MERGE_STATE_LABEL: Record<string, string> = {
  "ready-for-review": "Ready for review",
  queued: "Queued",
  blocked: "Blocked",
  merged: "Merged",
  archived: "Archived",
};

export function MergeQueue({
  items,
  selectedTaskId,
  onSelectTask,
  badge,
}: {
  items: MergeItem[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
  badge?: LiveBadge | null;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">Merge Queue</h2>
          {badge ? <LiveBadgePill badge={badge} /> : null}
        </div>
        <span className="text-[11px] text-ink-faint">{items.length} in queue</span>
      </div>

      {items.length === 0 ? (
        <p className="mt-3 rounded-xl border border-dashed border-border-soft px-4 py-6 text-center text-sm text-ink-faint">
          No merge items are currently queued.
        </p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {items.map((item) => {
            const author = getAgentById(item.author);
            const active = item.taskId === selectedTaskId;
            const mergeState = item.mergeState ?? "queued";
            const stateStyle =
              MERGE_STATE_STYLES[mergeState] ?? MERGE_STATE_STYLES.queued;
            const stateLabel =
              MERGE_STATE_LABEL[mergeState] ?? mergeState;
            return (
              <li
                key={item.id}
                className={cn(
                  "rounded-xl border p-3",
                  active ? "border-accent/50 bg-accent/5" : "border-border-soft",
                )}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <button
                    type="button"
                    onClick={() => onSelectTask(item.taskId)}
                    className="min-w-0 text-left"
                  >
                    <p className="truncate text-sm font-medium text-ink hover:text-accent">
                      {item.title}
                    </p>
                    <p className="truncate font-mono text-[11px] text-ink-faint">
                      {item.branch}
                    </p>
                  </button>
                  <div className="flex items-center gap-2">
                    <VerdictBadge verdict={item.verdict} />
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                        stateStyle,
                      )}
                    >
                      {stateLabel}
                    </span>
                  </div>
                </div>

                <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-faint">
                  <span>{author ? author.name : item.author}</span>
                  <span className="text-status-approved">+{item.additions}</span>
                  <span className="text-status-blocked">−{item.deletions}</span>
                  <span>{item.filesChanged} files</span>
                  <span className="ml-auto">{formatTimestamp(item.submittedAt)}</span>
                </div>

                <div className="mt-3 rounded-lg border border-border-soft bg-surface-2/50 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                      Decision Guidance
                    </p>
                    <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold text-ink ring-1 ring-inset ring-border">
                      {item.decisionGuidance.recommendedDecision}
                    </span>
                    <span
                      className={cn(
                        "text-[11px] font-semibold",
                        RISK_STYLES[item.decisionGuidance.riskLevel],
                      )}
                    >
                      {item.decisionGuidance.riskLevel} risk
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                    {item.decisionGuidance.reason}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-faint">
                    Evidence: {item.decisionGuidance.requiredEvidence}
                  </p>
                </div>

                <div className="mt-3 grid grid-cols-4 gap-1.5">
                  {ACTIONS.map((action) => (
                    <button
                      key={action.label}
                      type="button"
                      disabled
                      aria-disabled
                      title="Disabled in prototype"
                      className={cn(
                        "cursor-not-allowed rounded-lg px-2 py-1.5 text-[11px] font-medium opacity-55 ring-1 ring-inset",
                        action.className,
                      )}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-3 text-[11px] text-ink-faint">
        Actions are visual only — no merge, fix, or reject is executed.
      </p>
    </section>
  );
}
