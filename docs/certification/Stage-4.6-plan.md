# Stage 4.6 — First Customer Operating Kit (Certification Plan)

## Scope

Add a local-only First Customer Operating Kit generator that converts an accepted
Stage 4.5 commercial acceptance result into a deterministic local folder an operator
can use to serve the first real customer. Operating-kit layer only: it inspects
existing artifacts, generates markdown + a JSON manifest, optionally copies evidence,
and mutates nothing upstream.

New files:
- `scos/commercial/customer_kit_models.py` — `CUSTOMER_KIT_SCHEMA_VERSION`,
  `CustomerKitFile`, `CustomerKitResult`, `CustomerKitError`.
- `scos/commercial/customer_kit.py` — `generate_first_customer_kit(...)`.
- `scos/commercial/tests/test_customer_kit.py` — plain-script suite.
- `docs/specification/FIRST_CUSTOMER_OPERATING_KIT_CONTRACT.md`.
- `docs/certification/Stage-4.6-plan.md` (this file).

Modified:
- `scos/commercial/__init__.py` — lazy exports for the five Stage 4.6 public names.

## Assumptions (incl. schema adaptation decision)

- The real Stage 4.5 artifact `commercial_acceptance_report.json` does not carry
  `accepted`, `acceptance_id`, `checked_at`, or top-level artifact paths. Stage 4.6
  **adapts to the real schema**: `certification_id → acceptance_id`,
  `ok && overall_status == "PASS" → accepted`, `created_at → checked_at`.
- Source artifact paths (report / package / package manifest) are read from the
  Stage 4.4 run manifest `commercial_run_manifest.json`, passed via the optional
  `run_manifest_path` argument or auto-discovered from the acceptance report's
  `evidence_paths` (deterministic sort, first name match).
- Timestamps are explicit injected strings. The kit id derives from `customer_id`
  when not provided.

## Architecture boundary

- Python standard library only (`json`, `pathlib`, `shutil`, `typing`,
  `dataclasses`) plus the Stage 4.1 `FrozenMap` and the Stage 4.6 models module.
- Never imports or calls the Stage 3 knowledge layer, the Stage 4.1 report builder,
  the Stage 4.2 package builder, the Stage 4.4 orchestrator, or the Stage 4.5 gate.
- Never mutates or deletes inspected artifacts; writes only inside the kit folder.
- Alters no Stage 4.1/4.2/4.3/4.4/4.5 contract or output.
- Preserves the PEP 562 lazy-export architecture in `__init__.py` (no eager imports,
  no knowledge import at package import time).

## First-customer operating workflow

1. Operator runs the Stage 4.4 commercial delivery flow → run manifest.
2. Operator runs the Stage 4.5 acceptance gate → accepted acceptance report.
3. Operator runs `generate_first_customer_kit(...)` against the accepted report →
   kit folder with manifest, intake/SOP/handoff/certificate/pricing/follow-up/
   files-to-send markdown, and optional evidence copies.
4. Operator manually reviews, then hands off the Stage 4 delivery-package files and
   the operating-kit documents to the customer.

## No-SaaS / no-network / no-LLM / no-payment rules

- No SaaS, dashboard, web UI, portal, auth, payment processing/validation, email,
  cloud upload, or LLM-generated copy.
- `pricing_offer_checklist.md` is a checklist/template only; payment fields are
  placeholders. No payment code exists.
- A static forbidden-token scan of `customer_kit.py` is enforced by the test suite.

## Required test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

Note: the original task listed `test_commercial_acceptance_gate.py`; the actual
Stage 4.5 suite file is `test_acceptance_gate.py`.

## Remaining risks

- Auto-discovery of the run manifest relies on the filename
  `commercial_run_manifest.json` appearing in the acceptance report's
  `evidence_paths`. When absent, callers must pass `run_manifest_path` explicitly;
  otherwise a deterministic `MISSING_SOURCE_ARTIFACT` is returned.
- The generator trusts the run manifest's recorded paths; if an operator moves the
  Stage 4 artifacts after acceptance, generation fails deterministically rather than
  silently producing a broken kit.

## PASS criteria

- All required test commands report 0 failures.
- No Certified Core files modified; no `scos/knowledge` implementation modified; no
  Stage 4.1/4.2/4.3/4.4/4.5 contract changed; no source artifact mutated.
- No commit/push/tag/release; no pull/merge/rebase/reset/stash/clean/switch-branch.

## Note

Stage 4.6 is operating-kit-only and does not alter the Stage 4.1/4.2/4.3/4.4/4.5
contracts.
