# Operator Read Surface UI Projection Contract

Stage 7.4 adds a frontend-only UI projection for approved Stage 7.1, Stage 7.2, and Stage 7.3 read-model concepts. It renders deterministic local fixture data inside the existing Control Center dashboard and preserves the static/mock fallback path.

## Scope

- Render operator readiness, health signals, recent activity, and read-surface coherence.
- Use TypeScript types that mirror approved read-model concepts without importing Python.
- Use deterministic local fixture data only.
- Keep all projection functions pure and side-effect free.

## UI Panel Contract

Stage 7.4 provides:

- `OperatorReadinessSummary`: go/no-go, readiness score, checked timestamp, signal count, blockers, warnings, degraded/stale count.
- `OperatorHealthSignalCard`: signal group, status, severity, summary, references count, warning/blocker hints.
- `OperatorActivityFeed`: supplied occurrence timestamp, activity type, status, summary, source stage, reference label.
- `ReadSurfaceCoherenceCard`: coherence status, checked timestamp, inspected sources, blockers, warnings, fallback note.
- `OperatorReadSurfacePanel`: composed panel with loading, empty, populated, degraded, and error states.

## Projection Data Shape

The frontend defines:

- `OperatorReadSurfaceStatus`
- `OperatorHealthSignalType`
- `OperatorHealthSignal`
- `OperatorActivityRecord`
- `OperatorReadinessSummary`
- `ReadSurfaceCoherenceSummary`
- `OperatorReadSurfaceProjection`
- `OperatorReadSurfaceProjectionState`

The projection states are `loading`, `empty`, `populated`, `degraded`, and `error`.

## Fallback Behavior

Stage 7.4 always displays the operator note:

`Stage 7.4 uses deterministic local projection data. Live transport is deferred to Stage 7.5 decision.`

Missing arrays project as empty or degraded-safe state, never as healthy runtime evidence. Error fixtures expose blockers and no-go readiness.

## Forbidden Transport Behavior

Stage 7.4 introduces no live sync, network request, socket, event-stream client, polling loop, timer-based simulation, backend route, server action, middleware, direct SQLite read, command execution, adapter dispatch, cloud service, SaaS behavior, payment behavior, CRM behavior, or customer portal behavior.

## Relationship To Prior Stages

- Stage 7.1 remains the backend read-surface source concept.
- Stage 7.2 remains the coherence and non-mutation source concept.
- Stage 7.3 remains the operator health/activity snapshot source concept.
- Stage 7.4 is only a static frontend projection of those approved concepts.

## Stage 7.5 Handoff

Stage 7.5 may decide whether any live UI sync transport is approved. Until then, the Stage 7.4 projection must remain deterministic and local-only.

## Testing Expectations

Tests must cover projection determinism, activity limiting, populated UI rendering, loading/empty/degraded/error states, fallback notice visibility, forbidden live-transport token scan for Stage 7.4 files, and existing app-shell render compatibility.

## Rollback Plan

Remove the Stage 7.4 navigation entry, the `operator-read-surface` app-shell section, Stage 7.4 component files, Stage 7.4 projection library files, Stage 7.4 tests, and this contract document. No backend rollback is required because Stage 7.4 does not change backend behavior.
