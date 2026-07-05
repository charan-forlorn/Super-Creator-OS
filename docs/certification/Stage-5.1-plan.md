# Stage 5.1 — Local Control Center Command Bridge (Plan)

## Stage goal

Create the first local-first bridge between the SCOS Control Center concept
and the local SCOS command system, answering:

> Can an operator create a safe local command draft, validate it, approve it,
> queue it, run only allowed local commands, and record deterministic
> command/result events?

Stage 4 is closed (Stage 4.19 final release gate). No Stage 4.20+ is created.

## Preflight

Run and require ALL of:

```
git fetch origin
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/main
git branch --show-current
git log --oneline -12
```

- current branch is `main`
- `HEAD == origin/main`
- working tree clean
- latest history includes the Stage 4.19 final release gate

If preflight fails: stop, report, change nothing.

## Implementation scope

- New stdlib-only package `scos/control_center/` implementing:
  `CommandDraft -> validation -> operator approval -> ApprovedCommand ->
  JSONL queue -> allowlisted runner -> CommandResult -> JSONL event log`.
- Six allowlisted command types only: `RUN_SMOKE_CHECK`, `RUN_RELEASE_CHECK`,
  `RUN_SECURITY_SCAN`, `RUN_STAGE4_FINAL_GATE`, `OPEN_STAGE5_HANDOFF`,
  `GENERATE_STATUS_SNAPSHOT`.
- Contracts: `CONTROL_CENTER_COMMAND_BRIDGE_CONTRACT.md`,
  `CONTROL_CENTER_EVENT_LOG_CONTRACT.md`,
  `OPERATOR_APPROVAL_GATE_CONTRACT.md` (aligned with the Stage 4.18
  `CONTROL_CENTER_COMMAND_API_DESIGN.md`).
- Optional static mock UI panels in `apps/control-center` (draft panel,
  approval panel, event log) using deterministic mock data only.

## Allowed files

Create only:

- `scos/control_center/__init__.py`, `command_models.py`,
  `command_validation.py`, `operator_approval.py`, `command_queue.py`,
  `event_log.py`, `command_runner.py`
- `scos/control_center/tests/test_command_models.py`,
  `test_command_validation.py`, `test_operator_approval.py`,
  `test_command_queue.py`, `test_event_log.py`, `test_command_runner.py`
- `docs/specification/CONTROL_CENTER_COMMAND_BRIDGE_CONTRACT.md`,
  `CONTROL_CENTER_EVENT_LOG_CONTRACT.md`,
  `OPERATOR_APPROVAL_GATE_CONTRACT.md`
- `docs/certification/Stage-5.1-plan.md`

Frontend (only because `apps/control-center` exists): create
`lib/command-types.ts`, `lib/command-mock-data.ts`,
`components/command-draft-panel.tsx`, `components/operator-approval-panel.tsx`,
`components/command-event-log.tsx`; modify `components/app-shell.tsx`,
`components/sidebar.tsx`, `README.md` for wiring only.

## Hard constraints (non-negotiable)

- Python stdlib only; local-first only; deterministic outputs only.
- No network/cloud, no backend/API server, no database/SQLite, no WebSocket,
  no polling, no real agent dispatch, no CRM/payment/billing/invoice, no
  SaaS/customer portal, no email/LINE/message sending, no LLM calls.
- No Certified Core changes, no `scos/knowledge` changes, no Stage 4 public
  contract changes, no mutation of existing Stage 4 artifacts (including
  `scripts/test_release.py`).
- No clock/random/uuid in Stage 5.1 modules; all ids SHA-256 content-derived.
- Runner: never `shell=True`; list-args subprocess only; finite deterministic
  timeout; `dry_run=True` never spawns a subprocess; read-only git only.
- Frontend: no backend calls, no fetch/XHR, no storage, no `Date.now()` /
  `Math.random()` / `crypto.randomUUID()`, no new dependencies, no real
  command execution from UI — static deterministic mock data only.
- No commit / push / tag / release. Implement, test, report, stop.

## Required test commands

```
.venv\Scripts\python.exe scos\control_center\tests\test_command_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_validation.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_approval.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_queue.py
.venv\Scripts\python.exe scos\control_center\tests\test_event_log.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_runner.py
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
.venv\Scripts\python.exe scripts\test_release.py
```

If frontend files changed, from `apps/control-center`:

```
npm run lint
npm run build
```

Note: `scripts/test_release.py` uses a hardcoded step list and is a Stage 4
artifact, so Stage 5.1 tests are NOT registered there in this stage;
registration is a recommended Stage 5.2+ follow-up.

## Completion report template

- Verdict: PASS / FAIL
- Files created / modified (exact list)
- Commands run + results (per-test pass/fail counts)
- Skipped tests + reason
- Confirmations: no backend/API/database/WebSocket/network; no Stage 4
  contract changes; no real agent dispatch; no commit/push/tag/release
- Recommended commit command (only if all gates pass; not executed)
