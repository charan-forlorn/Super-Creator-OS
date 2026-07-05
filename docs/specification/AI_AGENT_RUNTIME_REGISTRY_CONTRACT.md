# AI Agent Runtime Registry Contract (Stage 5.2)

## Purpose

Define a static, read-only catalogue of declared AI agent runtime surfaces
(`scos/control_center/runtime_registry.py`) that the AI Work Session Manager
uses to validate an `assign_runtime` call. The registry describes runtimes;
it never launches, calls, drives, or communicates with any of them.

## Scope

- Module: `scos/control_center/runtime_registry.py` (Python stdlib only,
  no imports beyond `work_session_models`).
- `RUNTIME_REGISTRY_SCHEMA_VERSION = 1`.
- The registry is a fixed, in-source tuple of `AgentRuntime` instances — not
  read from disk, not fetched over a network, not user-editable at runtime
  in Stage 5.2.

## Non-goals

This module does NOT: open ChatGPT/Claude Code/Codex/Hermes, call any API,
spawn any process, drive a browser, drive a desktop GUI, or perform any I/O
beyond returning in-memory `AgentRuntime` values. Registering a runtime here
is a *declaration*, not a live connection.

## Registered agents and runtimes

| `agent_name` | `runtime_id` | `runtime_type` | Supported task types |
| --- | --- | --- | --- |
| `chatgpt` | `chatgpt-app` | `chatgpt_app` | planning, review, audit, status_update, prompt_build, result_summary |
| `chatgpt` | `chatgpt-web` | `chatgpt_web` | planning, review, audit, status_update, prompt_build, result_summary |
| `claude_code` | `claude-code-cli` | `claude_code_cli` | planning, implementation, review, audit, release_gate |
| `claude_code` | `claude-code-vscode` | `claude_code_vscode` | planning, implementation, review, audit |
| `codex` | `codex-cli` | `codex_cli` | implementation, review, audit |
| `codex` | `codex-app` | `codex_app` | implementation, review |
| `hermes` | `hermes-cli` | `hermes_cli` | planning, status_update, result_summary |
| `chatgpt` | `manual-clipboard` | `manual_clipboard` | every allowed task type (fallback) |

All eight are `enabled=True` in Stage 5.2 — "registered" does not imply "has
a working integration"; it only means the AI Work Session Manager will
accept an assignment to this `runtime_id` if the task's `task_type` is in
its `supported_task_types`.

## The manual_clipboard guarantee

`manual-clipboard` (`runtime_type = "manual_clipboard"`) is always present
in the registry and always enabled. It supports every value in
`ALLOWED_TASK_TYPES`, so there is always at least one valid assignment
target regardless of which named agent integrations exist. It models the
simplest possible handoff: the operator copies a prompt out of the Control
Center and pastes an agent's result back in — no execution, no automation.

## Public API

- `list_runtimes() -> tuple[AgentRuntime, ...]` — every registered runtime,
  fixed declaration order, deterministic across calls.
- `get_runtime(runtime_id: str) -> AgentRuntime | None` — lookup by id;
  `None` for an unknown id (never raises).
- `find_runtimes_for_task(task_type: str) -> tuple[AgentRuntime, ...]` —
  enabled runtimes supporting `task_type`, in fixed declaration order; an
  unknown `task_type` yields an empty tuple (this is a read-only lookup, not
  a validation gate — `work_session_manager` is what rejects unknown types).

## Local-only constraints

- Python stdlib only; no network, no process launch, no file I/O.
- No clock, no random, no uuid — `runtime_id` values are fixed string
  literals, not generated.
- Deterministic: `list_runtimes()` and `find_runtimes_for_task(...)` return
  the same tuple for the same input on every call.

## Stage 5.2 acceptance criteria

1. `test_runtime_registry.py` passes: eight built-in runtimes, no duplicate
   `runtime_id`, `manual-clipboard` always present/enabled and covering
   every task type, `get_runtime` / `find_runtimes_for_task` behave as
   documented above.
2. Adding a new named-agent runtime in a future stage is additive-only: it
   never removes or renames an existing `runtime_id`, and
   `RUNTIME_REGISTRY_SCHEMA_VERSION` only changes for a breaking change.
