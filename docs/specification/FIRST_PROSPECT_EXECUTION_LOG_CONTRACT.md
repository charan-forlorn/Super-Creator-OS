# First Prospect Execution Log Contract

## Purpose

Stage 4.12 provides a local-only first prospect execution log for recording the
first real or manual prospect outreach attempt as deterministic, evidence-first
output.

It captures a single manual outreach attempt: which prospect was contacted, which
outreach asset was used, whether a mini-audit was offered, the response status,
the follow-up due date, blockers, the next action, and manual evidence notes.

This is manual evidence logging only. It is NOT a customer database, lead
enrichment, scraping, auto-DM, email/LINE automation, payment, SaaS, dashboard,
or CRM. It does not send messages and does not process real sensitive PII beyond
an operator-provided prospect label/name.

## Architecture

The Stage 4.12 flow is:

```text
OutreachLaunchKit
        ↓
ManualProspectInput (ProspectProfile + ProspectOutreachAction + ProspectResponseStatus)
        ↓
FirstProspectExecutionLog (record_first_prospect_execution)
        ↓
prospect_execution_log.json
```

Steps:

1. `validate_inputs`
2. `validate_prospect_profile`
3. `validate_outreach_action`
4. `validate_response_status`
5. `validate_outreach_launch_kit_reference` (optional Stage 4.11 artifact, read-only)
6. `write_execution_log`
7. Return `FirstProspectExecutionLogResult` or `FirstProspectExecutionLogError`

Stage 4.12 does not call knowledge engines and does not modify Stage 4.1 through
Stage 4.11 behavior or contracts.

## Public API

```python
record_first_prospect_execution(
    *,
    output_dir,
    checked_at: str,
    prospect: ProspectProfile,
    outreach_action: ProspectOutreachAction,
    response_status: ProspectResponseStatus,
    outreach_launch_kit_path=None,
    overwrite: bool = False,
) -> FirstProspectExecutionLogResult | FirstProspectExecutionLogError
```

`checked_at` is explicit. The implementation never uses a real clock, random
value, or generated UUID. `output_dir` and `outreach_launch_kit_path` may be a
`str` or `pathlib.Path` but must be local filesystem paths.

## Prospect Profile Model

`ProspectProfile` fields:

- `prospect_id` (required)
- `display_name` (required)
- `business_type` (required)
- `channel` (required)
- `source` (required)
- `manual_context`
- `metadata`

There are no phone, email, or address fields. `display_name` should be a
business/display alias, not a real person's name, when logging a real prospect.
`metadata` must not contain keys matching `phone`, `email`, `address`, `token`,
`secret`, or `password`.

## Outreach Action Model

`ProspectOutreachAction` fields:

- `action_id`
- `action_type`
- `outreach_asset_id` (optional)
- `offered_mini_audit` (bool)
- `message_summary`
- `performed_at`
- `performed_by`
- `metadata`

Allowed `action_type`:

- `manual_dm`
- `manual_walk_in`
- `manual_call_note`
- `manual_follow_up`
- `manual_observation`
- `manual_mini_audit_offer`

Actions are manual-only. Only a message summary is recorded, never a raw full
message body, and no message is ever sent.

## Response Status Model

`ProspectResponseStatus` fields:

- `status`
- `response_summary`
- `next_action`
- `follow_up_due` (optional deterministic string)
- `blocker_summary` (optional)
- `metadata`

Allowed `status`:

- `not_contacted`
- `contacted`
- `interested`
- `not_interested`
- `no_response`
- `follow_up_needed`
- `mini_audit_requested`
- `blocked`

`next_action` is required unless `status` is `not_contacted`.

## Execution Log Schema

`prospect_execution_log.json` (from `FirstProspectExecutionLogResult`) includes:

- `ok`
- `schema_version`
- `logged`
- `execution_log_id`
- `checked_at`
- `prospect`
- `outreach_action`
- `response_status`
- `outreach_launch_kit_path`
- `execution_log_path`
- `checks`
- `metadata`

The `execution_log_id` is derived deterministically from the sanitized
`prospect_id` and `checked_at` plus a stable SHA-256 hex prefix. No UUID, random
value, or clock is used.

JSON is written with sorted keys, two-space indentation, UTF-8, LF newlines, and
a trailing newline.

## Manual-Only Restrictions

The log records manual actions only. It never sends a message, never performs
bulk or automated outreach, and never personalizes or dispatches content.

## No CRM / No Scraping / No Automation Rules

Stage 4.12 does not create customer-database or CRM records, does not scrape or
enrich leads, and does not run any automated messaging. It only records
operator-supplied evidence into a single local JSON file.

## No Sensitive PII Rule

Metadata on any model must not contain keys matching `phone`, `email`,
`address`, `token`, `secret`, or `password`. Providing such keys returns
`SENSITIVE_DATA_REJECTED`. Operators should log a business/display alias rather
than real personal contact data.

## Output Layout

```text
<output_dir>/
  prospect_execution_log.json
```

`output_dir` is created only after all validation passes. An existing log file is
replaced only when `overwrite=True`; otherwise the call returns `OUTPUT_EXISTS`.

## Error Kinds

- `INVALID_ARGUMENTS`
- `INPUT_NOT_FOUND`
- `INVALID_PROSPECT`
- `INVALID_OUTREACH_ACTION`
- `INVALID_RESPONSE_STATUS`
- `INVALID_OUTREACH_KIT`
- `SENSITIVE_DATA_REJECTED`
- `OUTPUT_EXISTS`
- `OUTPUT_WRITE_FAILED`
- `VALIDATION_FAILED`

## Determinism Guarantees

- No real clock.
- No random values.
- No UUID generation.
- Fixed `checked_at`, prospect, action, response, and `output_dir` produce
  byte-identical output.
- Tuples serialize as lists.
- `FrozenMap` serializes as a plain dict.

## Local-Only Restrictions

Stage 4.12 accepts only local filesystem paths and writes only a single local
file under `output_dir`. It performs no network, cloud, SaaS, payment, auth, CRM,
LLM, sending, or scraping behavior. Paths beginning with `http://` or `https://`
are rejected with `INVALID_ARGUMENTS`.

## Boundary Rules

- Stage 4.12 MAY read/validate an optional Stage 4.11 launch kit artifact
  (`outreach_launch_kit_path`): it checks that the file exists and, if the file
  is `.json`, that it parses. It is reference-only and is never copied, rewritten,
  or normalized.
- Stage 4.12 must NOT send messages, scrape data, enrich leads, create CRM
  behavior, or modify Stage 4.11 artifacts.

## Examples

```python
result = record_first_prospect_execution(
    output_dir="scos/work/prospect",
    checked_at="2026-07-03T07:00:00Z",
    prospect=ProspectProfile.of(
        prospect_id="prospect-001",
        display_name="Synthetic Clinic Alias",
        business_type="clinic",
        channel="manual_facebook_dm",
        source="manual_local_observation",
        manual_context="Observed unclear booking path in public content.",
    ),
    outreach_action=ProspectOutreachAction.of(
        action_id="action-001",
        action_type="manual_dm",
        message_summary="Sent a short manual note offering a mini-audit.",
        performed_at="2026-07-03T07:00:00Z",
        performed_by="SCOS Operator",
        offered_mini_audit=True,
    ),
    response_status=ProspectResponseStatus.of(
        status="interested",
        response_summary="Owner replied with mild interest.",
        next_action="Prepare a manual mini-audit and follow up.",
        follow_up_due="2026-07-06",
    ),
)
```

## Out Of Scope

- automated outreach / message sending
- lead scraping or enrichment
- CRM or customer-database records
- email / LINE automation
- payment links or processing
- dashboards
- SaaS delivery
- LLM-generated personalized outreach
- storing real sensitive PII
