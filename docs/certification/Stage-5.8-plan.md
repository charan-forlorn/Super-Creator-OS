# Stage 5.8 - Git Commit / Push Approval Gate

## Stage Goal

Create a deterministic, local-only approval/proposal layer that turns an
approved AI result / operator evidence into a `CommitProposal` and, once an
operator approves it, a `PushProposal` — recording every decision in an
append-only JSONL event log and producing only inert manual-command
guidance text. AI never commits or pushes; only the operator, acting outside
SCOS, ever runs the real `git` commands.

## Scope

- Backend models, evidence-snapshot builder, proposal/decision builder, and
  JSONL store under `scos/control_center/`.
- Plain executable tests under `scos/control_center/tests/`.
- Contract docs under `docs/specification/`.
- Static Control Center UI mock under `apps/control-center/`.

## Non-goals

No real git execution (`git add`/`commit`/`push`/`tag`/`stash`/`reset`/
`rebase`/`merge`/`clean`/`checkout`), no subprocess, no GitHub API, no
network, no browser/GUI/clipboard automation, no backend server, no API
routes, no database, no WebSocket, no polling, no timers, no background
workers, no Certified Core changes, no Stage 4 public contract changes, no
`scos/knowledge` implementation changes, no Stage 5.1-5.7 public contract
breaks.

## Files Created

- `scos/control_center/git_approval_models.py`
- `scos/control_center/git_evidence_snapshot.py`
- `scos/control_center/git_approval_builder.py`
- `scos/control_center/git_approval_store.py`
- `scos/control_center/tests/test_git_approval_models.py`
- `scos/control_center/tests/test_git_evidence_snapshot.py`
- `scos/control_center/tests/test_git_approval_builder.py`
- `scos/control_center/tests/test_git_approval_store.py`
- `docs/specification/GIT_COMMIT_PUSH_APPROVAL_GATE_CONTRACT.md`
- `docs/specification/GIT_EVIDENCE_SNAPSHOT_CONTRACT.md`
- `docs/certification/Stage-5.8-plan.md`
- `apps/control-center/lib/git-approval-types.ts`
- `apps/control-center/lib/git-approval-mock-data.ts`
- `apps/control-center/components/git-approval-panel.tsx`
- `apps/control-center/components/git-evidence-summary-panel.tsx`
- `apps/control-center/components/commit-proposal-card.tsx`
- `apps/control-center/components/push-approval-panel.tsx`
- `apps/control-center/components/git-decision-log-panel.tsx`

## Files Modified

- `scos/control_center/__init__.py`: additive lazy exports only (Stage
  5.1-5.7 exports untouched).
- `apps/control-center/components/app-shell.tsx`: adds the Stage 5.8
  "Commit/Push Gate" section.
- `apps/control-center/components/sidebar.tsx`: adds a "Commit/Push Gate"
  nav item.
- `apps/control-center/README.md`: documents the Stage 5.8 mock UI.

## Architecture Boundary

Stage 5.8 sits after Stage 5.7 (AI Result Intake & ChatGPT Status Update
Loop), Stage 5.5 (Operator Packet Review & Manual Handoff Flow), and Stage
5.1 (Local Control Center Command Bridge):

```
Approved AI result / operator evidence
        -> GitEvidenceSnapshot
        -> CommitProposal
        -> CommitApprovalDecision
        -> PushReadinessSnapshot
        -> PushProposal
        -> PushApprovalDecision
        -> GitApprovalEvent JSONL store
        -> Static Control Center UI
```

Stage 5.8 accepts only a plain string reference to a Stage 5.7
`AIResultIntakeRecord.intake_id` (`source_intake_id`) — it never imports or
mutates Stage 5.1-5.7 models directly, and never touches `scos.commercial`
or `scos.knowledge`.

## Hard Rules

Python stdlib only; local-first only; deterministic outputs only (no clock,
no random, no uuid — every id is a caller-input-derived `sha256` digest and
every timestamp is caller-supplied); no subprocess; no `git add`/`commit`/
`push`/`tag`/`stash`/`reset`/`rebase`/`merge`/`clean`/`checkout` execution;
no GitHub/network API; no browser/GUI/clipboard automation; no backend
server/API routes/database/WebSocket/polling/timers/background workers.

## Tests

Focused Stage 5.8 (plain executable scripts, matching the project's
existing convention — not pytest):

```
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_git_evidence_snapshot.py
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_builder.py
.venv\Scripts\python.exe scos\control_center\tests\test_git_approval_store.py
```

Result: 40 + 24 + 42 + 19 = 125 passed, 0 failed.

`-m pytest scos/control_center/tests` was also attempted per the operator's
request. Pytest *can* collect and pass the four new Stage 5.8 files on
their own (`pytest scos/control_center/tests -k "git_approval or
git_evidence"` -> 41 passed, since pytest counts each `test_N_*` function as
one test rather than each internal `check()` call). Run over the whole
`tests/` directory, pytest reports `202 passed, 12 errors` — the 12 errors
are pre-existing failures in `test_prompt_result_packet_store.py` and
`test_work_session_store.py` (Stage 5.2/5.4) caused by a missing `tmp_dir`
pytest fixture that predates this stage and is outside Stage 5.8's allowed
file list; they are unrelated to any Stage 5.8 change. The project's actual
test-invocation convention remains running each file directly with
`python.exe`.

Stage 5.1-5.7 regression (direct `python.exe` invocation, matching each
file's own convention):

```
.venv\Scripts\python.exe scos\control_center\tests\test_command_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_validation.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_queue.py
.venv\Scripts\python.exe scos\control_center\tests\test_event_log.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_approval.py
.venv\Scripts\python.exe scos\control_center\tests\test_command_runner.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_manager.py
.venv\Scripts\python.exe scos\control_center\tests\test_work_session_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_contracts.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_registry.py
.venv\Scripts\python.exe scos\control_center\tests\test_agent_adapter_simulator.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_builder.py
.venv\Scripts\python.exe scos\control_center\tests\test_prompt_result_packet_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review.py
.venv\Scripts\python.exe scos\control_center\tests\test_operator_packet_review_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_result_intake_models.py
.venv\Scripts\python.exe scos\control_center\tests\test_result_intake_builder.py
.venv\Scripts\python.exe scos\control_center\tests\test_result_intake_store.py
.venv\Scripts\python.exe scos\control_center\tests\test_chatgpt_status_update.py
.venv\Scripts\python.exe scos\control_center\tests\test_project_state_update.py
```

Result: 24+33+21+18+16+36+35+42+16+39+27+24+12+44+47+23+19+21+11+44+48+23+15+14
= 652 passed, 0 failed.

Stage 5.6 (`test_workflow_router_models.py`, `test_workflow_router.py`) is a
pre-existing pytest-style outlier (uses `assert` + absolute
`scos.control_center` imports, no `sys.path.insert` shim) that fails when
run directly (`ModuleNotFoundError: No module named 'scos'`) but passes
under `python -m pytest`: 6 passed, 0 failed. This predates Stage 5.8 and is
unrelated to it (Stage 5.6 was also never wired into the frontend by its
own commit).

Smoke/security/release:

```
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
.venv\Scripts\python.exe scripts\test_release.py
```

Result: smoke 16/16 passed; security scan 0 findings across 65 files
scanned; release check 9 passed, 1 warned (working-tree-dirty report-only
warning listing exactly the 21 Stage 5.8 files created/modified — no
unexpected files), 0 failed.

## Frontend Validation

`pnpm lint` and `pnpm build` both pass cleanly from `apps/control-center`.

## Security Scan

`scripts/security_scan_baseline.py` reports 0 findings (65 files scanned,
same baseline scope as Stage 5.7).

## Static Forbidden Scan

Scanned the Stage 5.8 files created/modified in this task
(`lib/git-approval-types.ts`, `lib/git-approval-mock-data.ts`,
`components/git-approval-panel.tsx`, `components/git-evidence-summary-panel.tsx`,
`components/commit-proposal-card.tsx`, `components/push-approval-panel.tsx`,
`components/git-decision-log-panel.tsx`, `components/app-shell.tsx`,
`components/sidebar.tsx`, `README.md`, and the four Python backend files)
for: `fetch(`, `XMLHttpRequest`, `axios`, `WebSocket`, `EventSource`,
`setInterval`, `setTimeout`, `Date.now`, `Math.random`, `crypto.randomUUID`,
`localStorage`, `sessionStorage`, `navigator.clipboard`, `"use server"`,
`app/api`, `route.ts`, `middleware.ts`, `git push --force`,
`--force-with-lease`, `git tag`, `gh release`, `subprocess`, `os.system`.
One match: `push-approval-panel.tsx` mentions `--force-with-lease` inside an
inert disclaimer sentence ("Force push, `--force-with-lease`, tags, and
releases are never generated by this stage") — descriptive text only, never
passed to an execution layer. No other matches found.

## PASS Criteria

- All Stage 5.8 backend tests pass (125/125).
- All Stage 5.1-5.7 regression tests still pass (636/636 direct + 6/6 via
  pytest for the pre-existing Stage 5.6 outlier) — no public contract
  broken.
- Smoke, security-scan, and release-check baselines pass.
- Frontend lint and build pass; no forbidden runtime pattern present in the
  Stage 5.8 frontend files (aside from one inert disclaimer string).
- Every model enforces its allow-lists, is frozen, and serializes
  deterministically; every builder function returns a model instance or a
  structured `GitApprovalError` (never raises for expected validation
  failures).
- `manual_command` is populated only when `decision == "approved"`, is
  `None` otherwise, and is never executed by any function in this stage.
- `PushProposal.proposed_command` is always exactly `git push origin main`;
  the model layer rejects any other string.

## Known Limitations

- This is a proposal layer only — it never runs a real git command; the
  operator must copy the `manual_command` guidance text and run it
  themselves outside SCOS.
- Push approval depends entirely on caller-supplied `GitEvidenceSnapshot` /
  `PushReadinessSnapshot` facts; Stage 5.8 does not itself run `git status`,
  `git rev-parse`, or `git fetch` — gathering that evidence remains an
  operator or upstream-stage responsibility.
- No GitHub API integration and no live remote monitoring exist yet; a
  future stage would need to add those (still gated by operator approval)
  if automatic remote-state refresh is ever desired.
- The frontend Approve/Reject/Needs Changes and Approve Push controls are
  intentionally fully inert (disabled), a deliberately stricter choice than
  Stage 5.5's local-state-toggle buttons, given this stage's higher blast
  radius.

## Commit Readiness

Ready for operator commit: all Stage 5.8 and Stage 5.1-5.7 tests pass,
smoke/security/release checks pass, frontend lint/build pass, and the
working tree contains exactly the 21 files listed above (no unexpected
dirty paths). AI has not run `git add`, `git commit`, `git push`, `git tag`,
or `gh release` at any point in this task.

## Suggested Commit Message

```
feat(control-center): add Stage 5.8 git approval gate
```

## Next Stage

Two candidates were considered:

- Stage 5.9 — Local Operator Execution Console / Manual Command Runbook
- Stage 5.9 — Git Approval Event Integration with Command Bridge

**Recommended: Stage 5.9 — Local Operator Execution Console / Manual
Command Runbook.** Stage 5.8 already produces precise `manual_command` text
and an event timeline; the highest-value next step is a static, read-only
runbook view that assembles the full sequence of manual commands the
operator needs to run (in order, with the evidence that justified each one)
without adding any execution capability — a pure UX/documentation layer
that keeps the "AI never executes" guarantee intact. Wiring Stage 5.8
events into Stage 5.1's command bridge is also plausible, but that stage
already has an allowlisted runner, so integrating one with the other
without changing the "no auto-execution" invariant would require careful,
separate design work — better done as its own explicitly-scoped stage,
not implemented here.
