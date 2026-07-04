"use client";

import { useState } from "react";

import { cn, formatTimestamp, getTaskById } from "@/lib/utils";
import type { LiveSeverity, LiveWorkEvent } from "@/lib/types";

const SEVERITY_STYLES: Record<LiveSeverity, { badge: string; dot: string; label: string }> = {
  info: {
    badge: "bg-status-review/15 text-status-review ring-status-review/30",
    dot: "bg-status-review",
    label: "Info",
  },
  success: {
    badge: "bg-status-approved/15 text-status-approved ring-status-approved/30",
    dot: "bg-status-approved",
    label: "Success",
  },
  warning: {
    badge: "bg-status-working/15 text-status-working ring-status-working/30",
    dot: "bg-status-working",
    label: "Warning",
  },
  error: {
    badge: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
    dot: "bg-status-blocked",
    label: "Error",
  },
};

export function LiveWorkUpdates({
  events,
  appliedCount,
  totalCount,
  onAdvance,
  onReset,
  onSelectTask,
}: {
  /** Applied events, newest first. */
  events: LiveWorkEvent[];
  appliedCount: number;
  totalCount: number;
  onAdvance: () => void;
  /** Local-only: rewinds the simulation index to 0. */
  onReset: () => void;
  onSelectTask: (taskId: string) => void;
}) {
  // sm-only cosmetic collapse; resets on refresh like everything else.
  const [collapsed, setCollapsed] = useState(false);
  const exhausted = appliedCount >= totalCount;

  return (
    <div className="rounded-card border border-border bg-surface p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="relative flex h-2 w-2" aria-hidden>
          <span className="absolute inline-flex h-full w-full rounded-full bg-status-approved opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-status-approved" />
        </span>
        <h2 className="text-sm font-semibold text-ink">Live Work Updates</h2>
        <span className="text-[11px] text-ink-faint">
          {appliedCount}/{totalCount} updates applied
        </span>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            aria-expanded={!collapsed}
            className="rounded-lg border border-border-soft px-2 py-1.5 text-[11px] text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink sm:hidden"
          >
            {collapsed ? "Show feed ▾" : "Hide feed ▴"}
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={appliedCount === 0}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium ring-1 ring-inset transition-colors",
              appliedCount === 0
                ? "cursor-not-allowed bg-surface-2 text-ink-faint ring-border"
                : "bg-surface-2 text-ink-muted ring-border hover:bg-surface-2/70 hover:text-ink",
            )}
          >
            Reset Live Updates
          </button>
          <button
            type="button"
            onClick={onAdvance}
            disabled={exhausted}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-semibold ring-1 ring-inset transition-colors",
              exhausted
                ? "cursor-not-allowed bg-surface-2 text-ink-faint ring-border"
                : "bg-accent/15 text-accent ring-accent/40 hover:bg-accent/25",
            )}
          >
            {exhausted ? "All updates applied" : "Simulate Next Update"}
          </button>
        </div>
      </div>

      <div className={cn(collapsed && "hidden sm:block")}>
        {events.length === 0 ? (
          <p className="mt-3 rounded-xl border border-dashed border-border-soft px-4 py-6 text-center text-sm text-ink-faint">
            No live updates yet — press “Simulate Next Update” to replay agent
            activity.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {events.map((event, index) => {
              const severity = SEVERITY_STYLES[event.severity];
              const task = getTaskById(event.taskId);
              return (
                <li key={event.id}>
                  <button
                    type="button"
                    onClick={() => onSelectTask(event.taskId)}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-colors hover:bg-surface-2/60",
                      index === 0 ? "border-accent/40 bg-accent/5" : "border-border-soft",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={cn("h-1.5 w-1.5 rounded-full", severity.dot)}
                        aria-hidden
                      />
                      <span className="text-xs font-semibold text-ink">
                        {event.agent}
                      </span>
                      <span className="font-mono text-[11px] text-ink-faint">
                        {task ? task.code : event.taskId}
                      </span>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                          severity.badge,
                        )}
                      >
                        {severity.label}
                      </span>
                      {index === 0 ? (
                        <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-semibold text-accent ring-1 ring-inset ring-accent/30">
                          Latest
                        </span>
                      ) : null}
                      <span className="ml-auto text-[11px] text-ink-faint">
                        {formatTimestamp(event.timestamp)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
                      {event.message}
                    </p>
                    <p className="mt-1 text-[11px] text-ink-faint">
                      → Check {event.route}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
