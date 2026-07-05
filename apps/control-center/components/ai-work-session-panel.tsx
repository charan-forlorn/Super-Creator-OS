import { cn } from "@/lib/utils";
import type { AIWorkSessionView, WorkSessionStatus } from "@/lib/ai-work-session-types";

const STATUS_STYLES: Record<WorkSessionStatus, string> = {
  draft: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  queued: "bg-status-idle/15 text-status-idle ring-status-idle/30",
  assigned: "bg-status-working/15 text-status-working ring-status-working/30",
  waiting_for_operator: "bg-status-review/15 text-status-review ring-status-review/30",
  sent_to_agent: "bg-status-working/15 text-status-working ring-status-working/30",
  agent_working: "bg-status-working/15 text-status-working ring-status-working/30",
  result_ready: "bg-status-review/15 text-status-review ring-status-review/30",
  review_required: "bg-status-review/15 text-status-review ring-status-review/30",
  needs_fix: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  approved: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
  cancelled: "bg-status-idle/10 text-ink-faint ring-status-idle/20",
  done: "bg-status-approved/10 text-status-approved/80 ring-status-approved/20",
};

const AGENT_LABEL: Record<string, string> = {
  chatgpt: "ChatGPT",
  claude_code: "Claude Code",
  codex: "Codex",
  hermes: "Hermes",
};

function SessionCard({ session }: { session: AIWorkSessionView }) {
  const agentLabel = session.assignment
    ? AGENT_LABEL[session.assignment.agentName] ?? session.assignment.agentName
    : null;

  return (
    <li className="rounded-lg border border-border-soft bg-surface/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-ink-faint">{session.sessionId}</span>
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-muted ring-1 ring-inset ring-border">
          {session.task.taskType}
        </span>
        <span
          className={cn(
            "ml-auto rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase ring-1 ring-inset",
            STATUS_STYLES[session.status],
          )}
        >
          {session.status.replace(/_/g, " ")}
        </span>
      </div>

      <p className="mt-2 text-sm text-ink">{session.task.title}</p>
      <p className="mt-1 text-[11px] text-ink-faint">{session.task.objective}</p>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
        {agentLabel ? (
          <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">
            {agentLabel} · {session.assignment?.runtimeId}
          </span>
        ) : (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-ink-faint">
            unassigned
          </span>
        )}
        <span>priority: {session.task.priority}</span>
        <span>updated {session.updatedAt}</span>
      </div>

      {session.nextAction ? (
        <p className="mt-2 rounded bg-surface-2 px-2.5 py-1.5 text-[11px] text-ink-muted">
          Next: {session.nextAction}
        </p>
      ) : null}
    </li>
  );
}

export function AIWorkSessionPanel({
  sessions,
}: {
  sessions: readonly AIWorkSessionView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">AI Work Sessions</h2>
        <span className="text-[11px] text-ink-faint">
          mock data · no AI execution
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-faint">
        Stage 5.2 work session lifecycle: create → assign runtime → track
        status → collect result. This panel only displays state produced by
        <code className="mx-1 rounded bg-surface-2 px-1 py-0.5">
          scos/control_center/work_session_manager.py
        </code>
        — it never dispatches work itself.
      </p>
      <ul className="mt-3 space-y-3">
        {sessions.map((session) => (
          <SessionCard key={session.sessionId} session={session} />
        ))}
      </ul>
    </section>
  );
}
