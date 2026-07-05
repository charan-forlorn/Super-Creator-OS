# First Customer Conversion Handoff Contract (Stage 4.17)

Schema version: `1` (`FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION`)

## Purpose

Stage 4.17 is a **read-only, local-first, deterministic manual close preparation
layer**. Given a Stage 4.16 `first_prospect_outcome_review.json` that shows
conversion readiness, it produces the exact manual handoff package an operator
needs to confirm scope, offer, pricing, next steps, and close readiness with a
prospect — before any manual outreach.

It answers: *"Given an outcome review showing conversion readiness, what manual
handoff package does the operator need to close the first customer by hand?"*

It is preparation only. It never sends messages, never collects money, never
generates commercial money-documents, never syncs a customer-relationship system,
and never triggers automation. It never mutates Stage 4.16 (or any 4.1–4.16)
artifacts.

## Inputs

`create_first_customer_conversion_handoff` reads one Stage 4.16 outcome review
JSON object. Required fields (aligned to the real Stage 4.16 output contract):

- `schema_version`
- `review_id` (or `outcome_review_id`)
- `prospect_id`
- `checked_at`
- `action` (nested `{"action": "<STR>", ...}`) or `next_action`
- `blockers`
- `metadata`
- `conversion_ready` / `accepted` are read as readiness evidence when present.

Conversion-ready (forward) actions accepted for handoff:
`ESCALATE_TO_FIRST_CUSTOMER_CONVERSION`, `REQUEST_SCOPE_CONFIRMATION`.

Non-ready actions (`WAIT_FOR_RESPONSE`, `FOLLOW_UP_AFTER_MINI_AUDIT`,
`SEND_REVISED_MINI_AUDIT`, `CLOSE_NO_GO`, `BLOCKED`) return `CONVERSION_NOT_READY`
when `require_conversion_ready=True` (the default).

## Public API

```python
create_first_customer_conversion_handoff(
    *,
    outcome_review_path: str | pathlib.Path,
    output_dir: str | pathlib.Path,
    checked_at: str,
    handoff_id: str | None = None,
    require_human_review: bool = True,
    require_conversion_ready: bool = True,
    overwrite: bool = False,
) -> FirstCustomerConversionHandoffResult | FirstCustomerConversionHandoffError
```

- `checked_at` is an explicit caller-supplied string. No real clock is read.
- `handoff_id`: when omitted it is derived deterministically as
  `first-customer-conversion-<sanitized-review-id>-<sanitized-checked_at>-<sha256[:12]>`
  over `(review_id, prospect_id, checked_at)`. When supplied it is sanitized;
  empty/unsafe ids are rejected. No `uuid`/`random`/clock is used.
- URL paths (`http://`, `https://`) are rejected.
- Nothing is written until every validation passes.

## Outputs

A deterministic handoff folder `<output_dir>/<handoff_id>/` containing 8 files:

| File | artifact_type | Notes |
| --- | --- | --- |
| `first_customer_conversion_handoff_manifest.json` | `manifest` | Full result serialization |
| `scope_confirmation.md` | `scope_confirmation` | Manual scope checklist + questions |
| `offer_summary.md` | `offer_summary` | Offer, deliverables, delivery boundary, exclusions |
| `pricing_confirmation.md` | `pricing_confirmation` | Manual pricing checklist |
| `manual_close_checklist.md` | `manual_close_checklist` | Confirm scope/deliverables/price/timeframe/acceptance/channel/review |
| `next_step_script.md` | `next_step_script` | Manual operator draft message; review required |
| `operator_review.md` | `operator_review` | Final review checklist, blockers, approvals |
| `evidence_summary.json` | `evidence_summary` | Deterministic evidence of the source review |

All artifacts are deterministic, template-based (no LLM text), and clearly mark
scripts as "manual operator draft / review required" with "Human review required
before sending."

## Manifest schema (`first_customer_conversion_handoff_manifest.json`)

Written UTF-8, LF newlines, `sort_keys=True`, `indent=2`, trailing newline. Keys:

- `ok`, `schema_version`, `accepted`
- `handoff_id`, `outcome_review_id`, `prospect_id`, `checked_at`
- `source_outcome_review_path`, `handoff_dir`, `manifest_path`
- `artifacts` — list of `{artifact_name, artifact_type, path, required, description, metadata}`
- `checks` — list of `{check_name, status, severity, artifact_path, error_kind, error_detail, metadata}`
- `blockers` — list of `{blocker_id, category, severity, title, detail, recommended_action, metadata}`
- `metadata` — `{generator, manual_only: true, handoff_layer: true}`

`evidence_summary.json` keys: `schema_version, outcome_review_id, prospect_id,
checked_at, source_outcome_review_path, action, conversion_ready,
accepted_upstream, ready_for_handoff, blockers, metadata`.

## Manual-only boundaries

The layer inspects the outcome review for enabled non-manual / external-service
markers (auto-send, auto-DM, customer-relationship sync, scraping, browser
automation, message/email sending, money-collection, money-documents,
`SaaS`, network, dashboard, checkout). If any such field is enabled it returns
`MANUAL_ONLY_VIOLATION` and writes nothing.

There is **no** payment, money-document generation, money-automation,
customer-relationship system, `SaaS`, customer portal, network, scraping,
auto-DM, message sending, or LLM behavior anywhere in this stage. The written
artifacts explicitly state these exclusions for the human operator.

## PII rejection

Direct personal-data keys anywhere in the inspected review are rejected with
`SENSITIVE_METADATA_REJECTED`: `phone`, `email`, `address`, `personal_name`,
`personal_id`, `national_id`, `tax_id`. Generic business/display aliases
(e.g. `display_name`, `business_type`) are allowed.

## Deterministic behavior

Given fixed inputs, `checked_at`, and `output_dir`, outputs are byte-identical
across runs. No real clock, randomness, uuid, network, or environment reads are
used. JSON is emitted with `sort_keys=True, indent=2` and a trailing newline.

## Acceptance criteria

`accepted = True` only when **all** hold:

- the outcome review supports conversion handoff (forward-ready action), and
- all required artifacts are written, and
- no `critical` blocker exists, and
- human review is required (`require_human_review=True`).

Otherwise `accepted = False`. With `require_conversion_ready=False`, a non-ready
review still produces a package but with `accepted=False` and a `critical`
blocker explaining that manual review / a conversion-ready review is required.

## Error kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `INVALID_OUTCOME_REVIEW`,
`CONVERSION_NOT_READY`, `MANUAL_ONLY_VIOLATION`, `SENSITIVE_METADATA_REJECTED`,
`PATH_CONTAINMENT_FAILED`, `OUTPUT_EXISTS`, `OUTPUT_WRITE_FAILED`,
`VALIDATION_FAILED`.

## Out of scope

This stage is **NOT**: payment, money-document generation, money-automation,
customer-relationship system, `SaaS`, dashboard, customer portal, auto-DM,
email/chat automation, live outreach, LLM-generated sales copy, scraping, or
message sending. It must not alter Stage 4.16 artifacts, Stage 4.1–4.16
contracts, the Certified Core, or the `scos/knowledge` implementation.
