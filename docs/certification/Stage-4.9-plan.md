# Stage 4.9 Plan - Commercial Launch Certification Pack

## Scope

Stage 4.9 adds a local-only launch certification packaging layer. It inspects an existing Stage 4.8 dry-run report and referenced commercial evidence, then writes a deterministic certification pack.

It does not alter Stage 4.1 through Stage 4.8 contracts.

## Assumptions

- Stage 4.8 produced `first_paid_customer_dry_run_report.json`.
- Referenced evidence paths are local filesystem paths.
- `checked_at` is supplied explicitly by the caller.
- The dry-run customer case is synthetic and does not contain real customer PII.

## Architecture Boundary

Stage 4.9 reads:

- Stage 4.8 dry-run report
- Stage 4.4 commercial run manifest path
- Stage 4.5 acceptance report path
- Stage 4.6 operating kit path
- Stage 4.7 monetization readiness report path

Stage 4.9 writes only:

- `launch_certification_report.json`
- `launch_certification_summary.md`
- `launch_readiness_checklist.md`
- `launch_blockers.md`
- `operator_next_steps.md`

It does not call knowledge engines, rerun commercial delivery, rerun acceptance, regenerate operating kits, or rerun readiness review.

## No-SaaS / No-Network / No-LLM Rules

The implementation is Python stdlib only and local-first. It performs no network, cloud, SaaS, payment, auth, CRM, or LLM behavior.

## No Real Customer PII

Stage 4.9 rejects phone, email, or address keys in the dry-run `customer_case` or report `metadata`. The expected error kind is `PII_DETECTED`.

## Required Test Commands

```powershell
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_paid_customer_dry_run.py
.venv\Scripts\python.exe scos\commercial\tests\test_launch_certification_pack.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

## Remaining Risks

- Stage 4.9 depends on Stage 4.8 report paths remaining accurate.
- Certification status is evidence-based; it does not prove real market demand.
- Operators must still manually review the generated pack before contacting a real customer.

## PASS Criteria

- Valid Stage 4.8 dry-run report loads.
- Required evidence exists.
- Acceptance evidence is accepted.
- Monetization readiness is `GO`.
- No critical blockers exist.
- No PII-like keys are detected.
- All five certification pack files are written under `output_dir`.
- Required regression tests pass.

## Stage Boundary Note

Stage 4.9 is launch certification packaging only. It does not alter Stage 4.1, Stage 4.2, Stage 4.3, Stage 4.4, Stage 4.5, Stage 4.6, Stage 4.7, or Stage 4.8 contracts.
