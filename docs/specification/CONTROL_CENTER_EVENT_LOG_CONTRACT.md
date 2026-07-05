# Control Center Event Log Contract (Stage 5.1)

## Purpose

Define the append-only, deterministic JSONL event log that records every
command lifecycle transition in the Stage 5.1 command bridge. The log is the
local realization of the "engine emits events" half of the Stage 4.18
`CONTROL_CENTER_COMMAND_API_DESIGN.md` boundary: readable without any server,
replayable to an identical byte stream.

## Event schema

One `CommandEvent` per JSONL line, keys in this exact order:

```json
{"event_id": "evt-<sha256-16>",
 "command_id": "cmd-001",
 "event_type": "COMMAND_STARTED",
 "created_at": "2026-07-05T10:20:00Z",
 "status": "pending",
 "message": "RUN_SMOKE_CHECK started",
 "metadata": [["key", "value"]]}
```

- `event_id`: `evt-` + first 16 hex chars of SHA-256 (see below).
- `command_id`: the draft/approved command this event belongs to.
- `created_at`: caller-supplied ISO-8601 string; never read from a clock.
- `metadata`: list of `[key, value]` string pairs (tuple-backed in Python,
  never a mutable dict).
- Schema version constant: `CONTROL_CENTER_EVENT_LOG_SCHEMA_VERSION = 1`
  (additive-only evolution).

## Event types

Exactly nine allowed `event_type` values (anything else is rejected at model
construction):

`COMMAND_DRAFTED`, `COMMAND_VALIDATED`, `COMMAND_REJECTED`,
`COMMAND_APPROVED`, `COMMAND_QUEUED`, `COMMAND_STARTED`, `COMMAND_COMPLETED`,
`COMMAND_FAILED`, `COMMAND_BLOCKED`.

Allowed `status` values: `success`, `failure`, `skipped`, `blocked`,
`pending`.

Runner convention: a run appends `COMMAND_STARTED` (status `pending`,
`created_at = started_at`) followed by `COMMAND_COMPLETED` (status `success`)
or `COMMAND_FAILED` (status `failure`) with `created_at = finished_at`. A
command that never starts (unknown type, missing required arg) appends a
single `COMMAND_BLOCKED` (status `blocked`).

## JSONL append-only behavior

- `append_command_event(event_log_path=..., event=...) -> str` appends one
  compact JSON object line (UTF-8, LF) and returns the line's SHA-256 hex.
- The log is strictly append-only: no deletion, truncation, or rewrite of
  existing lines, ever.
- Parent directories are created as needed; `event_log_path` may be `str` or
  `pathlib.Path`; URL paths raise the stable `URL_PATH_REJECTED: ...` error.
- `read_command_events(event_log_path=...)` returns events in append order,
  skipping blank lines; an invalid line raises the stable
  `INVALID_EVENT_LINE: line <n> is not valid JSON`; a missing file reads as an
  empty log.

## Deterministic event_id

```
event_id = "evt-" + sha256("|".join((command_id, event_type, created_at, message)))[:16]
```

Identical lifecycle transitions always produce identical event ids, so
replaying the same command list yields a byte-identical log (the Stage 4.18
replay-determinism rule).

## Event ordering

Ordering is physical append order in the file — the reader never sorts.
Producers must append events in lifecycle order; timestamps are labels, not
ordering keys.

## No clock / no random rule

The event log layer never calls a real clock, `random`, or `uuid`. Every
`created_at` is supplied by the caller, and every id is content-derived
SHA-256. Two runs with the same inputs are indistinguishable byte-for-byte.
