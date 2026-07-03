# Stage 4.10 Plan - Operator Practice Lab

## Scope

Stage 4.10 adds a local-only operator practice lab. It lets the operator run predefined synthetic scenarios before contacting real customers.

This stage is operator training and practice only.

## Assumptions

- Stage 4.8 and Stage 4.9 are complete.
- The Stage 4.9 public API is `create_commercial_launch_certification_pack`.
- Practice scenarios are synthetic.
- `checked_at` is supplied explicitly.
- `scos/work/practice/` is the intended operator workspace, though callers may pass any local output directory.

## Architecture Boundary

Stage 4.10 calls only:

- Stage 4.8 first paid customer dry run
- Stage 4.9 launch certification pack

It does not alter Stage 4.1 through Stage 4.9 contracts. It does not modify Certified Core files or `scos/knowledge` implementation files.

## Practice-Only Rule

Practice output is not customer outreach material. Customer-facing file lists are marked synthetic/practice only, and internal evidence files warn operators not to send raw JSON or manifests to customers by default.

Scenario training gaps are documented as operator observations unless the existing Stage 4.8 or Stage 4.9 pipeline naturally reports them.

## No-SaaS / No-Network / No-LLM Rules

The implementation is Python stdlib only and local-first. It performs no network, cloud, SaaS, payment, auth, CRM, or LLM behavior.

## No Real Customer PII

Predefined scenarios and synthetic customer cases must not contain phone, email, or address fields. PII-like keys are rejected before practice execution.

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
.venv\Scripts\python.exe scos\commercial\tests\test_operator_practice_lab.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

## Remaining Risks

- Practice scenarios demonstrate operator workflow, not real market demand.
- Operators must still manually review customer-facing files before adapting them.
- Internal evidence separation depends on operators following the generated guidance.

## PASS Criteria

- Five predefined synthetic scenarios are available.
- `clinic-ready` completes through Stage 4.8 and Stage 4.9.
- Practice output writes all required files under `output_dir`.
- Customer-facing files are marked synthetic/practice only.
- Internal evidence warns against sending raw JSON and manifests by default.
- Operator observations include a manual checklist.
- Fixed `checked_at` and same scenario produce deterministic output.
- Required regression tests pass with zero failures.

## Stage Boundary Note

Stage 4.10 is operator training/practice only. It does not alter Stage 4.1, Stage 4.2, Stage 4.3, Stage 4.4, Stage 4.5, Stage 4.6, Stage 4.7, Stage 4.8, or Stage 4.9 contracts.
