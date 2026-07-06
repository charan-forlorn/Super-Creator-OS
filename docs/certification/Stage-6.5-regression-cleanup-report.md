# Stage 6.5 Regression Cleanup Report

## Verdict: PASS

## 1. Preflight evidence

- Branch: `main`
- HEAD: `7942ebf8eb6f45557db2aed618d724ccff462a19`
- origin/main: `7942ebf8eb6f45557db2aed618d724ccff462a19`
- Working tree: clean at start
- Latest commit matches the confirmed Stage 6.4 commit
  (`feat(control-center): add Stage 6.4 local event stream and UI state sync
  foundation`)

## 2. Baseline regression reproduction (before fix)

`scos/control_center/tests -q`:

```
12 failed, 343 passed, 12 errors in 6.72s
```

- 12 failures: all in `test_stage5_final_certification.py` (e.g.
  `test_certification_id`, `test_go_on_complete_fixture`,
  `test_no_go_on_missing_artifact`, `test_real_repo_readonly`, etc.), every
  one raising `AssertionError: subprocess.run must never be called in this
  suite` from `test_command_runner.py`'s `_SubprocessGuard`.
- 12 errors: `fixture 'tmp_dir' not found` across
  `test_prompt_result_packet_store.py` (7 tests) and
  `test_work_session_store.py` (5 tests).

Targeted reproduction — `test_command_runner.py` in isolation:

```
7 passed in 0.29s
```

Confirms the guard itself is correct; the leak only manifests across the
full suite (test-order pollution), matching the reported Issue A.

## 3. Root cause classification

- **Issue A — confirmed pre-existing test-order-pollution debt.**
  `test_command_runner.py` assigned
  `command_runner.subprocess.run = _GUARD` at module import time with no
  restoration. Because pytest imports all test modules into one process and
  `test_stage5_final_certification.py` sorts after `test_command_runner.py`
  alphabetically, its real-repo integration test (`run_stage5_final_certification`
  with `run_smoke=False` etc., which still shells out to run individual test
  scripts) inherited the patched guard and failed. This is a test-harness
  defect, not a production defect — `command_runner.py` itself was never
  touched.
- **Issue B — confirmed pre-existing test-only defect.** The two Stage 5.x
  store test suites are dual-mode scripts: they have a `main()` that supplies
  its own `tempfile.mkdtemp()`-based directory for standalone execution, but
  their `test_*` functions declare a `tmp_dir` parameter that pytest
  interprets as a fixture request. No fixture named `tmp_dir` existed
  anywhere in the repo (only a similarly-shaped `tmp` fixture in the root
  `conftest.py`), so pytest collection errored for every affected test.
- No new Stage 6.4 issues were found. No production defects were found.

## 4. Files changed

**Modified:**
- `scos/control_center/tests/test_command_runner.py` — replaced the
  module-level, unrestored `command_runner.subprocess.run = _GUARD`
  assignment with an `autouse` pytest fixture that patches the guard in for
  this module's tests only and restores the original `subprocess.run` in a
  `finally` block on teardown. The standalone `main()` entry point (for
  `python test_command_runner.py` direct execution) was updated to apply
  and restore the same patch manually, preserving its original behavior.
  No safety-check intent was weakened — the guard still raises on any real
  subprocess call during this module's tests, and `_GUARD.calls == 0`
  assertions are preserved.
- `conftest.py` (repo root) — added a `tmp_dir` fixture aliasing `tmp_path`,
  alongside the existing `tmp` fixture. No production code was touched.

**Created:**
- `docs/certification/Stage-6.5-plan.md`
- `docs/certification/Stage-6.5-regression-cleanup-report.md` (this file)
- `docs/specification/STAGE6_EVENT_STREAM_READINESS_GATE.md`

**Not touched:**
- `scos/control_center/tests/test_prompt_result_packet_store.py` (fixed via
  the root fixture, no file-level change needed)
- `scos/control_center/tests/test_work_session_store.py` (same)
- `scos/control_center/tests/conftest.py`, `scos/control_center/conftest.py`
  (no per-package conftest existed or was needed)
- `scripts/test_control_center_regression.py` (not needed — existing
  pytest invocation is sufficient)
- All production modules (`command_runner.py`, `prompt_result_packet_store.py`,
  `work_session_store.py`, event stream models/builder/snapshot, UI state
  sync foundation) — no production contract changes.

## 5. Tests run (exact commands and results)

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_command_runner.py -q
  -> 7 passed in 0.32s

.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_prompt_result_packet_store.py scos/control_center/tests/test_work_session_store.py -q
  -> 15 passed in 0.34s

.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_event_stream_models.py scos/control_center/tests/test_event_stream_builder.py scos/control_center/tests/test_event_stream_snapshot.py scos/control_center/tests/test_ui_state_sync.py -q
  -> 34 passed in 0.08s

.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
  -> 367 passed in 37.99s

.venv\Scripts\python.exe -m pytest scos/commercial/tests -q
  -> 243 passed in 205.23s

.venv\Scripts\python.exe scripts/test_smoke.py
  -> 16 passed, 0 failed / SMOKE: PASS

.venv\Scripts\python.exe scripts/security_scan_baseline.py
  -> 65 files scanned, 0 findings / SECURITY SCAN: PASS

.venv\Scripts\python.exe scripts/test_release.py
  -> 9 passed, 1 warned (dirty-tree, report-only), 0 failed / RELEASE CHECK: PASS

pnpm lint (apps/control-center)
  -> clean, no output, exit 0

pnpm build (apps/control-center)
  -> Next.js 15.5.18 build succeeded, all routes prerendered as static content
```

## 6. Static scan result

Scanned the two changed files (`conftest.py`,
`scos/control_center/tests/test_command_runner.py`) for the full forbidden
pattern list (WebSocket, EventSource, setInterval/setTimeout, fetch(,
XMLHttpRequest, axios, Date.now, Math.random, crypto.randomUUID,
localStorage/sessionStorage, route.ts/middleware.ts/server actions, socket,
websocket, aiohttp/fastapi/flask/django, requests, urllib.request,
http.server, `subprocess` with `shell=True`, time.time, datetime.now, uuid,
random).

**Result: no forbidden pattern found.** Both files touch only pytest
fixture wiring and monkeypatch/teardown for `subprocess.run` guarding — no
new runtime transport, timer, network, or nondeterminism was introduced.

## 7. Scope compliance

- No new product features added.
- No WebSocket / SSE / polling / timers / background workers introduced.
- No real adapter dispatch (ChatGPT/Claude Code/Codex/Hermes) activated.
- No backend socket server or Next.js API routes added.
- Stage 6.4 event stream and UI state sync contract unchanged — all 34
  Stage 6.4 tests pass unmodified.
- Stage 4/5/6.2/6.3 public contracts unchanged — no production files were
  modified.
- `scos/knowledge` untouched.

## 8. Final regression state

- `scos/control_center/tests`: **367 passed, 0 failed, 0 errors**
- `scos/commercial/tests`: **243 passed, 0 failed**
- Smoke: **PASS**
- Security scan: **PASS** (0 findings)
- Release check: **PASS** (1 informational warning: 2 dirty paths at scan
  time — `conftest.py` and `test_command_runner.py`, i.e. this stage's own
  in-progress fix, report-only and expected)
- Frontend lint: **PASS**
- Frontend build: **PASS**

## 9. Stage 6.6 readiness

- **GO**, pending operator review and explicit approval per the readiness
  gate's Stage 6.6 entry criteria (see
  `docs/specification/STAGE6_EVENT_STREAM_READINESS_GATE.md`).
- No blockers identified. All required clean-regression, Stage 6.4 event
  stream, durable-state, and frontend static-build checks pass.
- Recommended next stage: Stage 6.6, scoped narrowly per the readiness
  gate's stated non-goals (no WebSocket/SSE/polling/timers/real dispatch
  until a future stage explicitly authorizes them).

## 10. git status --short --untracked-files=all

```
 M conftest.py
 M scos/control_center/tests/test_command_runner.py
?? docs/certification/Stage-6.5-plan.md
?? docs/certification/Stage-6.5-regression-cleanup-report.md
?? docs/specification/STAGE6_EVENT_STREAM_READINESS_GATE.md
```

## 11. git diff --stat

```
 conftest.py                                      |  4 +++
 scos/control_center/tests/test_command_runner.py | 44 ++++++++++++++++++------
 2 files changed, 38 insertions(+), 10 deletions(-)
```

## 12. git diff --name-only

```
conftest.py
scos/control_center/tests/test_command_runner.py
```

## 13. Commit recommendation

**Not recommended by this agent run** — per the task's explicit
instruction, no commit/push/tag/release was performed. The changes are
staged in the working tree only, ready for operator review and manual
commit if approved.

## 14. Would-be commit message

```
fix(control-center): clean Stage 6.5 regression debt and add event stream readiness gate
```
