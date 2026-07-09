# Operator Health Activity Read Models Contract

Stage 7.3 defines deterministic, read-only operator-facing models for local Control Center health, host metrics, recent activity, and drift status. The read models consume the Stage 7.1 read surface and Stage 7.2 coherence gate outputs; they do not parse raw stores when those public APIs are available.

## Purpose

Answer whether SCOS can expose health/activity/drift evidence as stable operator-ready backend models with freshness, coherence, degraded-state, missing-evidence, and stale-evidence metadata.

## Public API

- `build_operator_health_activity_snapshot(repo_root, checked_at, activity_limit=25)`
- `query_operator_health_activity_read_models(repo_root, checked_at, activity_limit=25)`
- `validate_operator_read_models_are_read_only(repo_root, checked_at)`
- `evaluate_operator_readiness(health_signals, recent_activity, checked_at)`

All timestamps are caller-supplied. `checked_at` must be a timestamp-like string accepted by the Stage 7.1 validation helpers.

## Model Schemas

- `OperatorFreshnessStatus`: `checked_at`, `source_id`, `source_type`, `is_present`, `is_readable`, `is_stale`, `freshness_level`, `warnings`
- `OperatorHealthSignal`: `signal_id`, `signal_type`, `status`, `severity`, `summary`, `source_stage`, `freshness`, `metadata`
- `OperatorActivityRecord`: `activity_id`, `activity_type`, `status`, `summary`, `source_stage`, `occurred_at`, `references`, `metadata`
- `OperatorReadModelSnapshot`: `snapshot_id`, `checked_at`, `health_signals`, `recent_activity`, `readiness_score`, `go_no_go`, `blockers`, `warnings`
- `OperatorReadModelResult`: `accepted`, `go_no_go`, `readiness_score`, `snapshot`, `blockers`, `warnings`, `checked_at`
- `OperatorReadModelError`: `error_code`, `message`, `checked_at`, `blockers`

All models are frozen dataclasses and expose deterministic `to_dict()` output.

## Health Signal Types

- `BACKEND_HEALTH`
- `STATE_STORE_HEALTH`
- `EVENT_STREAM_HEALTH`
- `APPROVAL_HEALTH`
- `AUDIT_HEALTH`
- `SECURITY_BASELINE`
- `DRIFT_STATUS`
- `HOST_METRICS`

Statuses are `HEALTHY`, `DEGRADED`, `STALE`, `MISSING`, `BLOCKED`, or `UNKNOWN`. Unknown evidence is never converted to `HEALTHY`.

## Activity Record Types

- `COMMAND_ACTIVITY`
- `APPROVAL_ACTIVITY`
- `AUDIT_ACTIVITY`
- `EVENT_ACTIVITY`
- `STATE_ACTIVITY`
- `SECURITY_ACTIVITY`
- `DRIFT_ACTIVITY`

Recent activity is sorted deterministically and limited by `activity_limit`.

## Freshness Model

Freshness levels are:

- `FRESH`: source evidence is present, readable, and has no warnings.
- `STALE`: evidence is present but carries warning or stale metadata.
- `MISSING`: source evidence is absent.
- `UNKNOWN`: evidence cannot be confidently classified.

No wall-clock freshness calculation is performed; Stage 7.3 does not call clocks.

## Degraded, Stale, And Missing Handling

Missing optional runtime artifacts become warnings and `MISSING` or `DEGRADED` signals. Missing required source evidence becomes blockers and `BLOCKED` readiness. Stale, drifted, malformed, or incoherent evidence is surfaced through signal status, freshness warnings, blockers, and activity records.

## Deterministic ID Rules

All Stage 7.3 IDs use SHA-256 over stable caller-supplied values and upstream deterministic evidence IDs. No UUIDs, randomness, clocks, network values, or process state are used.

## Error Model

Invalid input, failed read-surface queries, failed coherence gate execution, and malformed upstream envelopes return `OperatorReadModelError`. Errors include deterministic blockers and the caller-supplied `checked_at`.

## Read-Only Guarantee

Stage 7.3 does not create output paths, append JSONL, write SQLite, migrate schemas, execute commands, dispatch adapters, or start transports. Read-only validation delegates to Stage 7.1 boundary checks and Stage 7.2 non-mutation/hash-stability checks.

## Forbidden Behavior

No frontend UI, Next.js routes, HTTP routes, WebSocket, SSE, polling, timers, background workers, subprocess command execution, real adapter activation, AI dispatch, schema migration, cloud/network/SaaS/payment/CRM behavior, or package/dependency changes are allowed in Stage 7.3.

## Stage 7.4 Handoff

Stage 7.4 may consume `OperatorReadModelSnapshot.to_dict()` as a UI projection source. Stage 7.4 must remain downstream of these read models and must not mutate Stage 6 stores or bypass Stage 7.1/7.2 evidence checks.
