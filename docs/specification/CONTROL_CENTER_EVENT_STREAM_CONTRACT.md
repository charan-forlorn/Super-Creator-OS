# Control Center Event Stream Contract (Stage 6.4)

## Purpose

Defines the local-only, deterministic event stream projection layer that sits
above the Stage 6.3 durable SQLite WAL state store. This is a **snapshot**
contract, not a transport contract: there is no live push, no subscription,
no socket.

## Modules

- `scos/control_center/event_stream_models.py` — `EventStreamRecord`,
  `EventStreamSnapshot` immutable dataclasses, plus the closed vocabularies
  `ALLOWED_EVENT_TYPES` and `ALLOWED_EVENT_STATUSES`.
- `scos/control_center/event_stream_builder.py` — `build_event_stream_snapshot`,
  the pure/deterministic assembly function.
- `scos/control_center/event_stream_snapshot.py` — projects Stage 6.3
  `DurableEventRecord` rows (from `state_repository.list_events()`) into
  `EventStreamRecord` instances and calls the builder.

## EventStreamRecord

| field | type | notes |
|---|---|---|
| `event_id` | `str` | non-empty |
| `sequence` | `int` | `>= 0`, caller-supplied monotonic order |
| `event_type` | `str` | one of `ALLOWED_EVENT_TYPES` |
| `source` | `str` | non-empty, e.g. `control_center` |
| `entity_type` | `str` | non-empty, e.g. `command`, `session` |
| `entity_id` | `str` | non-empty |
| `status` | `str` | one of `ALLOWED_EVENT_STATUSES` |
| `occurred_at` | `str` | caller-supplied timestamp string |
| `payload` | `FrozenMap` (`Mapping[str, str]`) | frozen; rejects URL values and secret-bearing keys |
| `evidence_refs` | `tuple[str, ...]` | frozen; rejects URL-shaped references |

## EventStreamSnapshot

| field | type | notes |
|---|---|---|
| `schema_version` | `int` | `EVENT_STREAM_SCHEMA_VERSION = 1` |
| `snapshot_id` | `str` | `sha256` of `(generated_at, cursor, ordered event keys)` |
| `generated_at` | `str` | caller-supplied, never `time.time()`/`datetime.now()` |
| `cursor` | `str` | caller-supplied or the last ordered event's `event_id` |
| `event_count` | `int` | must equal `len(events)` |
| `events` | `tuple[EventStreamRecord, ...]` | ordered by `(sequence, event_id)` |
| `status_counts` | `Mapping[str, int]` | derived, sorted by key |
| `source_counts` | `Mapping[str, int]` | derived, sorted by key |
| `warnings` | `tuple[str, ...]` | e.g. `no_local_events_available`, `skipped_unsupported_event:<id>` |

## Builder guarantees (`build_event_stream_snapshot`)

- Deterministic ordering by `(sequence, event_id)` regardless of input order.
- Rejects duplicate `(sequence, event_id)` pairs with `EventStreamBuilderError`.
- Rejects non-`EventStreamRecord` entries, unsupported `event_type`/`status`
  (defense in depth — the model layer already rejects these at construction).
- Never reads a clock (`time.time`, `datetime.now`) or generates a random
  value; `generated_at` and `cursor` are always caller-supplied.
- `snapshot_id` is a `sha256` digest of stable inputs, never a UUID.

## Projection guarantees (`event_stream_snapshot.py`)

Stage 6.3's `DurableEventRecord.event_type` is a free string (not constrained
to the Stage 6.4 vocabulary). `project_durable_event()` normalizes known
values (uppercasing, status aliasing) and **skips** (does not raise on)
records whose type/status cannot be mapped onto the Stage 6.4 vocabulary,
surfacing a `skipped_unsupported_event:<event_id>` warning on the resulting
snapshot instead. This keeps the projection layer read-only and non-mutating
of Stage 6.3 durable records.

## Explicitly out of scope

No `WebSocket`, `EventSource`/SSE, polling loop, timer, file watcher,
background thread, async worker, or network endpoint of any kind. See
`STAGE6_EVENT_STREAM_BOUNDARY.md` for the deferred-transport rationale.
