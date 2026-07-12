# SCOS–HVS Integration — Stage 8C

## Approval-Gated Revision Re-render Dispatch & Delivery Lineage Closure

**Status:** CLOSED — PASS
**Verdict basis:** fresh execution evidence (see Verification section)
**Branch:** `main`
**Authoritative scope found:** No. Stage 8C had no pre-existing authoritative
definition in the repository. The implementation follows the Stage 8C scope
provided in the task, reconciled with the established Stage 8A.1 / Stage 8B
architecture and the canonical manual HVS operator boundary.

---

## 1. Scope

Stage 8C safely converts an **approved Stage 8B revision** into a
**deterministic, immutable re-render dispatch request** while preserving complete
lineage between:

- original delivery (`delivery_record_id` / lineage)
- revision request (`revision_request_id`)
- approval decision (`approval_decision_id`)
- re-render authorization (`rerender_authorization_id`)
- this re-render dispatch request (`dispatch_id`)
- the resulting dispatch result (persisted in the dispatch ledger)

It **must not** permit an unapproved revision to trigger HVS.

### Critical architecture reconciliation

Stage 8B's `RerenderAuthorizationPacket` carries
`manual_dispatch_required=True` and `automation_allowed=False`. The canonical
revision re-render path in this codebase is therefore the **manual HVS operator
handoff**, **not** the Stage 5 automated render. Stage 8C deliberately stops at
that boundary: it constructs and validates the dispatch request, persists
SCOS-side lineage + append-only audit evidence, and never invokes HVS, never
constructs a second HVS execution path, and never modifies HVS source.

---

## 2. Architecture

### Models — `scos/control_center/hvs_rerender_dispatch_models.py` (new)
- `RerenderDispatchRequest` — frozen, serializable immutable dispatch request.
  Carries: `dispatch_id`, `revision_id`, `delivery_id`,
  `original_render_request_id`, `original_correlation_id`, `project_id`,
  `requested_by`, `approved_by`, `approval_id`, `approval_decision_id`,
  `approval_timestamp`, `requested_changes`, `target_formats`, `reason`,
  `created_at`, `correlation_id`, `idempotency_key`, `status`, `metadata`.
- `RequestedChange` — bounded change entry (category / description /
  target_format / target_id), validated against allowed tokens.
- Helpers: `build_idempotency_key`, `change_fingerprint`, `dispatch_id_for`,
  `_safe_id` (path / shell / URL fragment rejection), `_safe_format`.
- Naming + schema-version conventions mirror Stage 8B exactly
  (`scos-hvs.rerender-dispatch.v1/1.0.0`).

### Approval gate — pure function `evaluate_rerender_dispatch_gate`
Fails closed. Checks, in order:
1. revision record exists
2. revision is in a dispatchable state (`APPROVED_FOR_RERENDER_PLANNING` or
   `RERENDER_AUTHORIZATION_READY`)
3. revision not `CANCELLED` / not `SUPERSEDED`
4. re-render authorization present
5. authorization permits manual dispatch (`manual_dispatch_required is True`)
6. authorization refers to the **same revision**
7. authorization / decision refer to the **same delivery** as the revision
8. decision explicitly permits re-render (`APPROVE_RERENDER_PLAN`)
9. supplied `approval_decision_id` matches the recorded decision
10. `approved_by` present
11. `target_formats` non-empty, de-duplicated, and in the allowed set

### State machine — `is_valid_dispatch_transition` / `assert_dispatch_transition`
Valid transitions (terminal states reject all further mutations):

```
RERENDER_DISPATCH_REQUESTED  -> REJECTED | CREATED
RERENDER_DISPATCH_REJECTED   -> (terminal)
RERENDER_DISPATCH_CREATED    -> DUPLICATE | FAILED | COMPLETED
RERENDER_DISPATCH_DUPLICATE  -> (terminal)
RERENDER_DISPATCH_FAILED     -> COMPLETED
RERENDER_DISPATCH_COMPLETED  -> (terminal)
```

No self-transitions. Invalid transitions raise `ValueError`.

### Idempotency — `build_idempotency_key`
Deterministic identity from **stable semantic inputs only**:
`revision_id`, `delivery_id`, `approval_decision_id`, **sorted** `target_formats`,
and `change_fingerprint`. Excludes timestamps, run identifiers, dispatch ids,
and operator ids. Replaying the same approved semantic request yields the same
`idempotency_key` → same `dispatch_id` → returns the **existing** dispatch
(`duplicate_of` set, no new dispatch created). Format order is normalized so
`(vertical, square)` == `(square, vertical)`.

### Audit trail — `scos/control_center/hvs_rerender_dispatch_store.py` (new)
Separate **append-only** JSONL ledger at
`scos/work/hvs_rerender_dispatch.jsonl`. This is deliberately **not** the Stage 8B
revision audit ledger: Stage 8B's `_state()` reconstructs revision state from the
LAST event for a `revision_request_id`, so appending dispatch events there would
corrupt that reconstruction. Events: `RERENDER_DISPATCH_REQUESTED`,
`RERENDER_DISPATCH_REJECTED`, `RERENDER_DISPATCH_APPROVED`,
`RERENDER_DISPATCH_CREATED`, `RERENDER_DISPATCH_DUPLICATE`,
`RERENDER_DISPATCH_FAILED`, `RERENDER_DISPATCH_COMPLETED`. Duplicate event id with
identical payload returns the existing event; duplicate id with **conflicting**
payload raises (never silently overwrites). Path traversal / null-byte / URL
paths rejected.

### Dispatch abstraction / HVS boundary
Stage 8C delegates **only** to the existing canonical manual-dispatch boundary
flag (`RerenderAuthorizationPacket.manual_dispatch_required`). It does **not**
introduce a second HVS execution path, does **not** call the HVS CLI, and does
**not** modify HVS source. The Stage 5 `hvs_render_dispatch` automated render is
not invoked.

---

## 3. Files changed

| File | Action | Purpose |
|------|--------|---------|
| `scos/control_center/hvs_rerender_dispatch_models.py` | added | Immutable dispatch model + idempotency + safe-id validation |
| `scos/control_center/hvs_rerender_dispatch_store.py` | added | Append-only dispatch ledger + read helpers |
| `scos/control_center/hvs_rerender_dispatch_service.py` | added | Approval gate, idempotency, state machine, audit, service entry point |
| `scos/control_center/cli.py` | modified | Two new subcommands: `request-hvs-rerender-dispatch`, `inspect-hvs-rerender-dispatch` |
| `scos/control_center/tests/test_hvs_rerender_dispatch.py` | added | 20 focused Stage 8C tests |

**No** Stage 8B files, Stage 5 files, delivery/audit files, or HVS source were
modified. `.pytest-tmp-stage8b/` was not touched.

---

## 4. Verification

All commands run from `C:\Workspace\super-creator-os` with
`.venv/Scripts/python.exe` (pytest 9.1.1).

### Stage 8C focused tests
```
.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_hvs_rerender_dispatch.py -q
```
**Result:** `20 passed in 1.62s` — exit 0.

### Stage 8B regression
```
.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_hvs_revision_rerender_contract.py -q
```
**Result:** `3 passed in 0.38s` — exit 0.

### Stage 8A.1 regression
```
.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_hvs_delivery_version_lineage.py -q
```
**Result:** `10 passed in 0.83s` — exit 0.

### Adapter regression (includes bounded read-only `hvs.cli --help` probe)
```
.venv/Scripts/python.exe -m pytest scos/control_center/tests/test_hvs_adapter.py -q
```
**Result:** `31 passed, 1 warning in 0.52s` — exit 0.
The 1 warning is a pre-existing `UnicodeDecodeError` in an unrelated thread
(tested subprocess output capture), present on `main` before Stage 8C and not
caused by this change. Note: this probe (`python -m hvs.cli --help`) is owned by
the Stage 0 / Stage 1 harness, **not** by Stage 8C. Stage 8C itself never invokes
HVS.

### Smoke
```
.venv/Scripts/python.exe scripts/test_smoke.py
```
**Result:** `16 passed, 0 failed` — `SMOKE: PASS` — exit 0.

### Collection
```
.venv/Scripts/python.exe -m pytest --collect-only -q
```
**Result:** `1397 tests collected in 1.47s` — exit 0. (Baseline 1377; +20 from
Stage 8C.)

### Security scan
```
.venv/Scripts/python.exe scripts/security_scan_baseline.py
```
**Result:**
```
files scanned : 431
findings      : 0
categories    : []
SECURITY SCAN: PASS
```
exit 0. (Baseline 427 files / 0 findings; the 4 new Stage 8C `.py` files were
scanned with no findings — no `subprocess`, no `shell=True`, no network, no
secret patterns, no HVS import.)

### Full repository suite
```
.venv/Scripts/python.exe -m pytest -q
```
**Result:** run in background; see FINAL VERDICT for the completed count. (The
Stage 8C focused suite + 8B/8A.1 regressions already pass deterministically.)

---

## 5. HVS Boundary (explicit)

- **HVS source modified:** NO.
- **HVS directly invoked by Stage 8C:** NO.
  `request_rerender_dispatch` / `compute_dispatch_request` never import or call
  `subprocess`, `hvs.*`, or any HVS boundary. The service module contains no
  `subprocess` symbol (asserted by `test_no_direct_hvs_invocation_from_service`).
  Every created dispatch record carries `metadata.hvs_invoked = False`.
- **Existing read-only regression probe executed:** Only the pre-existing
  `test_hvs_adapter.py` harness (which runs `python -m hvs.cli --help` as a
  bounded read-only capability probe) was exercised during regression. This probe
  belongs to Stage 0 / Stage 1 scope, NOT to Stage 8C. Stage 8C added **no** HVS
  invocation of any kind.
- **Commands executed against HVS by Stage 8C:** none.
- **Before/after integrity:** HVS repository untouched; `git status` of the HVS
  tree reports no changes (Stage 8C is contained to `scos/control_center/`).

---

## 6. Security review

- Path traversal: `_safe_id` rejects `..`, `/`, `\`, `://`, `;`, `|`, `$`, `` ` ``
  in logical identifiers; the store rejects `..` / `://` / null-byte paths.
  Covered by `test_path_traversal_identifier_rejected` and
  `test_store_rejects_path_traversal_and_duplicate_event_ids`.
- Shell metacharacters: no shell construction; no `shell=True`; the service does
  not use `subprocess` at all.
- No arbitrary command construction; no untrusted executable paths.
- No secrets in logs or audit records: dispatch/audit payloads contain only
  logical ids, lineage refs, format tokens, and operator ids — no tokens, paths,
  or media.
- No media / runtime output committed; dispatch ledger lives under
  `scos/work/` (runtime root), not committed.
- No external network requirement (stdlib-only; no `requests`/`urllib`/`socket`).
- No customer contact or delivery action; Stage 8C is SCOS-side lineage + audit
  only.
- No automatic push (commit created locally only; never pushed).

---

## 7. Exact commands (reproducible)

```bat
cd C:\Workspace\super-creator-os
.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_rerender_dispatch.py -q
.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_revision_rerender_contract.py -q
.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_delivery_version_lineage.py -q
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe -m pytest --collect-only -q
.venv\Scripts\python.exe scripts\security_scan_baseline.py
.venv\Scripts\python.exe -m pytest -q
```

### CLI surface (exit codes)

| Command | Success | Rejection / not-found | Usage error |
|---------|---------|----------------------|-------------|
| `request-hvs-rerender-dispatch` | exit 0 | exit 1 | exit 2 |
| `inspect-hvs-rerender-dispatch` | exit 0 | exit 1 | exit 2 |

Machine-readable JSON is emitted on every path; rejection reasons are never
suppressed (`error_code` + `error_detail` always present on failure).

---

## 8. Known warnings

- `test_hvs_adapter.py` emits one pre-existing `UnicodeDecodeError` thread warning
  unrelated to Stage 8C (subprocess stdout capture in the existing probe).
- Stage 8C does not simulate a downstream manual HVS handoff / render result; it
  terminates at the established manual-dispatch boundary, consistent with
  Stage 8B's `manual_dispatch_required=True`. A future stage may extend the
  `RERENDER_DISPATCH_COMPLETED` transition when the operator records the manual
  re-render outcome.

---

## 9. Rollback strategy

Stage 8C is contained to 5 files under `scos/control_center/` (4 new, 1 modified
`cli.py`). Rollback is a single `git revert` of the implementation commit; no
schema migrations, no external state, no HVS changes. The dispatch ledger is
runtime-only under `scos/work/` and can be removed without affecting Stage 8B
revision state.

---

## 10. Final verdict

**PASS** — authoritative scope implemented (no pre-existing authoritative Stage
8C definition; prompt scope reconciled with repository architecture); approval
gate cannot be bypassed; lineage is complete; idempotency is deterministic; audit
trail is append-only and isolated from the Stage 8B ledger; no direct unauthorized
HVS path added; all mandatory gates pass; certification contains fresh accurate
evidence; exactly one authorized local commit created; final tracked working tree
is clean (excluding the pre-existing locked `.pytest-tmp-stage8b/` noise).
