# Operator Practice Lab Contract

## Purpose

Stage 4.10 provides a local-only operator practice lab for rehearsing SCOS commercial delivery before contacting real customers.

It runs deterministic synthetic scenarios through the existing Stage 4.8 dry-run boundary and Stage 4.9 launch certification boundary, then writes practice guidance, sample file lists, and operator observations.

This is practice and training only. It does not process real customers or create outreach copy.

## Architecture

The Stage 4.10 flow is:

1. Resolve a predefined `PracticeScenario`.
2. Run the Stage 4.8 first paid customer dry-run API.
3. Run the Stage 4.9 launch certification pack API.
4. Generate local practice files.
5. Return `OperatorPracticeResult` or `OperatorPracticeError`.

Stage 4.10 does not alter Stage 4.1 through Stage 4.9 contracts.

## Public API

```python
run_operator_practice_scenario(
    *,
    scenario_id: str,
    output_dir,
    checked_at: str,
    overwrite: bool = False,
    require_go: bool = True,
) -> OperatorPracticeResult | OperatorPracticeError
```

`checked_at` is explicit. The implementation never uses a real clock, random value, or generated UUID.

## Predefined Scenarios

- `clinic-ready`
- `clinic-missing-offer`
- `spa-low-content`
- `creator-video-audit`
- `restaurant-local-promo`

All scenarios are synthetic and contain no real customer PII. Scenario training gaps are recorded as operator observations unless the existing Stage 4.8 or Stage 4.9 pipeline naturally reports a blocker.

## Output Layout

```text
<output_dir>/<scenario_id>/
  dry_run/
  launch_certification/
  practice_summary.json
  practice_walkthrough.md
  customer_facing_files.md
  internal_evidence_files.md
  operator_observations.md
```

`overwrite=False` fails if the scenario output folder exists. `overwrite=True` replaces only the resolved scenario output folder after containment validation.

## Generated Practice Files

`practice_summary.json` records schema version, practice id, scenario id, checked time, dry-run report path, launch certification report path, practice status, observations, and steps.

`practice_walkthrough.md` explains the run in plain operator language: what scenario ran, what SCOS generated, where to inspect files, what PASS/CONDITIONAL/FAIL means, and what to review before real customer work.

`customer_facing_files.md` lists files that may be adapted later for customer delivery. Every listed file is marked synthetic/practice only.

`internal_evidence_files.md` lists files that should not be sent directly to customers by default, including raw JSON evidence, manifests, launch certification reports, blockers, operator next steps, and the dry-run report.

`operator_observations.md` lists recorded observations and includes a manual checklist after each run.

## Customer-Facing vs Internal Evidence

Customer-facing practice files are markdown files an operator may later adapt manually. They are not ready-to-send messages.

Internal evidence files include raw JSON, manifests, certification evidence, blockers, and execution reports. These are for operator review and audit only.

## Practice Status Rules

`PASS` means the Stage 4.8 dry run passed and Stage 4.9 certification status is `PASS`.

`CONDITIONAL_PASS` means execution completed but warning-only observations or conditional certification require operator review.

`FAIL` means dry-run failure, certification failure, or an error-severity observation exists.

## Error Kinds

- `INVALID_ARGUMENTS`
- `UNKNOWN_SCENARIO`
- `INPUT_NOT_FOUND`
- `DRY_RUN_FAILED`
- `LAUNCH_CERTIFICATION_FAILED`
- `OUTPUT_ALREADY_EXISTS`
- `OUTPUT_WRITE_FAILED`
- `VALIDATION_FAILED`

## Determinism Guarantees

- Fixed `checked_at` and the same `scenario_id` produce deterministic scenario output.
- No real clock.
- No random values.
- No UUID generation.
- JSON is written with sorted keys and stable indentation.
- Markdown is generated from deterministic scenario and evidence data.

## Local-Only Restrictions

Stage 4.10 accepts only local filesystem paths and writes only local files under the requested `output_dir`.

It does not use network, cloud, SaaS, payment, auth, CRM, or LLM behavior.

## No Real Customer PII Rule

Scenario definitions and generated synthetic customer cases must not contain phone, email, or address fields. PII-like keys are rejected.

## Boundary Rules

Stage 4.10 may call:

- `run_first_paid_customer_dry_run`
- `create_commercial_launch_certification_pack`

Stage 4.10 must not bypass Stage 4.8 or Stage 4.9 by calling earlier commercial pipeline internals directly.

## Example

```python
result = run_operator_practice_scenario(
    scenario_id="clinic-ready",
    output_dir="scos/work/practice",
    checked_at="2026-07-03T06:00:00Z",
)
```

## Out Of Scope

- live customer outreach
- customer portals
- dashboards
- cloud delivery
- billing or payment processing
- authentication
- CRM workflows
- LLM-generated sales copy
- real customer processing
