# AI Work Session Manager Contract (Stage 5.2)

## Purpose

Define the deterministic local model of AI work used to coordinate work
across ChatGPT, Claude Code, Codex, and Hermes, without executing any of
them. Stage 5.2 answers one question:

> Can an operator create a task, assign it to a declared AI runtime, track
> its status through a fixed lifecycle, collect a result, and hand that
> result to another AI — as pure, deterministic local state?

This module is the orchestration *foundation*: it models state transitions
only. Real dispatch to ChatGPT/Claude Code/Codex/Hermes, API calls, browser
automation, and GUI automation are explicitly out of scope and are follow-up
work for a later stage (see `AI_AGENT_RUNTIME_REGISTRY_CONTRACT.md` for the
matching runtime-registry contract).

Per `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`, this
module belongs to the **Development Framework Layer** (it manages how work
gets done *on* SCOS, and is coordinated through the Operator Tools Layer). It
must never be imported by, or embedded into, the Runtime Product Layer, and
Stage 5.2 makes no change to Runtime Product Layer behavior.

## Scope

- Package: `scos/control_center/` (Python stdlib only), alongside the
  Stage 5.1 command bridge modules.
- Modules: `work_session_models`, `runtime_registry`, `work_session_manager`,
  `work_session_store`.
- Schema versions: every module exports a `*_SCHEMA_VERSION = 1` constant;
  changes are additive-only.
- These modules never import `scos.commercial`, `scos.knowledge`, or any
  other Runtime Product Layer package.

## Non-goals

Stage 5.2 is NOT: a ChatGPT/Claude Code/Codex/Hermes integration, an API
client, MCP, a WebSocket server, a database (no SQLite), an HTTP server,
browser automation, GUI automation, AI execution of any kind, a background
worker or scheduler, git execution (no commit/push), a SaaS/CRM/payment
surface, or a cloud service. It changes no Runtime Product Layer behavior
and mutates no Stage 4 or Stage 5.1 artifact.

## Work session lifecycle

```
AIWorkTask
  -> AIWorkSession (status: draft)         create_work_session
  -> AgentAssignment attached              assign_runtime
  -> status transitions (queued, sent_to_agent, agent_working,
     result_ready, review_required, needs_fix, approved, blocked, ...)
                                            transition_status
  -> done                                  complete_session
  -> cancelled (from any non-terminal)     cancel_session
```

### Allowed statuses

`draft`, `queued`, `assigned`, `waiting_for_operator`, `sent_to_agent`,
`agent_working`, `result_ready`, `review_required`, `needs_fix`, `approved`,
`blocked`, `cancelled`, `done`.

`cancelled` and `done` are terminal: no further transition is ever allowed
out of either status, and no manager function will mutate a session already
in one of them (`SESSION_ALREADY_COMPLETED`).

### Transition table

| From | Allowed to |
| --- | --- |
| `draft` | `queued`, `cancelled` |
| `queued` | `assigned`, `blocked`, `cancelled` |
| `assigned` | `waiting_for_operator`, `sent_to_agent`, `blocked`, `cancelled` |
| `waiting_for_operator` | `sent_to_agent`, `blocked`, `cancelled` |
| `sent_to_agent` | `agent_working`, `blocked`, `cancelled` |
| `agent_working` | `result_ready`, `blocked`, `cancelled` |
| `result_ready` | `review_required`, `cancelled` |
| `review_required` | `needs_fix`, `approved`, `cancelled` |
| `needs_fix` | `queued`, `sent_to_agent`, `blocked`, `cancelled` |
| `approved` | `done`, `cancelled` |
| `blocked` | `queued`, `cancelled` |
| `cancelled` | *(none — terminal)* |
| `done` | *(none — terminal)* |

The canonical table is `ALLOWED_TRANSITIONS` in
`scos/control_center/work_session_manager.py`; `validate_transition(current,
new)` is the single source of truth callers should use to check a move
before attempting it.

## Public API (`work_session_manager.py`)

All functions take an explicit `sessions: dict[str, AIWorkSession]` supplied
by the caller (no hidden global state) and return either an updated
`AIWorkSession` or an `AIWorkSessionError`.

- `create_work_session(*, sessions, session_id, task, created_at, metadata=())`
  — creates a new session in `draft` status. Rejects a duplicate
  `session_id` (`DUPLICATE_SESSION_ID`) and a non-`AIWorkTask` `task`
  (`INVALID_TASK`).
- `assign_runtime(*, sessions, session_id, runtime_id, assignment_id, reason, assigned_at, metadata=())`
  — binds a registered, enabled runtime that supports the task's
  `task_type`. Only valid from `draft`, `queued`, `blocked`, or `needs_fix`
  (`INVALID_STATUS_FOR_ASSIGNMENT` otherwise). Rejects an unknown runtime
  (`UNKNOWN_RUNTIME`), a disabled runtime (`RUNTIME_DISABLED`), and a runtime
  that does not support the task's type (`UNSUPPORTED_TASK_TYPE`).
- `transition_status(*, sessions, session_id, new_status, updated_at, result_summary=None, next_action=None)`
  — moves a session along the transition table. Rejects an unknown session
  (`UNKNOWN_SESSION`), a terminal session (`SESSION_ALREADY_COMPLETED`), and
  a disallowed move (`INVALID_TRANSITION`).
- `complete_session(*, sessions, session_id, updated_at, result_summary)` —
  convenience wrapper requiring the session be `approved`; moves it to `done`
  with the given `result_summary`.
- `cancel_session(*, sessions, session_id, updated_at, reason)` — moves any
  non-terminal session to `cancelled`, recording `reason` as
  `result_summary`.
- `validate_transition(current_status, new_status) -> (bool, error|None)` —
  pure lookup against the transition table; used internally and available
  for callers that want to pre-check a move.

## Models (`work_session_models.py`)

`AI_WORK_SESSION_SCHEMA_VERSION = 1`. Five frozen dataclasses, each with an
explicit `to_dict()` (fixed key order) and a `.of(...)` factory:
`AgentRuntime`, `AIWorkTask`, `AgentAssignment`, `AIWorkSession`,
`AIWorkSessionError`. No dataclass exposes a mutable field — `metadata` and
`supported_task_types` are always tuples.

Allowed `agent_name` values: `chatgpt`, `claude_code`, `codex`, `hermes`.
Allowed `task_type` values: `planning`, `implementation`, `review`, `audit`,
`status_update`, `prompt_build`, `result_summary`, `release_gate`,
`manual_handoff`. Allowed `priority` values: `low`, `normal`, `high`,
`urgent`.

## JSONL store (`work_session_store.py`)

- `append_session(*, sessions_path, session)` appends one compact JSON
  snapshot line (UTF-8, LF) and returns its SHA-256 hex digest. The store is
  append-only: no line is ever deleted or rewritten. Every transition is
  persisted as a *new full snapshot line* — history is the audit trail.
- `load_sessions(*, sessions_path)` replays every line and returns the
  latest snapshot per `session_id`, in first-seen order.
- `load_session(*, sessions_path, session_id)` returns the latest snapshot
  for one id, or `None`.
- `list_sessions(*, sessions_path)` returns every distinct `session_id`.
- `append_event(*, events_path, event)` appends one plain-dict JSON event
  line; used for lightweight lifecycle logging alongside the session
  snapshots. Rejects non-dict input.
- A missing file reads as an empty store (no error). An invalid JSON line
  raises `ValueError` with a stable `INVALID_SESSION_LINE: ...` message.

## Local-only constraints

- Python stdlib only; no network, no server, no database, no WebSocket.
- No real clock, no random, no uuid: every timestamp (`created_at`,
  `assigned_at`, `updated_at`) and every id (`session_id`, `assignment_id`)
  is caller-supplied.
- The only writes are appends to caller-supplied `sessions_path` /
  `events_path` files.
- No AI execution, no subprocess, no external call of any kind — this
  module only manipulates in-memory dataclasses and appends JSON lines.

## Stage 5.2 acceptance criteria

1. All four Stage 5.2 test scripts pass
   (`scos/control_center/tests/test_work_session_models.py`,
   `test_runtime_registry.py`, `test_work_session_manager.py`,
   `test_work_session_store.py`, plain executable style).
2. A task flows end-to-end: create -> assign -> queued -> sent_to_agent ->
   agent_working -> result_ready -> review_required -> approved -> done.
3. An invalid transition, an unknown runtime, an unsupported task type, and
   a duplicate `session_id` are all rejected deterministically and never
   mutate existing state.
4. `manual_clipboard` is always registered, always enabled, and supports
   every allowed task type — the universal fallback runtime.
5. Identical inputs produce byte-identical JSONL lines and digests.
6. Existing Stage 4 and Stage 5.1 checks remain unchanged and passing.
