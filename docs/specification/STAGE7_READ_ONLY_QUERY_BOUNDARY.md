# Stage 7 Read-Only Query Boundary

Status: **Stage 7.1 boundary**

Stage 7.1 is a module-level Python read API only. It creates the inspection
foundation needed by later Stage 7 stages, but it does not expose a transport,
render UI, execute commands, activate adapters, or mutate stores.

## 1. Why module-level only

The Stage 7 handoff recommends the smallest safe implementation step: a
deterministic local read/query surface over Stage 6 artifacts. A Python
module API is the narrowest boundary because it can be tested directly,
offline, and without introducing server lifecycle, frontend coupling, or
transport decisions.

## 2. No localhost route

Stage 7.1 does not add HTTP routes, local API routes, Next.js routes, backend
socket servers, middleware, or route handlers. Any future localhost route
requires a later Stage 7 scope decision and security review.

## 3. No WebSocket, SSE, or polling

Stage 7.1 does not add live sync transport. WebSocket, SSE/EventSource,
polling, timers, and background workers remain forbidden until the explicit
Stage 7 transport decision stage.

## 4. No UI feature

Stage 7.1 does not modify `apps/control-center/` and does not render
operator-facing panels. Later Stage 7.3/7.4 work may consume the read surface
after Stage 7.2 adds coherence gates.

## 5. No command execution

The read surface never executes commands and never calls command runner APIs.
It may inspect command state, command queue evidence, and command-related
audit records. It must not approve, deny, enqueue, run, or append command
events.

## 6. No adapter dispatch

Stage 7.1 does not activate ChatGPT, Claude Code, Codex, Hermes, Buffer, or
any other adapter. It does not read API keys and does not call external
services. Adapter activation remains deferred to a later explicit approval
stage.

## 7. No store mutation

Stage 7.1 must not mutate:

- SQLite state databases.
- Event logs.
- Command queues.
- Approval records.
- Approval audit ledger.
- Stage 4, Stage 5, or Stage 6 contract files.

SQLite is inspected through read-only connections. JSONL artifacts are read
only. Missing optional runtime files produce warnings rather than writes.

## 8. Future dependencies

Stage 7.2 should add the read surface coherence gate. Stage 7.3 should build
operator health and activity read models. Stage 7.4 should project selected
UI panels from approved read models. None of those later stages should bypass
the read-only and approval boundaries established here.
