# Control Center UI State Sync Contract (Stage 6.4)

## Purpose

Defines the `UIStateSyncSnapshot` — a single deterministic summary combining
a Stage 6.3 durable state snapshot with a Stage 6.4 event stream snapshot,
intended for Control Center static/local UI panels. This is a **read
summary**, not a live sync channel.

## Module

`scos/control_center/ui_state_sync.py` — `build_ui_state_sync_snapshot(...)`.

## UIStateSyncSnapshot

| field | type | notes |
|---|---|---|
| `schema_version` | `int` | `UI_STATE_SYNC_SCHEMA_VERSION = 1` |
| `sync_id` | `str` | `sha256` of `(generated_at, event snapshot_id, state checked_at, active_stage, active_task)` |
| `generated_at` | `str` | caller-supplied |
| `state_source` | `str` | e.g. `scos.control_center.state_snapshot` |
| `sync_status` | `str` | one of the shared status vocabulary (`ready`, `blocked`, `stale`, ...) |
| `active_stage` | `str` | e.g. `"6.4"` |
| `active_task` | `str` | e.g. `"event_stream_foundation"` |
| `backend_status` | `str` | derived from the Stage 6.3 state snapshot's `db_mode`/`wal_enabled` |
| `durable_state_status` | `str` | `ready` iff `wal_enabled` is true, else `blocked` |
| `latest_event_id` | `str` | from the last ordered event in the supplied event snapshot |
| `latest_event_sequence` | `int` | `>= 0` |
| `pending_operator_actions` | `tuple[str, ...]` | caller-supplied |
| `blockers` | `tuple[str, ...]` | e.g. `durable_state_store_not_ready`, `backend_health_unknown` |
| `warnings` | `tuple[str, ...]` | propagated from the event snapshot plus staleness warnings |

## Staleness detection without a clock

`stale_if_state_checked_before` is an optional caller-supplied ISO-8601
timestamp string. If the durable state snapshot's own `checked_at` is
lexicographically earlier than that caller-supplied threshold, `sync_status`
becomes `"stale"` and a `durable_state_snapshot_older_than_expected` warning
is added. **No system clock is ever read** — both timestamps being compared
come from the caller (e.g. a Control Center panel comparing "now" from an
operator-visible clock element to the last-recorded state timestamp).

## Builder guarantees

- Requires a non-empty `generated_at`.
- Requires `event_snapshot` to be an actual `EventStreamSnapshot` instance.
- `sync_id` is a `sha256` digest of stable inputs, never a UUID.
- Never reads `time.time()`/`datetime.now()`/`random`.

## Explicitly out of scope

No `WebSocket`, SSE, polling, timers, background workers, or live push of
any kind. See `STAGE6_EVENT_STREAM_BOUNDARY.md`.
