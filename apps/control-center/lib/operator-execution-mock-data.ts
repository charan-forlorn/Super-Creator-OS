// SCOS Control Center - Stage 5.9 static mock data for the Operator
// Execution Console. Deterministic, hand-authored fixtures only. No clock,
// no random, no UUIDs, no fetch. IDs mirror the deterministic sha256-prefixed
// shapes produced by scos/control_center/operator_execution_runbook.py but are
// fixed strings here (this is a static UI mirror, not a live computation).

import type {
  CommandExecutionCaptureView,
  ExecutionSafetyCheckView,
  ManualCommandRunbookView,
  OperatorExecutionConsoleRow,
  OperatorExecutionOutcomeView,
  RunbookCommandStepView,
} from "./operator-execution-types";

const COMMIT_STEPS: readonly RunbookCommandStepView[] = [
  {
    stepId: "rbs-commit-1",
    stepOrder: 1,
    title: "Inspect working tree",
    command: "git status --short --untracked-files=all",
    commandType: "git_status",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Only approved Stage 5.9 files should appear.",
    riskLevel: "medium",
  },
  {
    stepId: "rbs-commit-2",
    stepOrder: 2,
    title: "Stage the approved files",
    command: "git add scos/control_center/operator_execution_models.py",
    commandType: "git_add",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Stages exactly the approved paths; nothing else.",
    riskLevel: "medium",
  },
  {
    stepId: "rbs-commit-3",
    stepOrder: 3,
    title: "Review staged stat",
    command: "git diff --cached --stat",
    commandType: "git_diff",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Staged diff scope must match the approved proposal.",
    riskLevel: "medium",
  },
  {
    stepId: "rbs-commit-4",
    stepOrder: 4,
    title: "Review staged file list",
    command: "git diff --cached --name-only",
    commandType: "git_diff",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Must equal the approved staged paths exactly.",
    riskLevel: "medium",
  },
  {
    stepId: "rbs-commit-5",
    stepOrder: 5,
    title: "Create the commit",
    command:
      'git commit -m "feat(control-center): add Stage 5.9 local operator execution console"',
    commandType: "git_commit",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Expect a [main <hash>] summary line.",
    riskLevel: "high",
  },
  {
    stepId: "rbs-commit-6",
    stepOrder: 6,
    title: "Confirm post-commit status",
    command: "git status -sb",
    commandType: "git_status",
    shell: "powershell",
    workingDirectory: ".",
    requiresManualCopy: true,
    requiresOperatorConfirmation: true,
    expectedResultHint: "Clean tree on main; NO push happens here.",
    riskLevel: "medium",
  },
];

const COMMIT_SAFETY: readonly ExecutionSafetyCheckView[] = [
  {
    checkId: "rbc-commit-1",
    title: "Confirm branch is main",
    description: "The commit must land on the main branch.",
    status: "passed",
    severity: "critical",
    required: true,
    operatorInstruction: "Run `git status -sb` and confirm the branch is `main`.",
  },
  {
    checkId: "rbc-commit-2",
    title: "Confirm working tree contains only expected Stage files",
    description: "No unexpected file may be committed.",
    status: "passed",
    severity: "error",
    required: true,
    operatorInstruction:
      "Compare `git status --short` against the approved file list; stop if anything unexpected appears.",
  },
  {
    checkId: "rbc-commit-3",
    title: "Confirm staged files match the approved proposal",
    description: "Staged paths must equal the approved proposal.",
    status: "pending",
    severity: "error",
    required: true,
    operatorInstruction:
      "Run `git diff --cached --name-only` and match against the approved staged paths.",
  },
  {
    checkId: "rbc-commit-4",
    title: "Confirm commit message matches the approved proposal",
    description: "Use the approved commit message verbatim.",
    status: "pending",
    severity: "error",
    required: true,
    operatorInstruction: "Copy the commit message from the approved proposal; do not edit it.",
  },
  {
    checkId: "rbc-commit-5",
    title: "Confirm tests were reviewed",
    description: "Stage test evidence must be green.",
    status: "passed",
    severity: "warning",
    required: true,
    operatorInstruction: "Confirm the Stage 5.9 test evidence was reviewed and is green.",
  },
  {
    checkId: "rbc-commit-6",
    title: "Confirm operator approval exists",
    description: "A Stage 5.8 commit approval decision must be approved.",
    status: "passed",
    severity: "critical",
    required: true,
    operatorInstruction: "Verify the Stage 5.8 commit approval decision is `approved`.",
  },
  {
    checkId: "rbc-commit-7",
    title: "Confirm no push happens during the commit runbook",
    description: "This runbook commits only; push is separate.",
    status: "requires_review",
    severity: "critical",
    required: true,
    operatorInstruction:
      "Do NOT run `git push` here; push is a separate approved runbook.",
  },
];

// 1) Commit runbook from an approved Stage 5.8 commit proposal.
const COMMIT_RUNBOOK: ManualCommandRunbookView = {
  runbookId: "rb-commit-5f9a1c2d",
  sourceApprovalId: "cad-8b21f0c4",
  sourceCommitProposalId: "cp-3e77aa19",
  sourcePushProposalId: null,
  sessionId: "sess-59",
  taskId: "task-59",
  title: "Manual git commit runbook",
  objective:
    "Commit the approved staged files for Stage 5.9 with the approved commit message.",
  commandSummary:
    'git add …; git commit -m "feat(control-center): add Stage 5.9 local operator execution console"',
  runbookType: "commit_runbook",
  createdAt: "2026-07-06T09:00:00Z",
  status: "ready_for_operator",
  safetyChecks: COMMIT_SAFETY,
  commandSteps: COMMIT_STEPS,
  expectedOutputs: [
    "A [main <hash>] commit summary line",
    "`git status -sb` shows a clean tree on main",
  ],
  blockedReasons: [],
  operatorNotes: [
    "SCOS does not run these commands. Run them manually and paste the output back.",
    "Do NOT push in this runbook; push is a separate approved runbook.",
  ],
};

const PUSH_STEPS: readonly RunbookCommandStepView[] = [
  ["git fetch origin", "git_fetch", "Fetch latest remote refs", "Updates remote-tracking refs; no local changes."],
  ["git status -sb", "git_status", "Inspect status before push", "Confirm branch is main and the tree is clean."],
  ["git rev-parse HEAD", "git_status", "Record local HEAD", "Prints the local commit hash to be pushed."],
  ["git rev-parse origin/main", "git_status", "Record remote HEAD", "Prints the remote commit hash for comparison."],
  ["git log --oneline --left-right main...origin/main", "git_diff", "Compare local vs remote", "Confirm only local-ahead commits (<) exist."],
  ["git push origin main", "git_push", "Push the approved branch", "Expect a main -> main line. Never force."],
  ["git fetch origin", "git_fetch", "Re-fetch after push", "Refreshes remote refs after the push."],
  ["git status -sb", "git_status", "Inspect status after push", "Confirm the branch is up to date with origin/main."],
  ["git rev-parse HEAD", "git_status", "Record local HEAD after push", "Prints the local commit hash after push."],
  ["git rev-parse origin/main", "git_status", "Record remote HEAD after push", "Should now equal local HEAD (HEAD == origin/main)."],
  ["git log --oneline -6", "git_status", "Review recent history", "Confirms the pushed commit is at the top of history."],
].map(([command, commandType, title, hint], index) => ({
  stepId: `rbs-push-${index + 1}`,
  stepOrder: index + 1,
  title,
  command,
  commandType: commandType as RunbookCommandStepView["commandType"],
  shell: "powershell",
  workingDirectory: ".",
  requiresManualCopy: true,
  requiresOperatorConfirmation: true,
  expectedResultHint: hint,
  riskLevel: commandType === "git_push" ? "critical" : "medium",
}));

const PUSH_SAFETY: readonly ExecutionSafetyCheckView[] = [
  { checkId: "rbc-push-1", title: "Confirm commit exists locally", description: "The approved commit must be present locally.", status: "passed", severity: "critical", required: true, operatorInstruction: "Run `git rev-parse HEAD` and confirm the approved commit is present." },
  { checkId: "rbc-push-2", title: "Confirm no remote-only commit exists", description: "No divergent remote commits.", status: "passed", severity: "error", required: true, operatorInstruction: "Run `git log --oneline --left-right main...origin/main`." },
  { checkId: "rbc-push-3", title: "Confirm branch is main", description: "Push only from main.", status: "passed", severity: "critical", required: true, operatorInstruction: "Run `git status -sb` and confirm the branch is `main`." },
  { checkId: "rbc-push-4", title: "Confirm HEAD state is understood", description: "Understand local vs remote HEAD.", status: "pending", severity: "warning", required: true, operatorInstruction: "Compare `git rev-parse HEAD` and `git rev-parse origin/main`." },
  { checkId: "rbc-push-5", title: "Confirm push approval exists", description: "Push approval is separate from commit approval.", status: "requires_review", severity: "critical", required: true, operatorInstruction: "Verify the Stage 5.8 push approval decision is `approved`." },
  { checkId: "rbc-push-6", title: "Confirm no force push is used", description: "Never force push.", status: "passed", severity: "critical", required: true, operatorInstruction: "Use a plain `git push`; never add `--force`." },
  { checkId: "rbc-push-7", title: "Confirm post-push verification will be run", description: "Verify sync after push.", status: "pending", severity: "warning", required: true, operatorInstruction: "Re-run fetch + status + rev-parse after the push." },
];

// 2) Push runbook from an approved Stage 5.8 push proposal.
const PUSH_RUNBOOK: ManualCommandRunbookView = {
  runbookId: "rb-push-7c04e6b1",
  sourceApprovalId: "pad-11d9ac30",
  sourceCommitProposalId: null,
  sourcePushProposalId: "pp-6a2f8e5c",
  sessionId: "sess-59",
  taskId: "task-59",
  title: "Manual git push runbook",
  objective: "Push main to origin after separate push approval.",
  commandSummary: "git push origin main",
  runbookType: "push_runbook",
  createdAt: "2026-07-06T09:20:00Z",
  status: "ready_for_operator",
  safetyChecks: PUSH_SAFETY,
  commandSteps: PUSH_STEPS,
  expectedOutputs: [
    "A main -> main push confirmation line",
    "HEAD == origin/main after the push",
    "`git status -sb` shows the branch up to date",
  ],
  blockedReasons: [],
  operatorNotes: [
    "SCOS does not run these commands. Run them manually and paste the output back.",
    "Push approval is separate from commit approval; never force push.",
  ],
};

// 3) Blocked runbook requiring operator review.
const BLOCKED_RUNBOOK: ManualCommandRunbookView = {
  runbookId: "rb-verify-9d1b3a77",
  sourceApprovalId: null,
  sourceCommitProposalId: null,
  sourcePushProposalId: null,
  sessionId: "sess-59",
  taskId: "task-60",
  title: "Verification runbook (blocked)",
  objective: "Re-run the Stage test suite before any commit is proposed.",
  commandSummary: ".venv\\Scripts\\python.exe scripts\\test_smoke.py",
  runbookType: "verification_runbook",
  createdAt: "2026-07-06T09:40:00Z",
  status: "blocked",
  safetyChecks: [
    {
      checkId: "rbc-verify-1",
      title: "Confirm no approval exists yet",
      description: "This runbook is not backed by an approved proposal.",
      status: "failed",
      severity: "critical",
      required: true,
      operatorInstruction:
        "Do not run any git commit/push step until a Stage 5.8 approval exists.",
    },
  ],
  commandSteps: [
    {
      stepId: "rbs-verify-1",
      stepOrder: 1,
      title: "Run smoke tests",
      command: ".venv\\Scripts\\python.exe scripts\\test_smoke.py",
      commandType: "verification",
      shell: "powershell",
      workingDirectory: ".",
      requiresManualCopy: true,
      requiresOperatorConfirmation: true,
      expectedResultHint: "Expect SMOKE: PASS.",
      riskLevel: "low",
    },
  ],
  expectedOutputs: ["SMOKE: PASS"],
  blockedReasons: [
    "No approved commit/push proposal is linked to this runbook.",
    "Operator review required before any git step may be run.",
  ],
  operatorNotes: [
    "Blocked runbooks are read-only guidance; resolve the blockers before use.",
  ],
};

// 4) Captured PASS output (for the commit runbook).
const CAPTURE_PASS: CommandExecutionCaptureView = {
  captureId: "cap-commit-2f18b9d0",
  runbookId: "rb-commit-5f9a1c2d",
  sessionId: "sess-59",
  taskId: "task-59",
  operatorReportedCommand:
    'git commit -m "feat(control-center): add Stage 5.9 local operator execution console"',
  pastedOutputSummary: "Commit created on main; working tree clean afterward.",
  rawOutputExcerpt:
    "[main a1b2c3d] feat(control-center): add Stage 5.9 local operator execution console\n 6 files changed\nnothing to commit, working tree clean",
  exitStatusText: "exit 0",
  verdict: "PASS",
  capturedAt: "2026-07-06T09:12:00Z",
  evidencePaths: ["scos/work/control_center/command_execution_captures.jsonl"],
  warnings: [],
  blockers: [],
};

// 5) Captured FAIL / BLOCKED output (for the push runbook).
const CAPTURE_BLOCKED: CommandExecutionCaptureView = {
  captureId: "cap-push-4c7ea200",
  runbookId: "rb-push-7c04e6b1",
  sessionId: "sess-59",
  taskId: "task-59",
  operatorReportedCommand: "git push origin main",
  pastedOutputSummary: "Push rejected by remote; non-fast-forward.",
  rawOutputExcerpt:
    "error: failed to push some refs to 'origin'\n! [rejected]        main -> main (fetch first)\nhint: Updates were rejected because the remote contains work",
  exitStatusText: "exit 1",
  verdict: "BLOCKED",
  capturedAt: "2026-07-06T09:32:00Z",
  evidencePaths: [],
  warnings: ["Remote contains work not present locally."],
  blockers: ["Push was rejected (non-fast-forward); fetch/rebase then re-approve."],
};

// 6) Outcome recommending ChatGPT status update (from the PASS capture).
const OUTCOME_CHATGPT: OperatorExecutionOutcomeView = {
  outcomeId: "oeo-commit-1a2b3c4d",
  runbookId: "rb-commit-5f9a1c2d",
  captureId: "cap-commit-2f18b9d0",
  sessionId: "sess-59",
  taskId: "task-59",
  outcome: "command_succeeded",
  summary: "Commit runbook classified PASS with no warnings or blockers.",
  recommendedNextAction: "record_result_and_update_chatgpt_status",
  recommendedNextAgent: "chatgpt",
  operatorReviewRequired: false,
  createdAt: "2026-07-06T09:13:00Z",
};

// 7) Outcome recommending Codex review (a FAIL that routes back for a fix).
const OUTCOME_CODEX: OperatorExecutionOutcomeView = {
  outcomeId: "oeo-fix-5e6f7a8b",
  runbookId: "rb-commit-5f9a1c2d",
  captureId: "cap-commit-2f18b9d0",
  sessionId: "sess-59",
  taskId: "task-61",
  outcome: "command_failed",
  summary: "A follow-up build step failed; route back to Codex for a fix.",
  recommendedNextAction: "route_back_to_codex_for_fix",
  recommendedNextAgent: "codex",
  operatorReviewRequired: true,
  createdAt: "2026-07-06T09:18:00Z",
};

// 8) Outcome requiring operator manual review (from the BLOCKED push capture).
const OUTCOME_OPERATOR: OperatorExecutionOutcomeView = {
  outcomeId: "oeo-push-9a0b1c2d",
  runbookId: "rb-push-7c04e6b1",
  captureId: "cap-push-4c7ea200",
  sessionId: "sess-59",
  taskId: "task-59",
  outcome: "command_blocked",
  summary: "Push runbook classified BLOCKED; route back to operator review.",
  recommendedNextAction: "route_back_to_review_blocked",
  recommendedNextAgent: "operator",
  operatorReviewRequired: true,
  createdAt: "2026-07-06T09:33:00Z",
};

export const OPERATOR_EXECUTION_ROWS: readonly OperatorExecutionConsoleRow[] = [
  { runbook: COMMIT_RUNBOOK, capture: CAPTURE_PASS, outcome: OUTCOME_CHATGPT },
  { runbook: PUSH_RUNBOOK, capture: CAPTURE_BLOCKED, outcome: OUTCOME_OPERATOR },
  { runbook: BLOCKED_RUNBOOK, capture: null, outcome: null },
];

export const OPERATOR_EXECUTION_OUTCOMES: readonly OperatorExecutionOutcomeView[] = [
  OUTCOME_CHATGPT,
  OUTCOME_CODEX,
  OUTCOME_OPERATOR,
];

export {
  BLOCKED_RUNBOOK,
  CAPTURE_BLOCKED,
  CAPTURE_PASS,
  COMMIT_RUNBOOK,
  OUTCOME_CHATGPT,
  OUTCOME_CODEX,
  OUTCOME_OPERATOR,
  PUSH_RUNBOOK,
};
