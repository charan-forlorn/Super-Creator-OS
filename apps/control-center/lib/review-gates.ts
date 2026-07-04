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
    reason: "Frontend-only review gate component lives inside the Control Center app.",
    owningArea: "Control Center UI",
  },
  {
    id: "cf-2",
    filePath: "apps/control-center/lib/review-gates.ts",
    changeType: "added",
    scopeStatus: "allowed",
    reason: "Static deterministic mock data for the v0.1.4 review gate.",
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
    filePath: "apps/control-center/components/app-shell.tsx",
    changeType: "modified",
    scopeStatus: "allowed",
    reason: "Wires the existing review gate into the static dashboard shell.",
    owningArea: "Control Center UI",
  },
];

export const TEST_EVIDENCE: TestEvidence[] = [
  {
    id: "te-1",
    label: "pnpm lint",
    command: "pnpm lint",
    result: "PASS",
    required: true,
    reason: "ESLint completed with zero errors for v0.1.4.",
  },
  {
    id: "te-2",
    label: "pnpm build",
    command: "pnpm build",
    result: "PASS",
    required: true,
    reason: "Next.js production build completed for v0.1.4.",
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
    result: "PASS",
    required: true,
    reason: "v0.1.4 changed only Control Center frontend files.",
  },
  {
    id: "te-5",
    label: "latest UI commit",
    command: "git log --oneline -1",
    result: "PASS",
    required: true,
    reason: "798c88b feat(ui): add operator review and commit gate flow.",
  },
  {
    id: "te-6",
    label: "deployment evidence",
    command: "vercel deployment review",
    result: "PASS",
    required: true,
    reason: "Control Center v0.1.4 is deployed.",
  },
];

export const COMMIT_CHECKLIST: CommitChecklistItem[] = [
  {
    id: "cc-1",
    label: "Codex review PASS",
    status: "pass",
    reason: "Codex returned a passing review summary for the v0.1.4 UI flow.",
  },
  {
    id: "cc-2",
    label: "changed files inside allowed scope",
    status: "pass",
    reason: "All listed files are under apps/control-center/.",
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
    status: "pass",
    reason: "Scope review lists no forbidden changed files.",
  },
  {
    id: "cc-7",
    label: "no backend/API/network behavior",
    status: "pass",
    reason: "Static scan found no prohibited behavior.",
  },
  {
    id: "cc-8",
    label: "remote state reviewed",
    status: "pass",
    reason: "Latest UI commit is present on main and deployed.",
  },
  {
    id: "cc-9",
    label: "commit evidence archived",
    status: "pass",
    reason: "Commit 798c88b is shown as the latest v0.1.4 evidence.",
  },
];

export const REMOTE_SAFETY: RemoteSafetyCheck = {
  verdict: "REMOTE_SAFE",
  branch: "main",
  localAheadCommits: 0,
  remoteOnlyCommits: 0,
  workingTree: "clean",
  evidence: [
    {
      id: "rs-1",
      label: "git fetch origin",
      value: "completed in operator preflight",
      result: "PASS",
    },
    {
      id: "rs-2",
      label: "git status --short",
      value: "clean",
      result: "PASS",
    },
    {
      id: "rs-3",
      label: "git rev-parse HEAD",
      value: "798c88b24f5ce28e30b26f458c1eedb16c6b7bec",
      result: "PASS",
    },
    {
      id: "rs-4",
      label: "git rev-parse origin/main",
      value: "798c88b24f5ce28e30b26f458c1eedb16c6b7bec",
      result: "PASS",
    },
  ],
};

export const OPERATOR_REVIEW_GATE: OperatorReviewGate = {
  reviewStatus: "PASS",
  reviewer: "Codex",
  reviewedTaskId: "task-05",
  reviewSummary:
    "Control Center v0.1.4 review gate is complete and deployed. Latest UI commit: 798c88b feat(ui): add operator review and commit gate flow.",
  recommendedOperatorAction:
    "Keep the review gate visible as committed evidence; use Stage 4.17 or v0.1.5 for the next planning target.",
  gateVerdict: "COMMIT_READY",
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
      "v0.1.4 is already committed and deployed.",
      "The UI never executes git commands.",
      "Next archive work belongs in Control Center v0.1.5.",
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
