# Stage 6 Durable State Boundary (Stage 6.3)

## Boundary Diagram

```
Stage 6.2 LocalBackendRequest / Command API
            |
            v
  ControlCenterStateRepository        (state_repository.py)
            |
            v
      SQLiteStateStore                (sqlite_state_store.py)
            |
            v
   SQLite database file, WAL mode     (scos/work/control_center/state/*.sqlite3)
            |
            v
  Durable command / session / event / approval / result rows
            |
            v
      build_state_snapshot()          (state_snapshot.py)
            |
            v
  future Stage 6.4 event stream / UI sync   <-- NOT built in Stage 6.3
```

## Allowed Dependencies

- Python standard library only: `sqlite3`, `hashlib`, `json`, `pathlib`, `re`,
  `dataclasses`, `typing`
- `scos.control_center.operator_packet_review_models.FrozenMap` (existing
  Stage 5.5 immutable metadata map)
- Stage 6.2's `backend_models` request/response shapes (referenced by name in
  docs/repository helper naming; not imported/altered)

## Forbidden Dependencies

- No third-party package (no ORM, no `aiosqlite`, no `sqlalchemy`, no
  `requests`, no `httpx`, no `websockets`)
- No `scos.commercial` or `scos.knowledge` import from any Stage 6.3 module
- No `datetime.now()`, `time.time()`, `random`, or `uuid` anywhere in Stage
  6.3 Python or frontend code
- No `fetch`, `XMLHttpRequest`, `axios`, `WebSocket`, `EventSource`,
  `setInterval`, `setTimeout` in the Stage 6.3 frontend files

## Backend Boundary Relation

Stage 6.2 defined the local backend request/response envelope
(`LocalBackendRequest`/`LocalBackendResponse`) and a facade
(`local_backend.py`) that answers requests using in-memory logic only.
Stage 6.3 sits *underneath* that facade: `ControlCenterStateRepository`
exposes `record_backend_request`/`record_backend_response` so a future
change to `local_backend.py` can persist what it already computes, without
Stage 6.3 calling into `local_backend.py` itself and without altering the
Stage 6.2 request/response contract.

## Event Stream Handoff

`state_snapshot.build_state_snapshot()` is the single read surface a future
Stage 6.4 event stream implementation is expected to poll from -- but Stage
6.3 does not poll it, does not push it anywhere, and does not open a
connection for a UI client to read it live. `list_events()` already returns
events in strict `sequence` order, which is the ordering contract Stage 6.4
will need for an append-only stream; Stage 6.3 stops at "the data exists and
is orderable," not "the data streams."

## Adapter Activation Handoff

None of `state_models.py`, `sqlite_state_schema.py`, `sqlite_state_store.py`,
`state_repository.py`, or `state_snapshot.py` import
`agent_adapter_contracts.py`, `agent_adapter_registry.py`, or
`agent_adapter_simulator.py`. Recording a `DurableSessionRecord` with an
`agent_id` is purely descriptive data storage; it never triggers, invokes,
or simulates an adapter call.

## Security Constraints

- Every query is parameterized; no caller value is ever concatenated into
  SQL text.
- `validate_database_path()` rejects URL-like paths and path traversal
  before any file is touched.
- `FrozenMap` (reused from Stage 5.5) already rejects secret-bearing
  metadata keys and URL-shaped metadata values at construction time, so
  metadata attached to any Stage 6.3 record inherits that protection.
- No Stage 6.3 module opens a socket, binds a port, or accepts inbound
  connections.

## Local-Only Guarantee

The default database path
(`scos/work/control_center/state/control_center.sqlite3`) is local disk
storage under the project's own `scos/work/` generated-state convention. No
Stage 6.3 code path sends any record over a network, writes to a remote
service, or reads from one. The entire durable-state feature functions
identically with the machine fully offline.
