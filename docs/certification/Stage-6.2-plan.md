# Stage 6.2 Plan -- Local Control Center Backend & Command API

## Stage Goal

Create the first local backend boundary for the Control Center: a
deterministic, in-process Command API that validates requests and
produces structured responses, so the frontend has a stable contract to
build against before any real transport, database, or event stream
exists.

## Scope

- Immutable backend models (`backend_models.py`): `LocalBackendRequest`,
  `LocalBackendResponse`, `BackendError`, `BackendWarning`,
  `BackendHealthSnapshot`.
- Deterministic validation (`backend_validation.py`): request type,
  payload shape, URL rejection, path safety, secret-metadata rejection.
- Response builder helpers (`backend_response_builder.py`): success /
  rejected / error / health builders, stable JSON serialization.
- Command API boundary (`command_api.py`): preview, validate, dry-run
  enqueue, health check -- reusing the Stage 5.1 command contract.
- Local backend facade (`local_backend.py`): `LocalControlCenterBackend`.
- Static frontend mock under `apps/control-center/` showing the Stage 6.2
  concept without connecting to anything real.

## Non-Goals

- SQLite / WAL / any database.
- WebSocket / Server-Sent Events / polling / timers.
- A socket server, HTTP server, or Next.js API route of any kind.
- Real AI adapter dispatch.
- Arbitrary command execution.
- Any network, cloud, SaaS, payment, or CRM behavior.

## Files Created

Python:
- `scos/control_center/backend_models.py`
- `scos/control_center/backend_validation.py`
- `scos/control_center/command_api.py`
- `scos/control_center/local_backend.py`
- `scos/control_center/backend_response_builder.py`
- `scos/control_center/tests/test_backend_models.py`
- `scos/control_center/tests/test_backend_validation.py`
- `scos/control_center/tests/test_command_api.py`
- `scos/control_center/tests/test_local_backend.py`
- `scos/control_center/tests/test_backend_response_builder.py`

Docs:
- `docs/specification/LOCAL_CONTROL_CENTER_BACKEND_CONTRACT.md`
- `docs/specification/CONTROL_CENTER_COMMAND_API_CONTRACT.md`
- `docs/specification/STAGE6_LOCAL_BACKEND_BOUNDARY.md`
- `docs/certification/Stage-6.2-plan.md` (this file)

Frontend (static mock only, `apps/control-center/`):
- `lib/local-backend-types.ts`
- `lib/local-backend-mock-data.ts`
- `components/local-backend-status-panel.tsx`
- `components/command-api-panel.tsx`
- `components/backend-response-card.tsx`
- `components/app-shell.tsx` (modified)
- `components/sidebar.tsx` (modified)
- `README.md` (modified)

## Architecture

```
UI request model -> LocalBackendRequest -> validate_backend_request()
  -> CommandAPI boundary -> Stage 5.1 command contract (read-only reuse)
  -> LocalBackendResponse -> response builder -> static frontend panels
```

See `docs/specification/STAGE6_LOCAL_BACKEND_BOUNDARY.md` for the full
diagram and dependency rules.

## Acceptance Criteria

- All five backend modules import cleanly and are stdlib-only.
- `LocalBackendRequest` / `LocalBackendResponse` / `BackendError` /
  `BackendWarning` / `BackendHealthSnapshot` serialize deterministically
  (`to_dict()` / `from_dict()` round-trip, stable key order).
- Validation rejects: unknown request types, malformed payload shapes,
  URL values, path traversal, secret-bearing metadata keys.
- Command preview / validate / dry-run enqueue work without execution or
  real queue writes; unknown command types are rejected deterministically.
- `LocalControlCenterBackend` facade covers health / handle / preview /
  validate / dry-run with no socket, server, or persistence code.
- Frontend displays the Stage 6.2 concept using static, deterministic mock
  data only -- no `fetch`, no timers, no browser storage, no real clock.
- All existing Stage 5 `scos/control_center` tests remain unaffected by
  this change (see Regression Plan).

## Test Plan

Targeted:
```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_backend_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_backend_validation.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_command_api.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_local_backend.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_backend_response_builder.py -q
```

Regression:
```
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
```

## Regression Plan

The full `scos/control_center/tests` run has 12 pre-existing failures and
12 pre-existing errors (in `test_stage5_final_certification.py`,
`test_prompt_result_packet_store.py`, `test_work_session_store.py`) that
reproduce identically with the Stage 6.2 files excluded from the run --
confirmed by running the same suite both with and without the five new
Stage 6.2 test files present. These are a pre-existing test-isolation
issue (sys.path module-name collisions when the whole directory is
collected together) unrelated to this stage; they are reported here for
transparency and were not introduced or worsened by Stage 6.2.

## Security Scan Plan

- Static backend scan for: `sqlite3`, `socket`, `http.server`, `FastAPI`,
  `Flask`, `subprocess`, `requests`, `urllib.request`, WebSocket/SSE
  markers, real adapter dispatch calls, automation calls.
- Static frontend scan for: `fetch(`, `XMLHttpRequest`, `axios`,
  `WebSocket`, `EventSource`, `setInterval`, `setTimeout`, `Date.now`,
  `Math.random`, `crypto.randomUUID`, `localStorage`, `sessionStorage`,
  `navigator.clipboard`, `"use server"`, `app/api`, `route.ts`,
  `middleware.ts`.
- Run repo `scripts/security_scan_baseline.py`, `scripts/test_smoke.py`,
  `scripts/test_release.py` where practical and report results honestly.

## Stage 6.3 Handoff

Stage 6.3 may introduce SQLite/WAL-backed persistence behind the same
`LocalControlCenterBackend` method signatures, replacing
`active_store="in_memory_only"` and `snapshot_mocked` warnings with real
reads/writes -- without changing the `LocalBackendRequest` /
`LocalBackendResponse` contract this stage defines.

## Explicit Confirmation

- No SQLite.
- No WebSocket/SSE.
- No polling.
- No real adapter dispatch.
- No backend socket server.
- No Next.js API route.
