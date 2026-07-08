# Operator Approval Persistence & Audit Trail Contract (Stage 6.6)

## Purpose

This contract defines the unified, durable, append-only, tamper-evident
approval and audit ledger introduced in Stage 6.6. It is the single place
where operator approve/deny decisions for every approvable subject are
persisted and where the chronological audit trail that proves those
decisions were not altered lives.

It binds Stage 6.6 implementation and is subordinate to
`docs/specification/STAGE6_SCOPE_BOUNDARY.md` and
`docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md`. It authorizes no
implementation by itself; each required module derives from this document.

## Subject domains covered

Every approvable action in the Control Center resolves to one
`(subject_type, subject_id)` pair. The ledger is domain-agnostic; the
following subject types are in scope:

- `command` — a Control Center command draft/approval (Stage 5.1).
- `packet` — a prompt/result packet or operator review decision (Stage 5.4/5.5).
- `git_proposal` — a commit/push proposal decision (Stage 5.8).
- `adapter_dispatch` — a per-dispatch adapter activation decision (Stage 6.5,
  future). The ledger is ready for it; Stage 6.6 does not activate any
  adapter.

New subject types may be added without a schema change (the column is free
text constrained only by non-emptiness), provided they remain local-first and
approval-first.

## Decision lifecycle

Every approval decision carries exactly one of:

- `pending` — decision recorded but not yet resolved (awaiting operator).
- `approved` — operator granted execution.
- `denied` — operator refused execution.

`pending` is an explicit, persisted, non-final state — it does not grant
execution. A subject is executably approved only when its latest decision is
`approved`. The latest decision is the one with the greatest chain
`sequence` for that `(subject_type, subject_id)`.

## Data model

### ApprovalDecision (in-memory frozen model)

| field | type | notes |
|---|---|---|
| `decision_id` | `str` | content-derived id, see ID derivation |
| `subject_type` | `str` | one of the domains above; non-empty |
| `subject_id` | `str` | the subject's stable id; non-empty |
| `decision` | `str` | `pending` \| `approved` \| `denied` |
| `decided_by` | `str` | operator identity; non-empty |
| `decided_at` | `str` | caller-supplied timestamp; non-empty |
| `reason` | `str \| None` | free-text rationale |
| `metadata` | `FrozenMap` | string→string; rejects secret keys + URL values |

### AuditEntry (in-memory frozen model)

| field | type | notes |
|---|---|---|
| `entry_id` | `str` | content-derived id, see ID derivation |
| `sequence` | `int` | 1-based, strictly increasing per chain |
| `prev_hash` | `str` | SHA-256 hex of the previous entry; `"0" * 64` for the genesis entry |
| `entry_hash` | `str` | SHA-256 hex of the canonical entry payload (see below) |
| `decision_id` | `str` | the `ApprovalDecision.decision_id` this entry records |
| `subject_type` | `str` | denormalized for query convenience |
| `subject_id` | `str` | denormalized for query convenience |
| `decision` | `str` | denormalized snapshot of the decision value |
| `decided_by` | `str` | denormalized |
| `decided_at` | `str` | denormalized |
| `reason` | `str \| None` | denormalized |
| `metadata_json` | `str` | stable-JSON serialization of metadata |

## Hash-chain design (tamper evidence)

The audit ledger is a SHA-256 hash chain over `AuditEntry` rows in
`sequence` order.

- **Genesis entry** (`sequence == 1`): `prev_hash = "0" * 64`.
- **Subsequent entries**: `prev_hash` equals the `entry_hash` of the entry
  with `sequence - 1`.
- **Entry hash** is `SHA-256(canonical_entry_bytes)` where
  `canonical_entry_bytes` is the UTF-8 encoding of the stable-JSON object:
  ```json
  {
    "sequence": <int>,
    "prev_hash": <str>,
    "decision_id": <str>,
    "subject_type": <str>,
    "subject_id": <str>,
    "decision": <str>,
    "decided_by": <str>,
    "decided_at": <str>,
    "reason": <str|null>,
    "metadata_json": <str>
  }
  ```
  Keys are sorted and values are JSON-escaped deterministically (see
  `stable_json_dumps` in `sqlite_state_schema.py`). The entry's own
  `entry_hash` and `entry_id` are NOT part of the hashed payload — they are
  derived outputs.

- **ID derivation**: `entry_id` and `decision_id` are content-derived short
  digests (first 16 hex chars of a SHA-256 over their respective canonical
  payloads), so identical inputs always produce identical ids (no random
  UUID in deterministic paths).

### Tamper detection

`verify_chain()` replays the persisted rows in `sequence` order and asserts,
for every entry:

1. The first entry's `prev_hash` == `"0" * 64`.
2. Each subsequent entry's `prev_hash` equals the prior entry's recomputed
   `entry_hash`.
3. Each entry's stored `entry_hash` equals the freshly recomputed hash of its
   own canonical payload.

Any mismatch returns `False` (chain broken). This is what the "detect
tampered persisted data" test exercises: a byte is flipped in the stored
database so a stored `entry_hash` or `prev_hash` no longer matches the
recomputed value, and `verify_chain()` returns `False`.

Because entries are append-only and the chain links each entry to its
predecessor, tampering with any historical entry breaks the chain from that
point forward — it cannot be silently rewritten without breaking the link to
the next entry.

## Persistence design

- Storage: the existing Stage 6.3 SQLite WAL store. The audit ledger is a new
  `audit_ledger` table in the same database file
  (`DEFAULT_STATE_DB_RELATIVE_PATH`), sharing the established WAL PRAGMAs and
  parameterized-query discipline from `sqlite_state_store.py`.
- Schema versioning: `SQLITE_STATE_SCHEMA_VERSION` is bumped to `2` and the
  `audit_ledger` table + indexes are added via the existing
  `get_schema_statements` / `get_index_statements` mechanism. Existing tables
  are unchanged (`CREATE TABLE IF NOT EXISTS`), so the Stage 6.3 round-trips
  remain valid.
- Append-only: decisions and audit entries are INSERT-only. No UPDATE or
  DELETE is ever issued against `audit_ledger`. Changing a decision is
  expressed by appending a *new* decision (e.g. `pending` → `approved`),
  never by mutating the old row.
- Restart safety: because the data lives in the SQLite WAL file, reopening
  the store and calling `verify_chain()` produces an identical chain. No
  in-memory-only state.
- Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
  network, no server, no socket, no API route, no real AI dispatch.

## Store API (Stage 6.6)

Implemented in `approval_audit_store.py` on top of the
`sqlite_state_schema` helpers:

- `append_decision(*, subject_type, subject_id, decision, decided_by,
  decided_at, reason=None, metadata=None, repo_root, db_path=None)`
  → `ApprovalDecision`: persists the decision and its audit entry as one
  atomic transaction; returns the frozen model.
- `append_audit_entry(*, decision, repo_root, db_path=None)` → `AuditEntry`:
  low-level append of a single audit entry for an already-built decision.
- `load_decisions(*, subject_type=None, subject_id=None, repo_root,
  db_path=None)` → `tuple[ApprovalDecision, ...]`: returns all decisions,
  optionally filtered. Callers derive "latest decision" by `sequence`.
- `verify_chain(*, repo_root, db_path=None)` → `bool`: replays persisted
  entries and returns `True` iff the hash chain is intact.
- `latest_decision(*, subject_type, subject_id, repo_root, db_path=None)` →
  `ApprovalDecision | None`: convenience helper returning the highest-sequence
  decision for a subject, or `None`.

## Safety / boundary preservation

- No approvable subject is considered granted unless its `latest_decision`
  is `approved`. A `denied` or `pending` latest decision blocks execution;
  tests assert this.
- Timestamps (`decided_at`) are always supplied by the caller — the store
  never reads a clock.
- No nondeterministic identifiers (no `uuid`, no `random`, no `Date.now`) in
  any path.
- `metadata` flows through `FrozenMap`, which rejects secret-bearing keys
  (`api_key`, `token`, `secret`, `password`, `private_key`) and URL values —
  so no secret can enter the ledger.
- Parameterized SQL only; no string-concatenated SQL.
- The store never starts a server, opens a port, or dispatches AI work.

## Non-goals (out of scope for Stage 6.6)

- No real-time transport, no WebSocket/SSE/polling/timers.
- No adapter activation or real AI dispatch (separate, gated concern).
- No new network ports, no Next.js/socket/API routes.
- No changes to Stage 4/5 public contracts.
- No UI surface in `apps/control-center/` (deferred; ledger is backend-only).

## Stage 6.7 Integration — Execution-Grant Enforcement (additive)

Stage 6.7 wires the Stage 6.6 ledger into the operator approval gate and the
command executor. It adds **no new schema, no new API, and no new
dependency**; it only changes who calls `append_decision` and who calls
`is_execution_granted`.

### Write ownership — approval gate only

`operator_approval.py` is the SOLE writer of command approval-audit rows.

- `approve_command(...)` and `reject_command(...)` accept optional
  `repo_root` / `db_path`. When `repo_root` is provided they call
  `append_decision(subject_type="command", subject_id=<command id>, ...)`,
  persisting the decision exactly once, at the gate.
- When `repo_root` is omitted the behavior is unchanged from pre-6.7
  (in-memory only, no persistence) — existing callers/tests are unaffected.
- The executor (`command_runner.py`) NEVER calls `append_decision`. This
  guarantees no double persistence.

### Read / enforcement ownership — command executor

`command_runner.py` is the enforcement reader. `run_approved_command(...)`
gains an opt-in `enforce_audit_grant: bool = False` flag (and optional
`audit_repo_root` / `audit_db_path`). When `enforce_audit_grant=True`:

1. It calls `verify_chain(...)` first. A broken chain blocks execution with a
   deterministic `blocked` result (reason: `"audit ledger tamper detected:
   hash chain invalid"`). **The chain is consulted, not just the latest
   decision** — so a tampered `decision` column that still passes
   `latest_decision` shape checks is caught.
2. It calls `is_execution_granted(subject_type="command",
   subject_id=<command id>, ...)`. Only a latest `approved` decision with an
   intact chain grants execution. `denied`, `pending`, missing, or tampered
   states block execution (deterministic `blocked` result).
3. There is no bypass flag, no auto-approve, and no silent fallback to
   in-memory approval. The ledger is the single execution-grant source.

The flag defaults to `False` so pre-6.7 callers that do not wire a ledger are
completely unchanged (backward compatibility preserved).

### subject_type / subject_id mapping

- `subject_type` is always `"command"`.
- `subject_id` is the command's `command_id` — the same id on
  `CommandDraft`, `OperatorApproval`, `ApprovedCommand`, and the ledger row.
  The gate writes with `approval.command_id`; the runner reads with
  `approved_command.command_id`. They match by construction.

### Denial / pending / tamper blocking behavior

- `denied` latest → blocked.
- `pending` latest (or no decision) → blocked.
- broken hash chain → blocked regardless of decision value.
- A persisted denial survives a new store instance (reopen) and still blocks.

