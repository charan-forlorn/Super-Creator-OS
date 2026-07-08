# Stage 6.7 Certification Plan — Wire Approval Audit Ledger Into Execution

**Status:** IMPLEMENTED, READY FOR COMMIT (no push)
**Date:** 2026-07-08
**Branch:** main (HEAD == origin/main == e9425be before this stage)
**Mode:** Backend-only safety integration. No UI, no frontend test tier, no network/server/dependency/schema changes.

## Objective

Wire the Stage 6.6 approval-audit ledger into the operator approval gate and
the command executor so that:

> Does every operator approve/reject decision persist to the tamper-evident
> audit ledger, and does command execution block if the persisted ledger does
> not grant execution?

## Scope

- **Modify:** `scos/control_center/operator_approval.py`, `scos/control_center/command_runner.py`.
- **Create:** `scos/control_center/tests/test_approval_audit_integration.py`.
- **Update:** `docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md`.
- **Create (this doc):** `docs/certification/Stage-6.7-plan.md`.
- **Reuse only:** `approval_audit_store.py`, `approval_audit_models.py` (no rewrite).

## Non-Goals

- No UI / `apps/control-center/` changes.
- No new dependency, schema change, network port, server, WebSocket/SSE/polling.
- No real AI adapter activation or dispatch.
- No `local_backend.py` changes (it does not call the runner; enforcement is
  wired at the runner boundary, ready for a later backend caller).
- No Certified Core / Stage 4 / Stage 5 / Stage 6.2–6.6 public-contract breaks.

## Implementation Summary

### 1. Approval persistence (gate is the sole writer)
`approve_command` / `reject_command` gained optional `repo_root` / `db_path`.
When `repo_root` is given, the decision is persisted via
`append_decision(subject_type="command", subject_id=<command id>, ...)` exactly
once, at the gate. `repo_root=None` (default) preserves pre-6.7 in-memory
behavior. `metadata` flows through `FrozenMap` (secrets rejected).

### 2. Execution enforcement (opt-in, ledger is single grant source)
`run_approved_command` gained `enforce_audit_grant: bool = False` (default
unchanged for existing callers) plus `audit_repo_root` / `audit_db_path`. When
enabled it:
1. Calls `verify_chain()` — a broken hash chain blocks execution.
2. Calls `is_execution_granted(subject_type="command", subject_id=<command id>)` —
   only a latest `approved` decision with an intact chain grants.
3. `denied` / `pending` / missing / tampered all block with a deterministic
   `blocked` result. No bypass, no auto-approve, no silent in-memory fallback.

### 3. No double persistence
The executor never calls `append_decision`. The integration test asserts the
ledger row count is unchanged by `run_approved_command`.

### 4. Hash-chain consultation fix (store bug justification)
`is_execution_grant` previously returned a decision's `latest_decision`
**without** verifying the hash chain, so a tampered `decision` column could
"grant". To meet acceptance #3 ("tampered audit evidence must block
execution"), `run_approved_command` now consults `verify_chain()` first. This
is a minimal, justified addition to the read path (no schema/API change).

## Files Changed

- `scos/control_center/operator_approval.py` — +persistence at gate.
- `scos/control_center/command_runner.py` — +opt-in enforcement.
- `scos/control_center/tests/test_approval_audit_integration.py` — NEW.
- `docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md` — +Stage 6.7 section.
- `docs/certification/Stage-6.7-plan.md` — NEW (this document).

## Tests Run (evidence)

| Suite | Result |
|---|---|
| `test_approval_audit_integration.py` | 8 passed |
| `test_approval_audit_models.py` | 10 passed |
| `test_approval_audit_store.py` | 10 passed |
| `test_operator_approval.py` | 5 passed |
| `test_command_runner.py` | 7 passed |
| `scripts/test_smoke.py` | 16 passed, 0 failed (SMOKE: PASS) |
| `scripts/security_scan_baseline.py` | 0 findings (SECURITY: PASS) |
| `scos/control_center/tests/` (full dir) | 395 passed, 0 failed |

### Integration test coverage (acceptance mapping)
- approve persists ledger row + `is_execution_granted` True. ✔
- reject persists denial. ✔
- rejected command blocked by runner. ✔
- missing ledger blocks execution. ✔
- denial survives restart (new store instance) and blocks. ✔
- tampered ledger → `verify_chain` False → blocks execution. ✔
- runner reads ledger but appends no duplicate row. ✔
- existing runner behavior unchanged without enforcement flag. ✔

## Acceptance Criteria Results

1. Every approve/reject persists a ledger row — **PASS**.
2. Approval grant survives restart; `is_execution_granted` True — **PASS**.
3. Denied/pending/missing/tampered blocks `run_approved_command` — **PASS**.
4. `is_execution_granted` is the single enforcement source — **PASS** (chain-checked).
5. No execution if ledger does not grant — **PASS**.
6. No double persistence — **PASS** (test asserts row count unchanged).
7. Existing approval/runner tests still pass — **PASS** (5 + 7).
8. New integration tests pass — **PASS** (8).
9. `test_smoke.py` passes — **PASS**.
10. `security_scan_baseline.py` passes — **PASS** (0 findings).
11. No frontend/backend server/network/dependency/schema changes — **PASS**.
12. This plan records evidence — **PASS**.

## Known Risks

- Enforcement is **opt-in** (`enforce_audit_grant=False` default). Until a
  production caller (e.g. `local_backend`) passes `enforce_audit_grant=True`,
  the gate still persists decisions (audit completeness) but the runner does
  not yet block on them. This is intentional backward compatibility; the wire
  is complete and tested, activation is a separate one-line caller change.
- Untracked directory `pacesuper-creator-os` and `.scos-local-backups/` exist
  in the working tree but are OUTSIDE this stage's scope and must NOT be
  committed.

## Commit Readiness Evidence

- `git status` (pre-commit) shows only the 5 Stage 6.7 files (plus the two
  out-of-scope untracked items above, excluded).
- All required test suites pass (see table).
- Security baseline clean.
- No schema/dependency/network changes.
- READY FOR COMMIT pending operator approval. **No push** (per task rules).
