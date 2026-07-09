# Stage 7.5 Plan - Read Surface Transport Decision Gate

Predecessor: Stage 7.4, confirmed at commit
`9330f6eef0a58b2227b43fd59870b09987cc907c`.

## Objective

Implement the deterministic Stage 7.5 decision and local UI sync activation
gate that answers whether SCOS may introduce live UI sync transport for the
local read surface now.

The Stage 7.5 decision is `NO_LIVE_TRANSPORT`.

## Scope

Allowed Python files:

- `scos/control_center/transport_decision_models.py`
- `scos/control_center/read_surface_transport_decision.py`
- `scos/control_center/tests/test_transport_decision_models.py`
- `scos/control_center/tests/test_read_surface_transport_decision.py`
- `scos/control_center/__init__.py` lazy exports only

Allowed docs:

- `docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md`
- `docs/specification/LOCAL_UI_SYNC_ACTIVATION_GATE.md`
- `docs/certification/Stage-7.5-plan.md`
- `docs/architecture/STAGE7_TRANSPORT_SECURITY_ANALYSIS.md`

## Non-Goals

- no WebSocket implementation
- no Server-Sent Events or EventSource implementation
- no polling
- no timers or background workers
- no frontend changes
- no Next.js API routes
- no localhost HTTP routes
- no backend socket server
- no dependency changes
- no direct frontend SQLite reads
- no state, event, approval, audit, or queue mutation
- no command execution behavior changes
- no real AI adapter dispatch
- no cloud, network, SaaS, payment, CRM, or customer portal behavior
- no commit, push, tag, or release

## Allowed Files

Stage 7.5 is limited to the files listed in the Scope section. Any unexpected
dirty files outside that set must stop the stage until reviewed.

## Implementation Summary

Stage 7.5 adds immutable transport decision models, a deterministic decision
builder, a gate validator, and deterministic markdown export.

The public gate defaults to `NO_LIVE_TRANSPORT` and
`allow_transport_implementation=False`. Immediate implementation requests
produce `NO_GO` with blockers.

Decision IDs are SHA-256 based on caller-supplied and normalized inputs.

## Test Plan

Run:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_decision_models.py scos/control_center/tests/test_read_surface_transport_decision.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Focused tests cover:

- preferred `NO_LIVE_TRANSPORT` decision
- WebSocket allowed-later decision without implementation
- SSE allowed-later decision without implementation
- polling allowed-later decision without implementation
- immediate implementation blocker
- invalid requested decision error
- required caller-supplied `decided_at`
- deterministic decision ID
- deterministic markdown export
- forbidden production token scan

## Acceptance Criteria

- Preflight passes on `main` with clean tree and `HEAD == origin/main`.
- Decision/gate models are immutable and deterministic.
- A transport decision record is generated.
- The decision uses one allowed decision value.
- Security analysis exists for no live transport, WebSocket, SSE, and polling.
- Localhost boundary is documented.
- Rollback plan is documented.
- Test expectations are documented.
- Forbidden behaviors are documented.
- No live transport implementation is introduced.
- No frontend runtime transport is introduced.
- No command execution, store mutation, real adapter dispatch, or cloud/SaaS
  behavior is introduced.
- Stage 7.4 static/mock fallback remains valid and unmodified.
- Stage 7.6 handoff remains approval-aware command views, not transport
  implementation.
- Focused and relevant regression checks pass or failures are reported with
  exact evidence.
- No commit, push, tag, or release is performed.

## Expected Commit Message

```text
docs(control-center): add Stage 7.5 read surface transport decision gate
```
