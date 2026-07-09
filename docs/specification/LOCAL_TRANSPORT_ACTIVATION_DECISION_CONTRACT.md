# Local Transport Activation Decision Contract

Stage: 8.1 - Local Transport Activation Decision & Safety Contract.

## Purpose

Stage 8.1 is a deterministic decision and safety gate over Stage 6, Stage 7,
and Stage 8.0 local integration evidence. It answers which local transport
option, if any, is safe to approve for future implementation and under what
safety contract.

It does not implement transport.

## Public API

```python
run_local_transport_activation_decision_gate(
    *,
    repo_root,
    decided_at: str,
    requested_decision: str = "NO_TRANSPORT",
    allow_future_implementation: bool = False,
    output_path=None,
) -> LocalTransportActivationDecisionResult | LocalTransportActivationDecisionError
```

Rules:

- `decided_at` is caller-supplied and required.
- The gate must not read clocks or generate random identifiers.
- Stable identifiers use SHA-256 over caller-supplied values and inspected
  local evidence.
- The gate may read local evidence files.
- The gate writes nothing unless `output_path` is supplied.
- If supplied, `output_path` must resolve inside `repo_root`.
- The gate must not mutate state, event, approval, audit, queue, or schema
  stores.

## Result Schema

`LocalTransportActivationDecisionResult` includes:

- `gate_id`
- `gate_name`
- `decided_at`
- `go_no_go`
- `readiness_score`
- `accepted`
- `can_implement_now`
- `transport_implemented`
- `dispatch_blocked`
- `decision_record`
- `option_analyses`
- `safety_requirements`
- `blockers`
- `warnings`
- `inspected_artifacts`
- `forbidden_behavior_findings`
- `report_path`

All public models are frozen dataclasses with deterministic `to_dict()` output.

## Decision Values

Allowed request and result decisions:

- `NO_TRANSPORT`
- `FILE_SNAPSHOT_REFRESH_ALLOWED_LATER`
- `LOCAL_HTTP_ALLOWED_LATER`
- `WEBSOCKET_ALLOWED_LATER`
- `SSE_EVENTSOURCE_ALLOWED_LATER`
- `POLLING_ALLOWED_LATER`
- `BLOCK_TRANSPORT_ACTIVATION`

The six analyzed transport options are:

- `NO_TRANSPORT`
- `FILE_SNAPSHOT_REFRESH`
- `LOCAL_HTTP`
- `WEBSOCKET`
- `SSE_EVENTSOURCE`
- `POLLING`

## Readiness Scoring

- `GO / 100` means the requested decision is accepted and has zero blockers.
- `NO_GO / 70-99` means the gate intentionally blocks transport activation
  without missing required evidence.
- `BLOCKED / 0-69` means required evidence, input validation, or safety scan
  rules failed.

`can_implement_now` is always `False`. `transport_implemented` is always
`False`. `dispatch_blocked` is always `True`.

## Default NO_TRANSPORT Decision

The default call:

```python
run_local_transport_activation_decision_gate(
    repo_root=repo_root,
    decided_at=decided_at,
)
```

returns `NO_TRANSPORT` with `GO`, score `100`, `accepted=True`,
`can_implement_now=False`, `transport_implemented=False`, and
`dispatch_blocked=True` when all required evidence is present and the static
source scan has no findings.

## No-Implementation Guarantee

Stage 8.1 must not create:

- live transport
- localhost routes
- backend socket servers
- WebSocket
- SSE/EventSource
- polling
- timers or background workers
- frontend runtime features
- real adapter activation
- real AI dispatch
- API-key handling or secret storage
- command execution paths
- external network, cloud, SaaS, payment, CRM, customer portal, Buffer, or
  external API integration

Allowed-later decisions authorize only a later explicit Stage 8 implementation
task. They do not authorize implementation inside Stage 8.1.

## Output Write Rules

- `output_path=None` writes nothing.
- A file path writes deterministic JSON to that file.
- A directory path writes
  `stage8_1_local_transport_activation_decision_report.json`.
- The JSON payload is stable, sorted, and newline-terminated.
- The serialized `report_path` inside the written payload remains `None` so
  report content is deterministic independent of the filesystem target.

## Blockers

The gate returns `BLOCKED` when:

- `decided_at` is missing.
- `requested_decision` is invalid.
- `repo_root` is missing, remote, or invalid.
- `output_path` resolves outside `repo_root`.
- Stage 4, Stage 5, Stage 6, Stage 7, or Stage 8.0 compatibility evidence is
  missing.
- Stage 8.1 source contains forbidden runtime behavior markers.
- an allowed-later transport is requested without
  `allow_future_implementation=True`.

The blocker code for immediate or unapproved implementation intent is:

```text
TRANSPORT_IMPLEMENTATION_NOT_APPROVED_IN_STAGE_8_1
```

## Test Expectations

Required focused tests:

- frozen deterministic models
- default `NO_TRANSPORT` returns `GO / 100 / accepted=True`
- all six options are analyzed
- allowed-later decisions keep `can_implement_now=False`
- immediate or unapproved implementation intent is rejected
- missing `decided_at` is rejected
- outside `output_path` is rejected
- explicit output write is deterministic
- compatibility evidence gaps block the gate
- static forbidden behavior scan blocks the gate

Required local checks:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_activation_decision_models.py scos/control_center/tests/test_transport_activation_decision_gate.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```
