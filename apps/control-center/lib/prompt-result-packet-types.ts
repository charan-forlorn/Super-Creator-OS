// SCOS Control Center — Stage 5.4 Unified Prompt & Result Packet types.
// Frontend prototype only: these mirror the Python models in
// scos/control_center/prompt_result_packet_models.py for static mock
// display. No backend contracts, no execution from the UI, no agent
// dispatch, no auto-routing.

export type PacketContextRefType =
  | "session"
  | "stage_plan"
  | "implementation_report"
  | "review_report"
  | "audit_report"
  | "file_path"
  | "git_commit"
  | "test_result"
  | "operator_note"
  | "specification"
  | "certification"
  | "handoff";

export type PromptPacketType =
  | "planning_prompt"
  | "implementation_prompt"
  | "review_prompt"
  | "audit_prompt"
  | "status_update_prompt"
  | "result_summary_prompt"
  | "release_gate_prompt"
  | "manual_handoff_prompt";

export type PacketAgentName = "chatgpt" | "claude_code" | "codex" | "hermes" | "operator";

export type PromptPacketStatus =
  | "drafted"
  | "ready_for_operator_review"
  | "approved_for_handoff"
  | "sent_to_agent"
  | "result_expected"
  | "cancelled"
  | "blocked";

export type ResultArtifactType =
  | "text_result"
  | "implementation_report"
  | "review_report"
  | "audit_report"
  | "test_output"
  | "changed_files"
  | "diff_summary"
  | "blocker_list"
  | "decision"
  | "next_action"
  | "certification_report";

export type PacketResultType =
  | "planning_result"
  | "implementation_result"
  | "review_result"
  | "audit_result"
  | "status_update_result"
  | "result_summary"
  | "release_gate_result"
  | "manual_handoff_result";

export type PacketVerdict =
  | "PASS"
  | "PASS_WITH_WARNINGS"
  | "NEEDS_FIX"
  | "BLOCKED"
  | "FAIL"
  | "INFO";

export type ResultPacketStatus =
  | "received"
  | "validated"
  | "review_required"
  | "next_prompt_ready"
  | "archived"
  | "blocked";

export type RoutingPriority = "low" | "normal" | "high" | "urgent";

export interface PacketContextRefView {
  refId: string;
  refType: PacketContextRefType;
  title: string;
  path: string | null;
  summary: string;
  required: boolean;
  sha256: string | null;
}

export interface PromptPacketView {
  packetId: string;
  packetType: PromptPacketType;
  sessionId: string;
  taskId: string;
  sourceAgent: PacketAgentName;
  targetAgent: PacketAgentName;
  targetRuntimeId: string;
  title: string;
  objective: string;
  promptBody: string;
  contextRefs: readonly PacketContextRefView[];
  constraints: readonly string[];
  expectedResultFormat: string;
  expectedArtifacts: readonly string[];
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  status: PromptPacketStatus;
}

export interface ResultArtifactView {
  artifactId: string;
  artifactType: ResultArtifactType;
  path: string | null;
  summary: string;
  sha256: string | null;
  required: boolean;
}

export interface ResultPacketView {
  resultPacketId: string;
  promptPacketId: string;
  sessionId: string;
  taskId: string;
  sourceAgent: PacketAgentName;
  targetAgent: PacketAgentName;
  resultType: PacketResultType;
  verdict: PacketVerdict;
  summary: string;
  artifacts: readonly ResultArtifactView[];
  blockers: readonly string[];
  nextAction: string | null;
  recommendedNextAgent: PacketAgentName | null;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  status: ResultPacketStatus;
}

export interface PacketRoutingDecisionView {
  decisionId: string;
  sourceResultPacketId: string;
  nextAgent: PacketAgentName;
  nextPacketType: PromptPacketType;
  reason: string;
  priority: RoutingPriority;
  requiresOperatorApproval: boolean;
}

/** One prompt/result/routing triple for one stage of the mock flow. */
export interface PacketScenarioView {
  scenarioId: string;
  label: string;
  prompt: PromptPacketView;
  result: ResultPacketView;
  routing: PacketRoutingDecisionView | null;
}

/** One node in the mock 5-stage routing flow visualization. */
export interface PacketFlowStageView {
  stageLabel: string;
  agent: PacketAgentName;
  packetType: PromptPacketType;
  resultVerdict: PacketVerdict | null;
  note: string;
}
