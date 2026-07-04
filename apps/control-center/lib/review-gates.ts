// Deterministic operator review and commit-gate data.
// Frontend-only: no git execution, no network, no storage, no shell calls.

import type {
  ChangedFileReview,
  CommitChecklistItem,
  OperatorDecision,
  OperatorReviewGate,
  MascotMood,
  RemoteSafetyCheck,
  TestEvidence,
} from "./types";

export const CHANGED_FILE_REVIEWS: ChangedFileReview[] = [
  {
    id: "cf-1",
    filePath: "apps/control-center/components/operator-review-gate.tsx",
    changeType: "added",
    scopeStatus: "allowed",
    reason: "New frontend-only review gate component lives inside the allowed app.",
    owningArea: "Control Center UI",
  },
  {
    id: "cf-2",
    filePath: "apps/control-center/lib/review-gates.ts",
    changeType: "added",
    scopeStatus: "allowed",
    reason: "Static deterministic mock data for v0.1.4.",
    owningArea: "Control Center mock data",
  },
  {
    id: "cf-3",
    filePath: "apps/control-center/lib/types.ts",
    changeType: "modified",
    scopeStatus: "allowed",
    reason: "Typed frontend-only review gate contracts.",
    owningArea: "Control Center types",
  },
  {
    id: "cf-4",
    filePath: "apps/control-center/README.md",
    changeType: "modified",
    scopeStatus: "warning",
    reason: "Documentation changes are allowed in the app, but should stay factual.",
    owningArea: "Control Center docs",
  },
  {
    id: "cf-5",
    filePath: "docs/stage-4-commercial-pipeline.md",
    changeType: "modified",
    scopeStatus: "forbidden",
    reason: "Stage 4 commercial files are outside the approved frontend scope.",
    owningArea: "Stage 4 commercial",
  },
];

export const TEST_EVIDENCE: TestEvidence[] = [
  {
    id: "te-1",
    label: "pnpm lint",
    command: "pnpm lint",
    result: "PASS",
    required: true,
    reason: "ESLint completed with zero errors.",
  },
  {
    id: "te-2",
    label: "pnpm build",
    command: "pnpm build",
    result: "PASS",
    required: true,
    reason: "Next.js production build completed.",
  },
  {
    id: "te-3",
    label: "static source scan",
    command: "rg forbidden tokens apps/control-center",
    result: "PASS",
    required: true,
    reason: "No backend, network, timer, storage, or random APIs found.",
  },
  {
    id: "te-4",
    label: "git diff --stat scope check",
    command: "git diff --stat",
    result: "FAIL",
    required: true,
    reason: "One simulated forbidden Stage 4 path is present in the scope review.",
  },
  {
    id: "te-5",
    label: "no app/api check",
    command: "find app/api",
    result: "PASS",
    required: true,
    reason: "No API routes are present.",
  },
  {
    id: "te-6",
    label: "no route.ts check",
    command: "find route.ts",
    result: "PASS",
    required: true,
    reason: "No route handlers are present.",
  },
  {
    id: "te-7",
    label: "no backend/network check",
    command: "static forbidden-token scan",
    result: "PASS",
    required: true,
    reason: "No network or backend behavior is introduced.",
  },
  {
    id: "te-8",
    label: "manual mobile smoke",
    command: "manual viewport check",
    result: "MISSING",
    required: false,
    reason: "Optional manual viewport pass has not been attached to this simulated gate.",
  },
];

export const COMMIT_CHECKLIST: CommitChecklistItem[] = [
  {
    id: "cc-1",
    label: "Codex review PASS",
    status: "pass",
    reason: "Codex returned a passing review summary.",
  },
  {
    id: "cc-2",
    label: "changed files inside allowed scope",
    status: "fail",
    reason: "A simulated Stage 4 commercial file is marked forbidden.",
  },
  {
    id: "cc-3",
    label: "lint passed",
    status: "pass",
    reason: "pnpm lint evidence is PASS.",
  },
  {
    id: "cc-4",
    label: "build passed",
    status: "pass",
    reason: "pnpm build evidence is PASS.",
  },
  {
    id: "cc-5",
    label: "static scan passed",
    status: "pass",
    reason: "Forbidden-token scan evidence is PASS.",
  },
  {
    id: "cc-6",
    label: "no forbidden files",
    status: "fail",
    reason: "Forbidden file review must be resolved before commit.",
  },
  {
    id: "cc-7",
    label: "no backend/API/network behavior",
    status: "pass",
    reason: "Static scan found no prohibited behavior.",
  },
  {
    id: "cc-8",
    label: "no root package/lockfile",
    status: "pass",
    reason: "No root package or lockfile changes are listed.",
  },
  {
    id: "cc-9",
    label: "commit message prepared",
    status: "pass",
    reason: "Recommended message is ready for operator review.",
  },
  {
    id: "cc-10",
    label: "remote safety check reviewed",
    status: "warning",
    reason: "Remote safety blocks push until remote-only commits are reconciled.",
  },
];

export const REMOTE_SAFETY: RemoteSafetyCheck = {
  verdict: "REMOTE_BLOCKED",
  branch: "main",
  localAheadCommits: 1,
  remoteOnlyCommits: 1,
  workingTree: "dirty_expected",
  evidence: [
    {
      id: "rs-1",
      label: "git fetch origin",
      value: "completed in operator preflight",
      result: "PASS",
    },
    {
      id: "rs-2",
      label: "git status -sb",
      value: "main...origin/main [ahead 1, behind 1]",
      result: "FAIL",
    },
    {
      id: "rs-3",
      label: "git rev-parse HEAD",
      value: "local-review-gate-sha",
      result: "PASS",
    },
    {
      id: "rs-4",
      label: "git rev-parse origin/main",
      value: "remote-newer-sha",
      result: "PASS",
    },
    {
      id: "rs-5",
      label: "git log --oneline --left-right main...origin/main",
      value: "remote-only commits: 1",
      result: "FAIL",
    },
  ],
};

export const OPERATOR_REVIEW_GATE: OperatorReviewGate = {
  reviewStatus: "PASS",
  reviewer: "Codex",
  reviewedTaskId: "task-06",
  reviewSummary:
    "Codex review passed the frontend implementation, but commit is blocked by a forbidden scope item in the simulated changed-files review.",
  recommendedOperatorAction:
    "Request a fix for the forbidden Stage 4 path, then rerun scope and remote safety checks before commit or push.",
  gateVerdict: "HOLD",
  changedFiles: CHANGED_FILE_REVIEWS,
  testEvidence: TEST_EVIDENCE,
  checklist: COMMIT_CHECKLIST,
  commitPlan: {
    recommendedMessage: "feat(ui): add operator review and commit gate flow",
    stagedFiles: [
      "apps/control-center/components/operator-review-gate.tsx",
      "apps/control-center/components/changed-files-review.tsx",
      "apps/control-center/components/test-evidence-panel.tsx",
      "apps/control-center/components/commit-readiness-checklist.tsx",
      "apps/control-center/components/commit-plan-preview.tsx",
      "apps/control-center/components/remote-safety-panel.tsx",
      "apps/control-center/lib/review-gates.ts",
      "apps/control-center/lib/types.ts",
      "apps/control-center/components/app-shell.tsx",
    ],
    scope: "Frontend-only Control Center review and commit gate simulation.",
    riskNotes: [
      "Commit is not ready while forbidden scope exists.",
      "Push is blocked while remote-only commits are present.",
      "This UI never executes git commands.",
    ],
    reminder: "This UI does not execute git commands.",
  },
  remoteSafety: REMOTE_SAFETY,
};

export function hasForbiddenFiles(files: ChangedFileReview[]): boolean {
  return files.some((file) => file.scopeStatus === "forbidden");
}

export function hasRequiredEvidenceGap(evidence: TestEvidence[]): boolean {
  return evidence.some(
    (item) => item.required && (item.result === "FAIL" || item.result === "MISSING"),
  );
}

export function isCommitReady(gate: OperatorReviewGate): boolean {
  return (
    gate.gateVerdict === "COMMIT_READY" &&
    !hasForbiddenFiles(gate.changedFiles) &&
    !hasRequiredEvidenceGap(gate.testEvidence)
  );
}

export function isPushReady(gate: OperatorReviewGate): boolean {
  const remote = gate.remoteSafety;
  return (
    remote.verdict === "REMOTE_SAFE" &&
    remote.branch === "main" &&
    remote.localAheadCommits === 1 &&
    remote.remoteOnlyCommits === 0
  );
}

export function decisionLabel(decision: OperatorDecision): string {
  switch (decision) {
    case "approve_commit":
      return "Approve Commit selected locally";
    case "approve_push":
      return "Approve Push selected locally";
    case "request_fix":
      return "Request Fix selected locally";
    case "hold":
      return "Hold selected locally";
    case "reject":
      return "Reject selected locally";
    default:
      return "No operator decision selected";
  }
}

export function deriveCommitGateAdvisor(gate: OperatorReviewGate): {
  mood: MascotMood;
  message: string;
  nextAction: string;
  summary: string;
} {
  if (gate.remoteSafety.verdict === "REMOTE_BLOCKED") {
    return {
      mood: "blocked",
      message: "Remote safety blocks push. Do not commit or push until the operator gate is clean.",
      nextAction:
        "Resolve remote-only commits, rerun safety evidence, then revisit Approve Push.",
      summary: `${gate.reviewedTaskId} - REMOTE_BLOCKED`,
    };
  }

  if (gate.gateVerdict === "COMMIT_READY" && gate.remoteSafety.verdict === "REMOTE_SAFE") {
    return {
      mood: "approved",
      message: "Commit and push gates are green in the simulation.",
      nextAction:
        "Review the commit plan, then choose Approve Commit or Approve Push locally.",
      summary: `${gate.reviewedTaskId} - PUSH_READY`,
    };
  }

  if (gate.gateVerdict === "COMMIT_READY") {
    return {
      mood: "approved",
      message: "Codex review and commit readiness are green, but push safety still needs review.",
      nextAction: "Inspect Remote Safety Check before approving push.",
      summary: `${gate.reviewedTaskId} - COMMIT_READY`,
    };
  }

  if (gate.gateVerdict === "REQUEST_FIX") {
    return {
      mood: "blocked",
      message: "The commit gate needs a fix before staging would be safe.",
      nextAction: "Use Changed Files Scope Review and Test Evidence to request a fix.",
      summary: `${gate.reviewedTaskId} - REQUEST_FIX`,
    };
  }

  return {
    mood: "review",
    message: "The commit gate is on hold for operator review.",
    nextAction:
      "Review file scope, test evidence, commit plan, and remote safety before choosing a local decision.",
    summary: `${gate.reviewedTaskId} - ${gate.gateVerdict}`,
  };
}
