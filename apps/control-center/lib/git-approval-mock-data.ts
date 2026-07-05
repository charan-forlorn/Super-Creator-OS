// SCOS Control Center - Stage 5.8 static mock data for the Git Commit / Push
// Approval Gate. All values are hand-authored constants — no fetch, no
// timers, no random ids, no clock reads. This scenario picks up right after
// the Stage 5.7 Hermes PASS result: evidence is summarized, tests passed,
// a commit proposal is ready, and the operator's commit approval decision
// is still pending — the push proposal stays locked until that decision is
// approved.

import type {
  CommitApprovalDecisionView,
  CommitProposalView,
  GitApprovalEventView,
  GitEvidenceSnapshotView,
  PushApprovalDecisionView,
  PushProposalView,
  PushReadinessSnapshotView,
} from "./git-approval-types";

export const GIT_EVIDENCE_SNAPSHOT: GitEvidenceSnapshotView = {
  snapshotId: "ges-9a1b2c3d4e5f6071",
  taskId: "task-hermes-audit-01",
  sessionId: "sess-stage-5-7",
  sourceIntakeId: "ri-7f3a9c1d2b4e5f60",
  branch: "main",
  headCommit: "09fd1cd87b48703284b68898b078b41aedcff8fc",
  originMainCommit: "09fd1cd87b48703284b68898b078b41aedcff8fc",
  isCleanBeforeStage: true,
  hasRemoteOnlyCommits: false,
  changedFiles: [
    {
      path: "scos/control_center/git_approval_models.py",
      changeType: "added",
      staged: false,
      summary: "Stage 5.8 immutable models (10 dataclasses).",
    },
    {
      path: "scos/control_center/git_approval_builder.py",
      changeType: "added",
      staged: false,
      summary: "Stage 5.8 commit/push proposal + approval builder.",
    },
    {
      path: "scos/control_center/git_approval_store.py",
      changeType: "added",
      staged: false,
      summary: "Stage 5.8 append-only JSONL store.",
    },
  ],
  testEvidence: [
    {
      evidenceId: "ev-git-approval-models",
      commandLabel: ".venv\\Scripts\\python.exe scos\\control_center\\tests\\test_git_approval_models.py",
      status: "passed",
      summary: "40 passed, 0 failed",
      passedCount: 40,
      failedCount: 0,
      warningCount: 0,
      outputPath: null,
    },
    {
      evidenceId: "ev-git-approval-builder",
      commandLabel: ".venv\\Scripts\\python.exe scos\\control_center\\tests\\test_git_approval_builder.py",
      status: "passed",
      summary: "42 passed, 0 failed",
      passedCount: 42,
      failedCount: 0,
      warningCount: 0,
      outputPath: null,
    },
  ],
  riskFlags: [],
  createdAt: "2026-07-06T10:00:00Z",
};

export const COMMIT_PROPOSAL: CommitProposalView = {
  proposalId: "cp-2b3c4d5e6f708192",
  snapshotId: "ges-9a1b2c3d4e5f6071",
  taskId: "task-hermes-audit-01",
  sessionId: "sess-stage-5-7",
  commitMessage: "feat(control-center): add Stage 5.8 git approval gate",
  commitTitle: "add Stage 5.8 git approval gate",
  commitBody: "",
  filesToCommit: [
    "scos/control_center/git_approval_builder.py",
    "scos/control_center/git_approval_models.py",
    "scos/control_center/git_approval_store.py",
  ],
  evidenceSummary: "3 changed file(s) on branch 'main' at 09fd1cd87b48703284b68898b078b41aedcff8fc",
  testSummary: "82 passed, 0 failed, 0 with warnings across 2 evidence item(s)",
  riskLevel: "low",
  approvalRequired: true,
  proposedAt: "2026-07-06T10:05:00Z",
};

// Pending: no CommitApprovalDecision has been recorded yet in this mock
// scenario. The operator must decide before a push proposal can exist.
export const COMMIT_APPROVAL_DECISION: CommitApprovalDecisionView | null = null;

// Locked: a PushProposal can only be built from an *approved*
// CommitApprovalDecision, so this mock scenario has none yet either.
export const PUSH_READINESS_SNAPSHOT: PushReadinessSnapshotView = {
  pushSnapshotId: "prs-3c4d5e6f70819203",
  branch: "main",
  headCommit: "09fd1cd87b48703284b68898b078b41aedcff8fc",
  originMainCommit: "09fd1cd87b48703284b68898b078b41aedcff8fc",
  aheadBy: 0,
  behindBy: 0,
  hasRemoteOnlyCommits: false,
  workingTreeClean: true,
  latestCommitMessage: "feat(control-center): add Stage 5.7 AI result intake loop",
  createdAt: "2026-07-06T10:07:00Z",
};

export const PUSH_PROPOSAL: PushProposalView | null = null;
export const PUSH_APPROVAL_DECISION: PushApprovalDecisionView | null = null;

export const GIT_APPROVAL_EVENTS: readonly GitApprovalEventView[] = [
  {
    eventId: "gae-4d5e6f7081920314",
    eventType: "git_evidence_snapshot_created",
    taskId: "task-hermes-audit-01",
    sessionId: "sess-stage-5-7",
    relatedId: "ges-9a1b2c3d4e5f6071",
    summary: "Evidence snapshot built: 3 changed files, 82 passed tests, 0 risk flags.",
    createdAt: "2026-07-06T10:00:01Z",
  },
  {
    eventId: "gae-5e6f708192031425",
    eventType: "commit_proposal_created",
    taskId: "task-hermes-audit-01",
    sessionId: "sess-stage-5-7",
    relatedId: "cp-2b3c4d5e6f708192",
    summary: "Commit proposal ready (risk: low). Awaiting operator commit approval.",
    createdAt: "2026-07-06T10:05:01Z",
  },
] as const;
