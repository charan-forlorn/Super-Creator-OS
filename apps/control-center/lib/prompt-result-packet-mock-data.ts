// SCOS Control Center — Stage 5.4 Unified Prompt & Result Packet mock data.
// Static, deterministic display data only. Nothing here is executed and
// nothing is generated at runtime (no Date.now / Math.random / randomUUID);
// ids and timestamps are fixed literals shaped like the Python builder's
// sha256-derived output. Mirrors scos/control_center/prompt_result_packet_builder.py
// (id format, routing table) and prompt_result_packet_models.py (field shapes).

import type {
  PacketFlowStageView,
  PacketRoutingDecisionView,
  PacketScenarioView,
} from "./prompt-result-packet-types";

/**
 * Scenario 1: ChatGPT planning -> Claude Code implementation.
 * (planning_result PASS -> claude_code / implementation_prompt)
 */
const SCENARIO_1: PacketScenarioView = {
  scenarioId: "scenario-1-planning-to-implementation",
  label: "1. ChatGPT plans, hands off to Claude Code",
  prompt: {
    packetId: "pp-a1c3e5f7091b2d4f",
    packetType: "planning_prompt",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "operator",
    targetAgent: "chatgpt",
    targetRuntimeId: "chatgpt_app",
    title: "Draft the Stage 5.4 packet layer plan",
    objective: "Produce a concrete implementation plan for the packet layer.",
    promptBody:
      "Draft a plan for the Unified Prompt & Result Packet layer covering models, builder, store, tests, and docs.",
    contextRefs: [
      {
        refId: "ref-5401-stage-goal",
        refType: "specification",
        title: "Stage 5.4 task spec",
        path: null,
        summary: "Full field-level spec for the packet layer.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["stdlib only", "no network", "no clipboard"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["decision"],
    createdAt: "2026-07-06T09:00:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-b2d4f6081a2c3e5b",
    promptPacketId: "pp-a1c3e5f7091b2d4f",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "chatgpt",
    targetAgent: "operator",
    resultType: "planning_result",
    verdict: "PASS",
    summary: "Plan drafted: models, builder, store, docs, tests, frontend mock.",
    artifacts: [
      {
        artifactId: "artifact-5401-plan",
        artifactType: "decision",
        path: null,
        summary: "Approved implementation plan for Stage 5.4.",
        sha256: null,
        required: true,
      },
    ],
    blockers: [],
    nextAction: "Hand off implementation to Claude Code.",
    recommendedNextAgent: "claude_code",
    createdAt: "2026-07-06T09:15:00Z",
    status: "next_prompt_ready",
  },
  routing: {
    decisionId: "rd-c3e5f709112b3d4c",
    sourceResultPacketId: "rp-b2d4f6081a2c3e5b",
    nextAgent: "claude_code",
    nextPacketType: "implementation_prompt",
    reason: "Plan approved; ready for implementation.",
    priority: "normal",
    requiresOperatorApproval: true,
  },
};

/**
 * Scenario 2: Claude Code implementation -> Codex review.
 * (implementation_result PASS -> codex / review_prompt)
 */
const SCENARIO_2: PacketScenarioView = {
  scenarioId: "scenario-2-implementation-to-review",
  label: "2. Claude Code implements, hands off to Codex",
  prompt: {
    packetId: "pp-d4f608121a2c3e5d",
    packetType: "implementation_prompt",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "chatgpt",
    targetAgent: "claude_code",
    targetRuntimeId: "claude_code_cli",
    title: "Implement the Stage 5.4 packet layer",
    objective: "Implement the models, builder, and store per the approved plan.",
    promptBody:
      "Implement prompt_result_packet_models.py, prompt_result_packet_builder.py, and prompt_result_packet_store.py per the approved plan.",
    contextRefs: [
      {
        refId: "ref-5401-plan",
        refType: "stage_plan",
        title: "Approved Stage 5.4 plan",
        path: null,
        summary: "The plan produced in scenario 1.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["stdlib only", "match Stage 5.2/5.3 dataclass conventions"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["implementation_report", "test_output"],
    createdAt: "2026-07-06T09:20:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-e5f70913132c3e5e",
    promptPacketId: "pp-d4f608121a2c3e5d",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "claude_code",
    targetAgent: "chatgpt",
    resultType: "implementation_result",
    verdict: "PASS",
    summary: "Models, builder, and store implemented; all new tests pass.",
    artifacts: [
      {
        artifactId: "artifact-5401-impl-report",
        artifactType: "implementation_report",
        path: null,
        summary: "3 new modules, 3 new test files, all green.",
        sha256: null,
        required: true,
      },
      {
        artifactId: "artifact-5401-test-output",
        artifactType: "test_output",
        path: null,
        summary: "94 assertions passed across the 3 new test files.",
        sha256: null,
        required: true,
      },
    ],
    blockers: [],
    nextAction: "Route to Codex for review.",
    recommendedNextAgent: "codex",
    createdAt: "2026-07-06T09:40:00Z",
    status: "next_prompt_ready",
  },
  routing: {
    decisionId: "rd-f708131315394c5f",
    sourceResultPacketId: "rp-e5f70913132c3e5e",
    nextAgent: "codex",
    nextPacketType: "review_prompt",
    reason: "Implementation complete; ready for review.",
    priority: "normal",
    requiresOperatorApproval: true,
  },
};

/**
 * Scenario 3: Codex review finds an issue -> routes back to Claude Code.
 * (review_result NEEDS_FIX -> claude_code / implementation_prompt)
 */
const SCENARIO_3: PacketScenarioView = {
  scenarioId: "scenario-3-review-needs-fix",
  label: "3. Codex requests a fix, routes back to Claude Code",
  prompt: {
    packetId: "pp-081315173a4c5d6f",
    packetType: "review_prompt",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "claude_code",
    targetAgent: "codex",
    targetRuntimeId: "codex_cli",
    title: "Review the Stage 5.4 implementation",
    objective: "Review the packet layer implementation for correctness.",
    promptBody: "Review prompt_result_packet_models.py and prompt_result_packet_builder.py for correctness.",
    contextRefs: [
      {
        refId: "ref-5401-impl-report",
        refType: "implementation_report",
        title: "Implementation report",
        path: null,
        summary: "Report produced in scenario 2.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["read-only review", "no direct edits"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["review_report"],
    createdAt: "2026-07-06T09:45:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-1315173a4c5d6e70",
    promptPacketId: "pp-081315173a4c5d6f",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "codex",
    targetAgent: "claude_code",
    resultType: "review_result",
    verdict: "NEEDS_FIX",
    summary: "Missing edge-case test for empty metadata pairs.",
    artifacts: [
      {
        artifactId: "artifact-5401-review-report",
        artifactType: "review_report",
        path: null,
        summary: "One gap found: empty metadata tuple is not covered by a test.",
        sha256: null,
        required: true,
      },
    ],
    blockers: ["Missing test coverage for empty metadata tuples."],
    nextAction: "Add the missing test and resubmit.",
    recommendedNextAgent: "claude_code",
    createdAt: "2026-07-06T09:55:00Z",
    status: "review_required",
  },
  routing: {
    decisionId: "rd-15173a4c5d6e70f8",
    sourceResultPacketId: "rp-1315173a4c5d6e70",
    nextAgent: "claude_code",
    nextPacketType: "implementation_prompt",
    reason: "Review found a gap; route back for a fix.",
    priority: "high",
    requiresOperatorApproval: true,
  },
};

/**
 * Scenario 4: Codex review passes -> routes to Hermes for audit.
 * (review_result PASS -> hermes / audit_prompt)
 */
const SCENARIO_4: PacketScenarioView = {
  scenarioId: "scenario-4-review-pass-to-audit",
  label: "4. Codex approves, routes to Hermes for audit",
  prompt: {
    packetId: "pp-173a4c5d6e70f819",
    packetType: "review_prompt",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "claude_code",
    targetAgent: "codex",
    targetRuntimeId: "codex_cli",
    title: "Re-review the Stage 5.4 implementation",
    objective: "Re-review the packet layer implementation after the fix.",
    promptBody: "Re-review prompt_result_packet_models.py after the missing test was added.",
    contextRefs: [
      {
        refId: "ref-5401-fix-report",
        refType: "implementation_report",
        title: "Fix report",
        path: null,
        summary: "The missing metadata test was added.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["read-only review"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["review_report"],
    createdAt: "2026-07-06T10:00:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-3a4c5d6e70f8192a",
    promptPacketId: "pp-173a4c5d6e70f819",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "codex",
    targetAgent: "claude_code",
    resultType: "review_result",
    verdict: "PASS",
    summary: "Fix confirmed; review passed.",
    artifacts: [
      {
        artifactId: "artifact-5401-review-pass",
        artifactType: "review_report",
        path: null,
        summary: "All prior findings resolved.",
        sha256: null,
        required: true,
      },
    ],
    blockers: [],
    nextAction: "Route to Hermes for a repo-health audit.",
    recommendedNextAgent: "hermes",
    createdAt: "2026-07-06T10:10:00Z",
    status: "next_prompt_ready",
  },
  routing: {
    decisionId: "rd-4c5d6e70f8192a3b",
    sourceResultPacketId: "rp-3a4c5d6e70f8192a",
    nextAgent: "hermes",
    nextPacketType: "audit_prompt",
    reason: "Review passed; ready for repo-health audit.",
    priority: "normal",
    requiresOperatorApproval: true,
  },
};

/**
 * Scenario 5: Hermes audit passes -> routes to ChatGPT for a status update.
 * (audit_result PASS -> chatgpt / status_update_prompt)
 */
const SCENARIO_5: PacketScenarioView = {
  scenarioId: "scenario-5-audit-to-status-update",
  label: "5. Hermes audits, ChatGPT summarizes",
  prompt: {
    packetId: "pp-5d6e70f8192a3b4c",
    packetType: "audit_prompt",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "codex",
    targetAgent: "hermes",
    targetRuntimeId: "hermes_cli",
    title: "Audit the Stage 5.4 implementation",
    objective: "Audit repo health for the Stage 5.4 changes.",
    promptBody: "Audit the packet layer implementation and its test coverage for repo health.",
    contextRefs: [
      {
        refId: "ref-5401-review-pass",
        refType: "review_report",
        title: "Review pass report",
        path: null,
        summary: "Codex's passing review report.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["read-only audit"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["audit_report"],
    createdAt: "2026-07-06T10:15:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-6e70f8192a3b4c5d",
    promptPacketId: "pp-5d6e70f8192a3b4c",
    sessionId: "session-5401",
    taskId: "task-5401",
    sourceAgent: "hermes",
    targetAgent: "codex",
    resultType: "audit_result",
    verdict: "PASS",
    summary: "Repo health audit passed; no regressions detected.",
    artifacts: [
      {
        artifactId: "artifact-5401-audit-report",
        artifactType: "audit_report",
        path: null,
        summary: "All Stage 5.1-5.3 regression tests remain green.",
        sha256: null,
        required: true,
      },
    ],
    blockers: [],
    nextAction: "Route to ChatGPT to summarize stage completion.",
    recommendedNextAgent: "chatgpt",
    createdAt: "2026-07-06T10:25:00Z",
    status: "next_prompt_ready",
  },
  routing: {
    decisionId: "rd-70f8192a3b4c5d6e",
    sourceResultPacketId: "rp-6e70f8192a3b4c5d",
    nextAgent: "chatgpt",
    nextPacketType: "status_update_prompt",
    reason: "Audit passed; ready for a status summary.",
    priority: "normal",
    requiresOperatorApproval: true,
  },
};

/**
 * Scenario 6: a BLOCKED result that requires operator review instead of
 * continuing the automated chain.
 * (any result_type + BLOCKED -> operator / manual_handoff_prompt)
 */
const SCENARIO_6: PacketScenarioView = {
  scenarioId: "scenario-6-blocked-operator-review",
  label: "6. Blocked audit — escalated to operator",
  prompt: {
    packetId: "pp-8192a3b4c5d6e70f",
    packetType: "audit_prompt",
    sessionId: "session-5402",
    taskId: "task-5402",
    sourceAgent: "codex",
    targetAgent: "hermes",
    targetRuntimeId: "hermes_cli",
    title: "Audit a release-gate candidate",
    objective: "Audit repo health before a release gate.",
    promptBody: "Audit the release-gate candidate branch for repo health issues.",
    contextRefs: [
      {
        refId: "ref-5402-release-candidate",
        refType: "git_commit",
        title: "Release candidate commit",
        path: null,
        summary: "The commit under audit.",
        required: true,
        sha256: null,
      },
    ],
    constraints: ["read-only audit"],
    expectedResultFormat: "structured_report",
    expectedArtifacts: ["audit_report"],
    createdAt: "2026-07-06T10:30:00Z",
    status: "sent_to_agent",
  },
  result: {
    resultPacketId: "rp-92a3b4c5d6e70f81",
    promptPacketId: "pp-8192a3b4c5d6e70f",
    sessionId: "session-5402",
    taskId: "task-5402",
    sourceAgent: "hermes",
    targetAgent: "codex",
    resultType: "audit_result",
    verdict: "BLOCKED",
    summary: "Audit found an unresolved security finding; cannot proceed automatically.",
    artifacts: [
      {
        artifactId: "artifact-5402-blocker-list",
        artifactType: "blocker_list",
        path: null,
        summary: "1 unresolved finding requiring human judgment.",
        sha256: null,
        required: true,
      },
    ],
    blockers: ["Unresolved security finding requires operator judgment before proceeding."],
    nextAction: "Escalate to operator for manual review.",
    recommendedNextAgent: "operator",
    createdAt: "2026-07-06T10:40:00Z",
    status: "blocked",
  },
  routing: {
    decisionId: "rd-a3b4c5d6e70f8192",
    sourceResultPacketId: "rp-92a3b4c5d6e70f81",
    nextAgent: "operator",
    nextPacketType: "manual_handoff_prompt",
    reason: "BLOCKED verdict always escalates to operator manual handoff.",
    priority: "urgent",
    requiresOperatorApproval: true,
  },
};

export const PACKET_SCENARIOS: readonly PacketScenarioView[] = [
  SCENARIO_1,
  SCENARIO_2,
  SCENARIO_3,
  SCENARIO_4,
  SCENARIO_5,
  SCENARIO_6,
];

export const PROMPT_PACKETS = PACKET_SCENARIOS.map((scenario) => scenario.prompt);
export const RESULT_PACKETS = PACKET_SCENARIOS.map((scenario) => scenario.result);
export const PACKET_ROUTING_DECISIONS: readonly PacketRoutingDecisionView[] =
  PACKET_SCENARIOS.map((scenario) => scenario.routing).filter(
    (routing): routing is PacketRoutingDecisionView => routing !== null,
  );

/** The named 5-stage chain: ChatGPT -> Claude Code -> Codex -> Hermes -> ChatGPT. */
export const PACKET_ROUTING_FLOW: readonly PacketFlowStageView[] = [
  {
    stageLabel: "1. Planning",
    agent: "chatgpt",
    packetType: "planning_prompt",
    resultVerdict: "PASS",
    note: "ChatGPT drafts the stage plan.",
  },
  {
    stageLabel: "2. Implementation",
    agent: "claude_code",
    packetType: "implementation_prompt",
    resultVerdict: "PASS",
    note: "Claude Code implements against the plan.",
  },
  {
    stageLabel: "3. Review",
    agent: "codex",
    packetType: "review_prompt",
    resultVerdict: "NEEDS_FIX",
    note: "Codex requests a fix before sign-off.",
  },
  {
    stageLabel: "4. Audit",
    agent: "hermes",
    packetType: "audit_prompt",
    resultVerdict: "PASS",
    note: "Hermes audits the corrected implementation.",
  },
  {
    stageLabel: "5. Status Update",
    agent: "chatgpt",
    packetType: "status_update_prompt",
    resultVerdict: null,
    note: "ChatGPT reports the stage as complete.",
  },
];
