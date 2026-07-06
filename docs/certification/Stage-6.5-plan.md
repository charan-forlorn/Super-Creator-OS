# Stage 6.5 Plan — Regression Debt Cleanup & Event Stream Readiness Gate

## Scope

Stage 6.5 is a regression cleanup and readiness gate only. It sits between the
Stage 6.4 local event stream / UI state sync foundation and any future Stage
6.6 deeper local UI synchronization work.

In scope:

- Fix pre-existing `control_center` regression debt (test-order pollution,
  missing `tmp_dir` fixture).
- Confirm Stage 6.4 event stream / UI state sync tests remain green.
- Confirm commercial tests, smoke, security scan, release check, and frontend
  lint/build remain green.
- Author the Event Stream Readiness Gate specification.

Out of scope (non-goals): new product features, WebSocket, Server-Sent
Events, polling, timers/background workers, real-time frontend sync, real
adapter activation/dispatch, arbitrary command execution, network ports,
Next.js API routes, backend socket servers, SaaS/auth/payment/CRM/customer
portal behavior, any Stage 6.6 work.

## Allowed files

Modify only if needed:

- `scos/control_center/tests/test_command_runner.py`
- `scos/control_center/tests/test_prompt_result_packet_store.py`
- `scos/control_center/tests/test_work_session_store.py`
- `scos/control_center/tests/conftest.py`
- `scos/control_center/conftest.py`
- `conftest.py`

Create:

- `docs/certification/Stage-6.5-plan.md`
- `docs/certification/Stage-6.5-regression-cleanup-report.md`
- `docs/specification/STAGE6_EVENT_STREAM_READINESS_GATE.md`

Optional:

- `scripts/test_control_center_regression.py`

## Known debt (pre-Stage-6.5 baseline)

- **Issue A (test-order pollution):** `test_command_runner.py` patched
  `command_runner.subprocess.run` at module import time with no teardown.
  When the full suite ran alphabetically, `test_stage5_final_certification.py`
  (module name sorts after `test_command_runner.py`) inherited the patched
  guard and its real-repo integration test failed trying to spawn a real
  subprocess.
- **Issue B (missing fixture):** `test_prompt_result_packet_store.py` and
  `test_work_session_store.py` request a `tmp_dir` fixture that was never
  defined for pytest collection (the files were written as dual-mode
  scripts with a `main()` entry point that supplies its own temp directory
  for standalone runs, but pytest collection needs a fixture of that name).

## Acceptance criteria

1. Preflight passes (branch `main`, HEAD == origin/main, clean tree, base is
   the Stage 6.4 commit).
2. Baseline debt reproduced and classified before any fix.
3. Issue A fixed via scoped patch/teardown (pytest `autouse` fixture with a
   `finally` restore), without weakening the guard's safety intent.
4. Issue B fixed via a narrow `tmp_dir` fixture aliasing `tmp_path`, without
   changing any store production contract.
5. Stage 6.4 event stream / UI state sync tests remain passing.
6. Full `scos/control_center/tests` passes.
7. `scos/commercial/tests` passes.
8. Smoke, security scan, and release checks pass.
9. Frontend lint/build pass.
10. No forbidden runtime behavior (WebSocket/SSE/polling/timers/sockets/etc.)
    is introduced.
11. Stage 6.5 docs created.
12. Stage 6.6 entry criteria explicitly stated.
13. No commit/push/tag/release performed as part of this stage's execution.

## Tests to run

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_command_runner.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_prompt_result_packet_store.py scos/control_center/tests/test_work_session_store.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_event_stream_models.py scos/control_center/tests/test_event_stream_builder.py scos/control_center/tests/test_event_stream_snapshot.py scos/control_center/tests/test_ui_state_sync.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe -m pytest scos/commercial/tests -q
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_release.py
pnpm lint   (from apps/control-center)
pnpm build  (from apps/control-center)
```

## Non-goals

See "Out of scope" above; identical list also recorded in the readiness gate
specification.

## Final report format

See `docs/certification/Stage-6.5-regression-cleanup-report.md` for the
executed report using the required 15-part structure (verdict, preflight
evidence, baseline reproduction, root cause classification, files changed,
tests run, static scan result, scope compliance, final regression state,
Stage 6.6 readiness, git status/diff evidence, commit recommendation, and
would-be commit message).
