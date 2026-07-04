# First Prospect Outcome Review Contract (Stage 4.16)

Schema version: `1` (`FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION`)

## Purpose

Stage 4.16 is a **read-only outcome review / conversion readiness gate** over a
Stage 4.15 mini-audit delivery log. Given the delivery + response evidence it
answers a single operator question:

> Is this prospect ready to move toward first-customer conversion, or what
> manual action should happen next?

It produces a deterministic outcome review and decides the next **manual**
operator action. It is a decision layer only.

## Scope

This is **not** CRM, scraping, auto-DM, email/LINE automation, billing, SaaS, a
dashboard, a customer portal, an LLM evaluator, or payment collection. It never
sends messages, never triggers outreach, never contacts the network, and never
mutates the Stage 4.15 delivery log or the Stage 4.14 handoff artifacts.

## Public API

```python
from scos.commercial import review_first_prospect_outcome

review_first_prospect_outcome(
    *,
    delivery_log_path,               # str | pathlib.Path (local; URLs rejected)
    checked_at: str,                 # explicit timestamp string (no real clock)
    output_path=None,                # str | pathlib.Path | None (local)
    require_human_review: bool = True,
    allow_conversion_escalation: bool = False,
) -> FirstProspectOutcomeReviewResult | FirstProspectOutcomeReviewError
```

Returns a `FirstProspectOutcomeReviewResult` when the delivery log could be
inspected (including blocked / not-ready outcomes), or a
`FirstProspectOutcomeReviewError` for hard failures that prevent inspection.

## Input Contract

The delivery log is the Stage 4.15 `first_prospect_mini_audit_delivery_log.json`.
Stage 4.16 aligns to the **real** Stage 4.15 contract; required top-level keys:

- `schema_version`, `delivery_log_id`, `handoff_id`, `prospect_id`,
  `decision_id`, `execution_log_id`
- `checked_at` or `created_at`
- `source_handoff_manifest_path`
- `evidence` (object) — must contain `operator_review_status`,
  `manual_send_status`, `prospect_response_status`
- `next_action` (object) — must contain `action`
- `checks`, `blockers`, `metadata`

Missing required fields → `INVALID_DELIVERY_LOG`.

### Status normalization (Stage 4.15 is never modified)

Stage 4.15 status names, plus a documented superset of conceptual names, are
normalized into a compact internal vocabulary:

- **review** → `not_reviewed` (`not_reviewed`, `review_needed`), `reviewed`,
  `approved` (`approved`, `approved_for_manual_send`), `changes_requested`,
  `rejected`, `blocked`.
- **send** → `not_sent`, `sent` (`sent`, `sent_manually`, `manually_sent`),
  `deferred`, `send_failed`, `blocked`.
- **response** → `no_response` (`no_response`, `no_response_yet`, `none`),
  `waiting` (`waiting`, `deferred`, `pending`), `interested` (`interested`,
  `positive_response`, `requested_scope`, `requested_more_info`,
  `asked_questions`, `requested_call`), `requested_changes`, `ready_to_buy`,
  `not_interested` (`not_interested`, `declined`), `blocked`.

An unrecognized response status → `INVALID_RESPONSE_STATUS`. Unrecognized
review/send statuses normalize to the conservative `blocked` bucket.

## Output Contract

`FirstProspectOutcomeReviewResult.to_dict()` keys (explicit order): `ok`,
`schema_version`, `accepted`, `review_id`, `delivery_log_id`, `handoff_id`,
`prospect_id`, `decision_id`, `execution_log_id`, `checked_at`,
`conversion_ready`, `action`, `source_delivery_log_path`, `output_path`,
`checks`, `blockers`, `metadata`.

`action` is an `OutcomeReviewAction`: `action`, `reason`, `priority`, `due_at`,
`requires_human_review`, `metadata`.

`FirstProspectOutcomeReviewError.to_dict()` keys: `ok`, `schema_version`,
`error_kind`, `error_detail`, `failed_check`, `checks`, `blockers`, `metadata`.

`review_id` is derived deterministically from `delivery_log_id`, `handoff_id`,
`prospect_id`, `checked_at`, and the decided `action` (sanitized text plus a
SHA-256 prefix). No uuid/random/clock.

## Decision / Action Rules

Allowed actions: `WAIT_FOR_RESPONSE`, `FOLLOW_UP_AFTER_MINI_AUDIT`,
`REQUEST_SCOPE_CONFIRMATION`, `SEND_REVISED_MINI_AUDIT`,
`ESCALATE_TO_FIRST_CUSTOMER_CONVERSION`, `CLOSE_NO_GO`, `BLOCKED`.
Priorities: `low`, `normal`, `high`, `urgent`.

Precedence (first match wins):

1. Delivery log `blockers` non-empty → `BLOCKED`.
2. review/send/response `blocked`, or send `send_failed` → `BLOCKED`.
3. review `not_reviewed` / `changes_requested` → `BLOCKED`.
4. review `rejected` → `CLOSE_NO_GO` if response `not_interested`, else
   `SEND_REVISED_MINI_AUDIT`.
5. review complete but send `not_sent` → `BLOCKED`.
6. reviewed/approved and sent — drive by response:
   - `ready_to_buy` → `ESCALATE_TO_FIRST_CUSTOMER_CONVERSION` when
     `allow_conversion_escalation=True`; otherwise `REQUEST_SCOPE_CONFIRMATION`.
   - `interested` → `REQUEST_SCOPE_CONFIRMATION`.
   - `requested_changes` → `SEND_REVISED_MINI_AUDIT`.
   - `not_interested` → `CLOSE_NO_GO`.
   - `waiting` → `WAIT_FOR_RESPONSE`.
   - `no_response` → `FOLLOW_UP_AFTER_MINI_AUDIT` when the delivery log's
     `next_action` shows follow-up evidence (`FOLLOW_UP`/`SCHEDULE_CALL` or a
     `due_at`); otherwise `WAIT_FOR_RESPONSE`.

`accepted=True` for every non-`BLOCKED` outcome; `accepted=False` for `BLOCKED`.

## Conversion Readiness Rules

`conversion_ready=True` only when all hold:

- the delivery log is valid,
- the mini-audit was reviewed/approved and sent manually,
- the response is `interested` or `ready_to_buy`,
- no blockers exist.

Otherwise `conversion_ready=False`. When `allow_conversion_escalation=False` and
the prospect is ready to buy, the action is `REQUEST_SCOPE_CONFIRMATION` with
`conversion_ready=True` and `requires_human_review=True` — escalation stays a
human decision.

## Manual-Only Constraints

Every produced `action` sets `requires_human_review=True` and never implies
automatic execution. The delivery log is scanned for non-manual / external
signals (auto-send, auto-DM, CRM sync, scraping, message/email sending, billing,
SaaS, network, dashboard); a truthy signal → `MANUAL_ONLY_VIOLATION`.

## PII Rejection Rules

The metadata scopes (`metadata`, `evidence.metadata`, `next_action.metadata`,
and any `prospect` object) are scanned for direct personal-data keys: `phone`,
`email`, `address`, `personal_name`, `personal_id`, `national_id`, `tax_id`,
`line_id`, `contact_handle`. Any match → `SENSITIVE_METADATA`. Generic
business/display aliases are allowed.

## Determinism Rules

- No real clock, `random`, `uuid`, network, or environment-dependent output.
- `checked_at` is an explicit caller-supplied string.
- JSON is written UTF-8 / LF, `sort_keys=True`, `indent=2`, trailing newline.
- Identical inputs produce byte-identical output.

## Non-Mutation Guarantees

- The Stage 4.15 delivery log is read-only.
- The Stage 4.14 handoff manifest (via `source_handoff_manifest_path`) is
  reference-only: it may be parsed to validate but is never copied, normalized,
  rewritten, or mutated.
- Output is written only when `output_path` is provided and all validation
  passes. No files are deleted.

## Forbidden Behavior

No network/cloud/SaaS/auth/payment/LLM, no CRM, no scraping, no auto-DM, no
message sending, no billing execution, no real customer PII, no Certified Core
changes, no `scos/knowledge` implementation imports, no Stage 4.1–4.15 contract
changes, no source artifact mutation.

## Error Kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `INVALID_DELIVERY_LOG`,
`INVALID_RESPONSE_STATUS`, `SENSITIVE_METADATA`, `MANUAL_ONLY_VIOLATION`,
`PATH_CONTAINMENT_FAILED`, `OUTPUT_WRITE_FAILED`, `VALIDATION_FAILED`.

## Testing Requirements

`scos/commercial/tests/test_first_prospect_outcome_review.py` (plain-script
harness) covers the response decision table, blocker/review/send gates, input
and contract errors, output writing + containment, source non-mutation, PII
rejection and alias allowance, determinism (`review_id`, byte-identical output,
`to_dict`), required-checks presence, a static forbidden-token scan of the
executable source, and re-runs the Stage 4.1–4.15 and Stage 3.9 suites.
