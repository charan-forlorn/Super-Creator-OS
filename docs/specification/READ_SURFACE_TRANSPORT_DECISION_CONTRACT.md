# Read Surface Transport Decision Contract

Stage: 7.5 - Read Surface Transport Decision / Local UI Sync Activation Gate.

## Purpose

This contract defines the deterministic decision record that answers whether
the Stage 7 local Control Center read surface may introduce live UI sync
transport now.

Stage 7.5 is a decision and gate stage only. It does not implement WebSocket,
Server-Sent Events, EventSource, polling, timers, API routes, localhost HTTP
routes, socket servers, background workers, frontend transport state, adapter
dispatch, or command execution.

## Allowed Decision Values

The decision record must choose exactly one value:

- `NO_LIVE_TRANSPORT`
- `WEBSOCKET_ALLOWED_LATER`
- `SSE_ALLOWED_LATER`
- `POLLING_ALLOWED_LATER`

The Stage 7.5 preferred and implemented gate decision is
`NO_LIVE_TRANSPORT`.

## Public Models

`TransportOptionAnalysis`

- `option: str`
- `allowed: bool`
- `security_risk: str`
- `operational_risk: str`
- `localhost_boundary: str`
- `required_controls: tuple[str, ...]`
- `forbidden_behaviors: tuple[str, ...]`
- `test_expectations: tuple[str, ...]`
- `rollback_requirements: tuple[str, ...]`
- `notes: tuple[str, ...]`

Allowed option values:

- `NO_LIVE_TRANSPORT`
- `WEBSOCKET`
- `SSE`
- `POLLING`

`TransportDecisionRecord`

- `decision_id: str`
- `decision: str`
- `decided_at: str`
- `accepted: bool`
- `go_no_go: str`
- `readiness_score: int`
- `default_transport: str`
- `analyses: tuple[TransportOptionAnalysis, ...]`
- `blockers: tuple[str, ...]`
- `warnings: tuple[str, ...]`
- `required_next_stage_controls: tuple[str, ...]`
- `forbidden_until_next_approval: tuple[str, ...]`
- `rollback_plan: tuple[str, ...]`

`TransportDecisionError`

- `error_code: str`
- `message: str`
- `checked_at: str`
- `blockers: tuple[str, ...]`

All models are immutable frozen dataclasses and expose deterministic
`to_dict()` output.

## Public Functions

- `create_transport_option_analysis(...)`
- `build_read_surface_transport_decision(...)`
- `validate_transport_decision_gate(...)`
- `export_transport_decision_markdown(...)`

The gate defaults to:

```text
requested_decision = NO_LIVE_TRANSPORT
allow_transport_implementation = False
```

## Decision Semantics

`NO_LIVE_TRANSPORT` means Stage 7.4 static/mock fallback remains the active
read surface behavior and no live UI sync transport is introduced.

`WEBSOCKET_ALLOWED_LATER`, `SSE_ALLOWED_LATER`, and
`POLLING_ALLOWED_LATER` mean the transport may be considered by a later
explicit implementation stage only after operator approval and documented
controls. They do not authorize implementation in Stage 7.5.

If `allow_transport_implementation=True`, the gate returns `NO_GO` with a
blocker because Stage 7.5 does not approve immediate implementation.

## Readiness Score Semantics

- `100`: `NO_LIVE_TRANSPORT`, accepted, zero blockers.
- `90`: allowed-later decision, accepted, zero blockers, explicit next-stage
  controls present.
- `<= 50`: immediate implementation request or other blocker.

`go_no_go` is `GO` only when the record is accepted and blockers are empty.
Any blocker produces `NO_GO`.

## Deterministic ID Rules

`decision_id` is derived from SHA-256 over stable caller-supplied and
normalized inputs:

- `decided_at`
- `requested_decision`
- `allow_transport_implementation`
- normalized option analysis dictionaries

Stage 7.5 code must not use `datetime.now`, `time.time`, `random`, or UUID
generation.

## Forbidden Immediate Implementation

Stage 7.5 must not introduce:

- WebSocket
- Server-Sent Events or EventSource
- polling
- timers or background workers
- `fetch`, `XMLHttpRequest`, or `axios`
- Next.js API routes, `route.ts`, or `middleware.ts`
- localhost HTTP routes
- backend socket servers
- runtime transport dependencies
- real ChatGPT, Claude Code, Codex, Hermes, or other adapter dispatch
- command execution behavior changes
- state, event, approval, audit, or queue mutation
- cloud, SaaS, payment, CRM, customer portal, or external network behavior

## Relationship to Stage 7.4 and Stage 7.6

Stage 7.4 remains the active controlled UI projection from approved local read
models and deterministic static/mock fallback data.

Stage 7.5 documents the transport boundary after Stage 7.4 and before any
possible sync implementation.

Stage 7.6 handoff is approval-aware command views. It may display command,
approval, denial, execution, and audit status from approved read models, but
it is not a transport implementation stage and must not add execution paths.

## Error Model

Invalid inputs return `TransportDecisionError` instead of raising from public
gate functions:

- empty `decided_at` -> `INVALID_DECIDED_AT`
- unknown `requested_decision` -> `INVALID_REQUESTED_DECISION`
- unknown option analysis value -> `INVALID_TRANSPORT_OPTION`

Errors include deterministic `checked_at` and blocker text.

## Test Expectations

Focused tests must prove:

- `NO_LIVE_TRANSPORT` returns `GO`, readiness `100`, and accepted `True`.
- allowed-later WebSocket, SSE, and polling decisions do not implement
  transport and include next-stage controls.
- immediate implementation requests return `NO_GO` or blockers.
- invalid decisions return `TransportDecisionError`.
- `decided_at` is caller-supplied and required.
- `decision_id` and markdown export are deterministic.
- static source scan rejects forbidden implementation tokens in Stage 7.5
  production files.
