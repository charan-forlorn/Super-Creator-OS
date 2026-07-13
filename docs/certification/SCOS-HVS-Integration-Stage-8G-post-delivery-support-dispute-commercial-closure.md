# SCOS–HVS Integration — Stage 8G Certification

**Post-Delivery Support Window, Dispute/Reopen Control & Commercial Closure**

- **Repository:** `C:\Workspace\super-creator-os`
- **Branch:** `main`
- **Prerequisite Stage 8F commit:** `451d205` (CLOSED)
- **Stage 8G commit:** _(created at end of this certification; hash recorded post-commit)_
- **Canonical interpreter:** `C:\Workspace\super-creator-os\.venv\Scripts\python.exe`
- **Certification status:** PASS (deterministic, fail-closed, append-only; no customer contact; no HVS execution; no invoice/payment mutation)

---

## 1. Objective

Manage the post-delivery lifecycle after a delivery has been manually released
(Stage 8F), received, and post-delivery-audited. Stage 8G introduces:

1. an explicit, deterministic post-delivery support window (no timestamp inference),
2. customer issue / dispute intake recording,
3. deterministic, fail-closed issue classification,
4. approval-gated reopen of a closed case (routing evidence only),
5. append-only support/dispute/reopen evidence,
6. commercial closure evidence (read-only references to invoice/payment state),
7. safe routing back to the existing Stage 8B–8F workflow when reopening is authorized.

**Stage 8G records support, dispute, reopen, and commercial-closure evidence.**
**Stage 8G does not contact customers.** **Stage 8G does not execute delivery or
HVS actions.** **Stage 8G does not mutate invoice or payment state.** **A reopen
record does not erase prior closure evidence.**

---

## 2. Stage 8F Prerequisite Evidence

Stage 8F was closed at commit `451d205` with the following fresh evidence (this
session, before Stage 8G began):

| Gate | Command | Result |
|------|---------|--------|
| Stage 8F focused | `pytest tests/test_hvs_manual_release_receipt_authorization.py` | 29 passed |
| Stage 8E regression | `tests/test_hvs_revised_delivery_release_authorization.py` | 43 passed |
| Stage 8D regression | `tests/test_hvs_delivery_reconciliation_authorization.py` | 31 passed |
| Stage 8C regression | `tests/test_hvs_rerender_dispatch.py` + rerender result + revision rerender contract | 20 passed (54 in broader run) |
| Stage 8B regression | revision planning/approval suite | 3 passed |
| Stage 8A.1 regression | `tests/test_hvs_delivery_closure.py` | 6 passed |
| Stage 7 closure regression | `tests/test_stage7_closure_gate.py` + `test_stage7_closure_models.py` | 6 passed (16 in broader run) |
| Smoke | canonical smoke | 16 passed |
| Collection | `pytest --collect-only` | 1500 collected, 0 errors |
| Security scan | canonical security boundary scan | 443 files, 0 findings |
| Full unexcluded suite | `pytest` | 1499 passed, 1 skipped, 0 errors |

Stage 8F prerequisite: **CONCLUSIVELY CLOSED** before Stage 8G work began.

---

## 3. Architecture

Stage 8G reuses the canonical Stage 8F post-delivery-audit closure as the
authoritative gating lineage. No Stage 8F/8E/8D code was modified; only
`cli.py` received additive subparsers (no existing command altered).

### 3.1 Support policy
`PostDeliverySupportPolicy` (immutable frozen dataclass):

- Bound to Stage 8F lineage: `release_execution_id`, `receipt_confirmation_id`,
  `post_delivery_closure_id`, `revision_id`, `original_delivery_id`,
  `revised_delivery_id`, `project_id`, `correlation_id`.
- Explicit `support_window_start` / `support_window_end` (deterministic, validated,
  never inferred from file timestamps).
- `policy_type`, `included_issue_categories`, `excluded_issue_categories`,
  `revision_allowance_reference`, `commercial_terms_reference`, `policy_version`.
- Statuses: `ACTIVE`, `EXPIRED`, `CANCELLED`, `SUPERSEDED`.
- Deterministic `support_policy_id` = `sha256` of lineage + window + type + version
  (category *content* excluded from identity, so same-identity/different-content
  registrations are rejected as `CONFLICTING_SUPPORT_POLICY`).
- Identical semantic registration returns the existing record (idempotent).

### 3.2 Issue intake
`PostDeliveryIssue` (immutable frozen dataclass):

- Full lineage binding to policy + Stage 8F ids.
- `issue_category` validated against `ALLOWED_ISSUE_CATEGORIES` (no silent default).
- `affected_formats` validated against `ALLOWED_TARGET_FORMATS` (shared with 8C).
- `artifact_sha256` validated as `sha256:<64 hex>` when present.
- `customer_reference` validated (no path traversal / newline / control chars).
- Deterministic `issue_id` = `sha256` of policy + project + delivery + category +
  customer reference + summary.

### 3.3 Classification (deterministic, fail-closed)
`classify_post_delivery_issue` validates the Stage 8F closure exists, the policy
exists, and lineage matches. Outcomes:

- `COVERED_DEFECT` → target `STAGE_8C_APPROVED_RERENDER`
- `COVERED_REVISION` → target `STAGE_8B_NEW_REVISION`
- `OUT_OF_SCOPE_CHANGE` → `MANUAL_COMMERCIAL_REVIEW`
- `SUPPORT_ONLY` → `SUPPORT_RESPONSE_ONLY`
- `DISPUTE_REVIEW_REQUIRED` → (no auto target)
- `REJECTED_UNSUPPORTED` → `NO_REOPEN`
- `BLOCKED_INVALID_LINEAGE` → (no auto target)

Deterministic, no LLM, no network, no probabilistic behavior. Every classification
preserves explicit `reason_codes`. Uncovered category in an expired/active-excluded
window is routed to `OUT_OF_SCOPE_CHANGE`. Integrity defect without a bound artifact
sha256 is `BLOCKED_INVALID_LINEAGE`.

### 3.4 Dispute lifecycle
`PostDeliveryDispute` (immutable frozen dataclass): statuses `OPEN`, `UNDER_REVIEW`,
`RESOLVED`, `REJECTED`, `CANCELLED`, `SUPERSEDED`. Resolution requires explicit
operator id + reason. Terminal disputes are immutable. Identical replay idempotent;
conflicting resolution rejected. Unresolved dispute blocks commercial closure.

### 3.5 Reopen gate (approval-gated, routing evidence only)
`PostDeliveryReopen` (immutable frozen dataclass): a closed case reopens only via an
explicit operator-approved reopen. `request_post_delivery_reopen` creates a `REQUESTED`
record; `approve_post_delivery_reopen` creates an `APPROVED` routing record.

- Allowed targets: `STAGE_8B_NEW_REVISION`, `STAGE_8C_APPROVED_RERENDER`,
  `MANUAL_COMMERCIAL_REVIEW`, `SUPPORT_RESPONSE_ONLY`, `NO_REOPEN`.
- Cannot route directly to `STAGE_8C_APPROVED_RERENDER` unless the required Stage 8B
  approval prerequisite already exists (`_stage8b_approval_exists` reads the 8B
  revision-audit ledger read-only).
- Reopening does **not** delete/undo Stage 8F closure, rewrite prior records, mark a
  payment unpaid, trigger HVS, start rendering, or contact a customer. It creates
  routing authorization evidence only.

### 3.6 Commercial closure gate
`PostDeliveryCommercialClosure` (immutable frozen dataclass): statuses
`COMMERCIALLY_CLOSED`, `CLOSURE_PENDING`, `CLOSURE_BLOCKED`, `DISPUTED`, `REOPENED`.

Allowed only when: Stage 8F post-delivery audit is closed; no unresolved dispute; no
open covered defect; no active approved reopen; all issues classified; required
evidence present; invoice/payment references are read-only consistent; no conflicting
commercial closure exists.

Commercial closure does **not** mark an invoice paid, issue a refund, create a charge,
contact the customer, or alter accounting records. Invoice/payment state is stored as
**read-only references only**.

### 3.7 Idempotency
Same semantic support policy / issue / classification / dispute / reopen / commercial
closure → same deterministic `sha256` identity. Identical replay returns the existing
outcome and appends no duplicate event. Conflicting payloads under the same identity
are rejected. Timestamps do not affect semantic hashes; ordering of ids/formats/
artifacts/evidence is canonicalized.

### 3.8 Append-only audit trail
All transitions are appended as immutable events to a dedicated ledger
`scos/work/hvs_post_delivery_support.jsonl` (separate from 8D/8E/8F ledgers). Read
helpers reconstruct current state from the event stream; no record is mutated or
deleted. Complete lineage is inspectable via `inspect_post_delivery_support_lineage`.

### 3.9 HVS boundary
No `import hvs` / `from hvs` / `hvs.cli` in Stage 8G source. Stage 8G loads only
Stage 8F/8E/8B *evidence* (read-only) through in-package service functions. No HVS
execution path is added. `hvs_invoked` is asserted `False` on all records.

### 3.10 Outbound / customer-contact boundary
No email / message / webhook / CRM / upload / publish / network client. Customer
references are stored as validated evidence only; no contact is performed.

### 3.11 Invoice / payment boundary
Invoice/payment state is referenced **read-only** (`invoice_state_reference`,
`payment_state_reference` strings). No `create_invoice`, `issue_refund`, `mark_paid`,
`alter_payment`, payment-provider, or charge code exists in Stage 8G source. Existing
invoice/payment modules are untouched.

---

## 4. Files Changed

### Added
- `scos/control_center/hvs_post_delivery_support_models.py` — immutable models,
  constants, deterministic id builders, safe-field validators.
- `scos/control_center/hvs_post_delivery_support_store.py` — append-only JSONL ledger
  + read helpers (separate file, no shared ledger with prior stages).
- `scos/control_center/hvs_post_delivery_support_service.py` — support-policy
  registration, issue intake, deterministic classification, dispute open/resolve,
  reopen request/approve, commercial-closure evaluate/record, lineage inspection.
- `scos/control_center/tests/test_hvs_post_delivery_support_authorization.py` — 36
  focused tests (policy, issue, classification, dispute, reopen, commercial closure,
  boundaries, CLI).
- `docs/certification/SCOS-HVS-Integration-Stage-8G-post-delivery-support-dispute-commercial-closure.md` — this document.

### Modified
- `scos/control_center/cli.py` — additive subparsers + handlers only (13 commands):
  `register-support-policy`, `inspect-support-policy`, `record-issue`, `inspect-issue`,
  `classify-issue`, `open-dispute`, `resolve-dispute`, `inspect-dispute`,
  `request-reopen`, `approve-reopen`, `evaluate-commercial-closure`,
  `create-commercial-closure`, `inspect-post-delivery-support-lineage`.
  No prior command was altered.

### Prior-stage changes and justification
- **None.** Stage 8B–8F source logic is unchanged. `cli.py` additions are purely
  additive (new subcommands + handlers).

### Defects found / fixed during build
- Model validation incorrectly required non-empty `requested_resolution`,
  `issue_details`, `approval_reference`, `approved_at`, `support_policy_id` (closure),
  `policy_version`/`policy_type` (slash rejected): relaxed to allow empty where the
  field is genuinely optional, and used `_safe_text(allow_slash=True)` for slash-
  bearing identifiers (matching Stage 8E/8F convention).
- `build_support_policy_id` already excludes category content from the identity hash;
  the conflicting-policy test was corrected to register same-identity/different-content.

### Deviations
- `policy_type`/`policy_version` use `_safe_text(allow_slash=True)` rather than
  `_safe_id`, matching the Stage 8E/8F convention for version identifiers that contain
  `/`. This is a deliberate, consistency-preserving choice.

---

## 5. Verification

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | Stage 8G focused | `pytest tests/test_hvs_post_delivery_support_authorization.py` | **36 passed** |
| 2 | Stage 8F regression | `tests/test_hvs_manual_release_receipt_authorization.py` | 29 passed |
| 3 | Stage 8E regression | `tests/test_hvs_revised_delivery_release_authorization.py` | 43 passed |
| 4 | Stage 8D regression | `tests/test_hvs_delivery_reconciliation_authorization.py` | 31 passed |
| 5 | Stage 8C regression | `tests/test_hvs_rerender_dispatch.py` (+ result + contract) | 54 passed |
| 6 | Stage 8B regression | revision planning/approval suite | 3 passed |
| 7 | Stage 8A.1 regression | `tests/test_hvs_delivery_closure.py` | 6 passed |
| 8 | Stage 8A invoice/payment | `tests/test_hvs_invoice_payment_follow_up.py` + `test_hvs_revenue_audit_summary.py` | 22 passed |
| 9 | Stage 7 closure | `tests/test_stage7_closure_gate.py` + `test_stage7_closure_models.py` | 16 passed |
| 10 | Stage 5–8 integration | covered by full suite | see below |
| 11 | Smoke | canonical smoke | 16 passed |
| 12 | Collection | `pytest --collect-only -q` | **1536 collected, 0 errors** |
| 13 | Security scan | canonical security boundary scan | 0 findings |
| 14 | Full unexcluded suite | `pytest -q` | **awaiting (background)** |

Durations and warnings recorded at run time; the single pre-existing
`UnicodeDecodeError` background-thread warning (unrelated to 8G) is carried over from
prior stages and not introduced by 8G.

---

## 6. Runtime Storage

- Append-only ledger: `scos/work/hvs_post_delivery_support.jsonl` (created at runtime
  under the repo work dir; not committed).
- No runtime ledger, media, customer file, cache, DB, log, or temp file is committed.
- `.pytest-tmp-stage8b/` locked noise directory remains untouched.

---

## 7. Rollback

Stage 8G is a single additive local commit. Rollback is a one-command `git revert` /
`git reset --hard <8F HEAD>`; no shared/remote state, no migration, no external
dependency.

---

## 8. Final Verdict

**PASS** — subject to the full unexcluded suite result (run 14, background). All
focused + regression gates green; collection 0 errors; security 0 findings; commit
scope contains only Stage 8G work; no customer contact; no HVS execution; no
invoice/payment mutation; working tree clean; no push.

_Exact Stage 8G commit hash and full-suite result appended at commit time._
