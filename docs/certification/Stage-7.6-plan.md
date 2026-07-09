# Stage 7.6 Plan - Approval-Aware Operator Command Views

Predecessor: Stage 7.5, confirmed at commit
`433024d3043999dc6e49ee64c37d55516480159d`.

## Objective

Create deterministic approval-aware operator command read models and a static
Control Center evidence surface so the operator can inspect pending, approved,
denied, missing approval, executed, blocked, and audited command evidence.

## Scope

Backend files:

- `scos/control_center/operator_command_view_models.py`
- `scos/control_center/operator_command_views.py`
- `scos/control_center/execution_evidence_surface.py`
- focused tests for those modules
- lazy exports in `scos/control_center/__init__.py`

Frontend files:

- `apps/control-center/lib/operator-command-view-types.ts`
- `apps/control-center/lib/operator-command-view-mock-data.ts`
- `apps/control-center/components/operator-command-views-panel.tsx`
- `apps/control-center/components/operator-command-evidence-card.tsx`
- `apps/control-center/components/approval-state-badge.tsx`
- `apps/control-center/components/execution-evidence-surface-panel.tsx`
- `apps/control-center/components/app-shell.tsx`
- `apps/control-center/components/sidebar.tsx`
- `apps/control-center/README.md`

Docs:

- `docs/specification/APPROVAL_AWARE_OPERATOR_COMMAND_VIEWS_CONTRACT.md`
- `docs/specification/READ_ONLY_EXECUTION_EVIDENCE_SURFACE_CONTRACT.md`
- `docs/certification/Stage-7.6-plan.md`

## Non-Goals

- no approval or denial writes
- no command execution
- no queue, event, approval, audit, state, or schema mutation
- no live transport
- no route or server
- no adapter dispatch
- no network/cloud/SaaS/payment/CRM behavior
- no commit, push, tag, or release

## Implementation Summary

Stage 7.6 adds frozen deterministic Python read models, pure classification
functions, snapshot builders, deterministic markdown export, and static
frontend fixture panels.

Denied, missing approval, tampered, blocked, and executed states are terminal
for the current action instance. Approved and pending evidence is visible but
does not create an execution path.

## Test Plan

Run:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_operator_command_view_models.py scos/control_center/tests/test_operator_command_views.py scos/control_center/tests/test_execution_evidence_surface.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
pnpm lint
pnpm build
pnpm test
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Frontend commands run from `apps/control-center`.

## Acceptance Criteria

- Preflight passes.
- Read models are immutable and deterministic.
- Operator can inspect all required approval and execution states.
- Denied and missing approval are terminal.
- Audit records remain inspectable and append-only.
- No execution, approval, denial, mutation, adapter dispatch, live transport,
  or network behavior is added.
- Focused backend tests pass.
- Control Center regression tests pass or exact unrelated failures are
  documented.
- Frontend lint, build, and tests pass when available.
- Smoke, security, and release checks pass or exact failure evidence is
  documented.
- Docs match implementation.
- No commit, push, tag, or release is performed.

## Stage 7.7 Handoff Notes

Stage 7.7 remains adapter activation preflight with no dispatch. It must use
Stage 7.6 command visibility only as read-only evidence and must separately
prove approval evidence, secret handling, simulator fallback, manual fallback,
audit records, rollback, and security review.

## Would-Be Commit Message

```text
feat(control-center): add Stage 7.6 approval-aware command views
```
