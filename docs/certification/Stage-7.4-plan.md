# Stage 7.4 Certification Plan

## Objective

Create a controlled frontend UI projection for operator-facing health, activity, readiness, warnings, blockers, and read-surface coherence status using approved local read-model concepts from Stage 7.1 through Stage 7.3.

## Scope

- Add TypeScript projection types.
- Add deterministic local fixture states.
- Add pure projection helpers.
- Add operator readiness, health signal, activity, and coherence panels.
- Wire the panel into the existing static Control Center dashboard.
- Add focused frontend tests and documentation.

## Allowed Files

- `apps/control-center/lib/operator-read-surface-types.ts`
- `apps/control-center/lib/operator-read-surface-mock-data.ts`
- `apps/control-center/lib/operator-read-surface-projection.ts`
- `apps/control-center/components/operator-read-surface-panel.tsx`
- `apps/control-center/components/operator-health-signal-card.tsx`
- `apps/control-center/components/operator-activity-feed.tsx`
- `apps/control-center/components/operator-readiness-summary.tsx`
- `apps/control-center/components/read-surface-coherence-card.tsx`
- `apps/control-center/components/app-shell.tsx`
- `apps/control-center/components/sidebar.tsx`
- `apps/control-center/tests/operator-read-surface-projection.test.ts`
- `apps/control-center/tests/operator-read-surface-panel.test.tsx`
- `apps/control-center/tests/operator-health-activity-ui.test.tsx`
- `apps/control-center/tests/nav-wiring.test.tsx`
- `docs/specification/OPERATOR_READ_SURFACE_UI_PROJECTION_CONTRACT.md`
- `docs/certification/Stage-7.4-plan.md`

## Non-Goals

No backend routes, API routes, localhost routes, live sync transport, socket client, event-stream client, polling, timers, command execution, direct SQLite reads, adapter dispatch, package changes, dependency installation, cloud behavior, SaaS behavior, payment behavior, CRM behavior, or customer portal behavior.

## Implementation Summary

Stage 7.4 projects deterministic local fixture variants into UI panels. The populated fixture reflects Stage 7.1, 7.2, and 7.3 completion, Stage 7.4 projection in progress, and Stage 7.5 pending.

## Test Plan

- Run `pnpm lint` from `apps/control-center`.
- Run `pnpm build` from `apps/control-center`.
- Run `pnpm test` from `apps/control-center`.
- Run `.venv\Scripts\python.exe scripts/security_scan_baseline.py` from repo root.
- Run `.venv\Scripts\python.exe scripts/test_smoke.py` from repo root.
- Run `.venv\Scripts\python.exe scripts/test_release.py` from repo root.

## Safety Constraints

All projection helpers are pure. All timestamps are supplied by fixture data. No runtime clock, randomness, transport, direct persistence read, backend mutation, command behavior, or adapter behavior is introduced.

## Expected Commit Message

`feat(control-center): add Stage 7.4 operator read surface UI projection`
