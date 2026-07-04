import { LiveBadgePill, VerdictBadge } from "./status-badge";
import { cn, formatTimestamp, getAgentById } from "@/lib/utils";
import type { LiveBadge, ResultItem, ResultRouteStatus } from "@/lib/types";

const ROUTE_STYLES: Record<ResultRouteStatus, string> = {
  PASS: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  FAIL: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  BLOCKED: "bg-status-working/15 text-status-working ring-status-working/30",
  NEEDS_REVIEW: "bg-status-review/15 text-status-review ring-status-review/30",
};

export function ResultInbox({
  results,
  selectedTaskId,
  onSelectTask,
  badge,
}: {
  results: ResultItem[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
  badge?: LiveBadge | null;
}) {
  const passCount = results.filter((r) => r.verdict === "PASS").length;
  const failCount = results.length - passCount;

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink">Result Inbox</h2>
          {badge ? <LiveBadgePill badge={badge} /> : null}
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-status-approved">{passCount} PASS</span>
          <span className="text-ink-faint">·</span>
          <span className="text-status-blocked">{failCount} FAIL</span>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-dashed border-border-soft bg-surface-2/40 p-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
          Manual paste area
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          Display-only placeholder. Paste results in your external workflow, then
          review the static route guidance below.
        </p>
      </div>

      <ul className="mt-3 space-y-2">
        {results.map((result) => {
          const agent = getAgentById(result.producedBy);
          const active = result.taskId === selectedTaskId;
          return (
            <li key={result.id}>
              <button
                type="button"
                onClick={() => onSelectTask(result.taskId)}
                className={cn(
                  "w-full rounded-xl border p-3 text-left transition-colors",
                  active
                    ? "border-accent/50 bg-accent/5"
                    : "border-border-soft hover:bg-surface-2/60",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm font-medium text-ink">{result.title}</p>
                  <VerdictBadge verdict={result.verdict} />
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                  {result.summary}
                </p>
                <div className="mt-3 rounded-lg border border-border-soft bg-surface/70 p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset",
                        ROUTE_STYLES[result.route.status],
                      )}
                    >
                      {result.route.label}
                    </span>
                    <span className="text-[11px] text-ink-faint">
                      Destination: {result.route.destination}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                    {result.route.guidance}
                  </p>
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px] text-ink-faint">
                  <span>
                    {agent ? agent.name : result.producedBy} · {result.metric}
                  </span>
                  <span>{formatTimestamp(result.at)}</span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
