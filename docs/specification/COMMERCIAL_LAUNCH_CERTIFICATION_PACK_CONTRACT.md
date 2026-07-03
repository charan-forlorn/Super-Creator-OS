# Commercial Launch Certification Pack Contract

## Purpose

Stage 4.9 packages final local launch evidence into a deterministic certification bundle that answers whether SCOS is commercially ready to begin first real customer outreach and delivery.

This is a certification and documentation layer only. It does not perform outreach, delivery, billing, account management, live messaging, or cloud work.

## Architecture

The Stage 4.9 flow is:

1. Read an existing `first_paid_customer_dry_run_report.json`.
2. Inspect referenced Stage 4 evidence paths.
3. Validate launch certification checks.
4. Write a local certification folder.
5. Return `LaunchCertificationResult` or `LaunchCertificationError`.

Stage 4.9 does not call the knowledge layer and does not rerun Stage 4.1 through Stage 4.8 behavior.

## Public API

```python
create_commercial_launch_certification_pack(
    *,
    dry_run_report_path,
    output_dir,
    checked_at: str,
    certification_id: str | None = None,
    require_go: bool = True,
    require_no_critical_blockers: bool = True,
    overwrite: bool = False,
) -> LaunchCertificationResult | LaunchCertificationError
```

`checked_at` is explicit. The implementation never uses a real clock, random value, or generated UUID.

## Input Contract

`dry_run_report_path` must be a local file path to a Stage 4.8 dry-run report. The report must contain:

- `ok`
- `schema_version`
- `passed`
- `dry_run_id`
- `checked_at`
- `customer_case`
- `go_no_go`
- `readiness_level`
- `readiness_score`
- `readiness_max_score`
- `commercial_run_manifest_path`
- `acceptance_report_path`
- `operating_kit_path`
- `monetization_readiness_report_path`
- `dry_run_report_path`
- `steps`
- `blockers`
- `metadata`

The referenced evidence must exist locally. URL paths are rejected.

## Generated Output Layout

Default certification id:

```text
commercial-launch-certification-{dry_run_id}
```

Output layout:

```text
<output_dir>/<certification_id>/
  launch_certification_report.json
  launch_certification_summary.md
  launch_readiness_checklist.md
  launch_blockers.md
  operator_next_steps.md
```

`overwrite=False` fails if the pack folder already exists. `overwrite=True` rewrites only the five Stage 4.9 generated files inside that folder.

## JSON Report Schema

`launch_certification_report.json` serializes `LaunchCertificationResult.to_dict()` with sorted keys and two-space indentation.

Top-level fields:

- `ok`
- `schema_version`
- `certification_status`
- `launch_certification_id`
- `checked_at`
- `dry_run_report_path`
- `output_dir`
- `launch_certification_report_path`
- `launch_certification_summary_path`
- `launch_readiness_checklist_path`
- `launch_blockers_path`
- `operator_next_steps_path`
- `readiness_score`
- `readiness_max_score`
- `go_no_go`
- `checks`
- `blockers`
- `artifacts`
- `metadata`

## Markdown File Contracts

`launch_certification_summary.md` includes the certification id, checked time, status, go/no-go, readiness score, evidence summary, and final verdict.

`launch_readiness_checklist.md` includes checklist items for commercial run evidence, acceptance evidence, operating kit, monetization readiness, dry-run pass status, critical blockers, PII, and local-only evidence.

`launch_blockers.md` lists blockers grouped by severity with source check and recommended action. If none exist, it states: `No launch blockers detected.`

`operator_next_steps.md` includes operational next steps based on `PASS`, `CONDITIONAL_PASS`, or `FAIL`.

## Certification Status Rules

`PASS` requires:

- dry-run `passed=True`
- dry-run `go_no_go=GO`
- all required evidence exists
- acceptance evidence is accepted
- monetization readiness is `GO`
- no critical blockers
- no PII-like keys

`CONDITIONAL_PASS` means inspection completed and evidence exists, but warning or allowed non-critical blockers remain.

`FAIL` means required go/no-go evidence is not satisfied, a critical blocker exists, or launch evidence should not be used for real launch.

Hard input and inspection errors return `LaunchCertificationError` with a deterministic `error_kind`.

## Blocker Model

Each blocker has:

- `blocker_id`
- `category`
- `severity`
- `title`
- `detail`
- `recommended_action`
- `source_check`
- `metadata`

Allowed severities are `warning`, `error`, and `critical`.

## Determinism Guarantees

- No real clock.
- No random values.
- No UUID generation.
- JSON uses sorted keys and stable indentation.
- Markdown is generated from inspected evidence only.
- Tuples serialize as lists.
- `FrozenMap` serializes as a plain dict.

## Local-Only Restrictions

Stage 4.9 accepts only local filesystem paths and writes only local files under `output_dir`.

It does not use network, cloud, SaaS, payment, auth, CRM, or LLM behavior.

## No Real Customer PII Rule

The dry-run `customer_case` and `metadata` must not contain phone, email, or address keys. Detection returns `PII_DETECTED`.

## Boundary Rules

Stage 4.9 may inspect Stage 4.8 output and referenced evidence. It must not:

- rebuild commercial reports
- rebuild delivery packages
- rerun commercial delivery
- rerun acceptance
- regenerate operating kits
- rerun monetization readiness
- call knowledge engines directly
- mutate inspected source artifacts

## Example

```python
result = create_commercial_launch_certification_pack(
    dry_run_report_path="output/dry/first_paid_customer_dry_run_report.json",
    output_dir="output/launch-certification",
    checked_at="2026-07-03T05:00:00Z",
)
```

## Out Of Scope

- real customer outreach
- customer portals
- live delivery automation
- cloud deployment
- billing or payment processing
- authentication
- CRM workflows
- LLM-generated copy
