# Stage 4.12 Plan - First Prospect Execution Log

## Scope

Stage 4.12 adds a local-only first prospect execution log. It records the first
real or manual prospect outreach attempt as deterministic, evidence-first output
in a single `prospect_execution_log.json`.

This stage is manual evidence logging only.

## Assumptions

- Stage 4.1 through Stage 4.11 are complete and present in recent commit history.
- The operator supplies all prospect, action, and response data manually.
- An optional Stage 4.11 launch kit path, when supplied, is a local file.
- `checked_at` is supplied explicitly.
- `display_name` is a business/display alias, not a real person's name, when a
  real prospect is logged.

## Architecture Boundary

Stage 4.12 validates operator-supplied manual input models and writes one local
execution log file. It may read/validate an optional Stage 4.11 launch kit
artifact (existence, and JSON parse when the file is `.json`) as reference only.

It does not alter Stage 4.1 through Stage 4.11 contracts and does not modify
Certified Core files or `scos/knowledge` implementation files.

## No-SaaS / No-Network / No-LLM Rules

The implementation is Python stdlib only (`pathlib`, `json`, `typing`,
`dataclasses`, `hashlib`, `re`) and local-first. It performs no network, cloud,
SaaS, payment, auth, or LLM behavior. Paths beginning with `http://` or
`https://` are rejected.

## No CRM / No Scraping / No Auto-Message Rules

Stage 4.12 does not create CRM or customer-database records, does not scrape or
enrich leads, and does not send or automate any message. It only records
operator-supplied manual evidence. `action_type` is restricted to a fixed set of
manual-only values.

## No Sensitive PII

`ProspectProfile` has no phone/email/address fields. Metadata on any model
containing keys matching `phone`, `email`, `address`, `token`, `secret`, or
`password` is rejected with `SENSITIVE_DATA_REJECTED`.

## Required Test Commands

```powershell
.venv\Scripts\python.exe scos\commercial\tests\test_first_outreach_launch_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_operator_practice_lab.py
.venv\Scripts\python.exe scos\commercial\tests\test_launch_certification_pack.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_paid_customer_dry_run.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_execution_log.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
```

Note: the Stage 4.9 suite file is `test_launch_certification_pack.py` in this
repository. Full pytest is optional due to a known Windows temp `PermissionError`
risk; if attempted and blocked by temp permissions, report it as
environment-blocked, not a Stage 4.12 failure.

## Remaining Risks

- The log records what the operator reports; it does not verify real-world truth
  of the outreach or response.
- The optional launch kit reference is checked only for existence and JSON
  parseability, not business correctness.
- Operators must avoid logging real personal contact data; the PII guard checks
  metadata keys, not free-text field content.

## PASS Criteria

- A valid manual execution log writes `prospect_execution_log.json`.
- Fixed inputs (including `output_dir`) produce byte-identical output.
- Output stays under `output_dir`.
- Missing `output_dir`/`checked_at`, and URL paths, are rejected.
- Missing launch kit path returns `INPUT_NOT_FOUND`; a valid one is read-only.
- Missing prospect fields, invalid action type, and invalid status return their
  typed error kinds; sensitive metadata keys are rejected.
- `follow_up_needed` requires `next_action`; `not_contacted` does not.
- `overwrite` gating and determinism hold.
- All required check names are present.
- Static scans show no network, sending, scraping, payment, auth, CRM, LLM, or
  lower knowledge engine usage.
- Required regression tests pass with zero failures.

## Stage Boundary Note

Stage 4.12 is manual evidence logging only. It does not alter Stage 4.1, Stage
4.2, Stage 4.3, Stage 4.4, Stage 4.5, Stage 4.6, Stage 4.7, Stage 4.8, Stage 4.9,
Stage 4.10, or Stage 4.11 contracts.
