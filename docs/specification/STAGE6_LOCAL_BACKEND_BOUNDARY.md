# Stage 6 Local Backend Boundary

## Backend Boundary Diagram

```
Control Center UI request model (static mock, Stage 6.2)
        |
        v
LocalBackendRequest                        (backend_models.py)
        |
        v
validate_backend_request()                 (backend_validation.py)
        |
        v
CommandAPI boundary                        (command_api.py)
        |
        v
Stage 5.1 command/session/packet contracts (command_models.py,
                                             command_validation.py -- referenced, not mutated)
        |
        v
LocalBackendResponse                       (backend_models.py)
        |
        v
build_*_response() / stable_backend_json() (backend_response_builder.py)
        |
        v
Static frontend backend/API panels         (apps/control-center/)
```

`LocalControlCenterBackend` (`local_backend.py`) wraps the CommandAPI
boundary in a small facade class; it sits at the same layer as
`command_api.py` in the diagram above -- it does not add a new hop.

## Allowed Dependencies

- Python standard library only (`dataclasses`, `json`, `re`, `typing`).
- Existing Stage 5.x `scos/control_center` modules, read-only:
  `command_models.py` (`ALLOWED_COMMAND_TYPES`), `command_validation.py`
  (`validate_command_args`, `validate_no_forbidden_command_text`),
  `operator_packet_review_models.py` (`FrozenMap`, reused rather than
  redefined).

## Forbidden Dependencies

- `sqlite3`, any ORM, any database driver.
- `socket`, `http.server`, `asyncio` servers, `FastAPI`, `Flask`, or any
  web framework.
- `subprocess`, `os.system`, or any process-spawning API.
- `requests`, `urllib.request`, or any HTTP client.
- Next.js server-side primitives: `app/api`, `route.ts`, `middleware.ts`,
  server actions, `fetch`.
- Browser/GUI/clipboard automation of any kind.
- `scos.commercial` or `scos.knowledge` (Runtime Product Layer must not be
  imported by, or import, this Operator Tools Layer boundary).

## Relation to Stage 5.1 Command Bridge

Stage 6.2 never bypasses or duplicates the Stage 5.1 draft -> validate ->
approve -> queue -> run pipeline. It reuses the same command-type
allowlist and the same forbidden-argument/forbidden-text validation
functions so that "what the Command API would allow" and "what the
Stage 5.1 approval gate would allow" can never silently diverge. Stage
6.2 adds no new way to reach `command_runner.py`.

## Relation to Future SQLite WAL

Every snapshot request type (`session_snapshot`, `result_snapshot`,
`approval_snapshot`, `project_state_snapshot`) currently echoes back its
own payload with a `snapshot_mocked` warning -- there is no read path into
any real Stage 5 JSONL store yet. A future SQLite/WAL-backed store can
replace this mock behavior without changing the request/response shape,
because the shape was designed against the full snapshot vocabulary up
front.

## Relation to Future Event Stream

`BackendHealthSnapshot.event_stream_status` is fixed at
`disabled_until_stage_6_4` in this stage. There is no timer, no
`setInterval`/`setTimeout` equivalent, and no long-lived connection
anywhere in this boundary -- every call is a single synchronous
request/response. Stage 6.4 is the explicit home for introducing a push
mechanism once a real local server process exists to emit from.

## Relation to Future Real Adapter Activation

`BackendHealthSnapshot.adapter_dispatch_status` is fixed at
`disabled_until_later_stage`. No function in `command_api.py` or
`local_backend.py` calls into `agent_adapter_contracts.py`,
`agent_adapter_registry.py`, or `agent_adapter_simulator.py`. Real AI
dispatch remains gated behind a later, explicitly-scoped stage.

## Failure Modes

- **Unknown `request_type`**: rejected deterministically with
  `error_kind="invalid_request_type"` before any handler runs.
- **Malformed `payload`**: rejected with `error_kind="invalid_payload"`,
  naming the offending/missing key.
- **URL or path-traversal value**: rejected with `error_kind="url_rejected"`
  or `"unsafe_path"`.
- **Secret-bearing metadata key**: rejected at `FrozenMap` construction
  (raises `ValueError`) or, defensively, by
  `reject_secret_metadata()` with `error_kind="secret_metadata_rejected"`.
- **Unknown `command_type`**: rejected with
  `error_kind="command_not_allowed"`.
- **Forbidden command text/characters**: rejected with
  `error_kind="forbidden_operation"` or `"invalid_payload"`.

## Recovery Strategy

Every failure mode above returns a normal `LocalBackendResponse` with
`ok=False` and a populated `errors` tuple -- callers never need to catch
an exception for a routine validation failure (only malformed
construction inputs, e.g. missing required fields, raise `ValueError`,
matching the existing Stage 5.1 model convention). The frontend mock in
`apps/control-center/` demonstrates rendering both a success response and
a rejected-command example so the recovery path is visible before any
real backend exists.
