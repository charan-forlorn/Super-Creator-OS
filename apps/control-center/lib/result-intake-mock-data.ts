// SCOS Control Center - Stage 5.7 static mock data for the AI Result Intake
// & ChatGPT Status Update Loop. All values are hand-authored constants — no
// fetch, no timers, no random ids, no clock reads.

import type {
  AIResultIntakeRecordView,
  ChatGPTStatusUpdatePacketView,
  NextActionDecisionView,
  ProjectStateUpdateView,
} from "./result-intake-types";

export const RESULT_INTAKES: readonly AIResultIntakeRecordView[] = [
  {
    intakeId: "ri-7f3a9c1d2b4e5f60",
    sessionId: "sess-stage-5-7",
    taskId: "task-hermes-audit-01",
    sourceAgent: "hermes",
    sourceRuntimeId: "hermes-cli-local",
    title: "Hermes audit — Stage 5.6 workflow router",
    normalizedSummary:
      "Hermes audit complete. All Stage 5.6 contracts hold, no regressions found. Verdict: PASS",
    verdict: "PASS",
    confidence: "high",
    artifacts: [
      {
        artifactId: "art-audit-report",
        artifactType: "audit_report",
        title: "Audit report",
        path: "docs/certification/Stage-5.6-plan.md",
        summary: "Audit checklist, all items green.",
        required: true,
      },
      {
        artifactId: "art-test-report",
        artifactType: "test_report",
        title: "Test run output",
        path: null,
        summary: "39 passed, 0 failed across Stage 5.1-5.6 regressions.",
        required: false,
      },
    ],
    blockers: [],
    warnings: ["Coverage on workflow_router.py edge cases is thin."],
    testsSummary: "39 passed, 0 failed",
    changedFilesSummary: "No files changed (audit-only pass)",
    operatorReviewRequired: false,
    createdAt: "2026-07-06T09:12:00Z",
    status: "ready_for_chatgpt_update",
  },
  {
    intakeId: "ri-1a2b3c4d5e6f7081",
    sessionId: "sess-stage-5-7",
    taskId: "task-codex-review-04",
    sourceAgent: "codex",
    sourceRuntimeId: "codex-cli-local",
    title: "Codex review — result intake builder",
    normalizedSummary:
      "Review failed: verdict classification precedence was ambiguous for mixed-marker text and needs a documented tie-break rule before merge.",
    verdict: "FAIL",
    confidence: "medium",
    artifacts: [
      {
        artifactId: "art-review-report",
        artifactType: "review_report",
        title: "Review report",
        path: null,
        summary: "One correctness finding, no security findings.",
        required: true,
      },
    ],
    blockers: ["Verdict precedence rule is undocumented for mixed-marker text"],
    warnings: [],
    testsSummary: "Not reported",
    changedFilesSummary: "Not reported",
    operatorReviewRequired: true,
    createdAt: "2026-07-06T09:20:00Z",
    status: "review_required",
  },
  {
    intakeId: "ri-91a8b7c6d5e4f302",
    sessionId: "sess-stage-5-7",
    taskId: "task-claude-fix-02",
    sourceAgent: "claude_code",
    sourceRuntimeId: "claude-code-cli",
    title: "Claude Code — Stage 5.7 store implementation",
    normalizedSummary:
      "Blocked: sandboxed git fetch origin failed with a permission error on .git/FETCH_HEAD; cannot verify branch is up to date before editing.",
    verdict: "BLOCKED",
    confidence: "high",
    artifacts: [
      {
        artifactId: "art-command-output",
        artifactType: "command_output",
        title: "git fetch output",
        path: null,
        summary: "error: cannot open '.git/FETCH_HEAD': Permission denied",
        required: true,
      },
    ],
    blockers: ["git fetch origin denied in sandbox; needs operator-run preflight"],
    warnings: [],
    testsSummary: "Not reported",
    changedFilesSummary: "Not reported",
    operatorReviewRequired: true,
    createdAt: "2026-07-06T08:55:00Z",
    status: "blocked",
  },
  {
    intakeId: "ri-3e4d5c6b7a809112",
    sessionId: "sess-stage-5-7",
    taskId: "task-operator-note-01",
    sourceAgent: "operator",
    sourceRuntimeId: "manual-paste",
    title: "Operator note — manual smoke check",
    normalizedSummary:
      "Ran the app locally and clicked through the new panels; layout looks right on desktop, verdict badges read clearly. Partial: did not check mobile breakpoints yet.",
    verdict: "PARTIAL",
    confidence: "low",
    artifacts: [
      {
        artifactId: "art-screenshot-note",
        artifactType: "screenshot_note",
        title: "Desktop screenshot note",
        path: null,
        summary: "Panels render correctly at 1440px width.",
        required: false,
      },
    ],
    blockers: [],
    warnings: ["Mobile breakpoints not yet checked"],
    testsSummary: "Not reported",
    changedFilesSummary: "Not reported",
    operatorReviewRequired: true,
    createdAt: "2026-07-06T09:30:00Z",
    status: "review_required",
  },
] as const;

export const CHATGPT_STATUS_UPDATE: ChatGPTStatusUpdatePacketView = {
  updatePacketId: "cgu-4b5c6d7e8f9a0b1c",
  intakeId: "ri-7f3a9c1d2b4e5f60",
  sessionId: "sess-stage-5-7",
  taskId: "task-hermes-audit-01",
  targetRuntimeId: "chatgpt-web",
  title: "Hermes audit — Stage 5.6 workflow router",
  statusUpdateBody:
    "Session: sess-stage-5-7\n" +
    "Task: task-hermes-audit-01\n" +
    "Source Agent: hermes\n" +
    "Verdict: PASS\n\n" +
    "Summary:\n" +
    "Hermes audit complete. All Stage 5.6 contracts hold, no regressions found. Verdict: PASS\n\n" +
    "Blockers:\n" +
    "None\n\n" +
    "Warnings:\n" +
    "- Coverage on workflow_router.py edge cases is thin.\n\n" +
    "Tests: 39 passed, 0 failed\n" +
    "Changed Files: No files changed (audit-only pass)\n\n" +
    "Evidence:\n" +
    "- docs/certification/Stage-5.6-plan.md\n" +
    "- art-test-report\n\n" +
    "Requested ChatGPT Action: summarize_status\n\n" +
    "Constraints:\n" +
    "- Do not assume hidden files.\n" +
    "- Do not claim work committed/pushed unless evidence says so.\n" +
    "- Produce next action only from provided evidence.",
  resultVerdict: "PASS",
  resultSummary:
    "Hermes audit complete. All Stage 5.6 contracts hold, no regressions found. Verdict: PASS",
  evidenceRefs: ["docs/certification/Stage-5.6-plan.md", "art-test-report"],
  requestedChatGPTAction: "summarize_status",
  createdAt: "2026-07-06T09:13:00Z",
  status: "ready_for_chatgpt_update",
};

export const PROJECT_STATE_UPDATE: ProjectStateUpdateView = {
  stateUpdateId: "psu-2c3d4e5f60718293",
  intakeId: "ri-7f3a9c1d2b4e5f60",
  sessionId: "sess-stage-5-7",
  taskId: "task-hermes-audit-01",
  previousStage: "5.6",
  currentStage: "5.7",
  taskStatus: "approved",
  stageStatus: "active",
  latestAgent: "hermes",
  latestVerdict: "PASS",
  summary: "hermes reported PASS for task task-hermes-audit-01 at stage 5.7.",
  updatedAt: "2026-07-06T09:14:00Z",
  evidenceRefs: ["docs/certification/Stage-5.6-plan.md", "art-test-report"],
};

export const NEXT_ACTION_DECISION: NextActionDecisionView = {
  nextActionId: "nad-5f60718293a4b5c6",
  intakeId: "ri-7f3a9c1d2b4e5f60",
  sessionId: "sess-stage-5-7",
  taskId: "task-hermes-audit-01",
  recommendedAction: "send_to_chatgpt_status_update",
  targetAgent: "chatgpt",
  targetRuntimeId: "chatgpt-web",
  priority: "normal",
  reason: "hermes reported PASS; route to ChatGPT for a status update.",
  requiresOperatorApproval: true,
  createdAt: "2026-07-06T09:15:00Z",
};
