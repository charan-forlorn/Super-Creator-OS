import { cn } from "@/lib/utils";
import type { AIWorkSessionView, WorkSessionStatus } from "@/lib/ai-work-session-types";

const RESULT_STATUSES: readonly WorkSessionStatus[] = [
  "result_ready",
  "review_required",
  "needs_fix",
  "approved",
  "done",
  "blocked",
];

const VERDICT_STYLES: Record<string, string> = {
  ready: "bg-status-working/15 text-status-working ring-status-working/30",
  needs_review: "bg-status-review/15 text-status-review ring-status-review/30",
  needs_fix: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  done: "bg-status-approved/10 text-status-approved/80 ring-status-approved/20",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

function verdictKey(status: WorkSessionStatus): keyof typeof VERDICT_STYLES {
  if (status === "result_ready") return "ready";
  if (status === "review_required") return "needs_review";
  if (status === "needs_fix") return "needs_fix";
  if (status === "approved") return "approved";
  if (status === "done") return "done";
  return "blocked";
}

function ResultRow({ session }: { session: AIWorkSessionView }) {
  const verdict = verdictKey(session.status);
  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-faint">{session.sessionId}</span>
        <span className="text-sm text-ink">{session.task.title}</span>
        <span
          className={cn(
            "ml-auto rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            VERDICT_STYLES[verdict],
          )}
        >
          {session.status.replace(/_/g, " ")}
        </span>
      </div>

      <p className="mt-2 text-sm text-ink-muted">
        {session.resultSummary ?? "No result recorded yet."}
      </p>

      {session.nextAction ? (
        <p className="mt-2 rounded bg-surface-2 px-2.5 py-1.5 text-[11px] text-ink-muted">
          Next: {session.nextAction}
        </p>
      ) : null}
    </li>
  );
}

export function AgentResultStatusPanel({
  sessions,
}: {
  sessions: readonly AIWorkSessionView[];
}) {
  const withResults = sessions.filter((session) =>
    RESULT_STATUSES.includes(session.status),
  );

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Agent Result Status</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · placeholder results
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Sessions with a collected or pending result — from an agent&apos;s
        output through operator review to a final decision. Results here are
        static placeholders; no result is ever produced by this UI.
      </p>
      <ul className="mt-3 space-y-3">
        {withResults.map((session) => (
          <ResultRow key={session.sessionId} session={session} />
        ))}
      </ul>
    </section>
  );
}
