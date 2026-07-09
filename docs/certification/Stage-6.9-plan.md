# Stage 6.9 Certification Plan — Local Backend Monitoring & Observability

Status: **IMPLEMENTED / READY FOR REVIEW**

- Implementation is complete.
- No commit/push has been done.
- This plan records implementation and verification evidence.

---

## 1. Status

**IMPLEMENTED / READY FOR REVIEW**

This document records the scope, architecture, implementation, acceptance
criteria, and verification evidence for Stage 6.9 of the Super Creator OS
Control Center certification track.

Explicit status statements:

- Implementation is complete.
- No commit/push has been done.
- No frontend changes were made.
- No Read API, WebSocket, SSE, polling, API route, timer, daemon, network,
  cloud telemetry, or real AI dispatch behavior was introduced.

---

## 2. Objective

Stage 6.9 must create **local backend monitoring and observability** for the
Control Center.

The defining question Stage 6.9 must answer:

> Can SCOS determine backend health and recent activity from local artifacts
> through re-runnable, offline-safe checks?

Stage 6.9 is about observing what already exists locally — the SQLite WAL
state store, event logs, approval audit ledger, and command queue/runner
evidence — and producing a deterministic, read-only local health report. It
introduces no new network surface, no real-time path, and no state mutation.

---

## 3. Binding Docs Decision

Per the binding certification docs and the Hermes Gateway preflight result:

Stage 6.9 **IS**:

- Local Backend Monitoring & Observability

Stage 6.9 is explicitly **NOT**:

- Read API
- UI sync read surface
- WebSocket
- SSE
- polling
- real-time frontend sync
- Next.js API route
- backend socket server
- real AI dispatch
- integrations/buffer

The preflight verdict for Stage 6.9 was **GO**. Stage 6.9 must remain
local-first, read-only, offline-safe, and deterministic. WebSocket / SSE /
polling remain forbidden. The frontend must remain static/mock.

---

## 4. Scope

In scope for future implementation (docs only at this stage):

- local backend health checks
- structured local logs / metrics
- drift detection
- read-only inspection of SQLite WAL state
- read-only inspection of event logs
- read-only inspection of approval audit ledger
- read-only inspection of command queue / command execution evidence
- deterministic health report
- offline-safe re-runnable checks
- maintenance log convention

All of the above operate strictly against local on-disk artifacts and produce
a stable, reproducible report.

---

## 5. Non-Goals

Explicitly out of scope for Stage 6.9:

- no frontend changes
- no apps/control-center changes
- no cloud telemetry
- no hosted APM
- no data leaving local machine
- no external API
- no network port
- no WebSocket
- no SSE
- no polling
- no timers/background workers
- no real AI dispatch
- no CRM/payment/SaaS/customer portal
- no Buffer integration
- no arbitrary command execution

---

## 6. Implementation Files

Created:

- `scos/control_center/backend_health.py`
- `scos/control_center/host_metrics.py`
- `scos/control_center/drift_detection.py`
- `scos/control_center/tests/test_backend_health.py`
- `scos/control_center/tests/test_drift_detection.py`

Modified:

- `docs/certification/Stage-6.9-plan.md`

Not modified:

- `scos/control_center/__init__.py`

---

## 7. Existing Modules Read From

Future implementation may READ from the following existing modules:

- `scos/control_center/sqlite_state_store.py`
- `scos/control_center/state_repository.py`
- `scos/control_center/sqlite_state_schema.py`
- `scos/control_center/event_log.py`
- `scos/control_center/event_stream_models.py`
- `scos/control_center/event_stream_snapshot.py`
- `scos/control_center/approval_audit_store.py`
- `scos/control_center/approval_audit_models.py`
- `scos/control_center/command_runner.py`
- `scos/control_center/command_api.py`
- `scos/control_center/command_queue.py`
- `scos/control_center/operator_approval.py`

These modules were treated as **read-only sources**. Stage 6.9 does not mutate
state, event, audit, queue, or approval stores. The monitoring layer inspects
existing artifacts; it never writes to them.

Important implementation decision: `backend_health.py` reads SQLite artifacts
directly through read-only SQLite URI connections (`mode=ro`) instead of using
store helpers that create parent directories, initialize schema, or apply
write-oriented connection setup. This preserves the Stage 6.9 read-only
contract.

---

## 8. Proposed Architecture

Data flow:

```
SQLite WAL State Store
        |
Event Log / Event Stream Snapshot
        |
Approval Audit Ledger
        |
Command Queue / Command Runner Evidence
        |
Backend Health Probe
        |
Drift Detection
        |
Deterministic Local Health Report
```

The Backend Health Probe reads each local source (state store, event log,
approval audit ledger, command queue/runner evidence) without mutation. Drift
Detection compares the independent sources for consistency. The output is a
Deterministic Local Health Report containing the local-only metrics defined in
Section 10.

---

## 9. Health Checks to Support

Implemented checks:

- backend artifact availability
- SQLite WAL state readability
- event log readability
- approval audit ledger readability
- command queue readability
- recent activity summary
- missing artifact warnings
- malformed record warnings
- drift between state/event/audit evidence
- append-only audit invariant
- local-only path safety
- deterministic output stability

---

## 10. Metrics / Logs

Define local-only metrics for the health report:

- `source_coverage`
- `checked_at`
- `artifact_count`
- `event_count`
- `audit_record_count`
- `command_record_count`
- `drift_count`
- `warning_count`
- `blocker_count`
- `health_status`

Allowed `health_status` values:

- `healthy`
- `degraded`
- `blocked`

All metrics are derived solely from local artifacts and the caller-supplied
`checked_at` timestamp. No external collection occurs.

Implemented metric helpers in `host_metrics.py`:

- artifact exists/file/dir/readability/size status
- directory artifact count helper
- JSONL record count
- JSONL malformed line count
- last JSONL record metadata
- SQLite read-only readability check
- SQLite journal/WAL mode check
- SQLite table counts for expected local tables
- local path safety rejection for URL-like or repo-escaping paths

---

## 11. Test Results

Commands run:

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_backend_health.py scos/control_center/tests/test_drift_detection.py -q --basetemp .pytest-stage69-tmp` | PASS; 15 passed, 0 failed; warning: default `.pytest_cache` write denied |
| `.venv\Scripts\python.exe -m pytest scos/control_center/tests -q --basetemp .pytest-control-center-tmp` | PASS; 410 passed, 0 failed; warning: default `.pytest_cache` write denied |
| `.venv\Scripts\python.exe scripts/test_smoke.py` | PASS; 16 passed, 0 failed |
| `.venv\Scripts\python.exe scripts/security_scan_baseline.py` | PASS; 298 files scanned, 0 findings |

Frontend commands were not run because Stage 6.9 made no frontend changes.

## 11a. Health Model Summary

`run_backend_health_check(...)` returns a frozen `BackendHealthReport` with:

- `schema_version`
- `checked_at`
- `health_status`
- `source_coverage`
- `artifact_count`
- `event_count`
- `audit_record_count`
- `command_record_count`
- `drift_count`
- `warning_count`
- `blocker_count`
- `checks`
- `warnings`
- `blockers`
- `recent_activity_summary`
- `drift_findings`

Status rules:

- `healthy`: all inspected artifacts readable and no warnings/blockers.
- `degraded`: warnings exist but no blockers.
- `blocked`: one or more blockers exist, such as malformed required SQLite,
  malformed JSONL records, unsafe paths, or failed audit-chain verification.

## 11b. Drift Model Summary

`detect_backend_drift(...)` reports deterministic `DriftFinding` records for:

- command exists in queue but no matching event/result evidence
- event references unknown command
- SQLite event references unknown command/session
- approval decision exists but missing linked command evidence
- audit chain verification failure
- malformed source records

Drift IDs are SHA-256 derived from stable finding fields.

---

## 12. Determinism Requirements

The health report is deterministic. Implementation guarantees:

- caller-supplied timestamps only
- no `datetime.now`
- no `time.time`
- no `random`
- no `uuid`
- deterministic IDs use stable hash inputs
- same local artifacts + same `checked_at` must produce stable output

This ensures offline-safe re-runnability and prevents flaky or
time-dependent health reports.

Determinism evidence:

- Tests assert identical `to_dict()` output for identical artifacts and
  identical `checked_at`.
- Tests scan Stage 6.9 source for forbidden clock/random/uuid/network/subprocess
  tokens.
- All report timestamps are caller-supplied or read from existing artifacts.

---

## 13. Risks

Known risks to guard against during implementation:

- scope creep into Read API
- accidental frontend changes
- accidental WebSocket/SSE/polling
- accidental mutation of local stores
- health log becoming a hidden daemon
- false-positive drift checks
- integrations/buffer contamination
- duplicate lazy export key risk

Each risk maps to a guardrail in Sections 3, 5, and 7 (read-only sources,
no network surface, no timers/daemons).

---

## 14. Acceptance Criteria

Stage 6.9 implementation will pass only when:

- `Stage-6.9-plan.md` exists
- backend health can be determined from local artifacts
- recent activity can be summarized from local artifacts
- drift detection works deterministically
- no existing stores are mutated
- no frontend files are changed
- no network/cloud/telemetry behavior exists
- no WebSocket/SSE/polling/API route exists
- security scan passes
- control_center tests pass
- smoke passes
- no commit/push occurs without operator approval

Acceptance result: **PASS**.

Evidence:

- Backend health can be determined from local artifacts.
- Recent activity is summarized from local artifact content only.
- Drift detection works deterministically.
- Tests verify health checks do not mutate inspected files.
- No frontend files changed.
- No network/cloud/telemetry behavior exists.
- No WebSocket/SSE/polling/API route exists.
- Security scan passes with 0 findings.
- Control Center tests pass.
- Smoke passes.
- No commit/push was performed.

---

## 15. Final Verdict

**PASS**

Stage 6.9 Local Backend Monitoring & Observability is implemented and verified
locally. No commit, push, tag, release, branch switch, stash, reset, rebase, or
merge was performed.

---

## 16. Recommended Future Commit Message

```
feat(control-center): add Stage 6.9 local backend monitoring and observability
```

This commit message is a recommendation only. No commit or push occurs during
the planning stage, and none should occur without explicit operator approval.
