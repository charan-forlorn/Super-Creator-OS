import { VerdictBadge } from "./status-badge";
import { cn, formatTimestamp, getAgentById } from "@/lib/utils";
import type { ResultItem } from "@/lib/types";

export function ResultInbox({
  results,
  selectedTaskId,
  onSelectTask,
}: {
  results: ResultItem[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}) {
  const passCount = results.filter((r) => r.verdict === "PASS").length;
  const failCount = results.length - passCount;

  return (
    <section className="rounded-card border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Result Inbox</h2>
        <div className="flex items-center gap-2 text-[11px]">
          <span className="text-status-approved">{passCount} PASS</span>
          <span className="text-ink-faint">·</span>
          <span className="text-status-blocked">{failCount} FAIL</span>
        </div>
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
