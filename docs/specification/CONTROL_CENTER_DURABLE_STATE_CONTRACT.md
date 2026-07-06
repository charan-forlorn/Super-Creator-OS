# Control Center Durable State Contract (Stage 6.3)

## Purpose

Define the first durable local state model for the SCOS Control Center: a
deterministic set of record types (command, session, event, approval,
result) that can be persisted locally and read back without ambiguity. This
contract is the boundary the Stage 6.2 backend/API layer and the future
Stage 6.4 event stream both build against.

## Stage 6.3 Scope

- Immutable durable record dataclasses (`scos/control_center/state_models.py`)
- A local SQLite WAL-backed store implementing persistence for those records
  (`sqlite_state_store.py`, schema in `sqlite_state_schema.py`)
- A repository facade that builds deterministic record ids and writes/reads
  records on behalf of callers (`state_repository.py`)
- A state snapshot builder summarizing current durable state
  (`state_snapshot.py`)
- Static frontend mock panels showing the durable state concept

## Non-Goals

Stage 6.3 does **not** implement or activate:

- WebSocket, Server-Sent Events, or polling
- Timers or background workers
- Real-time UI sync
- Real ChatGPT / Claude Code / Codex / Hermes adapter dispatch
- Arbitrary command execution
- A backend socket server or any open network port
- Next.js API routes
- Auth, payment, CRM, or customer portal behavior

## Durable State Model

Five record types, all immutable frozen dataclasses with deterministic
`to_dict()`/`from_dict()`:

| Record | Purpose |
| --- | --- |
| `DurableCommandRecord` | One command's lifecycle status (draft -> ... -> completed/failed/blocked) |
| `DurableSessionRecord` | One AI work session's lifecycle status |
| `DurableEventRecord` | An append-only, sequence-ordered Control Center event |
| `DurableApprovalRecord` | An operator approval/rejection decision for a subject |
| `DurableResultRecord` | An agent/verification result (pass/fail/blocked/needs_fix/warning/info) |

Each type enforces an explicit allowed-value set for its status/decision/
verdict field at construction time and raises `ValueError` on an invalid
value -- callers never reach the store with an unvalidated status.

`StateRecordRef` is a lightweight cross-cutting reference (id, type,
created_at, updated_at, metadata) usable to describe any of the five record
types uniformly.

`DurableStateError` is the single deterministic failure shape returned by
the store and repository instead of a raised exception, with an
`error_kind` drawn from a fixed allowed set (`not_found`, `duplicate_id`,
`invalid_status`, `invalid_decision`, `invalid_verdict`, `invalid_payload`,
`invalid_path`, `schema_mismatch`, `storage_unavailable`).

## Deterministic ID Strategy

`ControlCenterStateRepository` builds every record id via
`sha256("|".join(stable_inputs))[:32]`, prefixed by record kind (`cmd_`,
`session_`, `approval_`, `result_`, `event_`). The stable inputs are always
caller-supplied identifiers (request id, request type, session key,
approval key, ...) -- never a clock read, never `random`/`uuid`. The same
inputs always produce the same id, so re-recording the same logical event
twice deterministically surfaces as a `duplicate_id` `DurableStateError`
rather than a silent second row.

## Caller-Supplied Timestamp Rule

No model, store, or repository method reads the system clock. Every
`created_at` / `updated_at` / `decided_at` / `applied_at` / `checked_at`
value must be passed in by the caller. This keeps every persisted row and
every snapshot fully reproducible from its inputs.

## Relation to Stage 6.2 Backend/API

Stage 6.2's `LocalBackendRequest`/`LocalBackendResponse` envelope
(`backend_models.py`) is unchanged. `ControlCenterStateRepository` exposes
`record_backend_request`/`record_backend_response` helpers a future backend
call site can use to persist request/response pairs as `DurableCommandRecord`
rows, without altering the Stage 6.2 request/response shapes themselves.

## Relation to Future Stage 6.4 Event Stream / UI Sync

`state_snapshot.build_state_snapshot()` returns a `disabled_capabilities`
map (`websocket`, `sse`, `polling`, `real_adapter_dispatch`,
`arbitrary_command_execution`, `nextjs_api_routes`, all `"disabled"`) and a
`next_stage` string naming Stage 6.4 explicitly. Stage 6.4 is expected to
read from this durable state (via `list_events`/`get_current_state_snapshot`)
to build a real operator event stream; Stage 6.3 does not start that stream.

## Failure Modes

- Duplicate primary key on insert -> `DurableStateError(error_kind="duplicate_id")`
- Read of a missing record -> `DurableStateError(error_kind="not_found")`
- Invalid status/decision/verdict -> rejected at model construction
  (`ValueError`) before it ever reaches the store
- Unsafe database path (URL-like or escaping the repo root) ->
  `ValueError` at `SQLiteStateStore` construction time, or
  `DurableStateError(error_kind="invalid_path")` from
  `validate_database_path`
- SQLite-level failure (disk full, permissions, corruption) ->
  `DurableStateError(error_kind="storage_unavailable")`

## Recovery Strategy

Because every write is a single parameterized `INSERT` inside a
`sqlite3` `with connection:` transaction, WAL mode guarantees the database
file never observes a torn write: either the row commits, or it doesn't. If
the database file becomes corrupted, the recovery path is to delete
`scos/work/control_center/state/control_center.sqlite3` (and its `-wal`/
`-shm` sidecars) and re-run `initialize()` -- there is no cache or
in-process index that needs to be separately invalidated, and no Certified
Core state is affected because this store lives entirely under
`scos/work/`.
