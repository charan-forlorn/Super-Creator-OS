# Control Center Command API Contract (Stage 6.2)

## Purpose

Define the public callable functions in
`scos/control_center/command_api.py` that stand in for the Control
Center's future backend API: preview, validate, and dry-run-enqueue a
command, plus a health check -- all without executing anything.

## Command Preview

`preview_command_request(...)` describes what a command looks like using
the Stage 5.1 command contract (`ALLOWED_COMMAND_TYPES`,
`validate_command_args`, forbidden-text checks), without asserting full
validity or side effects. Returns `response_type="validation_result"` with
a `dry_run_only` warning. Never executes the command.

## Command Validate

`validate_command_request(...)` runs the same Stage 5.1 contract checks
and reports the definitive validity of `command_type` +
`command_payload`. On success, `data.valid` is `"True"`. On failure, the
response is `status="rejected"` with one `BackendError` per contract
violation (unknown type, disallowed/missing arg, URL value, forbidden
shell character, forbidden command text).

## Dry-Run Enqueue

`dry_run_enqueue_command(...)` returns what *would* be enqueued
(`data.would_enqueue`, `data.command_type`, `data.command_payload`)
without writing to the real Stage 5.1 JSONL command queue
(`command_queue.py`) or touching any file. `status="success"` only when
validation passes; otherwise `status="rejected"` and
`data.would_enqueue` is `"False"`.

## Health Check

`get_backend_health(...)` returns a `BackendHealthSnapshot` describing
Stage 6.2's exact capability set (`response_type="health"`,
`status="success"`, never fails).

## Supported Request Types

Via `handle_local_backend_request()` / `LocalControlCenterBackend.handle()`:

| request_type               | response_type      | Notes                                    |
|-----------------------------|--------------------|-------------------------------------------|
| `health_check`              | `health`           | Always succeeds.                          |
| `command_preview`           | `validation_result`| No side effects.                          |
| `command_validate`          | `validation_result`| No side effects.                          |
| `command_enqueue_dry_run`   | `dry_run_result`   | Never writes to the real queue.           |
| `session_snapshot`          | `snapshot`         | Mocked; `snapshot_mocked` warning.        |
| `result_snapshot`           | `snapshot`         | Mocked; `snapshot_mocked` warning.        |
| `approval_snapshot`         | `snapshot`         | Mocked; `snapshot_mocked` warning.        |
| `project_state_snapshot`    | `snapshot`         | Mocked; `snapshot_mocked` warning.        |

## Rejected Behavior

Any request whose `request_type` is unknown, whose `payload` shape fails
its contract, or whose `metadata` carries a secret-like key or URL value
is rejected before any handler runs
(`response_type="rejected"`, `status="rejected"`,
`ok=False`), with one `BackendError` per violation and a
`recommended_action` string describing the fix.

An unknown `command_type` inside a command-shaped request is rejected
with `error_kind="command_not_allowed"`.

## Operator Approval Relationship

This API never substitutes for Stage 5.1 operator approval
(`operator_approval.py`). Preview, validate, and dry-run-enqueue all
describe what *would* happen; only the existing Stage 5.1
draft -> validate -> operator approval -> queue -> runner pipeline can
actually queue or run a command. Stage 6.2 adds no new execution path.

## Safety Rules

- No `subprocess` call anywhere in `command_api.py` or `local_backend.py`.
- No file writes to the real Stage 5.1 command queue or event log.
- No network call, socket, or external process.
- No real clock/random/uuid -- all timestamps/ids are caller-supplied.
- Command validation reuses Stage 5.1's forbidden-text and
  forbidden-character checks unchanged, so this boundary can never be used
  to smuggle a command past the same guardrails Stage 5.1 already enforces.

## No Arbitrary Command Execution

Every function in this module returns a description of an outcome
(preview data, validation result, or "would enqueue" data) and never
calls `os.system`, `subprocess`, or any process-spawning API. There is no
code path in Stage 6.2 that runs an operator-supplied command.

## Future Migration Path to Local Server/API

The functions in this module are already shaped like an API: request in,
structured response out. A future stage can put a stdlib-only local HTTP
server (or another local IPC transport) directly in front of
`handle_local_backend_request()` without changing its signature or the
`LocalBackendRequest` / `LocalBackendResponse` contract -- only the
transport layer changes, not the boundary defined here.
