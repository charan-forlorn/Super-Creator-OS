# Stage 8.2 Plan - File Snapshot Refresh Transport Foundation

Predecessor Stage 8.1 commit:
`c2c443fb6e35aa7e06c1bf7d4d93817b2298625c`
(`docs(control-center): add Stage 8.1 local transport activation decision gate`).

## Scope

Create a local-only manual file snapshot refresh transport foundation. The
stage may build a deterministic payload from approved read surfaces and may
write exactly one explicit local JSON snapshot file when called.

Allowed Python files:

- `scos/control_center/file_snapshot_transport_models.py`
- `scos/control_center/file_snapshot_transport_validation.py`
- `scos/control_center/file_snapshot_refresh_transport.py`
- `scos/control_center/tests/test_file_snapshot_transport_models.py`
- `scos/control_center/tests/test_file_snapshot_transport_validation.py`
- `scos/control_center/tests/test_file_snapshot_refresh_transport.py`
- `scos/control_center/__init__.py` lazy exports only

Allowed docs:

- `docs/specification/FILE_SNAPSHOT_REFRESH_TRANSPORT_CONTRACT.md`
- `docs/specification/STAGE8_FILE_SNAPSHOT_TRANSPORT_BOUNDARY.md`
- `docs/certification/Stage-8.2-plan.md`

## Assumptions

- Stage 8.1 selected `FILE_SNAPSHOT_REFRESH_ALLOWED_LATER` as the lowest-risk
  future transport foundation.
- Stage 8.2 does not authorize live transport or frontend consumption.
- Stage 7 read surfaces and operator read models remain the approved source
  boundary.

## Architecture

```text
Stage 7 read/query surface
  -> operator health/activity read models
  -> approval-aware command view snapshot
  -> Stage 8.1 transport decision evidence
  -> deterministic payload and manifest
  -> explicit local JSON snapshot file
```

## Tests

Required verification commands:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_activation_decision_models.py scos/control_center/tests/test_transport_activation_decision_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Frontend checks are not required because Stage 8.2 must not touch frontend
files.

## Risks

- A file snapshot could be mistaken for live transport.
- A future UI could consume stale snapshots without freshness display.
- Output path validation could accidentally allow writes outside the repo.
- Snapshot content could drift into command execution, adapter dispatch, or
  credential exposure if boundaries are weakened later.

## PASS Criteria

Stage 8.2 passes only if:

- preflight passes
- file snapshot models are deterministic and immutable
- payload build writes nothing
- manual refresh writes exactly one local JSON file
- output path validation rejects URL, traversal, and out-of-bound paths
- approved read surfaces are consumed through public APIs where available
- missing optional evidence is surfaced as warnings
- missing required evidence is surfaced as blockers
- no source artifacts are mutated
- no SQLite mutation occurs
- no JSONL logs are appended
- no WebSocket, SSE/EventSource, polling, timers, background workers, or file
  watchers exist
- no HTTP route, localhost route, backend socket server, or Next.js API route
  exists
- no frontend feature is implemented
- no adapter activation or AI dispatch exists
- no command execution, subprocess, or shell use exists
- no API-key, secret, cloud, network, SaaS, payment, CRM, Buffer, or external
  API behavior exists
- Stage 8.1 contract remains compatible
- relevant Stage 7 and Stage 8 tests pass
- security, smoke, and release checks pass or exact environment evidence is
  documented
- no commit, push, tag, or release occurs

## No Commit / Push Rule

No commit, push, tag, release, branch switch, merge, rebase, reset, stash, or
clean operation is authorized by Stage 8.2.

## Next Recommended Stage 8.3

Stage 8.3 should define runtime credential and secret handling policy. It
should remain policy-first and must not use file snapshots to store or expose
credentials.

## Would-Be Commit Message

```text
feat(control-center): add Stage 8.2 file snapshot refresh transport foundation
```
