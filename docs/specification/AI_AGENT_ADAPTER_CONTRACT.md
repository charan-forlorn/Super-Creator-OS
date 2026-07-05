# AI Agent Adapter Contract (Stage 5.3)

## Purpose

Define the deterministic boundary between the Stage 5.2 AI Work Session
Manager and any future real integration with ChatGPT, Claude Code, Codex, or
Hermes. Stage 5.3 answers one question:

> Can SCOS represent, validate, and simulate an AI adapter request/result
> lifecycle for each target AI runtime without coupling to any specific app
> implementation?

This module is a contract layer only: it models a request -> validate ->
adapter-select -> prepare -> send -> result lifecycle as pure, deterministic
state. It never dispatches real work to ChatGPT, Claude Code, Codex, or
Hermes. Real dispatch, API calls, browser automation, and GUI automation
remain out of scope and are follow-up work for Stage 5.4 (Unified Prompt &
Result Packet) and beyond.

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, this
module belongs to the **Development Framework Layer**. It must never be
imported by, or embedded into, the Runtime Product Layer, and Stage 5.3
makes no change to Runtime Product Layer behavior.

## Non-goals

Stage 5.3 is NOT: a ChatGPT/Claude Code/Codex/Hermes integration, an API
client, MCP, a WebSocket server, a database (no SQLite), an HTTP server,
browser automation, GUI automation, AI execution of any kind, clipboard
automation, a background worker or scheduler, git execution (no
commit/push), a SaaS/CRM/payment surface, or a cloud service. It changes no
Runtime Product Layer behavior, mutates no Stage 4/5.1/5.2 artifact, and
never writes to the Stage 5.2 JSONL session store.

## Adapter boundary

```
AIWorkSession (Stage 5.2, referenced conceptually only)
   |
   v
AgentAdapterRequest              (agent_adapter_models.py)
   | validate_request()
   v
BaseAgentAdapter contract        (agent_adapter_contracts.py)
   | registry lookup / recommend
   v
AgentAdapterRegistry             (agent_adapter_registry.py)
   | prepare_prompt -> simulate_send -> capture_result
   v
AgentAdapterSimulationEvent(s)   (agent_adapter_simulator.py)
   |
   v
AgentAdapterResult (attachable back to a work session later — not in Stage 5.3)
```

`BaseAgentAdapter` is the single contract every current and future adapter
must implement. Stage 5.3 ships five contract-only adapters that implement
it purely in terms of declared capability data — none of them perform I/O.

## Supported agents

`chatgpt`, `claude_code`, `codex`, `hermes`, `manual_clipboard`.
`manual_clipboard` is both a valid `agent_name` and the universal fallback —
it is always available and supports every allowed task type.

## Supported runtimes

`chatgpt_app`, `chatgpt_web`, `openai_api`, `claude_code_vscode`,
`claude_code_cli`, `codex_app`, `codex_cli`, `hermes_cli`,
`manual_clipboard`.

## Request model (`AgentAdapterRequest`)

Fields: `request_id`, `session_id`, `task_id`, `agent_name`, `runtime_id`,
`runtime_type`, `task_type`, `prompt_text`, `input_summary`, `created_at`,
`delivery_mode`, `expected_result_type`, `metadata`.

Allowed `delivery_mode`: `contract_only`, `manual_clipboard`, `simulated`.
Allowed `expected_result_type`: `plan`, `implementation_report`,
`review_report`, `audit_report`, `status_update`, `prompt_packet`,
`result_summary`, `release_gate_report`, `git_review_report`,
`manual_handoff_note`.

`request_id` and `created_at` must be caller-supplied — no clock, no
random, no uuid. `prompt_text` must be explicit, caller-authored text; it is
rejected with `ValueError` if it contains `http://` or `https://`
(case-insensitive), so this stage can never hold a "prompt" that could be
used to reach out over the network.

## Result model (`AgentAdapterResult`)

Fields: `result_id`, `request_id`, `session_id`, `agent_name`, `runtime_id`,
`status`, `result_type`, `result_summary`, `output_text`, `output_path`,
`created_at`, `next_action`, `metadata`.

Allowed `status`: `accepted`, `prepared`, `simulated_sent`,
`waiting_for_operator`, `result_ready`, `failed`, `blocked`. Allowed
`result_type` matches the request's `expected_result_type` allowed set.
`output_path`, when supplied, is treated as a plain local string — this
module never opens, reads, or writes it.

## Error model (`AgentAdapterError`)

Fields: `ok`, `schema_version`, `error_kind`, `error_detail`, `failed_step`,
`request_id`, `metadata`. Allowed `error_kind`: `invalid_agent`,
`invalid_runtime`, `invalid_task_type`, `invalid_delivery_mode`,
`unsupported_capability`, `unsafe_prompt`, `network_forbidden`,
`missing_required_field`, `contract_violation`, `adapter_blocked`.
Every adapter method returns a structured `AgentAdapterError` instead of
raising for expected invalid input.

## Capability model (`AgentAdapterCapability`)

Fields: `capability_id`, `agent_name`, `runtime_type`, `task_types`,
`supports_prompt_delivery`, `supports_result_capture`,
`supports_status_check`, `supports_manual_fallback`, `metadata`. Declares,
per runtime surface, which task types an adapter claims to support and
which of the three capability flags it advertises.

## Adapter lifecycle

`AgentAdapterSimulationEvent.event_type` sequence produced by
`simulate_adapter_lifecycle` (see `AI_AGENT_ADAPTER_REGISTRY_CONTRACT.md`
for the matching registry contract):

```
request_created -> request_validated -> adapter_selected -> prompt_prepared
  -> (manual_clipboard_ready | simulated_sent) -> result_simulated
  -> (result_ready | blocked)
```

A failed validation at any step returns an `AgentAdapterError` immediately
— no partial event list is emitted for an invalid request.

## manual_clipboard fallback rule

`ManualClipboardContractAdapter` is always registered and always declares
support for every value in `ALLOWED_ADAPTER_TASK_TYPES`. It models the
simplest possible handoff — the operator copies a prepared prompt out and
pastes a result back in — with no clipboard access, no automation. Every
task type therefore always has at least one valid adapter.

## Deterministic ID/timestamp rules

No clock, no random, no uuid anywhere in `scos/control_center/agent_adapter_*`.
Every `request_id`, `result_id`, `event_id`, and `created_at` is
caller-supplied. `AgentAdapterSimulationEvent.event_id` values produced by
the simulator are pure string formats built from the caller-supplied
`request_id` and the event's position in the sequence (e.g.
`"<request_id>-evt-3-adapter_selected"`) — never randomly generated.

## Forbidden behavior

No network call, no API call, no MCP, no WebSocket, no browser automation,
no GUI automation, no OS app control, no clipboard automation, no database,
no polling, no background worker, no real-time server. `prepare_prompt`,
`simulate_send`, and `capture_result` never perform I/O of any kind — they
only construct dataclasses from their inputs.

## Stage 5.4 handoff

Stage 5.3 defines the adapter contract and simulation; it does not attach a
result back to a Stage 5.2 `AIWorkSession`, and it does not define a single
unified packet format shared across all agents. Stage 5.4 (Unified Prompt &
Result Packet) is expected to build that shared packet format and the
attach-back-to-session step on top of the models defined here.
