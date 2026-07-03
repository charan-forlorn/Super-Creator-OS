# Monetization Readiness Review Contract (Stage 4.7)

Status: review-only contract, schema version 1
Module: `scos/commercial/monetization_readiness.py`, `scos/commercial/monetization_models.py`

## Purpose

Stage 4.7 is a deterministic, local-only, read-only review layer over the
certified Stage 4 commercial artifacts. It inspects a Stage 4.5 acceptance report
and a Stage 4.6 first customer operating kit, then emits a monetization readiness
score, a GO / CONDITIONAL_GO / NO_GO decision, concrete gaps, and optionally one
`monetization_readiness_report.json`.

It is not SaaS, a dashboard, a customer portal, payment processing, auth, cloud
upload, email sending, or LLM behavior. It does not alter Stage 4.1-4.6 contracts
or rebuild any artifact.

## Public API

```python
review_monetization_readiness(
    *,
    acceptance_report_path,
    operating_kit_path,
    checked_at: str,
    output_path=None,
    require_pricing=True,
    require_offer=True,
    require_delivery_artifacts=True,
    require_handoff_script=True,
    require_risk_checklist=True,
)
```

The review returns `MonetizationReadinessResult` when validation completes, even
when the decision is `NO_GO`. It returns `MonetizationReadinessError` when inputs
cannot be validated or loaded. `checked_at` is caller-injected; the module never
uses a real clock, random, UUID, network, cloud, payment, auth, or LLM service.

`http://` and `https://` paths are rejected for input and output arguments.
Inspected artifacts are never deleted or modified. The optional output report is
written only when `output_path` is provided and validation completes.

## Acceptance Shape Compatibility

Stage 4.7 accepts both the real Stage 4.5 report shape and the earlier spec
shape:

| Review concept | Real Stage 4.5 key | Spec-shape key |
| --- | --- | --- |
| acceptance id | `certification_id` | `acceptance_id` |
| accepted | `ok is True and overall_status == "PASS"` | `accepted` |
| acceptance checked time | `created_at` | `checked_at` |
| checks | `checks` | `checks` |

If `accepted` is present it is authoritative. Otherwise the review derives
acceptance from `ok` and `overall_status`.

## Ordered Checks

The review records checks in this order:

1. `validate_inputs`
2. `load_acceptance_report`
3. `inspect_operating_kit`
4. `check_offer_readiness`
5. `check_pricing_readiness`
6. `check_workflow_readiness`
7. `check_delivery_readiness`
8. `check_acceptance_readiness`
9. `check_risk_readiness`
10. `check_handoff_readiness`
11. `compute_readiness_score`
12. `determine_go_no_go`

Seven scoring categories are worth 10 points each, for `max_score = 70`:
offer, pricing, workflow, delivery, acceptance, risk, and handoff readiness.
Non-scoring validation, loading, scoring, and decision checks have max score 0.

## Explicit Risk File Requirement

Risk readiness must be explicit. Stage 4.7 looks for `risk_checklist.md` or
`risks.md` in the kit directory or as a referenced file in
`customer_kit_manifest.json`. It does not infer risk readiness from
`operator_sop.md`, pre-run checks, or other workflow text.

The default Stage 4.6 kit may legitimately produce `ready=False` / `NO_GO` when
`require_risk_checklist=True`, because Stage 4.6 does not create a risk checklist
by default.

## Decision Rules

`GO` requires all of the following:

- no blocking gaps
- score >= 60
- acceptance report accepted is true

`CONDITIONAL_GO` requires all of the following:

- no blocking gaps
- no critical/blocking acceptance failure
- score >= 50
- acceptance report accepted is true
- any remaining gaps are non-blocking

`NO_GO` is returned otherwise. Any blocking gap in risk, pricing, offer,
workflow, delivery, handoff, or acceptance readiness forces `NO_GO` and
`readiness_level = "not_ready"`.

Readiness levels are `ready`, `conditional`, and `not_ready`.

## Models

`MONETIZATION_READINESS_SCHEMA_VERSION = 1`.

The model layer defines:

- `MonetizationReadinessCheck`
- `MonetizationGap`
- `MonetizationReadinessResult`
- `MonetizationReadinessError`

Models are frozen dataclasses, reuse the Stage 4.1 `FrozenMap` and
`_freeze_value`, validate status/severity values, and provide deterministic
`to_dict()` output. Tuples serialize as lists and `FrozenMap` serializes as a
plain dict.

## Boundary Rules

- Python standard library only plus commercial model helpers.
- No network, cloud, SaaS, auth, payment, or LLM behavior.
- No imports from Stage 3 knowledge implementation.
- No calls to Stage 4.1 report builder, Stage 4.2 package builder, Stage 4.4
  orchestrator, Stage 4.5 acceptance gate, or Stage 4.6 kit generator.
- No Certified Core changes.
- No `scos/knowledge` implementation changes.
- No Stage 4.1-4.6 contract changes.

