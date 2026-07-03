# Stage 4.8 - First Paid Customer Dry Run (Certification Plan)

## Scope

Stage 4.8 adds a deterministic local rehearsal layer for one synthetic first paid
customer. It runs the existing Stage 4 commercial flow, writes a dry-run report,
records every step, verifies handoff artifacts, runs monetization readiness, and
lists concrete blockers before a real paying customer is accepted.

New files:

- `scos/commercial/dry_run_models.py`
- `scos/commercial/first_paid_customer_dry_run.py`
- `scos/commercial/tests/test_first_paid_customer_dry_run.py`
- `docs/specification/FIRST_PAID_CUSTOMER_DRY_RUN_CONTRACT.md`
- `docs/certification/Stage-4.8-plan.md`

Modified:

- `scos/commercial/__init__.py` for lazy Stage 4.8 exports only.

## Assumptions

- Stage 4.1-4.7 are complete on `origin/main`.
- The caller provides a valid Stage 3.9 `KnowledgeService`.
- The default synthetic customer case is acceptable for rehearsal and contains no
  real customer PII.
- Stage 4.7 requires an explicit risk file, so Stage 4.8 may add synthetic
  dry-run risk evidence to the generated operating kit.

## Architecture Boundary

Stage 4.8 may call:

- `run_commercial_delivery`
- `run_commercial_acceptance_gate`
- `generate_first_customer_kit`
- `review_monetization_readiness`

It must not call lower knowledge engines directly, alter Stage 4.1-4.7 behavior,
create real invoices, collect payment, or generate hidden business strategy.

## No-SaaS / No-Network / No-LLM Rules

- Python standard library only plus existing commercial modules.
- No network, cloud, SaaS, payment, auth, CRM, portal, outreach, email, LINE, or
  LLM behavior.
- URL paths are rejected.
- Static forbidden-token scans cover the Stage 4.8 executable module.

## No Real Customer PII

`SyntheticCustomerCase` has no phone, email, or address fields. Metadata keys
containing phone, email, or address are rejected.

## Required Test Commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_paid_customer_dry_run.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

## Remaining Risks

- The rehearsal proves artifact flow and readiness gates, not semantic quality of
  customer-facing copy.
- If `add_synthetic_risk_checklist=False`, the default Stage 4.6 kit can
  correctly produce Stage 4.7 `NO_GO`.
- The layer depends on existing Stage 4 APIs preserving their current file
  layouts and deterministic contracts.

## PASS Criteria

- All required test commands pass with 0 failures.
- Dry run writes `first_paid_customer_dry_run_report.json`.
- Synthetic customer contains no real PII.
- No source artifact mutation.
- No Certified Core files modified.
- No `scos/knowledge` implementation files modified.
- No Stage 4.1-4.7 contract changes.
- No commit, push, tag, release, pull, merge, rebase, reset, stash, clean, or
  branch switch.

## Note

Stage 4.8 is dry-run/rehearsal only and does not alter Stage 4.1-4.7 contracts.
