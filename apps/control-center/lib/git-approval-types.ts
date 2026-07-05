// SCOS Control Center - Stage 5.8 Git Commit / Push Approval Gate types.
// Static frontend mirror only. No backend calls, persistence, git execution,
// clipboard, or network behavior is implemented here.

export type GitChangeType =
  | "added"
  | "modified"
  | "deleted"
  | "renamed"
  | "copied"
  | "unknown";

export type GitTestEvidenceStatus = "passed" | "failed" | "skipped" | "unknown";

export type GitRiskLevel = "low" | "medium" | "high" | "blocked";

export type GitApprovalDecisionValue =
  | "approved"
  | "rejected"
  | "needs_changes"
  | "blocked";

export type GitApprovalEventType =
  | "git_evidence_snapshot_created"
  | "commit_proposal_created"
  | "commit_approval_recorded"
  | "push_readiness_snapshot_created"
  | "push_proposal_created"
  | "push_approval_recorded"
  | "git_gate_blocked";

export interface GitChangedFileView {
  path: string;
  changeType: GitChangeType;
  staged: boolean;
  summary: string;
}

export interface GitTestEvidenceView {
  evidenceId: string;
  commandLabel: string;
  status: GitTestEvidenceStatus;
  summary: string;
  passedCount: number;
  failedCount: number;
  warningCount: number;
  outputPath: string | null;
}

export interface GitEvidenceSnapshotView {
  snapshotId: string;
  taskId: string;
  sessionId: string;
  sourceIntakeId: string | null;
  branch: string;
  headCommit: string;
  originMainCommit: string;
  isCleanBeforeStage: boolean;
  hasRemoteOnlyCommits: boolean;
  changedFiles: readonly GitChangedFileView[];
  testEvidence: readonly GitTestEvidenceView[];
  riskFlags: readonly string[];
  createdAt: string;
}

export interface CommitProposalView {
  proposalId: string;
  snapshotId: string;
  taskId: string;
  sessionId: string;
  commitMessage: string;
  commitTitle: string;
  commitBody: string;
  filesToCommit: readonly string[];
  evidenceSummary: string;
  testSummary: string;
  riskLevel: GitRiskLevel;
  approvalRequired: boolean;
  proposedAt: string;
}

export interface CommitApprovalDecisionView {
  decisionId: string;
  proposalId: string;
  decision: GitApprovalDecisionValue;
  decidedBy: string;
  decidedAt: string;
  reason: string;
  manualCommand: string | null;
}

export interface PushReadinessSnapshotView {
  pushSnapshotId: string;
  branch: string;
  headCommit: string;
  originMainCommit: string;
  aheadBy: number;
  behindBy: number;
  hasRemoteOnlyCommits: boolean;
  workingTreeClean: boolean;
  latestCommitMessage: string;
  createdAt: string;
}

export interface PushProposalView {
  pushProposalId: string;
  commitDecisionId: string;
  pushSnapshotId: string;
  branch: string;
  remote: string;
  refspec: string;
  proposedCommand: string;
  riskLevel: GitRiskLevel;
  approvalRequired: boolean;
  proposedAt: string;
}

export interface PushApprovalDecisionView {
  pushDecisionId: string;
  pushProposalId: string;
  decision: GitApprovalDecisionValue;
  decidedBy: string;
  decidedAt: string;
  reason: string;
  manualCommand: string | null;
}

export interface GitApprovalEventView {
  eventId: string;
  eventType: GitApprovalEventType;
  taskId: string;
  sessionId: string;
  relatedId: string;
  summary: string;
  createdAt: string;
}
