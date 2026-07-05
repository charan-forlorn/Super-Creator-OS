import { cn } from "@/lib/utils";
import type { CommandEventStatus, CommandEventView } from "@/lib/command-types";

const STATUS_STYLES: Record<CommandEventStatus, string> = {
  success: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  failure: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  skipped: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  pending: "bg-status-working/15 text-status-working ring-status-working/30",
};

export function CommandEventLog({ events }: { events: readonly CommandEventView[] }) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Command Event Log</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · JSONL append-only
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Deterministic lifecycle events (content-derived event ids, no clock, no
        random). Ordering is physical append order.
      </p>

      <ol className="mt-3 space-y-2">
        {events.map((event) => (
          <li
            key={event.eventId}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-border-soft bg-surface/70 px-3 py-2"
          >
            <span className="font-mono text-[11px] text-ink-faint">
              {event.createdAt}
            </span>
            <span className="font-mono text-[11px] text-ink-muted">
              {event.commandId}
            </span>
            <span className="font-mono text-xs font-medium text-ink">
              {event.eventType}
            </span>
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                STATUS_STYLES[event.status],
              )}
            >
              {event.status}
            </span>
            <span className="w-full text-[11px] text-ink-muted sm:ml-auto sm:w-auto">
              {event.message}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
