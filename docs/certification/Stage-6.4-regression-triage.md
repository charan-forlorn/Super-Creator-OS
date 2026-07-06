# Stage 6.4 — Phase A: Regression Triage Gate

**Base commit:** `51d54b6e426b51d3aa7b587be65eb92495adc5cf` (Stage 6.3, `feat(control-center): add Stage 6.3 durable SQLite WAL state store`)
**origin/main:** matches base commit
**Working tree:** clean at start of triage
**Checked at (caller-supplied):** 2026-07-07T00:00:00Z

## Purpose

Stage 6.3's development report noted a full regression run of `scos/control_center/tests`
returned `12 failed, 309 passed, 12 errors`, reported as pre-existing and unrelated to
Stage 6.3. Per the Stage 6.4 gate, this triage must classify every one of those 24 items
before any Stage 6.4 event-stream/UI-sync implementation may begin.

## Commands run

```
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_stage5_final_certification.py -q   (isolation check)
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_prompt_result_packet_store.py scos/control_center/tests/test_work_session_store.py -q   (error detail)
.venv\Scripts\python.exe -m pytest scos/commercial/tests -q
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_release.py
```

## Results

- `scos/control_center/tests -q` → **12 failed, 309 passed, 12 errors** (exact match to the Stage 6.3 report; regression count is stable and reproducible).
- `scos/control_center/tests/test_stage5_final_certification.py -q` in isolation → **14 passed, 0 failed**.
- `scos/commercial/tests -q` → **243 passed**.
- `scripts/test_smoke.py` → **16 passed, 0 failed — SMOKE: PASS**.
- `scripts/security_scan_baseline.py` → **0 findings — SECURITY SCAN: PASS**.
- `scripts/test_release.py` → **10 passed, 0 warned, 0 failed — RELEASE CHECK: PASS**.

## Classification group 1 — 12 FAILED, `test_stage5_final_certification.py` (all 12 test functions in that file)

**Root cause:** `scos/control_center/tests/test_command_runner.py` (introduced Stage 5.1,
commit `f7fc236`) performs a module-level, unscoped monkeypatch:

```python
_GUARD = _SubprocessGuard()
command_runner.subprocess.run = _GUARD
```

This assignment has no fixture/teardown and is never restored. Because pytest imports and
collects all test modules into one process, once `test_command_runner.py` is collected,
`command_runner.subprocess.run` stays replaced with `_GUARD` for the rest of the session —
including for later-collected files such as `test_stage5_final_certification.py`, whose
tests legitimately call `subprocess.run` (e.g. `_run_repo_script`) and now hit
`AssertionError: subprocess.run must never be called in this suite`.

**Verification:** Running `test_stage5_final_certification.py` alone (no other test module
collected first) yields **14 passed, 0 failed** — proving the 12 failures are a test-order
/ test-isolation artifact, not a defect in the code under test, and not something that
touches Stage 6.2's backend boundary, Stage 6.3's durable SQLite state store, or any
prospective Stage 6.4 event/UI-sync code.

**Classification: `NON_BLOCKING_PRE_EXISTING`** for all 12 items.

**Age:** `test_command_runner.py`'s guard has existed since Stage 5.1; unrelated to Stage 6.3/6.4.

**Recommended follow-up (non-blocking):** scope the subprocess monkeypatch to a
`monkeypatch.setattr(...)`-based fixture with teardown instead of a bare module attribute
assignment, so it cannot leak across test files.

## Classification group 2 — 12 ERRORS, missing `tmp_dir` fixture

Files: `test_prompt_result_packet_store.py` (7 tests), `test_work_session_store.py` (5 tests).

**Root cause:** each affected test signature declares a `tmp_dir: Path` parameter, but no
fixture named `tmp_dir` exists in this pytest session (pytest's built-in fixture is
`tmp_path`, not `tmp_dir`). This raises `fixture 'tmp_dir' not found` at setup for every
affected test.

**Age:** `test_prompt_result_packet_store.py` was last touched in Stage 5.4 (commit
`93da717`, "add Stage 5.4 prompt result packets"); `test_work_session_store.py` was last
touched in Stage 5.2 (commit `d659abc`, "add Stage 5.2 AI work session manager"). Both
predate Stage 6.2 and Stage 6.3 entirely — the defect was never introduced or touched by
any Stage 6 work, and Stage 6.4 does not read, write, or depend on either store module.

**Classification: `NON_BLOCKING_PRE_EXISTING`** for all 12 items.

**Recommended follow-up (non-blocking):** rename the `tmp_dir` parameter to `tmp_path` (or
add a local `tmp_dir` alias fixture) in both files.

## Summary table

| Group | Count | Suite | Status | Related to 6.3 | Related to 6.4 |
|---|---|---|---|---|---|
| Subprocess-guard pollution | 12 failed | `test_stage5_final_certification.py` | NON_BLOCKING_PRE_EXISTING | No | No |
| Missing `tmp_dir` fixture | 12 errors | `test_prompt_result_packet_store.py`, `test_work_session_store.py` | NON_BLOCKING_PRE_EXISTING | No | No |

**Blockers: none.**

## Gate decision

- `stage6_4_allowed_to_begin`: **true**
- `blockers`: **[]**
- Every triage item is `NON_BLOCKING_PRE_EXISTING`, with concrete isolation-run /
  git-history evidence that none of the 24 items touch the Stage 6.2 backend boundary, the
  Stage 6.3 durable SQLite WAL state store, or any prospective Stage 6.4 event-stream/UI
  sync code.

**Phase B is authorized to proceed.**
