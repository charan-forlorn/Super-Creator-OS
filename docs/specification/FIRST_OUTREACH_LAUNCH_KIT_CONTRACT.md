# First Outreach Launch Kit Contract

## Purpose

Stage 4.11 creates a local-only first outreach launch kit for preparing the operator to start a manual first prospecting campaign.

The kit packages deterministic templates for lead tracking, mini-audits, manual outreach scripts, follow-up timing, offer explanation, objection handling, and launch readiness.

This is preparation only. It does not send messages, gather leads, create records in external systems, or process real customer PII.

## Architecture

The Stage 4.11 flow is:

1. Resolve an `OutreachLaunchProfile`.
2. Inspect optional local Stage 4.9 or Stage 4.10 evidence paths if supplied.
3. Write deterministic outreach kit assets.
4. Write `outreach_readiness_manifest.json`.
5. Return `FirstOutreachLaunchKitResult` or `FirstOutreachLaunchKitError`.

Stage 4.11 does not call knowledge engines and does not modify Stage 4.1 through Stage 4.10 behavior.

## Public API

```python
create_first_outreach_launch_kit(
    *,
    output_dir,
    created_at: str,
    profile: OutreachLaunchProfile | None = None,
    kit_id: str | None = None,
    launch_certification_pack_path=None,
    operator_practice_report_path=None,
    overwrite: bool = False,
) -> FirstOutreachLaunchKitResult | FirstOutreachLaunchKitError
```

`created_at` is explicit. The implementation never uses a real clock, random value, or generated UUID.

## Outreach Profile Contract

`OutreachLaunchProfile` fields:

- `profile_id`
- `operator_name`
- `target_market`
- `target_location`
- `primary_offer`
- `starting_price`
- `delivery_window`
- `outreach_goal`
- `allowed_channels`
- `excluded_channels`
- `metadata`

The default profile is `first-outreach-launch-001` for local clinics and service businesses, with the default offer `AI Content & Booking Readiness Audit`.

## Output Layout

```text
<output_dir>/<kit_id>/
  outreach_readiness_manifest.json
  lead_list_template.csv
  mini_audit_template.md
  outreach_scripts.md
  follow_up_sequence.md
  offer_one_pager.md
  objection_handling.md
  outreach_launch_checklist.md
```

Default kit id:

```text
first-outreach-launch-kit-{profile.profile_id}
```

## Asset Schemas

`lead_list_template.csv` columns:

- `lead_id`
- `business_name`
- `business_type`
- `location`
- `facebook_url`
- `line_or_booking_channel`
- `observed_problem`
- `mini_audit_status`
- `outreach_status`
- `follow_up_date`
- `notes`

The CSV includes one synthetic example row only.

Markdown assets are deterministic templates for manual operator use:

- mini-audit structure
- manual scripts
- follow-up sequence
- offer one-pager
- objection handling
- launch checklist

## Manifest Schema

`outreach_readiness_manifest.json` includes:

- `schema_version`
- `kit_id`
- `created_at`
- `profile`
- `assets`
- `checks`
- `ready_for_outreach`
- `go_no_go`
- `evidence_inputs`
- `metadata`

JSON is written with sorted keys, two-space indentation, UTF-8, LF newlines, and a trailing newline.

## GO / CONDITIONAL_GO / NO_GO Rules

`GO` requires all required assets to exist and all optional evidence inputs to be provided and readable.

`CONDITIONAL_GO` means all required assets exist, but optional evidence was not provided.

`NO_GO` means required assets are missing, profile metadata has PII-like keys, paths are invalid, or output writing fails.

## Determinism Guarantees

- No real clock.
- No random values.
- No UUID generation.
- Fixed `created_at`, profile, and kit id produce deterministic output.
- Tuples serialize as lists.
- `FrozenMap` serializes as a plain dict.

## Local-Only Restrictions

Stage 4.11 accepts only local filesystem paths and writes only local files under `output_dir`.

It performs no network, cloud, SaaS, payment, auth, CRM, LLM, sending, or scraping behavior.

## No Real PII Rule

Profile metadata must not contain phone, email, address, or contact-like keys. Lead templates use synthetic placeholder data only.

## Manual-Only Outreach Boundary

Generated scripts are manual templates. They are not personalized outreach, not ready-to-send automation, and not bulk campaign execution.

## Example

```python
result = create_first_outreach_launch_kit(
    output_dir="scos/work/outreach",
    created_at="2026-07-03T07:00:00Z",
)
```

## Out Of Scope

- automated outreach
- lead scraping
- CRM entry creation
- message sending
- payment links
- dashboards
- SaaS delivery
- LLM-generated personalized outreach
- real customer processing
