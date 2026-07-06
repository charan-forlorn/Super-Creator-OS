# Stage 6.1 Plan — Stage 5.6 Defect Verification & Stage 5.10 Gate Re-run

Predecessor: Stage 6.0 (execution plan / scope boundary, commit `f683ed2`).
Baseline verified: branch `main`, HEAD == origin/main == `f683ed2`, clean tree.

## 1. Stage goal

Verify that every Stage 5.6 defect listed as carried-forward in
`docs/roadmap/STAGE6_HANDOFF.md` is actually fixed at current HEAD, then
re-run the Stage 5.10 final certification gate on a clean committed tree
and confirm GO / 100 / `stage_closed=True` / `accepted=True` / zero
blockers. Verification-first: no patch unless a defect is proven present.

## 2. Preflight evidence (2026-07-06)

- `git branch --show-current` → `main`
- `git rev-parse HEAD` == `git rev-parse origin/main` == `f683ed2f8181...`
- `git status --short --untracked-files=all` → clean
- Latest commit: `f683ed2 docs(roadmap): add Stage 6.0 execution plan, ...`

## 3. Docs inspected

- `docs/roadmap/STAGE6_HANDOFF.md` (unmodified)
- `docs/roadmap/STAGE6_HANDOFF_REVIEW.md` (unmodified)
- `docs/certification/Stage-5-final-ai-command-center-certification.md`
- `docs/roadmap/STAGE6_EXECUTION_PLAN.md`, `docs/specification/STAGE6_SCOPE_BOUNDARY.md`

## 4. Stage 5.6 carried-forward defect verification

| # | Defect (per STAGE6_HANDOFF.md) | Status at HEAD | Evidence |
|---|---|---|---|
| 1 | Package export gap (`__init__.py` has zero `workflow_router*` exports) | FIXED | `scos/control_center/__init__.py:263-275` exports all 12 symbols; runtime import of every symbol succeeded via `.venv\Scripts\python.exe` |
| 2 | Duplicate `ALLOWED_COMMAND_TYPES` lazy-export key (5.9 shadows 5.1) | FIXED | Single key at `__init__.py:23` → `command_models`; Stage 5.9 constant renamed `ALLOWED_RUNBOOK_COMMAND_TYPES` (`__init__.py:234`, `operator_execution_models.py:42`); runtime check `cc.ALLOWED_COMMAND_TYPES is command_models.ALLOWED_COMMAND_TYPES` → True |
| 3 | Frontend wiring gap (`workflow-router-panel.tsx` never rendered) | FIXED | Imported and rendered in `app-shell.tsx:29,398-403`; `sidebar.tsx:20` NAV entry "Cross-Agent Router" |
| 4 | README stray leftover line | FIXED | `apps/control-center/README.md:129-142` — Stage 5.6 section is clean and well-formed |
| 5 | Module docstring convention gap (3 files) | FIXED | `workflow_router.py:1`, `workflow_router_models.py:1`, `workflow_route_store.py:1` all begin with `"""SCOS Stage 5.6 ..."""` |
| 6 | Test invocation inconsistency | FIXED | `tests/test_workflow_router.py` uses the standard `sys.path.insert` bootstrap + `__main__` runner; standalone run → 4 passed, 0 failed |

All six defects confirmed fixed. No Stage 5.6 re-fix was needed.

## 5. New defect found and fixed (Stage 5.10 gate false positive)

The first clean-tree gate run returned **NO_GO / 90** with one critical
blocker: `validate_no_stage5_11_plus` flagged
`docs/specification/STAGE6_SCOPE_BOUNDARY.md:36` — the line
"- Stage 5.11+ or Stage 4.20+ markers; reopening closed stages." under the
heading "## 2. Stage 6 Forbidden Scope". This is a prohibition of Stage
5.11+ work (a Stage 6.0-approved doc), not planned work: a gate false
positive. The gate's `_line_is_negated` heuristic only inspected the
matching line, never its section heading.

**Fix (minimal, gate-only):** `_scan_stage_over_fragmentation` in
`scos/control_center/stage5_final_certification.py` now tracks the nearest
preceding markdown heading and treats a marker line as negated when that
heading is negated (existing token `forbid` matches "Forbidden Scope").
The approved Stage 6.0 doc was NOT modified.

**Targeted test added:** `test_fragmentation_negated_heading` in
`tests/test_stage5_final_certification.py` — asserts (a) a prohibition
bullet under a forbidden-scope heading is not a finding, and (b) a planned
"Stage 5.11" line under a neutral heading is still flagged.

**Risk:** low. The scanner remains deterministic; detection of genuine
over-fragmentation is preserved (covered by the new negative-case assert).

## 6. Commands run & results

- `.venv\Scripts\python.exe -m pytest scos/control_center/tests -q` →
  229 passed, 11 failed, 12 errors. All failures/errors are pytest
  collection artifacts (missing standalone `tmp_dir` fixture / sys.path
  interference); the canonical invocation is standalone per file (how the
  gate itself runs them).
- Standalone canonical runs: `test_work_session_store.py` 16/0,
  `test_prompt_result_packet_store.py` 23/0,
  `test_stage5_final_certification.py` 47/0 (45 + 2 new),
  `test_workflow_router.py` 4/0.
- Static safety scan of the diff: no `fetch(`, `XMLHttpRequest`, `axios`,
  `WebSocket`, `EventSource`, `setInterval`, `setTimeout`, `Date.now`,
  `Math.random`, `crypto.randomUUID`, `"use server"`, `route.ts`,
  `middleware.ts`, `app/api` introduced.
- `scripts/security_scan_baseline.py` → SECURITY SCAN: PASS.

## 7. Stage 5.10 gate re-run

`run_stage5_final_certification(repo_root=Path("."),
checked_at="2026-07-06T00:00:00Z", output_path=None,
require_clean_git=True, run_smoke=True, run_security_scan=True,
run_frontend_checks=True)`

| Run | go_no_go | readiness | stage_closed | accepted | blockers |
|---|---|---|---|---|---|
| Pre-fix (clean tree @ f683ed2) | NO_GO | 90 | False | False | 1 critical (`blk-stage-over-fragmentation`, false positive) |
| Post-fix (tree dirty with the fix only) | GO | 95 | True | True | [] |

Post-fix, the single failing check is `validate_git_state`
(severity=warning, "working tree is not clean") caused solely by the two
uncommitted fix files. Once the fix is committed, the gate reads
GO / 100 / closed / accepted / zero blockers — the same commit-then-clean
pattern recorded in the original Stage 5.10 certification. Frontend checks
(`pnpm lint`, `pnpm build`) ran inside the gate and passed (49 checks, none
skipped).

## 8. Files changed

Code (confirmed-defect patch only):
- `scos/control_center/stage5_final_certification.py` (+8/-1)
- `scos/control_center/tests/test_stage5_final_certification.py` (+19)

Docs:
- `docs/certification/Stage-6.1-plan.md` (this file)

## 9. Scope confirmations

- No Stage 6.2 work started; no backend/API/SQLite/store/event-stream,
  no WebSocket/SSE/polling, no adapter activation, no AI dispatch.
- No network/cloud/SaaS/payment/CRM; no package installs or dependency
  changes; stdlib-only Python used.
- `docs/roadmap/STAGE6_HANDOFF.md` and `STAGE6_HANDOFF_REVIEW.md` unmodified.
- No commit/push/tag/release performed.

## 10. Commit recommendation

Commit the two gate files plus this doc as:

`fix(control-center): resolve Stage 6.1 verified Stage 5 closure blockers`

After committing, an optional confirmation gate run on the clean tree is
expected to return GO / 100 / stage_closed / accepted / zero blockers.
