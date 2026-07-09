# Stage 8.1 Plan - Local Transport Activation Decision & Safety Contract

Predecessor Stage 8.0 commit:
`cb9662e3119664f7dd9c97431d34e1d5641b24d4`
(`docs(roadmap): add Stage 8.0 execution plan, scope boundary, and acceptance criteria`).

## Objective

Create a deterministic decision and safety gate that evaluates local transport
activation options for the Control Center and decides whether a later Stage 8
item may implement exactly one local-only transport option.

Stage 8.1 answers:

```text
Which local transport option, if any, is safe to approve for future
implementation, and under what safety contract?
```

## Scope

Allowed Python files:

- `scos/control_center/transport_activation_decision_models.py`
- `scos/control_center/transport_activation_decision_gate.py`
- `scos/control_center/tests/test_transport_activation_decision_models.py`
- `scos/control_center/tests/test_transport_activation_decision_gate.py`
- `scos/control_center/__init__.py` only for lazy exports

Allowed docs:

- `docs/specification/LOCAL_TRANSPORT_ACTIVATION_DECISION_CONTRACT.md`
- `docs/specification/STAGE8_TRANSPORT_SAFETY_CONTRACT.md`
- `docs/architecture/STAGE8_TRANSPORT_SECURITY_ANALYSIS.md`
- `docs/certification/Stage-8.1-plan.md`

## Non-Goals

- no transport implementation
- no network ports
- no localhost routes
- no backend socket server
- no Next.js API routes
- no WebSocket
- no SSE/EventSource
- no polling
- no timers or background workers
- no frontend feature implementation
- no real adapter activation
- no real AI dispatch
- no API-key handling or secret storage
- no command execution, subprocess, or shell use
- no store schema migration
- no cloud, SaaS, payment, CRM, customer portal, Buffer, or external API
  integration
- no dependency or package changes
- no Stage 4, Stage 5, Stage 6, or Stage 7 public contract break
- no commit, push, tag, or release

## Allowed Files

Stage 8.1 must create or modify only the files listed in the Scope section.
Any unexpected dirty file outside that list blocks the stage.

## Test Plan

Run from repo root:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_activation_decision_models.py scos/control_center/tests/test_transport_activation_decision_gate.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Frontend checks are not required because Stage 8.1 must not touch frontend
files.

## Acceptance Criteria

Stage 8.1 passes only if:

- preflight passes on `main` with `HEAD == origin/main`
- decision models are frozen and deterministic
- default gate call returns `NO_TRANSPORT`, `GO`, score `100`, and
  `accepted=True`
- all six transport options are analyzed
- allowed-later decisions do not implement transport
- `can_implement_now` remains `False`
- `transport_implemented` remains `False`
- `dispatch_blocked` remains `True`
- immediate or unapproved implementation intent is rejected
- missing `decided_at` is rejected
- `output_path` outside `repo_root` is rejected
- explicit output write is deterministic
- no WebSocket, SSE/EventSource, polling, timers, or background workers are
  introduced
- no backend route, Next.js API route, or backend socket server is introduced
- no network, cloud, SaaS, payment, CRM, customer portal, Buffer, or external
  API behavior is introduced
- no API-key or secret handling is implemented
- no real adapter activation or AI dispatch occurs
- no command execution, subprocess, or shell use is introduced
- Stage 4, Stage 5, Stage 6, and Stage 7 public contracts remain compatible
- docs match implementation
- focused tests pass
- control-center regression passes or exact pre-existing failures are
  documented
- security scan passes
- smoke passes
- release script passes or expected dirty-tree warning is documented
- no commit, push, tag, or release is performed

## Final Report Requirements

The final report must include:

- verdict
- preflight evidence
- files created and modified
- public models and functions
- decision values and analyzed options
- safety requirements and blocker rules
- no-implementation guarantee evidence
- optional output write behavior
- focused, regression, security, smoke, and release results
- static forbidden behavior scan result
- documentation review
- architecture notes
- known limitations
- Stage 8.2 handoff recommendation
- git status and diff evidence
- commit recommendation
- would-be commit message

## Would-Be Commit Message

```text
docs(control-center): add Stage 8.1 local transport activation decision gate
```
