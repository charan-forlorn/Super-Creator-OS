# Stage 7.1 Plan - Local Control Center Read API / Query Surface

Predecessor: Stage 7.0, confirmed at commit
`79bca9f1f0b040b232a2fd373f2ae86aaa4a5f27`.

## 1. Goal

Create a deterministic, read-only Python query surface over existing Stage 6
Control Center artifacts.

Stage 7.1 answers:

> Can SCOS inspect local Control Center state, events, approvals, audit
> records, health, and drift evidence through a safe read-only API without
> mutating any store or introducing transport/UI/adapter behavior?

## 2. Scope

Allowed Python files:

- `scos/control_center/read_surface_models.py`
- `scos/control_center/read_surface_query.py`
- `scos/control_center/read_surface_facade.py`
- `scos/control_center/read_surface_snapshot.py`
- `scos/control_center/read_surface_validation.py`
- `scos/control_center/tests/test_read_surface_models.py`
- `scos/control_center/tests/test_read_surface_query.py`
- `scos/control_center/tests/test_read_surface_facade.py`
- `scos/control_center/tests/test_read_surface_snapshot.py`
- `scos/control_center/tests/test_read_surface_validation.py`
- `scos/control_center/__init__.py` only for lazy exports

Allowed docs:

- `docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md`
- `docs/specification/STAGE7_READ_ONLY_QUERY_BOUNDARY.md`
- `docs/certification/Stage-7.1-plan.md`

## 3. Non-goals

- No frontend UI.
- No Next.js API routes.
- No localhost HTTP routes.
- No WebSocket, SSE, polling, timers, or background workers.
- No command execution.
- No SQLite mutation.
- No JSONL append/write.
- No schema migration.
- No real ChatGPT, Claude Code, Codex, Hermes, or Buffer adapter activation.
- No cloud, network, SaaS, payment, CRM, customer portal, or telemetry.
- No package/dependency changes.
- No Stage 4, Stage 5, or Stage 6 public contract breaks.
- No commit, push, tag, or release.

## 4. Test plan

Targeted tests:

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_models.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_validation.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_query.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_snapshot.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_read_surface_facade.py -q
```

Regression checks:

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_release.py
```

When the default user temp directory is inaccessible, use `--basetemp` under
`work/pytest-tmp/` for pytest fixture creation.

## 5. Acceptance criteria

- Preflight passes on `main`, `HEAD == origin/main`, clean tree, latest Stage
  7.0 commit.
- New read surface models are immutable and deterministic.
- Query creation validates query type, timestamps, limit, and options.
- Snapshot builder inspects available Stage 6 evidence without writing.
- Facade returns deterministic `accepted`, `go_no_go`, and
  `readiness_score`.
- Missing optional artifacts produce deterministic warnings.
- Missing required artifacts produce deterministic blockers.
- Read-only validation confirms no output path or write operation is used.
- No SQLite mutation, JSONL append/write, command execution, adapter
  dispatch, transport, frontend feature, or cloud behavior is introduced.
- Targeted and regression tests pass or failures are reported with exact
  evidence.

## 6. Final report format

The final Stage 7.1 report must include:

1. Verdict.
2. Preflight evidence.
3. Files created.
4. Files modified.
5. Public models implemented.
6. Public functions implemented.
7. Validation rules implemented.
8. Stage 6 sources inspected/read.
9. Read-only guarantee evidence.
10. Tests run and results.
11. Smoke/security/release results.
12. Static scan results.
13. Architecture notes.
14. Known limitations.
15. Stage 7.2 handoff notes.
16. Required no-behavior confirmations.
17. `git status --short --untracked-files=all`.
18. `git diff --stat`.
19. Commit recommendation.
20. Would-be commit message.

## 7. Would-be commit message

```
feat(control-center): add Stage 7.1 local read query surface
```
