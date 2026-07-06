# Stage 5.9 - Local Operator Execution Console / Manual Command Runbook

## Stage Goal

Create a local-only Operator Execution Console and Manual Command Runbook
layer that transforms an approved Stage 5.8 `manual_command` /
`proposed_command` into a safe, checklist-driven operator runbook, captures the
operator's pasted-back result, classifies the outcome, and preserves
deterministic JSONL evidence — with a static Control Center UI mirror.

## Scope

- Immutable models: `RunbookCommandStep`, `ExecutionSafetyCheck`,
  `ManualCommandRunbook`, `CommandExecutionCapture`,
  `OperatorExecutionOutcome`, `OperatorExecutionError`.
- Builder: `create_manual_command_runbook`, `create_git_commit_runbook`,
  `create_git_push_runbook`, `capture_manual_command_result`,
  `classify_operator_execution_outcome`.
- JSONL store: append/load for runbooks, captures, outcomes.
- Static Control Center "Execution Console" section.

## Non-goals

No command execution, terminal emulator, shell integration, clipboard
automation, browser/GUI automation, backend server, real git execution, real
AI dispatch, or any SaaS/cloud/API/network behavior.

## Files Created

- `scos/control_center/operator_execution_models.py`
- `scos/control_center/operator_execution_runbook.py`
- `scos/control_center/operator_execution_store.py`
- `scos/control_center/tests/test_operator_execution_models.py`
- `scos/control_center/tests/test_operator_execution_runbook.py`
- `scos/control_center/tests/test_operator_execution_store.py`
- `apps/control-center/lib/operator-execution-types.ts`
- `apps/control-center/lib/operator-execution-mock-data.ts`
- `apps/control-center/components/operator-execution-console.tsx`
- `apps/control-center/components/manual-command-runbook-panel.tsx`
- `apps/control-center/components/command-result-capture-panel.tsx`
- `apps/control-center/components/runbook-step-card.tsx`
- `apps/control-center/components/execution-safety-checklist.tsx`
- `docs/specification/LOCAL_OPERATOR_EXECUTION_CONSOLE_CONTRACT.md`
- `docs/specification/MANUAL_COMMAND_RUNBOOK_CONTRACT.md`
- `docs/certification/Stage-5.9-plan.md`

## Files Modified

- `scos/control_center/__init__.py` — additive lazy exports only (one Stage 5.9
  block appended to `_LAZY_EXPORTS`; no existing entry changed).
- `apps/control-center/components/sidebar.tsx` — one `NAV_SECTIONS` entry added.
- `apps/control-center/components/app-shell.tsx` — import + one static section.
- `apps/control-center/README.md` — Stage 5.9 section documented.

## Architecture Boundary

```
Stage 5.8 Approval Gate → approved manual/proposed command
  → create_*_runbook → ManualCommandRunbook (safety checks + steps)
  → operator runs MANUALLY outside SCOS
  → capture_manual_command_result → CommandExecutionCapture
  → classify_operator_execution_outcome → OperatorExecutionOutcome
  → operator_execution_store (JSONL) → Control Center UI (static)
```

## Hard Rules

Python stdlib only; local-first; deterministic; no real command/shell/terminal
execution; no subprocess; no clipboard; no browser/GUI automation; no API /
network / database / websocket / polling / timers / background workers; no LLM
calls; no Certified Core or Stage 4 public-contract changes; no
`scos/knowledge` changes; no Stage 5.1–5.8 public-contract breaks; no
commit/push/tag/release.

## Tests

```
.venv\Scripts\python.exe scos\control_center\tests\test_operator_execution_models.py    # 37 passed, 0 failed
.venv\Scripts\python.exe scos\control_center\tests\test_operator_execution_runbook.py   # 36 passed, 0 failed
.venv\Scripts\python.exe scos\control_center\tests\test_operator_execution_store.py     # 15 passed, 0 failed
```

Stage 5.8 regression (exact filenames):

```
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_models.py     # 40 passed, 0 failed
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_builder.py    # 42 passed, 0 failed
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_store.py      # 19 passed, 0 failed
```

## Frontend Validation

```
pnpm lint     # (apps/control-center) clean, exit 0
pnpm build    # (apps/control-center) compiled + type-checked, exit 0
```

## Security Scan

```
.venv\Scripts\python.exe scripts\test_smoke.py                # SMOKE: PASS
.venv\Scripts\python.exe scripts\security_scan_baseline.py    # SECURITY SCAN: PASS
```

Note: `security_scan_baseline.py` scopes to `scos/commercial`, `scripts`, and
root config only; Stage 5.9 `scos/control_center` files are covered by the
manual static scan below.

## Static Forbidden Scan

- Frontend Stage 5.9 files contain none of: `fetch(`, `XMLHttpRequest`,
  `axios`, `WebSocket`, `EventSource`, `setInterval`, `setTimeout`,
  `Date.now`, `Math.random`, `crypto.randomUUID`, `localStorage`,
  `sessionStorage`, `navigator.clipboard`, `"use server"`, `app/api`,
  `route.ts`, `middleware.ts`.
- Backend Stage 5.9 files contain none of: `subprocess.run`,
  `subprocess.Popen`, `os.system`, `pty`, clipboard/terminal automation,
  `requests`, `urllib.request`, `socket`.

## PASS Criteria

All five models exist and serialize deterministically; deterministic sha256
IDs from caller-supplied inputs; caller-supplied timestamps only; no
clock/random/uuid; commit/push runbooks create manual steps only; no command
executed; URL paths and secret metadata rejected; capture supports pasted
output; classifier returns PASS on clear success, BLOCKED/FAIL on clear
failure, NEEDS_REVIEW on vague output; JSONL store writes/loads deterministic
lines and fails on malformed input; frontend displays console/runbook/checklist
/capture and makes the manual boundary obvious; no Stage 4 or Stage 5.1–5.8
contract broken; `scos/knowledge` untouched.

## Known Limitations

- The outcome classifier uses simple, documented substring rules and is not
  tuned to any single tool's output format; ambiguous output intentionally maps
  to `NEEDS_REVIEW`.
- Stage 5.9 does not verify that a referenced Stage 5.8 approval id actually
  exists; source ids are opaque strings supplied by the caller.
- The store performs no cross-record integrity checks (append-only by design).

## Commit Readiness

Implemented, tested, and validated. Not committed and not pushed, per stage
instructions. Working tree contains only the allowed Stage 5.9 files plus the
pre-existing Stage 5.8 modifications present at stage start.

## Suggested Commit Message

```
feat(control-center): add Stage 5.9 local operator execution console
```

## Next Stage

Stage 5.10 — Stage 5 Final AI Command Center Certification.
