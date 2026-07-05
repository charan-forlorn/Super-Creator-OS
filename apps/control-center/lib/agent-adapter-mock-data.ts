// SCOS Control Center — Stage 5.3 AI Agent Adapter Contract Layer mock data.
// Static, deterministic display data only. Nothing here is executed and
// nothing is generated at runtime (no Date.now / Math.random / randomUUID);
// ids and timestamps are fixed literals shaped like the Python adapter
// simulator output. Mirrors scos/control_center/agent_adapter_registry.py
// (adapter order + capabilities) and agent_adapter_simulator.py (event
// sequence).

import type {
  AgentAdapterCardView,
  AgentAdapterRequestView,
  AgentAdapterSimulationEventView,
} from "./agent-adapter-types";

/** Mirrors the five adapters returned by create_default_agent_adapter_registry(), same order. */
export const AGENT_ADAPTER_CARDS: readonly AgentAdapterCardView[] = [
  {
    adapterId: "chatgpt-contract",
    agentName: "chatgpt",
    displayName: "ChatGPT",
    role: "Planning, status updates, result summaries, prompt building",
    capabilities: [
      {
        capabilityId: "chatgpt-app-cap",
        agentName: "chatgpt",
        runtimeType: "chatgpt_app",
        taskTypes: ["planning", "status_update", "result_summary", "prompt_build"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: false,
        supportsManualFallback: false,
      },
      {
        capabilityId: "chatgpt-web-cap",
        agentName: "chatgpt",
        runtimeType: "chatgpt_web",
        taskTypes: ["planning", "status_update", "result_summary", "prompt_build"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: false,
        supportsManualFallback: false,
      },
    ],
  },
  {
    adapterId: "claude-code-contract",
    agentName: "claude_code",
    displayName: "Claude Code",
    role: "Implementation, prompt building, release gates",
    capabilities: [
      {
        capabilityId: "claude-code-cli-cap",
        agentName: "claude_code",
        runtimeType: "claude_code_cli",
        taskTypes: ["implementation", "prompt_build", "release_gate"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: true,
        supportsManualFallback: false,
      },
      {
        capabilityId: "claude-code-vscode-cap",
        agentName: "claude_code",
        runtimeType: "claude_code_vscode",
        taskTypes: ["implementation", "prompt_build", "release_gate"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: true,
        supportsManualFallback: false,
      },
    ],
  },
  {
    adapterId: "codex-contract",
    agentName: "codex",
    displayName: "Codex",
    role: "Review, git review, release gates",
    capabilities: [
      {
        capabilityId: "codex-cli-cap",
        agentName: "codex",
        runtimeType: "codex_cli",
        taskTypes: ["review", "git_review", "release_gate"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: false,
        supportsManualFallback: false,
      },
      {
        capabilityId: "codex-app-cap",
        agentName: "codex",
        runtimeType: "codex_app",
        taskTypes: ["review", "git_review", "release_gate"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: false,
        supportsManualFallback: false,
      },
    ],
  },
  {
    adapterId: "hermes-contract",
    agentName: "hermes",
    displayName: "Hermes",
    role: "Audits, status updates",
    capabilities: [
      {
        capabilityId: "hermes-cli-cap",
        agentName: "hermes",
        runtimeType: "hermes_cli",
        taskTypes: ["audit", "status_update"],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: true,
        supportsManualFallback: false,
      },
    ],
  },
  {
    adapterId: "manual-clipboard-contract",
    agentName: "manual_clipboard",
    displayName: "Manual clipboard handoff",
    role: "Universal fallback — every task type, operator-driven",
    capabilities: [
      {
        capabilityId: "manual-clipboard-cap",
        agentName: "manual_clipboard",
        runtimeType: "manual_clipboard",
        taskTypes: [
          "planning",
          "implementation",
          "review",
          "audit",
          "status_update",
          "prompt_build",
          "result_summary",
          "release_gate",
          "git_review",
          "manual_handoff",
        ],
        supportsPromptDelivery: true,
        supportsResultCapture: true,
        supportsStatusCheck: false,
        supportsManualFallback: true,
      },
    ],
  },
];

/** The request driving the simulated lifecycle below. */
export const AGENT_ADAPTER_SIMULATION_REQUEST: AgentAdapterRequestView = {
  requestId: "adapter-req-001",
  sessionId: "session-002",
  taskId: "task-002",
  agentName: "claude_code",
  runtimeId: "claude-code-cli",
  runtimeType: "claude_code_cli",
  taskType: "implementation",
  promptText: "Implement JSONL session store round-trip tests.",
  inputSummary: "work_session_store.py draft + contract",
  createdAt: "2026-07-06T11:00:00Z",
  deliveryMode: "contract_only",
  expectedResultType: "implementation_report",
};

/**
 * One fixed, deterministic simulated adapter lifecycle for
 * AGENT_ADAPTER_SIMULATION_REQUEST. Mirrors the exact event_type sequence
 * produced by simulate_adapter_lifecycle() in agent_adapter_simulator.py.
 */
export const AGENT_ADAPTER_SIMULATION_EVENTS: readonly AgentAdapterSimulationEventView[] = [
  {
    eventId: "adapter-req-001-evt-1-request_created",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "request_created",
    statusAfter: "accepted",
    message: "Adapter request adapter-req-001 created for claude_code (implementation)",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-2-request_validated",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "request_validated",
    statusAfter: "accepted",
    message: "Request passed registry validation",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-3-adapter_selected",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "adapter_selected",
    statusAfter: "accepted",
    message: "Selected adapter claude-code-contract (claude_code/claude_code_cli)",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-4-prompt_prepared",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "prompt_prepared",
    statusAfter: "prepared",
    message: "Prompt prepared for claude_code (implementation)",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-5-simulated_sent",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "simulated_sent",
    statusAfter: "simulated_sent",
    message: "Simulated send to claude_code (claude_code_cli)",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-6-result_simulated",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "result_simulated",
    statusAfter: "result_ready",
    message: "Simulated result captured for claude_code",
    createdAt: "2026-07-06T11:00:05Z",
  },
  {
    eventId: "adapter-req-001-evt-7-result_ready",
    requestId: "adapter-req-001",
    sessionId: "session-002",
    agentName: "claude_code",
    eventType: "result_ready",
    statusAfter: "result_ready",
    message: "Simulated result captured for claude_code",
    createdAt: "2026-07-06T11:00:05Z",
  },
];
