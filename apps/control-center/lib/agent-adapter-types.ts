// SCOS Control Center — Stage 5.3 AI Agent Adapter Contract Layer types.
// Frontend prototype only: these mirror the Python models in
// scos/control_center/agent_adapter_models.py for static mock display.
// No backend contracts, no execution from the UI, no agent dispatch.

export type AdapterAgentName =
  | "chatgpt"
  | "claude_code"
  | "codex"
  | "hermes"
  | "manual_clipboard";

export type AdapterRuntimeType =
  | "chatgpt_app"
  | "chatgpt_web"
  | "openai_api"
  | "claude_code_vscode"
  | "claude_code_cli"
  | "codex_app"
  | "codex_cli"
  | "hermes_cli"
  | "manual_clipboard";

export type AdapterTaskType =
  | "planning"
  | "implementation"
  | "review"
  | "audit"
  | "status_update"
  | "prompt_build"
  | "result_summary"
  | "release_gate"
  | "git_review"
  | "manual_handoff";

export type AdapterDeliveryMode = "contract_only" | "manual_clipboard" | "simulated";

export type AdapterResultType =
  | "plan"
  | "implementation_report"
  | "review_report"
  | "audit_report"
  | "status_update"
  | "prompt_packet"
  | "result_summary"
  | "release_gate_report"
  | "git_review_report"
  | "manual_handoff_note";

export type AdapterStatus =
  | "accepted"
  | "prepared"
  | "simulated_sent"
  | "waiting_for_operator"
  | "result_ready"
  | "failed"
  | "blocked";

export type AdapterEventType =
  | "request_created"
  | "request_validated"
  | "adapter_selected"
  | "prompt_prepared"
  | "manual_clipboard_ready"
  | "simulated_sent"
  | "result_simulated"
  | "result_ready"
  | "blocked";

/** [key, value] string pair, mirroring the Python tuple-of-pairs shape. */
export type StringPair = readonly [string, string];

export interface AgentAdapterCapabilityView {
  capabilityId: string;
  agentName: AdapterAgentName;
  runtimeType: AdapterRuntimeType;
  taskTypes: readonly AdapterTaskType[];
  supportsPromptDelivery: boolean;
  supportsResultCapture: boolean;
  supportsStatusCheck: boolean;
  supportsManualFallback: boolean;
}

export interface AgentAdapterRequestView {
  requestId: string;
  sessionId: string;
  taskId: string;
  agentName: AdapterAgentName;
  runtimeId: string;
  runtimeType: AdapterRuntimeType;
  taskType: AdapterTaskType;
  promptText: string;
  inputSummary: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  deliveryMode: AdapterDeliveryMode;
  expectedResultType: AdapterResultType;
}

export interface AgentAdapterResultView {
  resultId: string;
  requestId: string;
  sessionId: string;
  agentName: AdapterAgentName;
  runtimeId: string;
  status: AdapterStatus;
  resultType: AdapterResultType;
  resultSummary: string;
  outputText: string | null;
  outputPath: string | null;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
  nextAction: string | null;
}

export interface AgentAdapterSimulationEventView {
  eventId: string;
  requestId: string;
  sessionId: string;
  agentName: AdapterAgentName;
  eventType: AdapterEventType;
  statusAfter: AdapterStatus;
  message: string;
  /** Deterministic ISO-8601 timestamp. Never generated at runtime. */
  createdAt: string;
}

export interface AgentAdapterCardView {
  adapterId: string;
  agentName: AdapterAgentName;
  displayName: string;
  role: string;
  capabilities: readonly AgentAdapterCapabilityView[];
}
