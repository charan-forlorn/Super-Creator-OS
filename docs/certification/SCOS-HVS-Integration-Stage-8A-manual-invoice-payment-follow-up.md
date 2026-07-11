# SCOS–HVS Integration Stage 8A — Manual Invoice Preparation & Payment Follow-up Queue

Certification document. Read-only verification and local implementation only. No customer contact, no network, no HVS modification, no invoice transmission, no payment processing.

## 0. Objective

Convert completed, verified manual-delivery closures into operator-controlled invoice-preparation and payment-follow-up work. The system helps the operator identify deliverables ready for invoicing, prepare structured draft invoice data, track payment-pending/follow-up/overdue/disputed/cancelled/paid states, and maintain an append-only audit history. It never sends invoices, messages, or payment links automatically, and never marks payment as paid without explicit operator action.

## 1. Baseline

| Field | Value |
|-------|-------|
| SCOS root | `C:/Workspace/super-creator-os` |
| Branch | `main` |
| Starting (Stage 8A) HEAD | `5af565acb047e77afc14440a21f48764d9e3ca13` (Stage 7 feature commit) |
| Stage 7 feature commit | `5af565a` (delivery closure audit) |
| Stage 7 certification | `docs/certification/SCOS-HVS-integration-stage-7-delivery-closure.md` |
| Initial Git status | clean (before Stage 8A work) |
| Test collection | 1363 collected, exit 0 |
| Python | 3.11.15 (`.venv`) |

HVS baseline (read-only):

| Field | Value |
|-------|-------|
| HVS root | `C:/Workspace/hermes-video-studio` |
| Branch | `main` |
| Baseline HEAD | `139ce26be838247f4cd4607c2a32989d732d3ac5` |
| Working tree | clean (only `.vscode/settings.json` = PRE_EXISTING_UNRELATED) |

## 2. Business Boundary

Allowed: verified delivery evidence → delivery closure → invoice-preparation eligibility validation → invoice draft record → operator review → ready for manual invoice → operator marks invoice manually sent → payment pending → follow-up queue → operator-confirmed final status.

Prohibited: automatically issue invoice, automatically contact customer, automatically create payment link, automatically mark paid.

## 3. Existing Patterns Reused

- `hvs_delivery_closure_service.get_closure(closure_id, repo_root)` — eligibility source. `Closure` exposes `closure_status`, `accepted_by_customer`, `artifact_sha256`, `delivery_record_id`, `package_id`, `approval_request_id`, `project_id`.
- `hvs_revenue_audit.ALLOWED_CURRENCIES` — reused verbatim for currency validation (no redefinition).
- `hvs_delivery_closure_audit.append_closure_event/read_closure_events` — mirrored by `hvs_invoice_store.append_invoice_event/read_invoice_events` (append-only JSONL).
- `hvs_local_delivery_service._runtime_root(repo_root)` — runtime records under ignored `scos/work/`.
- `cli.py` `_emit`, `_repo_root`, `EXIT_OK/REJECT/USAGE`, `CLI_SCHEMA_VERSION`, `add_parser`+`set_defaults` — mirrored exactly.

## 4. Commercial Contract

Eligibility (PHASE 2): an `InvoicePreparationRecord` may be created only when the source closure `closure_status == "ACCEPTED_AND_CLOSED"` AND `accepted_by_customer is True`. Otherwise `ERR_INELIGIBLE_CLOSURE`. Artifact SHA-256 is re-verified against the source closure.

`commercial_scope_id` (`stable_commercial_scope_id`): deterministic from `customer_id`, `project_id`, `delivery_record_id`, `delivery_closure_id`, `artifact_sha256`, `billing_scope_key`, schema version. No timestamp/UUID/pid/username/path. Prevents duplicate billing for the same delivered work; a separate `billing_scope_key` allows an operator-approved distinct billing scope (documented limitation: revision billing has no repository contract — operator supplies `billing_scope_key`).

Duplicate prevention: `_find_by_scope` rejects a conflicting repeat (different price/line) under the same scope with `ERR_DUPLICATE_COMMERCIAL_SCOPE`; an identical re-submission returns the existing record (idempotent).

## 5. Invoice-Preparation Model

`InvoicePreparationRecord` fields: `schema_version`, `invoice_preparation_id`, `commercial_scope_id`, `source_project_id`, `customer_id`, `source_delivery_record_id`, `source_delivery_closure_id`, `source_approval_request_id`, `source_packet_id`, `source_evidence_id`, `artifact_display_path`, `artifact_sha256`, `currency`, `subtotal`, `tax_amount`, `discount_amount`, `total_amount`, `payment_terms`, `invoice_issue_date`, `due_date`, `follow_up_date`, `status`, `manual_action_required`, `automation_allowed`, `created_by_operator_id`, `created_at`, `content_hash`, `notes`.

`InvoiceLineItem`: `line_item_id`, `description`, `quantity` (Decimal >0), `unit_price` (Decimal ≥0), `amount`, `billing_scope_key`, optional note.

Money: `from decimal import Decimal, ROUND_HALF_UP`. Stored as `str` in JSON. `total_amount = subtotal + tax_amount - discount_amount`. Rounding = ROUND_HALF_UP to currency minor precision. Floats explicitly rejected (`normalize_money` raises on `float`). Tax/discount only when explicitly supplied (default `0`); never inferred. Currency required and validated against `ALLOWED_CURRENCIES`; THB is NOT assumed.

## 6. State Machine

States: `DELIVERY_CONFIRMED, INVOICE_DRAFT_PENDING, READY_FOR_MANUAL_INVOICE, INVOICE_MARKED_SENT, PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE, OVERDUE, DISPUTED, CANCELLED, PAID`.

Transitions (all require operator ID + append-only event):
- `DELIVERY_CONFIRMED → INVOICE_DRAFT_PENDING` (create)
- `INVOICE_DRAFT_PENDING → READY_FOR_MANUAL_INVOICE` (mark ready; complete valid data)
- `READY_FOR_MANUAL_INVOICE → INVOICE_MARKED_SENT → PAYMENT_PENDING` (mark sent; operator_id + sent_date + invoice_number; no network)
- `PAYMENT_PENDING → PAYMENT_FOLLOW_UP_DUE | OVERDUE | DISPUTED | CANCELLED | PAID`
- `PAYMENT_FOLLOW_UP_DUE → OVERDUE | DISPUTED | CANCELLED | PAID`
- `OVERDUE → DISPUTED | CANCELLED | PAID`
- `DISPUTED → PAYMENT_PENDING` (resolve_dispute, resolution note required) | `CANCELLED` (reason) | `PAID` (explicit confirmation + resolution note)
- `PAID` only via explicit operator confirmation (operator_id, paid_date, paid_amount Decimal, currency, payment reference/note). Never automatic.

Operator requirements: CANCELLED requires reason; DISPUTED requires reason; resolve_dispute requires resolution note; mark sent requires operator_id + sent_date + invoice_number; PAID requires operator_id + paid_date + paid_amount + currency + reference/note. Partial payment below total → `PARTIAL_PAYMENT_UNSUPPORTED` (documented limitation; no accounting invented). Currency mismatch on PAID vs record → rejected. Invalid transitions → `ERR_INVALID_TRANSITION`.

## 7. Implementation Files

Created:
- `scos/control_center/hvs_invoice_models.py` — dataclasses, status constants, deterministic ID helpers (`stable_commercial_scope_id`, `stable_invoice_preparation_id`, `stable_line_item_id`), Decimal money helpers (`normalize_money`, `quantize_money`, `money_to_json`), sensitive-data guard (`_reject_sensitive_data`, `SensitiveDataError`).
- `scos/control_center/hvs_invoice_store.py` — append-only JSONL store (`append_invoice_event`, `read_invoice_events`) under `_runtime_root(repo_root)/hvs_invoice_audit.jsonl`; safe-path; idempotent-duplicate + conflict handling; read does not mutate.
- `scos/control_center/hvs_invoice_service.py` — `create_invoice_preparation`, `inspect_invoice_preparation`, `update_invoice_draft`, `mark_invoice_ready`, `mark_invoice_sent`, `inspect_payment_status`, `list_payment_follow_up_queue`, `record_payment_status_decision`, `verify_invoice_source_integrity`. Each returns `InvoiceServiceResult` with `ok`, `error_code`, `to_dict()`.
- `scos/control_center/tests/test_hvs_invoice_payment_follow_up.py` — 17 focused tests covering eligibility, money precision, idempotency/conflict, transitions, queue read behavior, sensitive-data rejection, CLI JSON.

Modified:
- `scos/control_center/cli.py` — 7 subcommands: `create-hvs-invoice-preparation`, `inspect-hvs-invoice-preparation`, `mark-hvs-invoice-ready`, `mark-hvs-invoice-sent`, `list-hvs-payment-follow-ups`, `record-hvs-payment-status`, `inspect-hvs-payment-status`. Structured JSON, explicit `automation_allowed:false`, `manual_action_required`, `permitted_next_actions`, `invoice_not_sent` where relevant; exit 0 valid, non-zero invalid.

No HVS, renderer, Stage 5/6/7 semantics, frontend, payment/accounting integration, dependencies, or lock files changed. Scanner allow-list unchanged (Stage 8A uses no subprocess).

## 8. Sensitive-Data Guard (PHASE 8)

`_reject_sensitive_data(*fields)` raises `SensitiveDataError(category)` (generic category only, value NOT logged) for patterns: full card number, CVV/CVC, online-banking password, access token, API key, account password, seed phrase, private key. Legitimate non-sensitive values (invoice number, bank transfer receipt reference, transaction reference, PO number, short operator note) are accepted.

## 9. Acceptance Evidence (local, synthetic, ignored `scos/work/`)

Harness (`_stage8a_acceptance.py`, not committed) exercised the full lifecycle with `customer_id=test-customer-stage8a`, `currency=THB`, one video-production line item (5000.00), NET-7 terms:

| Step | Command (service call) | Result |
|------|------------------------|--------|
| A create | `create_invoice_preparation(...)` | `INVOICE_DRAFT_PENDING`, total `5000.00 THB` |
| B ready | `mark_invoice_ready(...)` | `READY_FOR_MANUAL_INVOICE`, `invoice_not_sent` boundary respected |
| C sent | `mark_invoice_sent(sent_date, invoice_number)` | `PAYMENT_PENDING` (no network/messaging) |
| D queue | `list_payment_follow_up_queue(as_of=...)` | due-soon / follow-up-due / overdue correctly categorized; record status unchanged by eval |
| E paid | `record_payment_status_decision(decision=paid, paid_date, paid_amount, currency, ref)` | `PAID`, `automation_allowed=False` |
| F ineligible | closure `REVISION_OPEN` | `ERR_INELIGIBLE_CLOSURE` (blocked) |
| G dup | conflicting scope, different price | `ERR_DUPLICATE_COMMERCIAL_SCOPE` (blocked) |
| H partial | `paid_amount` < total | `PARTIAL_PAYMENT_UNSUPPORTED` (blocked) |
| I sensitive | card number input | rejected (`payment_card`) |
| J invalid | transition `PAID → disputed` | rejected (`ERR_INVALID_TRANSITION`) |

## 10. Negative Evidence

All above F–J confirm: incomplete/non-closed delivery blocked; duplicate commercial scope blocked; partial payment blocked; sensitive data rejected; invalid transition blocked; queue evaluation performs no state mutation; SHA/closure mismatch blocked (via eligibility + `ERR_ARTIFACT_SHA_MISMATCH`).

## 11. Test Evidence (verified by oversight agent, not trusted from agent log)

| Suite | Result |
|-------|--------|
| Stage 8A focused | **17 passed** |
| Stage 5–7 regression | **69 passed, 1 skipped** |
| Control Center full | **933 passed, 1 skipped, 1 warning** (pre-existing HVS adapter readonly decode warning) |
| Full SCOS suite | **1363 passed, 1 skipped, 1 warning, exit 0** (327.96s) |
| Security scan | **PASS, 0 findings** (419 files) |
| Smoke | **16 passed, PASS** |

## 12. Scope and Safety

- No invoice sent, no customer contacted, no payment link, no payment provider accessed.
- No automatic paid state; PAID only via explicit operator confirmation.
- HVS unmodified (read-only).
- No dependency/lock-file change.
- No runtime invoice/payment JSONL or audit staged (all under ignored `scos/work/`).
- `automation_allowed` always `False` in records/events/CLI.
- Production scan: no `subprocess`/`os.system`/`shell=True`/network/AI/GUI/payment tokens (only a regex *definition* for the sensitive-data guard).

## 13. Known Limitations

- Partial payments are intentionally rejected (`PARTIAL_PAYMENT_UNSUPPORTED`); no complex accounting.
- Revision billing has no repository contract; an explicit operator `billing_scope_key` is the supported distinct-scope mechanism.
- The follow-up queue surfaces actionable items; pre-follow-up `PAYMENT_PENDING` items appear as `PAYMENT_PENDING` (due soon). Evaluation date must not be part of deterministic IDs (it is not).

## 14. Rollback

```
git revert <stage8a-feature-commit> --no-edit
# or, before downstream work: git reset --hard 5af565a
```
Runtime records under `scos/work/` are ignored and regenerable. HVS unaffected.

## 15. Final Verdict

SCOS–HVS Integration Stage 8A provides operator-controlled invoice preparation and payment follow-up readiness. It does not issue invoices, contact customers, process payments, or verify bank transactions.

Permitted conclusion only. No claim of legal invoice issuance until operator supplies a number; no customer contact; no payment provider; no revenue recognition; no tax calculation.
