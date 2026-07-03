# First Paid Customer Dry Run Contract (Stage 4.8)

## Purpose

Stage 4.8 rehearses one complete first paid customer delivery from explicit
local inputs. It answers whether an operator can run SCOS from synthetic intake
through monetization readiness without missing critical commercial steps.

This is dry-run/rehearsal only. It is not real payment, SaaS, CRM, customer
portal, dashboard, live outreach, email or LINE automation, cloud delivery, or
LLM-generated sales copy.

## Architecture

```
SyntheticCustomerCase
        -> run_commercial_delivery
        -> run_commercial_acceptance_gate
        -> generate_first_customer_kit
        -> review_monetization_readiness
        -> FirstPaidCustomerDryRunResult
```

Stage 4.8 calls public Stage 4 APIs only. It does not import lower knowledge
engines and does not change Stage 4.1-4.7 behavior or contracts.

## Public API

```python
run_first_paid_customer_dry_run(
    *,
    knowledge_service,
    output_dir,
    checked_at: str,
    customer_case: SyntheticCustomerCase | None = None,
    run_id: str = "first-paid-customer-dry-run",
    delivery_id: str | None = None,
    video_path=None,
    source_manifest_path=None,
    overwrite: bool = False,
    require_go: bool = True,
    add_synthetic_risk_checklist: bool = True,
)
```

`checked_at` is explicit. The implementation never uses a real clock, random, or
UUID. URL paths are rejected. Source artifacts are inspected or passed through to
existing stages but never deleted or modified.

## Synthetic Customer Case

The default case is deterministic and contains no real customer PII:

- `customer_id`: `synthetic-first-customer-001`
- `business_name`: `Synthetic Local Clinic`
- `business_type`: `clinic`
- `target_offer`: `AI Content Delivery Audit`
- `target_price`: `4900 THB dry-run offer`
- `intake_summary`: synthetic rehearsal text

`SyntheticCustomerCase` has no phone, email, or address fields. Metadata keys
containing phone, email, or address are rejected.

## Dry-Run Flow

1. `validate_inputs`
2. `prepare_customer_case`
3. `run_commercial_delivery`
4. `run_acceptance_gate`
5. `generate_operating_kit`
6. `ensure_required_readiness_artifacts`
7. `run_monetization_readiness`
8. `write_dry_run_report`
9. `summarize_go_no_go`

When `add_synthetic_risk_checklist=True`, Stage 4.8 writes a deterministic
`risk_checklist.md` into the generated operating kit. The file clearly states it
is synthetic dry-run evidence and not real customer advice.

## Output Layout

```
<output_dir>/
  commercial_run/
  acceptance/
  operating_kit/
  monetization_readiness_report.json
  first_paid_customer_dry_run_report.json
```

## Report Schema

`FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION = 1`.

`first_paid_customer_dry_run_report.json` contains:

- result status: `ok`, `passed`, `go_no_go`, `readiness_level`
- readiness score and max score
- synthetic customer case
- paths to run manifest, acceptance report, operating kit, monetization report,
  and dry-run report
- ordered dry-run steps
- blockers
- deterministic metadata

## Pass / Fail Rules

`passed=True` only when:

- commercial run completed
- acceptance passed
- operating kit generated
- monetization readiness returned `GO` when `require_go=True`
- no critical blockers exist

Otherwise `passed=False`, or a deterministic error is returned when the dry run
cannot continue.

## Blockers

`DryRunBlocker` records `blocker_id`, category, severity, title, detail,
recommended action, source step, and metadata. Severity is `warning`, `error`,
or `critical`.

## Determinism Guarantees

- No real clock, random, or UUID.
- JSON uses UTF-8, LF newlines, `sort_keys=True`, and `indent=2`.
- Repeated equivalent inputs produce equivalent schema-bearing content.

## Local-Only Restrictions

- Python standard library only plus existing commercial modules.
- No network, cloud, SaaS, payment, auth, CRM, LLM, outreach, or portal behavior.
- No real customer PII.
- No direct lower knowledge engine imports.
- No Certified Core changes.
- No `scos/knowledge` implementation changes.
- No Stage 4.1-4.7 contract changes.

## Example

```python
from scos.commercial import run_first_paid_customer_dry_run

result = run_first_paid_customer_dry_run(
    knowledge_service=knowledge_service,
    output_dir="output/first-paid-customer-dry-run",
    checked_at="2026-07-03T04:00:00Z",
)
print(result.passed, result.go_no_go)
```

## Out Of Scope

Real payment, invoices, authentication, CRM records, customer portals, SaaS,
dashboards, cloud delivery, email or LINE automation, live outreach, and
LLM-generated sales copy.
