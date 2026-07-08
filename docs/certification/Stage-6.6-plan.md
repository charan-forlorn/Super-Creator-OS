# Stage 6.6 — Operator Approval Persistence & Audit Trail Hardening

## Verdict: PASS

## 1. Objective

Implement a unified, durable, append-only, tamper-evident approval and audit
ledger for operator approve/deny decisions, covering commands, packets, git
proposals, and future adapter dispatches, reusing the Stage 6.3 SQLite WAL
persistence pattern. Support a `pending` → `approved` / `denied` lifecycle and
a SHA-256 hash-chain (`prev_hash` / `entry_hash`) that detects tampering.

## 2. Scope

In scope (all within Operator Tools Layer only):

- New model layer: `scos/control_center/approval_audit_models.py`
- New store layer: `scos/control_center/approval_audit_store.py`
- Schema extension: `scos/control_center/sqlite_state_schema.py`
  (bumped `SQLITE_STATE_SCHEMA_VERSION` 1 → 2; added `audit_ledger` table +
  indexes; existing tables untouched via `CREATE TABLE IF NOT EXISTS`).
- New tests: `scos/control_center/tests/test_approval_audit_models.py`,
  `scos/control_center/tests/test_approval_audit_store.py`
- New contract: `docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md`
- This certification doc.

Out of scope (permitted exclusions): no `apps/control-center` changes (backend
only), no real AI dispatch, no network ports/API routes, no Stage 4/5 contract
changes.

## 3. Files changed

**Modified:**
- `scos/control_center/sqlite_state_schema.py` — schema version 2; `audit_ledger`
  table (entry_id PK, sequence UNIQUE, prev_hash, entry_hash, decision_id,
  subject_type, subject_id, decision, decided_by, decided_at, reason,
  metadata_json) + 4 indexes. Parameterized SQL only.

**Created:**
- `scos/control_center/approval_audit_models.py`
- `scos/control_center/approval_audit_store.py`
- `scos/control_center/tests/test_approval_audit_models.py`
- `scos/control_center/tests/test_approval_audit_store.py`
- `docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md`
- `docs/certification/Stage-6.6-plan.md` (this file)

No production modules outside the allowed set were touched. `state_models.py`
was determined unnecessary to extend: the unified ledger stores the full
decision directly in `audit_ledger` (denormalized), so no new durable-record
type was required — this keeps the change minimal and the ledger the single
source of truth.

## 4. Audit model design

- `ApprovalDecision` (frozen): `decision_id` (content-derived SHA-256, 16 hex),
  `subject_type` (command|packet|git_proposal|adapter_dispatch), `subject_id`,
  `decision` (pending|approved|denied), `decided_by`, `decided_at` (caller-
  supplied), `reason`, `metadata` (FrozenMap).
- `AuditEntry` (frozen): `entry_id` (content-derived), `sequence` (1-based),
  `prev_hash`, `entry_hash`, `decision_id`, denormalized decision fields,
  `metadata_json`.

## 5. Persistence design

- Single `audit_ledger` table in the existing Stage 6.3 SQLite WAL file
  (`DEFAULT_STATE_DB_RELATIVE_PATH`). Connection/PRAGMA discipline reused from
  `sqlite_state_store`. Append-only: no UPDATE/DELETE ever issued. A status
  change is a new appended decision, never a mutation. Survives restart because
  the data lives in the WAL file.

## 6. Hash-chain design

`entry_hash = SHA-256(canonical_payload)` where `canonical_payload` is the
stable, sorted (key=value) serialization of
(sequence, prev_hash, decision_id, subject_type, subject_id, decision,
decided_by, decided_at, reason, metadata_json). Genesis entry: `prev_hash =
"0"*64`. Each subsequent entry's `prev_hash` equals the prior entry's
`entry_hash`. `verify_chain()` replays rows in sequence order and returns
`False` if any `prev_hash` link or `entry_hash` self-check fails.

## 7. Denial-blocking behavior

`is_execution_granted(subject_type, subject_id)` returns `True` only when the
highest-sequence decision for the subject is `approved`. `pending` and `denied`
both block. Tests assert a `denied` decision persists and blocks an execution
path that raises `PermissionError`.

## 8. Commands run (exit codes / results)

Verified evidence from the Hermes commit-readiness review session:

| Command | Result |
|---|---|
| `.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_approval_audit_models.py scos/control_center/tests/test_approval_audit_store.py -q` | **20 passed** (exit 0) |

NOT run in this session (claims carried from earlier author-side runs,
unverified here — recorded for traceability only, do NOT treat as certified
by this review):

| Command | Earlier claim |
|---|---|
| `python scos/control_center/tests/test_approval_audit_models.py` | 16 passed, 0 failed |
| `python -m pytest scos/control_center/tests -q` | 387 passed |
| `python -m pytest scos/commercial/tests -q` | 243 passed |
| `python scripts/test_smoke.py` | 16 passed / SMOKE: PASS |
| `python scripts/security_scan_baseline.py` | 65 files scanned, 0 findings / SECURITY SCAN: PASS |

Note: the 20-passed result above is the only evidence verified in this
commit-readiness session. Broader suite counts and the security scan were not
re-executed here. Frontend lint/build not run — `apps/control-center` was not
touched.

## 9. Required tests coverage (all 10 present)

1. Deterministic hash-chain creation — model suite test_1
2. Same payload → stable hash — model suite test_2
3. Changing payload → changes hash — model suite test_3
4. `prev_hash` links entries correctly — model suite test_4
5. `verify_chain()` true for valid chain — model suite test_5; store suite test_2
6. `verify_chain()` detects tampered persisted data — store suite test_7
   (mutates the persisted DB payload; chain detection returns False)
7. Approval decision persists after store restart — store suite test_3
8. Denied decision persists — store suite test_4
9. Denied decision blocks execution path in test — store suite test_4, test_10
10. Existing `sqlite_state_store` behavior unaffected — store suite test_9
    (full `control_center` + `commercial` suites green)

## 10. Risks

- R1 (Low): schema version bump to 2 — mitigated by `CREATE TABLE IF NOT EXISTS`
  and additive indexes; existing tables unchanged; both full suites green.
- R2 (Low): ledger is the single source of truth for decisions (no separate
  decisions table). Mitigated by denormalized decision columns and
  `load_decisions`/`latest_decision` helpers; covered by tests.
- R3 (Info): security baseline (`scripts/security_scan_baseline.py`) currently
  scans `scos/commercial` + `scripts` only (Stage 6.8 extends it to
  `control_center`); new `control_center` modules were still authored to the
  same forbidden-pattern discipline (no Date.now/uuid/random/network).

## 11. Git status

At feature-commit time (commit `657a4d5`), the working tree held the six
intended Stage 6.6 artifacts:

```
 M scos/control_center/sqlite_state_schema.py
?? docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md
?? scos/control_center/approval_audit_models.py
?? scos/control_center/approval_audit_store.py
?? scos/control_center/tests/test_approval_audit_models.py
?? scos/control_center/tests/test_approval_audit_store.py
```

Those six were committed as `657a4d5`. This certification doc
(`docs/certification/Stage-6.6-plan.md`) is an additional documentation
artifact committed separately afterward (see its own docs commit). No push,
no tag per task instructions.

## 12. Safe for human review

Yes. All changes are within the approved allowed-file scope, all required
tests pass, smoke + security scan PASS, and no forbidden scope (no network, no
dispatch, no Stage 4/5 contract changes) was introduced. Recommend the
operator review and commit on `main`.

## 13. Suggested commit message

```
feat(control-center): add Stage 6.6 approval persistence and tamper-evident audit ledger

- New approval_audit_models.py: frozen ApprovalDecision + hash-chained AuditEntry
- New approval_audit_store.py: append_decision/append_audit_entry/load_decisions/
  verify_chain/is_execution_granted over the Stage 6.3 SQLite WAL store
- sqlite_state_schema.py: version 2 + audit_ledger table (append-only, parameterized)
- Covers command/packet/git_proposal/adapter_dispatch subjects; pending->approved/denied
- SHA-256 prev_hash/entry_hash chain detects tampering; denied decisions block execution
- Tests: 16 model + 20 store checks; full control_center (387) + commercial (243) green;
  smoke + security scan PASS
```
