# First Prospect Mini-Audit Delivery Log Contract (Stage 4.15)

## Purpose

Stage 4.15 is a **read-only evidence/logging layer** recorded over a Stage 4.14
mini-audit handoff package. It answers one question:

> After the mini-audit handoff package was created, what happened when the human
> operator manually handled it?

It records whether the handoff was manually reviewed, manually sent, whether the
prospect responded, whether it needs follow-up, or whether it is blocked — and it
computes the next manual action. It is purely additive: it never sends messages,
never touches CRM/payment/billing/SaaS/dashboard/network/LLM behavior, and never
mutates the Stage 4.14 handoff artifacts.

This is **not** CRM, scraping, auto-DM, message/email/LINE sending, payment or
billing, SaaS, a dashboard, a customer portal, or an LLM evaluator.

## Architecture

```
mini_audit_handoff_manifest.json        (Stage 4.14 output, read-only)
        │
        ▼
FirstProspectMiniAuditDeliveryLog
        │  validate inputs + enums + evidence consistency
        │  load + validate handoff manifest contract
        │  validate handoff artifacts exist & are contained
        │  validate manual-only (no automation signals)
        │  validate sensitive metadata (no direct PII)
        │  evaluate delivery status → next manual action
        ▼
first_prospect_mini_audit_delivery_log.json   (optional, deterministic)
```

The handoff **directory** is derived as the parent directory of the supplied
manifest path — the Stage 4.14 manifest itself does not carry a `handoff_dir`
key. Artifact paths in the manifest are absolute and must resolve inside that
directory.

### Modules
- `scos/commercial/mini_audit_delivery_models.py` — immutable models + constants.
- `scos/commercial/first_prospect_mini_audit_delivery_log.py` — the public API.

Both reuse the Stage 4.1 `FrozenMap` / `_freeze_value` from `report_models`.

## Public API

```python
record_first_prospect_mini_audit_delivery(
    *,
    handoff_manifest_path,                       # str | pathlib.Path
    checked_at: str,                             # explicit timestamp string
    output_path=None,                            # str | pathlib.Path | None
    operator_review_status: str = "not_reviewed",
    manual_send_status: str = "not_sent",
    prospect_response_status: str = "no_response_yet",
    manual_channel: str | None = None,
    sent_at: str | None = None,
    response_received_at: str | None = None,
    response_summary: str | None = None,
    follow_up_due_at: str | None = None,
    allow_escalation: bool = False,
    require_human_review: bool = True,
    metadata=None,
) -> FirstProspectMiniAuditDeliveryLogResult | FirstProspectMiniAuditDeliveryLogError
```

Returns a Result or an Error object; it never raises for expected failures.

## Model contracts

Constant: `FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION = 1`.

Every model exposes `to_dict()` with deterministic explicit key order; tuples
serialize as lists, nested dataclasses via their own `to_dict()`, and `FrozenMap`
as a plain (key-sorted) dict. Callers write JSON with `sort_keys=True, indent=2`
plus a trailing newline.

### `MiniAuditDeliveryCheck`
`check_name, status, severity, artifact_path?, error_kind?, error_detail?, metadata`.
`status ∈ {success, failure, skipped}`, `severity ∈ {info, warning, error}`.

### `MiniAuditDeliveryEvidence`
`operator_review_status, manual_send_status, prospect_response_status,
manual_channel?, sent_at?, response_received_at?, response_summary?, metadata`.

- `operator_review_status ∈ {not_reviewed, reviewed, changes_requested,
  approved_for_manual_send, blocked}`
- `manual_send_status ∈ {not_sent, sent_manually, deferred, blocked}`
- `prospect_response_status ∈ {no_response_yet, interested, requested_more_info,
  requested_call, deferred, not_interested, blocked}`
- `manual_channel` is a business-safe label only, e.g. `manual_line`,
  `manual_facebook`, `manual_email`, `manual_in_person`, `manual_phone_note`.
  It must **not** store actual phone/email/address/account handles.
- `response_summary` must be short, operator-written, and contain no real PII.

### `MiniAuditDeliveryNextAction`
`action, reason, priority, due_at?, requires_human_review, metadata`.
- `action ∈ {REVIEW_HANDOFF, SEND_MANUALLY, FOLLOW_UP, WAIT, SCHEDULE_CALL,
  CLOSE_NO_GO, ESCALATE_TO_FIRST_CUSTOMER_FLOW, BLOCKED}`
- `priority ∈ {low, normal, high, urgent}`

### `FirstProspectMiniAuditDeliveryLogResult`
`ok, schema_version, accepted, delivery_log_id, handoff_id, decision_id?,
execution_log_id?, prospect_id, checked_at, source_handoff_manifest_path,
output_path?, evidence, next_action, checks, blockers, metadata`.

### `FirstProspectMiniAuditDeliveryLogError`
`ok(=False), schema_version, error_kind, error_detail, failed_check, checks,
blockers, metadata`.

## Input handoff manifest assumptions

Aligned to the actual Stage 4.14 output. Required top-level keys:
`schema_version, handoff_id, decision_id, execution_log_id, prospect_id,
artifacts, checks, metadata`, plus a timestamp under `checked_at` (a `created_at`
alias is also accepted). `artifacts` is a list of objects each with
`artifact_name` and an absolute `path`.

Required referenced artifacts (all must exist and resolve inside the handoff
directory):
`mini_audit_summary.md, operator_review_checklist.md, prospect_context.json,
handoff_message_draft.md, evidence_index.json, mini_audit_handoff_manifest.json`.

## Delivery Log ID

Deterministic. Derived from `handoff_id | prospect_id | checked_at |
operator_review_status | manual_send_status | prospect_response_status` as
sanitized text plus a 12-char SHA-256 prefix. No clock, random, or uuid.

## Next action rules

Evaluated in this precedence:

1. `operator_review_status == blocked` → `BLOCKED`
2. `manual_send_status == blocked` → `BLOCKED`
3. `prospect_response_status == blocked` → `BLOCKED`
4. A concrete prospect response drives the action:
   - `interested` → `ESCALATE_TO_FIRST_CUSTOMER_FLOW` if `allow_escalation` else `FOLLOW_UP`
   - `requested_more_info` → `FOLLOW_UP`
   - `requested_call` → `SCHEDULE_CALL`
   - `deferred` → `FOLLOW_UP` if `follow_up_due_at` else `WAIT`
   - `not_interested` → `CLOSE_NO_GO`
5. Otherwise (`no_response_yet`):
   - review `not_reviewed` / `changes_requested` → `REVIEW_HANDOFF`
   - review `approved_for_manual_send` and send `not_sent` → `SEND_MANUALLY`
   - send `deferred` → `FOLLOW_UP` if `follow_up_due_at` else `WAIT`
   - send `sent_manually` → `FOLLOW_UP` if `follow_up_due_at` else `WAIT`

`accepted = True` when the next action is usable by the operator; `accepted =
False` only when the state is `BLOCKED`.

## Output schema (`first_prospect_mini_audit_delivery_log.json`)

Only written when `output_path` is provided and all validation passes. It is the
`to_dict()` of `FirstProspectMiniAuditDeliveryLogResult`, serialized UTF-8, LF,
`sort_keys=True`, `indent=2`, with a trailing newline. If `output_path` names a
directory, the file `first_prospect_mini_audit_delivery_log.json` is created
inside it.

## Error kinds

`INVALID_ARGUMENTS, INPUT_NOT_FOUND, INVALID_HANDOFF_MANIFEST,
INVALID_HANDOFF_PACKAGE, INVALID_DELIVERY_EVIDENCE, SENSITIVE_METADATA,
MANUAL_ONLY_VIOLATION, PATH_CONTAINMENT_FAILED, OUTPUT_WRITE_FAILED,
VALIDATION_FAILED`.

Notable rules:
- Invalid status enum → `INVALID_DELIVERY_EVIDENCE`.
- `sent_at` provided while `manual_send_status != sent_manually` → `INVALID_ARGUMENTS`.
- `response_received_at` provided while `prospect_response_status == no_response_yet`
  → `INVALID_ARGUMENTS`.

## Determinism guarantees

No real clock, random, uuid, network, or environment-dependent output. Given the
same inputs (including the explicit `checked_at`), the `delivery_log_id`, the
Result, and the on-disk JSON are byte-identical across runs.

## Local-only / manual-only restrictions

- Stdlib only (`pathlib, json, hashlib, re, typing`).
- `http://` / `https://` paths are rejected for both the manifest and the output.
- The manifest and supplied metadata are scanned for automation signals
  (auto-send, auto-DM, CRM sync, scraping, message/email sending, payment,
  billing, SaaS, network, dashboard); any enabled signal → `MANUAL_ONLY_VIOLATION`.

## No real customer PII rule

Supplied metadata, manifest metadata, and `prospect_context.json` metadata are
scanned for direct PII keys: `phone, email, address, personal_name, personal_id,
national_id, tax_id, line_id, facebook_profile, contact_handle`. Any such key →
`SENSITIVE_METADATA`. Generic business/display aliases are allowed.

## Boundary rules

Stage 4.15 may **read** Stage 4.14 output files. It must NOT call outreach, CRM,
message sending, scraping, payment, billing, network, or SaaS functions; must NOT
modify or delete any inspected source file; must NOT mutate the Stage 4.14
handoff package; and must NOT import the knowledge service or lower knowledge
engines.

## Examples

```python
from scos.commercial import record_first_prospect_mini_audit_delivery

# Just after the handoff package was created — nothing done yet.
r = record_first_prospect_mini_audit_delivery(
    handoff_manifest_path="out/mini-audit-handoff-.../mini_audit_handoff_manifest.json",
    checked_at="2026-07-04T07:00:00Z",
)
assert r.next_action.action == "REVIEW_HANDOFF"

# Operator sent it manually; prospect asked to talk.
r = record_first_prospect_mini_audit_delivery(
    handoff_manifest_path="out/.../mini_audit_handoff_manifest.json",
    checked_at="2026-07-04T07:00:00Z",
    operator_review_status="approved_for_manual_send",
    manual_send_status="sent_manually",
    sent_at="2026-07-04T08:00:00Z",
    prospect_response_status="requested_call",
    response_received_at="2026-07-04T09:00:00Z",
    manual_channel="manual_line",
    output_path="delivery/",
)
assert r.next_action.action == "SCHEDULE_CALL"
```

## Out of scope

No message/email/LINE sending, no auto-DM, no CRM, no scraping, no payment or
billing, no SaaS, no dashboard, no customer portal, no LLM evaluation, no network
or cloud calls, no source-artifact mutation, and no changes to the Stage 4.1–4.14
contracts.
