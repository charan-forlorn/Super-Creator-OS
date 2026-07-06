# Stage 6.4 Plan — Local Event Stream & UI State Sync Foundation

## Stage Goal

Give the Control Center its first deterministic local event stream snapshot
layer and UI state sync summary, built on top of the Stage 6.3 durable SQLite
WAL state store, with zero live transport of any kind.

## Prerequisite gate

Phase A (regression triage) ran first and confirmed all 24 pre-existing
Stage 5/6 regression items (12 failed + 12 errors) are `NON_BLOCKING_PRE_EXISTING`
— see `docs/certification/Stage-6.4-regression-triage.md` /
`.json`. Phase B below only proceeded because that gate passed with zero
blockers.

## Scope

- Immutable event models: `EventStreamRecord`, `EventStreamSnapshot`,
  `UIStateSyncSnapshot` (`scos/control_center/event_stream_models.py`)
- Deterministic snapshot builder with ordering/dedup/rejection guarantees
  (`scos/control_center/event_stream_builder.py`)
- Projection from Stage 6.3 durable events into Stage 6.4 event records
  (`scos/control_center/event_stream_snapshot.py`)
- UI state sync snapshot combining durable state + event snapshot
  (`scos/control_center/ui_state_sync.py`)
- Specification docs: event stream contract, UI sync contract, architecture
  boundary explaining why WebSocket/SSE/polling are deferred
- Static frontend mock panels (event stream panel, snapshot card, UI sync
  panel, sync health panel) wired into the existing Control Center shell

## Non-Goals

- WebSocket / Server-Sent Events / polling / timers / background workers
- Real-time UI sync or live push transport of any kind
- Real ChatGPT / Claude Code / Codex / Hermes adapter activation
- Real AI dispatch or arbitrary command execution
- Backend socket server, async server, or any open network port
- Next.js API routes, `route.ts`, `middleware.ts`, server actions
- `fetch()` / `XMLHttpRequest` / `axios` / any network call
- Auth / payment / CRM / customer portal / cloud / SaaS behavior
- Any change to Stage 4/5 public contracts or Stage 6.2/6.3 public contracts

## Files Created

Backend:
- `scos/control_center/event_stream_models.py`
- `scos/control_center/event_stream_builder.py`
- `scos/control_center/event_stream_snapshot.py`
- `scos/control_center/ui_state_sync.py`
- `scos/control_center/tests/test_event_stream_models.py`
- `scos/control_center/tests/test_event_stream_builder.py`
- `scos/control_center/tests/test_event_stream_snapshot.py`
- `scos/control_center/tests/test_ui_state_sync.py`

Docs:
- `docs/certification/Stage-6.4-regression-triage.md`
- `docs/certification/Stage-6.4-regression-triage.json`
- `docs/certification/Stage-6.4-plan.md` (this file)
- `docs/specification/CONTROL_CENTER_EVENT_STREAM_CONTRACT.md`
- `docs/specification/CONTROL_CENTER_UI_STATE_SYNC_CONTRACT.md`
- `docs/specification/STAGE6_EVENT_STREAM_BOUNDARY.md`

Frontend (static/local mock data only):
- `apps/control-center/lib/event-stream-types.ts`
- `apps/control-center/lib/event-stream-mock-data.ts`
- `apps/control-center/lib/ui-state-sync-types.ts`
- `apps/control-center/components/event-stream-panel.tsx`
- `apps/control-center/components/event-snapshot-card.tsx`
- `apps/control-center/components/ui-state-sync-panel.tsx`
- `apps/control-center/components/sync-health-panel.tsx`

Frontend (modified to add navigation entry point only):
- `apps/control-center/components/app-shell.tsx`
- `apps/control-center/components/sidebar.tsx`
- `apps/control-center/README.md`

## Architecture Compliance

- Local-first: all backend modules read only local durable state; no network.
- Deterministic: all IDs are `sha256` of caller-supplied stable values; no
  `uuid`, no `random`.
- No clock: no `datetime.now()` / `time.time()` / `Date.now()` anywhere in
  new code; all timestamps are caller-supplied strings.
- No live transport: no WebSocket, SSE, polling, timers, or background
  workers in either backend or frontend new code.
- Approval-first / no real dispatch: this stage never activates a real AI
  adapter and never executes arbitrary commands.

## Next Stage

Stage 6.5+ can introduce a real transport (to be decided) against the stable
`EventStreamSnapshot` / `UIStateSyncSnapshot` contracts established here,
without needing to redesign the underlying data model.
