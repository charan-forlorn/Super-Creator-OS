import type { GitApprovalEventType, GitApprovalEventView } from "@/lib/git-approval-types";

const EVENT_LABEL: Record<GitApprovalEventType, string> = {
  git_evidence_snapshot_created: "Evidence snapshot created",
  commit_proposal_created: "Commit proposal created",
  commit_approval_recorded: "Commit approval recorded",
  push_readiness_snapshot_created: "Push readiness snapshot created",
  push_proposal_created: "Push proposal created",
  push_approval_recorded: "Push approval recorded",
  git_gate_blocked: "Gate blocked",
};

export function GitDecisionLogPanel({
  events,
}: {
  events: readonly GitApprovalEventView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-ink">Git Approval Decision Log</h2>
      <p className="mt-1 text-xs text-ink-faint">
        Append-only event timeline. Every entry mirrors
        <code className="mx-1">GitApprovalStore</code>
        (Stage 5.8) — no entry here represents an executed git command.
      </p>

      {events.length ? (
        <ol className="mt-3 space-y-2">
          {events.map((event, index) => (
            <li
              key={event.eventId}
              className="flex gap-3 rounded-lg border border-border-soft bg-surface-2/40 px-3 py-2"
            >
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-semibold text-accent ring-1 ring-inset ring-accent/30">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-ink">
                    {EVENT_LABEL[event.eventType]}
                  </span>
                  <span className="rounded-full bg-surface px-2 py-0.5 font-mono text-[10px] text-ink-faint ring-1 ring-inset ring-border">
                    {event.relatedId}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-ink-muted">{event.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-3 text-xs text-ink-faint">No git approval events recorded yet.</p>
      )}

      <p className="mt-3 rounded-lg bg-surface-2/40 px-3 py-2 text-[11px] text-ink-faint">
        Push proposal / push approval events only appear after the commit
        approval decision above is recorded as <span className="font-semibold">approved</span>.
      </p>
    </section>
  );
}
