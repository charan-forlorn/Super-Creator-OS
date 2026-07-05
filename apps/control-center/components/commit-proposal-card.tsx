import type {
  CommitApprovalDecisionView,
  CommitProposalView,
  GitRiskLevel,
} from "@/lib/git-approval-types";

const RISK_STYLES: Record<GitRiskLevel, string> = {
  low: "bg-status-approved/15 text-status-approved ring-status-approved/30",
  medium: "bg-status-review/15 text-status-review ring-status-review/30",
  high: "bg-status-working/15 text-status-working ring-status-working/30",
  blocked: "bg-status-blocked/15 text-status-blocked ring-status-blocked/30",
};

const DECISION_ACTIONS = [
  { label: "Approve" },
  { label: "Reject" },
  { label: "Needs Changes" },
] as const;

export function CommitProposalCard({
  proposal,
  decision,
}: {
  proposal: CommitProposalView;
  decision: CommitApprovalDecisionView | null;
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Commit Proposal</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Proposal only — nothing here runs <code>git add</code> or{" "}
            <code>git commit</code>. The operator must type the real commands
            themselves.
          </p>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${RISK_STYLES[proposal.riskLevel]}`}
        >
          risk: {proposal.riskLevel}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-semibold">
        <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-ink-faint ring-1 ring-inset ring-border">
          {proposal.proposalId}
        </span>
        {proposal.approvalRequired ? (
          <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-status-review ring-1 ring-inset ring-status-review/30">
            approval required
          </span>
        ) : null}
      </div>

      <pre className="mt-3 overflow-auto rounded-lg border border-border-soft bg-surface-2/50 p-3 font-mono text-[11px] text-ink">
{proposal.commitMessage}
      </pre>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Files to commit ({proposal.filesToCommit.length})
          </p>
          <ul className="mt-1 space-y-0.5">
            {proposal.filesToCommit.map((file) => (
              <li key={file} className="truncate font-mono text-[11px] text-ink-muted">
                {file}
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Evidence summary
            </p>
            <p className="mt-1 text-[11px] text-ink-muted">{proposal.evidenceSummary}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
              Test summary
            </p>
            <p className="mt-1 text-[11px] text-ink-muted">{proposal.testSummary}</p>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-dashed border-border-soft bg-surface-2/30 p-3">
        <p className="text-[11px] text-ink-faint">
          Operator decision (inert mock — no click here approves, rejects, or
          dispatches anything; the real decision happens outside SCOS).
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          {DECISION_ACTIONS.map((action) => (
            <button
              key={action.label}
              type="button"
              disabled
              className="cursor-not-allowed rounded-lg border border-border-soft bg-surface px-3 py-2 text-left text-xs font-semibold text-ink-faint opacity-60"
            >
              {action.label} (disabled)
            </button>
          ))}
        </div>
      </div>

      {decision ? (
        <div className="mt-3 rounded-lg border border-border-soft bg-surface-2/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
            Recorded decision
          </p>
          <p className="mt-1 text-xs text-ink">
            <span className="font-semibold">{decision.decision}</span> by{" "}
            {decision.decidedBy} — {decision.reason}
          </p>
          {decision.manualCommand ? (
            <pre className="mt-2 overflow-auto rounded bg-surface p-2 font-mono text-[11px] text-ink-muted">
{decision.manualCommand}
            </pre>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 rounded-lg bg-surface-2/40 px-3 py-2 text-[11px] text-ink-faint">
          No commit approval decision has been recorded yet. A push proposal
          cannot be built until this decision is <span className="font-semibold">approved</span>.
        </p>
      )}
    </section>
  );
}
