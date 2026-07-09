# Read Surface Coherence Gate Contract

Status: **Stage 7.2 contract**

This document defines the deterministic Stage 7.2 contract and coherence gate
for the Stage 7.1 local Control Center read surface.

## 1. Purpose

The coherence gate answers:

> Can SCOS verify that the local read surface accurately reflects Stage 6
> artifacts without mutating state, hiding drift, or silently falling back?

The gate is a certification layer only. It does not add read capabilities,
UI, routes, transports, command execution, adapter dispatch, or store writes.

## 2. Public API

```python
run_read_surface_coherence_gate(
    *,
    repo_root,
    checked_at: str,
    query_type: str = "FULL_LOCAL_READ_SURFACE",
    require_stage7_1_contract: bool = True,
    require_stage6_sources: bool = True,
) -> ReadSurfaceCoherenceReport | ReadSurfaceCoherenceError
```

```python
validate_read_surface_contract_alignment(
    *,
    repo_root,
    checked_at: str,
) -> tuple[ReadSurfaceContractCheck, ...] | ReadSurfaceCoherenceError
```

```python
compare_read_surface_to_stage6_artifacts(
    *,
    repo_root,
    checked_at: str,
    query_type: str = "FULL_LOCAL_READ_SURFACE",
) -> tuple[ReadSurfaceCoherenceIssue, ...] | ReadSurfaceCoherenceError
```

```python
validate_read_surface_non_mutation_contract(
    *,
    repo_root,
    checked_at: str,
) -> tuple[ReadSurfaceContractCheck, ...] | ReadSurfaceCoherenceError
```

## 3. Models

All models are frozen dataclasses with deterministic `to_dict()` output.

### ReadSurfaceContractCheck

- `check_id: str`
- `check_name: str`
- `status: str`
- `severity: str`
- `summary: str`
- `source_stage: str`
- `references: tuple[str, ...]`
- `metadata: tuple[tuple[str, str], ...]`

### ReadSurfaceCoherenceIssue

- `issue_id: str`
- `issue_type: str`
- `severity: str`
- `message: str`
- `source_reference: str`
- `read_surface_reference: str`
- `blocker: bool`

### ReadSurfaceCoherenceReport

- `report_id: str`
- `checked_at: str`
- `accepted: bool`
- `go_no_go: str`
- `readiness_score: int`
- `contract_checks: tuple[ReadSurfaceContractCheck, ...]`
- `coherence_issues: tuple[ReadSurfaceCoherenceIssue, ...]`
- `blockers: tuple[str, ...]`
- `warnings: tuple[str, ...]`

### ReadSurfaceCoherenceError

- `error_code: str`
- `message: str`
- `checked_at: str`
- `blockers: tuple[str, ...]`

## 4. PASS / NO_GO rules

- `GO` requires zero blockers.
- Any missing required Stage 6 source artifact is a blocker.
- Missing optional Stage 6 runtime artifacts are warnings.
- Malformed Stage 7.1 result envelopes are blockers.
- Stage 7.1 public export or contract-file gaps are blockers.
- Non-mutation evidence changing across a gate run is a critical blocker.
- Warnings alone do not block `GO`, but reduce readiness score.

## 5. Blocker rules

The gate records blockers for:

- Invalid `repo_root` or `checked_at`.
- Missing required Stage 7.1 contract/certification files.
- Missing required Stage 7.1 public exports.
- Missing required Stage 6 source artifacts.
- Stage 7.1 read surface returning blockers.
- Stage 7.1 `accepted` / `go_no_go` inconsistency.
- Known local artifact hashes changing during the gate.

## 6. Warning rules

The gate records warnings for:

- Missing optional runtime artifacts such as local SQLite state, event log, or
  command queue.
- Required Stage 6 source artifacts that exist but are not referenced by the
  read surface output.
- Stage 7.1 read-surface warnings.
- Unknown or ambiguous evidence that is not severe enough to block.

## 7. Stage 6 source artifact assumptions

Required Stage 6 source/contract artifacts:

- `scos/control_center/backend_health.py`
- `scos/control_center/drift_detection.py`
- `scos/control_center/sqlite_state_schema.py`
- `scos/control_center/host_metrics.py`
- `docs/roadmap/STAGE7_HANDOFF.md`
- `docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md`

Optional Stage 6 runtime artifacts:

- `scos/work/control_center/state/control_center.sqlite3`
- `scos/work/control_center/events/command_events.jsonl`
- `scos/work/control_center/queue/approved_commands.jsonl`

## 8. Stage 7.1 dependency

Stage 7.2 depends on the Stage 7.1 public read surface. It uses
`query_control_center_read_surface(...)` and
`validate_read_surface_is_read_only(...)` as the source of read-surface truth.
It does not bypass Stage 7.1 by adding a second query API.

## 9. Deterministic ID rules

- Check, issue, and report IDs use SHA-256 over stable caller-supplied and
  local artifact inputs.
- `checked_at` is caller-supplied.
- Collections are sorted before serialization.
- The same local artifacts and same `checked_at` produce the same report.

## 10. Read-only / non-mutation guarantee

The gate reads known local artifacts before and after the Stage 7.1 query and
compares stable hashes. It does not write output files, mutate SQLite, append
JSONL, run migrations, execute commands, or start transports.

## 11. Error model

Expected input failures return `ReadSurfaceCoherenceError`, including:

- `INVALID_COHERENCE_INPUT`
- `READ_SURFACE_QUERY_FAILED`
- `MALFORMED_READ_SURFACE_RESULT`

Errors contain deterministic blockers and no output file.

## 12. Forbidden behavior

Stage 7.2 does not authorize:

- New read capabilities beyond Stage 7.1.
- Frontend UI work.
- Next.js or localhost routes.
- WebSocket, SSE, polling, timers, or background workers.
- Command execution.
- Real AI adapter dispatch.
- Cloud, network, SaaS, payment, CRM, telemetry, or customer portal behavior.
- Package/dependency changes.
- Stage 4, Stage 5, Stage 6, or Stage 7.1 public contract breaks.

## 13. Stage 7.3 handoff

Stage 7.3 should consume Stage 7.1 read outputs only after the Stage 7.2
coherence gate returns `GO` or records understood non-blocking warnings. Any
health/activity read model must preserve the warning/blocker semantics
established here.
