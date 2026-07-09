# Control Center Read Surface Contract

Status: **Stage 7.1 contract**

This document defines the Stage 7.1 module-level local read API over existing
Stage 6 Control Center artifacts. It is a read-only query surface. It does not
create transports, UI features, command execution paths, schema migrations, or
adapter dispatch.

## 1. Purpose

The read surface answers:

> Can SCOS inspect local Control Center state, events, approvals, audit
> records, health, and drift evidence through a safe read-only API without
> mutating any store or introducing transport/UI/adapter behavior?

Stage 7.1 creates a Python stdlib-only foundation for later Stage 7.2
coherence gates and Stage 7.3/7.4 read models/UI projection.

## 2. Query types

Allowed `query_type` values:

- `CONTROL_CENTER_OVERVIEW`
- `STATE_SUMMARY`
- `EVENT_SUMMARY`
- `APPROVAL_SUMMARY`
- `AUDIT_SUMMARY`
- `HEALTH_SUMMARY`
- `DRIFT_SUMMARY`
- `FULL_LOCAL_READ_SURFACE`

Unknown query types return `ReadSurfaceError` and do not inspect artifacts.

## 3. Public API

```python
create_read_surface_query(
    *,
    query_type: str,
    requested_at: str,
    include_state: bool = True,
    include_events: bool = True,
    include_approvals: bool = True,
    include_audit: bool = True,
    include_health: bool = True,
    include_drift: bool = True,
    limit: int = 50,
) -> ReadSurfaceQuery | ReadSurfaceError
```

```python
build_read_surface_snapshot(
    *,
    repo_root,
    query: ReadSurfaceQuery,
    checked_at: str,
) -> ReadSurfaceSnapshot | ReadSurfaceError
```

```python
query_control_center_read_surface(
    *,
    repo_root,
    query_type: str,
    checked_at: str,
    include_state: bool = True,
    include_events: bool = True,
    include_approvals: bool = True,
    include_audit: bool = True,
    include_health: bool = True,
    include_drift: bool = True,
    limit: int = 50,
) -> ReadSurfaceResult | ReadSurfaceError
```

```python
validate_read_surface_is_read_only(
    *,
    repo_root,
    checked_at: str,
) -> dict
```

## 4. Models

All models are frozen dataclasses with deterministic `to_dict()` output.

### ReadSurfaceReference

- `reference_id: str`
- `reference_type: str`
- `path: str`
- `exists: bool`
- `readable: bool`
- `source_stage: str`

### ReadSurfaceQuery

- `query_id: str`
- `query_type: str`
- `requested_at: str`
- `include_state: bool`
- `include_events: bool`
- `include_approvals: bool`
- `include_audit: bool`
- `include_health: bool`
- `include_drift: bool`
- `limit: int`

### ReadSurfaceRecord

- `record_id: str`
- `record_type: str`
- `source_stage: str`
- `summary: str`
- `status: str`
- `references: tuple[ReadSurfaceReference, ...]`
- `metadata: tuple[tuple[str, str], ...]`

### ReadSurfaceSnapshot

- `snapshot_id: str`
- `checked_at: str`
- `query_id: str`
- `records: tuple[ReadSurfaceRecord, ...]`
- `readiness: FrozenMap`
- `blockers: tuple[str, ...]`
- `warnings: tuple[str, ...]`

### ReadSurfaceResult

- `accepted: bool`
- `go_no_go: str`
- `readiness_score: int`
- `snapshot: ReadSurfaceSnapshot | None`
- `blockers: tuple[str, ...]`
- `warnings: tuple[str, ...]`
- `checked_at: str`

### ReadSurfaceError

- `error_code: str`
- `message: str`
- `checked_at: str`
- `blockers: tuple[str, ...]`

## 5. Read-only guarantee

Stage 7.1 must not:

- Write output files.
- Append JSONL records.
- Mutate SQLite databases.
- Run schema migrations.
- Execute commands.
- Create local or network transports.
- Activate adapters.

SQLite inspection uses read-only URI mode. JSONL inspection reads existing
files only. Missing optional runtime artifacts produce deterministic warnings.
Missing required Stage 6 source/contract artifacts produce deterministic
blockers.

## 6. Deterministic ID rules

- `ReadSurfaceQuery.query_id` uses SHA-256 over stable query inputs.
- `ReadSurfaceReference.reference_id`, `ReadSurfaceRecord.record_id`, and
  `ReadSurfaceSnapshot.snapshot_id` use SHA-256 over stable local inputs.
- `checked_at` and `requested_at` are caller-supplied only.
- No clock, nondeterministic ID source, or process-global mutable state is
  used.
- Collections are sorted before serialization.

## 7. Error model

Invalid inputs return `ReadSurfaceError`:

- `INVALID_QUERY`
- `INVALID_QUERY_OBJECT`
- `INVALID_SNAPSHOT_INPUT`
- `INVALID_CHECKED_AT`

Errors include deterministic blockers and do not inspect or mutate stores
after validation fails.

## 8. Allowed Stage 6 sources

Stage 7.1 may read:

- Stage 6.3 SQLite state path
  `scos/work/control_center/state/control_center.sqlite3`
- Stage 6.4 event log path
  `scos/work/control_center/events/command_events.jsonl`
- Stage 6.2 command queue path
  `scos/work/control_center/queue/approved_commands.jsonl`
- Stage 6.6/6.7 approval and audit tables in the Stage 6 SQLite store.
- Stage 6.9 backend health and drift modules.
- Stage 6 handoff, gate, and boundary documentation.

The read surface must reject URL-like paths and path traversal outside
`repo_root`.

## 9. Forbidden behavior

Stage 7.1 does not authorize:

- Frontend UI work.
- Next.js API routes.
- Localhost HTTP routes.
- WebSocket, SSE, polling, timers, or background workers.
- Command execution.
- Real AI adapter dispatch.
- External API calls.
- Cloud, SaaS, payment, CRM, telemetry, or customer portal behavior.
- Dependency or package changes.
- Stage 4, Stage 5, or Stage 6 public contract breaks.

## 10. Stage 7.2 handoff

Stage 7.2 should add a read surface contract/coherence gate that verifies:

- Non-mutation across representative Stage 6 artifacts.
- Schema and error model stability.
- Required source coverage.
- Optional artifact warning behavior.
- Security/static scan coverage for the new read surface.

Stage 7.2 implements this handoff in
`docs/specification/READ_SURFACE_COHERENCE_GATE_CONTRACT.md` and the
`run_read_surface_coherence_gate(...)` public function. This is additive only:
the Stage 7.1 query types, models, and public API remain unchanged.
