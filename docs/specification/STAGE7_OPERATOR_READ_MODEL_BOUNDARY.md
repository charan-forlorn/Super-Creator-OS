# Stage 7 Operator Read Model Boundary

## Stage 7.3 Scope

Stage 7.3 adds backend-only operator read models for health, activity, drift, freshness, and readiness. It projects existing Stage 7.1 read-surface records and Stage 7.2 coherence-gate evidence into immutable operator-facing dataclasses.

## Non-Goals

- No frontend UI.
- No Next.js API routes.
- No localhost HTTP routes.
- No WebSocket, SSE, polling, timers, or background workers.
- No command execution.
- No real ChatGPT, Claude Code, Codex, Hermes, or other adapter dispatch.
- No SQLite schema changes.
- No JSONL append/write.
- No state, event, approval, audit, or queue mutation.
- No cloud, network, SaaS, payment, CRM, or customer portal behavior.

## Allowed Sources

- Stage 7.1 read surface public APIs.
- Stage 7.2 coherence gate public APIs.
- Stage 6 local source/runtime evidence only through existing read-only surfaces.
- Stage 7.1/7.2 validation helpers for path and read-only boundary checks.

## Path Boundary

`repo_root` must be a local directory. URL-like paths and path traversal are rejected through existing Stage 7 validation helpers. References exposed by the read models must originate from Stage 7.1/7.2 read evidence and remain local.

## No UI Yet

Stage 7.3 produces backend read models only. UI projection is a Stage 7.4 concern.

## No Transport Yet

Stage 7.3 exposes Python functions only. It introduces no server, socket, route, stream, polling loop, or event source.

## No Command Execution

Stage 7.3 does not invoke subprocesses, shell commands, command runners, adapters, browsers, GUI automation, or clipboard automation.

## No Adapter Dispatch

Stage 7.3 reads existing evidence only. It does not activate, simulate, or dispatch real AI work.

## No Mutation

Stage 7.3 does not write local stores. Read-only evidence is validated through Stage 7.1 boundary checks and Stage 7.2 non-mutation/hash-stability checks.
