import { GitEvidenceSummaryPanel } from "./git-evidence-summary-panel";
import { CommitProposalCard } from "./commit-proposal-card";
import { PushApprovalPanel } from "./push-approval-panel";
import { GitDecisionLogPanel } from "./git-decision-log-panel";
import type {
  CommitApprovalDecisionView,
  CommitProposalView,
  GitApprovalEventView,
  GitEvidenceSnapshotView,
  PushApprovalDecisionView,
  PushProposalView,
  PushReadinessSnapshotView,
} from "@/lib/git-approval-types";

export function GitApprovalPanel({
  snapshot,
  proposal,
  commitDecision,
  pushReadiness,
  pushProposal,
  pushDecision,
  events,
}: {
  snapshot: GitEvidenceSnapshotView;
  proposal: CommitProposalView;
  commitDecision: CommitApprovalDecisionView | null;
  pushReadiness: PushReadinessSnapshotView;
  pushProposal: PushProposalView | null;
  pushDecision: PushApprovalDecisionView | null;
  events: readonly GitApprovalEventView[];
}) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">
            Git Commit / Push Approval Gate
          </h2>
          <p className="mt-1 text-xs text-ink-faint">
            Stage 5.8 static deterministic mock. Proposal/approval modeling
            only — no git state is read or mutated by this UI.
          </p>
        </div>
        <span className="rounded-full bg-status-review/15 px-2 py-0.5 text-[10px] font-semibold text-status-review ring-1 ring-inset ring-status-review/30">
          {commitDecision?.decision === "approved" ? "commit approved" : "awaiting commit decision"}
        </span>
      </div>

      <div
        role="note"
        className="mt-3 rounded-lg border border-dashed border-border-soft bg-surface-2/30 px-3 py-2 text-[11px] font-semibold text-ink-faint"
      >
        AI can propose commit/push. Operator must execute manually.
      </div>

      <div className="mt-4 space-y-4">
        <GitEvidenceSummaryPanel snapshot={snapshot} />
        <CommitProposalCard proposal={proposal} decision={commitDecision} />
        <PushApprovalPanel
          readiness={pushReadiness}
          commitDecision={commitDecision}
          proposal={pushProposal}
          decision={pushDecision}
        />
        <GitDecisionLogPanel events={events} />
      </div>
    </section>
  );
}
