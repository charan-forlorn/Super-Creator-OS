# Stage 6 — Event Stream Readiness Gate

## Purpose

This gate answers one question: is the Control Center regression suite clean
enough, and is the Stage 6.4 local event stream / UI state sync foundation
stable enough, to safely proceed toward deeper local UI synchronization work
in Stage 6.6?

It is a checkpoint, not a feature. Passing this gate does not authorize any
real-time transport, adapter activation, or AI dispatch — those remain
explicitly out of scope until a future stage defines and certifies them.

## Required clean regression state

- `scos/control_center/tests` passes in full, with zero failures and zero
  errors, run as a single suite (not only in isolation per-file).
- No test leaks global/module-level monkeypatch state across test files.
- No test requests a fixture that pytest cannot resolve.
- `scos/commercial/tests` passes in full.

## Required Stage 6.4 event stream checks

The following modules must pass, both in isolation and as part of the full
suite:

- `test_event_stream_models.py`
- `test_event_stream_builder.py`
- `test_event_stream_snapshot.py`
- `test_ui_state_sync.py`

The Stage 6.4 event stream contract (model shapes, builder behavior, snapshot
projection semantics) must be unchanged unless a concrete regression proves
the contract itself is broken — in which case the issue is reported with
evidence and a minimal repair is proposed, not silently folded into a larger
change.

## Required durable state compatibility checks

- `test_prompt_result_packet_store.py` and `test_work_session_store.py` (the
  Stage 5.x durable JSONL store suites) pass without modification to
  production store contracts (append/load semantics, deterministic digests,
  append-only ordering, error message stability).
- SQLite WAL durable state store tests introduced in Stage 6.3 remain
  passing.

## Required frontend static build checks

- `pnpm lint` passes from `apps/control-center`.
- `pnpm build` passes from `apps/control-center` (static Next.js export /
  optimized production build succeeds with no route or type errors).

## Explicit non-goals

Stage 6.5 (and this gate) do not authorize, require, or imply any of the
following. Their presence in implementation code is a gate failure; their
presence in this document is solely to state them as excluded:

- No WebSocket transport.
- No Server-Sent Events (SSE) / `EventSource`.
- No polling loops.
- No timers or background workers driving synchronization.
- No real-time frontend sync.
- No activation of real ChatGPT / Claude Code / Codex / Hermes adapters.
- No real AI work dispatch.
- No arbitrary command execution.
- No new network ports opened.
- No Next.js API routes.
- No backend socket server.
- No SaaS, auth, payment, CRM, or customer-portal behavior.

## Stage 6.6 entry criteria

Stage 6.6 (deeper local UI synchronization / activation work) may begin only
when all of the following hold:

1. This gate's "required clean regression state" section passes in full.
2. This gate's "required Stage 6.4 event stream checks" pass in full.
3. This gate's "required durable state compatibility checks" pass in full.
4. This gate's "required frontend static build checks" pass in full.
5. Smoke, security scan baseline, and release check scripts all report PASS
   (informational-only warnings are acceptable; failures are not).
6. No forbidden runtime behavior (per the non-goals list above) exists in
   the codebase at the time Stage 6.6 begins.
7. A human operator has reviewed and approved the Stage 6.5 regression
   cleanup report and explicitly authorized Stage 6.6 to begin.

## Stage 6.6 blockers

Stage 6.6 must not begin if any of the following are true:

- Any control_center or commercial regression test fails or errors.
- Any Stage 6.4 event stream/UI-state-sync test fails.
- Any durable store test fails or a production store contract was weakened
  to make a test pass.
- Frontend lint or build fails.
- A static scan finds real (non-prose, non-doc) usage of a forbidden
  pattern (WebSocket, EventSource, setInterval/setTimeout used for sync,
  fetch/XHR/axios, backend socket/http-server frameworks, subprocess with
  `shell=True`, nondeterministic time/uuid/random usage in deterministic
  paths, Next.js `route.ts`/`middleware.ts`/server actions).
- Operator approval has not been explicitly given.
