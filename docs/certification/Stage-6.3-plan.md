# Stage 6.3 Plan — Durable Local State Store with SQLite WAL

## Stage Goal

Give the Control Center its first durable local state layer using Python
stdlib `sqlite3` in WAL mode, so a future Stage 6.4 event stream/UI sync has
real local state to read from instead of in-memory-only data.

## Scope

- Immutable durable record models: command, session, event, approval, result
- SQLite schema (tables, indexes, pragmas) with WAL required
- `SQLiteStateStore`: parameterized CRUD/list operations, deterministic
  ordering, deterministic `DurableStateError` on duplicate/missing/invalid
  input
- `ControlCenterStateRepository`: sha256-derived deterministic ids, write
  helpers for backend requests/responses, commands, sessions, approvals,
  results, events
- `state_snapshot.build_state_snapshot()`: one deterministic summary dict
  (counts, latest records, WAL verification, disabled-capability flags,
  next-stage pointer)
- Static frontend mock panels showing the durable state concept in the
  Control Center UI
- Specification and certification docs

## Non-Goals

- WebSocket / Server-Sent Events / polling
- Timers or background workers
- Real-time UI sync
- Real ChatGPT / Claude Code / Codex / Hermes adapter activation
- Real AI dispatch or arbitrary command execution
- Backend socket server or any open network port
- Next.js API routes
- Auth / payment / CRM / customer portal
- Any change to Stage 4/5 public contracts or Stage 6.2 request/response
  behavior beyond additive repository helpers

## Files Created

Python:
- `scos/control_center/state_models.py`
- `scos/control_center/sqlite_state_schema.py`
- `scos/control_center/sqlite_state_store.py`
- `scos/control_center/state_repository.py`
- `scos/control_center/state_snapshot.py`
- `scos/control_center/tests/test_state_models.py`
- `scos/control_center/tests/test_sqlite_state_schema.py`
- `scos/control_center/tests/test_sqlite_state_store.py`
- `scos/control_center/tests/test_state_repository.py`
- `scos/control_center/tests/test_state_snapshot.py`

Docs:
- `docs/specification/CONTROL_CENTER_DURABLE_STATE_CONTRACT.md`
- `docs/specification/SQLITE_WAL_STATE_STORE_CONTRACT.md`
- `docs/specification/STAGE6_DURABLE_STATE_BOUNDARY.md`
- `docs/certification/Stage-6.3-plan.md` (this file)

Frontend (new):
- `apps/control-center/lib/durable-state-types.ts`
- `apps/control-center/lib/durable-state-mock-data.ts`
- `apps/control-center/components/durable-state-status-panel.tsx`
- `apps/control-center/components/state-snapshot-panel.tsx`
- `apps/control-center/components/state-record-card.tsx`

Frontend (modified):
- `apps/control-center/components/app-shell.tsx` (wire new section)
- `apps/control-center/components/sidebar.tsx` (add nav entry)
- `apps/control-center/README.md` (document Stage 6.3 section)

## Architecture

See `docs/specification/STAGE6_DURABLE_STATE_BOUNDARY.md` for the full
boundary diagram. Summary: Stage 6.2 request/response models sit above;
`ControlCenterStateRepository` sits below them and above
`SQLiteStateStore`; `SQLiteStateStore` owns the WAL-mode SQLite file; a
`state_snapshot` read view sits on top for future Stage 6.4 consumption.

## Acceptance Criteria

- SQLite database initializes under `scos/work/control_center/state/`
- WAL mode enabled and verified in `health_snapshot()`
- Schema version persisted in `state_schema` table
- All six tables and nine indexes present
- Commands/sessions/events/approvals/results persist and list back
  deterministically ordered
- Missing record -> deterministic `DurableStateError(error_kind="not_found")`
- Duplicate id -> deterministic `DurableStateError(error_kind="duplicate_id")`
- Invalid status/verdict/decision rejected at model construction
- Path traversal and URL-like db paths rejected
- Repository ids are sha256-derived from stable caller inputs
- State snapshot returns deterministic JSON
- No clock/random/uuid anywhere in Stage 6.3 code
- No WebSocket/SSE/polling/timers/backend server/Next.js routes/real
  adapter dispatch/arbitrary command execution anywhere in Stage 6.3 code
- Frontend displays the durable state foundation, static/mock-only
- Stage 6.2 and Stage 5 Control Center tests still pass
- Smoke/security/release checks pass or failures reported with exact cause

## Test Plan

Targeted pytest runs (all pass, 27 test functions total, plain-script
convention matching existing Stage 5/6 tests):

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_state_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_sqlite_state_schema.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_sqlite_state_store.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_state_repository.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_state_snapshot.py -q
```

## Regression Plan

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
```

12 pre-existing failures/errors in `test_stage5_final_certification.py`,
`test_prompt_result_packet_store.py`, and `test_work_session_store.py` are
present on the Stage 6.2 baseline (unaffected by adding or removing the
Stage 6.3 test files) and are unrelated to this stage's changes.

## Security Scan Plan

```
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Plus a manual static grep for forbidden frontend/backend patterns (fetch,
WebSocket, EventSource, setInterval/setTimeout, Date.now, Math.random,
crypto.randomUUID, localStorage/sessionStorage, `"use server"`, `app/api`,
FastAPI/Flask/http.server/socket, `datetime.now`/`time.time`/`uuid`/`random`
in Stage 6.3 files).

## Stage 6.4 Handoff

Stage 6.4 ("Real operator event stream / UI sync") is expected to:

1. Read from `SQLiteStateStore.list_events()` / `build_state_snapshot()`
2. Introduce the first real-time transport (WebSocket, SSE, or polling —
   Stage 6.3 takes no position on which)
3. Connect the frontend to that transport
4. Leave the Stage 6.3 durable state schema and repository API intact,
   extending additively where new fields are needed

## Explicit Confirmations

- SQLite WAL: implemented and required (`PRAGMA journal_mode=WAL` set on
  every connection; verified live in `health_snapshot()`)
- No WebSocket/SSE: none present in any Stage 6.3 file
- No polling: none present in any Stage 6.3 file
- No real adapter dispatch: no Stage 6.3 module imports the adapter
  contract/registry/simulator modules
- No backend socket server: no Stage 6.3 module opens a socket or binds a
  port
- No Next.js API route: no `app/api`, `route.ts`, or `middleware.ts` added
- No arbitrary command execution: no Stage 6.3 module calls `subprocess`,
  `os.system`, or similar
