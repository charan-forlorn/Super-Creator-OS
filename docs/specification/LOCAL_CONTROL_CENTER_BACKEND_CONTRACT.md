# Local Control Center Backend Contract (Stage 6.2)

## Purpose

Define the first local backend boundary for the Control Center: a
deterministic, in-process callable surface that validates requests and
returns structured responses, without any network transport. This gives the
frontend a stable request/response shape it can build against before any
real transport (socket server, database, event stream) exists.

## Current Stage 6.2 Scope

- Immutable request/response models: `LocalBackendRequest`,
  `LocalBackendResponse`, `BackendError`, `BackendWarning`,
  `BackendHealthSnapshot` (`scos/control_center/backend_models.py`).
- Deterministic validation: request type allowlisting, payload shape
  checking, URL rejection, path traversal rejection, secret-metadata
  rejection (`scos/control_center/backend_validation.py`).
- A pure local callable facade, `LocalControlCenterBackend`
  (`scos/control_center/local_backend.py`), backed by the Command API
  boundary (`scos/control_center/command_api.py`).
- A static frontend mock under `apps/control-center/` showing the shape of
  the eventual integration without connecting to anything real.

## Non-Goals (Explicitly Out of Scope for Stage 6.2)

- SQLite / WAL / any persistent database.
- WebSocket, Server-Sent Events, or any streaming transport.
- Polling, timers, or background workers.
- A socket server or HTTP server of any kind.
- Next.js API routes, route handlers, middleware, or server actions.
- Real dispatch to ChatGPT / Claude Code / Codex / Hermes adapters.
- Arbitrary command execution, `subprocess` calls, or shell access.
- Network calls, cloud services, or SaaS behavior of any kind.

## Local Callable Boundary

`LocalControlCenterBackend` is a plain Python object with plain methods
(`health`, `handle`, `preview_command`, `validate_command`,
`dry_run_enqueue`). Calling a method is a normal in-process function call:
no socket is opened, no port is bound, and no thread or process is
started. This mirrors how the Stage 5.1 command bridge is called directly
today, and gives Stage 6.3+ a stable seam to put a real transport behind
without changing the method signatures.

## Request/Response Envelope

Every call accepts caller-supplied identifiers and timestamps only --
never a real clock, random value, or UUID. Requests carry:

- `request_id`, `request_type`, `operator_id`, `created_at` (all
  caller-supplied strings)
- `payload` / `metadata` (immutable `FrozenMap` instances)

Every call returns a `LocalBackendResponse` with:

- `ok` (bool), `status` (`success` / `rejected` / `blocked` / `failure`)
- `response_type` (`health` / `validation_result` / `dry_run_result` /
  `snapshot` / `rejected` / `error`)
- `data` (`FrozenMap`), `errors` (tuple of `BackendError`), `warnings`
  (tuple of `BackendWarning`)
- `schema_version`, `created_at`, `metadata`

`to_dict()` on every model serializes with a fixed key order; combined
with `stable_backend_json()` (`sort_keys=True`, compact separators), the
same input always produces the same JSON text.

## Disabled Capabilities

`BackendHealthSnapshot` reports Stage 6.2's exact reach:

- `active_store: in_memory_only` -- no persistence backs any snapshot.
- `event_stream_status: disabled_until_stage_6_4` -- no push updates yet.
- `adapter_dispatch_status: disabled_until_later_stage` -- no real AI work
  is ever dispatched by this boundary.

`disabled_capabilities` on the snapshot additionally lists:
`sqlite_wal_persistence`, `websocket_stream`, `server_sent_events`,
`polling`, `real_adapter_dispatch`, `arbitrary_command_execution`.

## Validation Strategy

`validate_backend_request()` runs a fixed check sequence and never raises
for a normal validation failure -- it always returns a (possibly empty)
tuple of `BackendError`:

1. `request_type` must be one of the eight allowed types.
2. `payload` keys/required-keys are checked against a per-type contract.
3. URL-like values anywhere in `payload` are rejected.
4. Any `*path` / `*_path` payload value is checked for traversal or
   absolute-path use via `validate_safe_relative_path()`.
5. `metadata` is checked for secret-bearing key markers and URL values.

Command-shaped requests (`command_preview`, `command_validate`,
`command_enqueue_dry_run`) additionally reuse the Stage 5.1 command
contract (`ALLOWED_COMMAND_TYPES`, `validate_command_args`,
`validate_no_forbidden_command_text`) so a command that Stage 5.1's
approval gate would reject is rejected here first.

## Security Rules

- Metadata keys containing `secret`, `token`, `password`, `api_key`,
  `private_key`, `credential`, or `bearer` are rejected -- both at
  `FrozenMap` construction time (Stage 5.5 behavior, reused unchanged) and
  defensively inside backend validation.
- `http://` / `https://` (and any other URI scheme) values are rejected
  wherever a path or metadata value is expected.
- Absolute paths and `..` traversal segments are rejected in any payload
  key ending in `path` / `_path`.
- No secret-like value is ever printed or included in an error message
  (only the offending key name is reported).

## Why No Socket Server Yet

A local backend must first prove its request/response contract is
correct and stable before a transport is added on top of it. Stage 6.2
keeps the boundary a plain function call so every test in
`scos/control_center/tests/test_command_api.py` and
`test_local_backend.py` runs with zero sockets, zero ports, and zero
timing dependencies. Adding a transport before the contract is settled
would force a second migration once the contract inevitably shifts.

## Why No SQLite Yet

Stage 6.2's snapshots (`session_snapshot`, `result_snapshot`, etc.) are
intentionally mocked (`snapshot_mocked` warning) rather than backed by
real storage. Introducing SQLite/WAL now would mean choosing a schema
before the request/response contract it must serve has been exercised by
the frontend. Stage 6.3 is the first stage explicitly scoped to add
durable storage behind this same boundary.

## Why No Event Stream Yet

Real-time push (WebSocket/SSE) only matters once there is a real backend
process for the frontend to subscribe to. Stage 6.2 has no running
process at all -- it is a callable boundary invoked synchronously. Event
streaming is explicitly deferred to Stage 6.4, once a real local server
process exists to emit from.

## Stage 6.3 / 6.4 Handoff

- **Stage 6.3** may add SQLite/WAL-backed persistence behind the same
  `LocalControlCenterBackend` method signatures, replacing the
  `in_memory_only` / `snapshot_mocked` behavior with real reads/writes.
- **Stage 6.4** may add a real local server process (still local-only) and
  an event stream / push mechanism, changing `event_stream_status` from
  `disabled_until_stage_6_4` to an active value.
- Both stages must preserve the `LocalBackendRequest` /
  `LocalBackendResponse` shapes defined here so the Stage 6.2 frontend
  mock keeps working unchanged.
