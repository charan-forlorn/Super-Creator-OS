import { cn, formatTimestamp, getAgentById } from "@/lib/utils";
import type { TimelineEvent } from "@/lib/types";

const KIND_DOT: Record<TimelineEvent["kind"], string> = {
  info: "bg-agent-sky",
  success: "bg-status-approved",
  warning: "bg-status-blocked",
  review: "bg-status-review",
};

export function Timeline({
  events,
  selectedTaskId,
  onSelectTask,
}: {
  events: TimelineEvent[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <h2 className="text-sm font-semibold text-ink">Timeline</h2>

      <ol className="mt-4 space-y-4">
        {events.map((event, index) => {
          const agent = getAgentById(event.agent);
          const active = event.taskId != null && event.taskId === selectedTaskId;
          const isLast = index === events.length - 1;
          return (
            <li key={event.id} className="relative flex gap-3">
              {/* connector line */}
              {!isLast ? (
                <span
                  className="absolute left-[5px] top-4 h-full w-px bg-border"
                  aria-hidden
                />
              ) : null}
              <span
                className={cn(
                  "relative mt-1 h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-surface",
                  KIND_DOT[event.kind],
                )}
                aria-hidden
              />
              <div
                className={cn(
                  "min-w-0 flex-1 rounded-lg px-2 py-1 -mx-2",
                  active ? "bg-accent/5" : "",
                )}
              >
                <p className="text-sm text-ink">{event.message}</p>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
                  <span>{agent ? agent.name : event.agent}</span>
                  <span>·</span>
                  <span>{formatTimestamp(event.at)}</span>
                  {event.taskId ? (
                    <button
                      type="button"
                      onClick={() => onSelectTask(event.taskId as string)}
                      className="ml-auto text-accent/80 hover:text-accent"
                    >
                      view task
                    </button>
                  ) : null}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
