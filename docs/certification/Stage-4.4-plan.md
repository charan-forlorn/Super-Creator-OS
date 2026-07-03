# Stage 4.4 — Local Commercial Run Orchestrator (Certification Plan)

## Scope

Add a local-only, deterministic **library orchestration layer** that executes the full
commercial delivery flow in one call:

```
validate inputs → build commercial report (4.1) → build delivery package (4.2)
→ write commercial_run_manifest.json → return CommercialRunResult / CommercialRunError
```

New files:

- `scos/commercial/run_models.py` — `CommercialRunStep`, `CommercialRunResult`,
  `CommercialRunError`, `COMMERCIAL_RUN_SCHEMA_VERSION = 1`.
- `scos/commercial/run_orchestrator.py` — `run_commercial_delivery(...)`.
- `scos/commercial/tests/test_commercial_run_orchestrator.py` — plain-script suite.
- `docs/specification/COMMERCIAL_RUN_ORCHESTRATOR_CONTRACT.md`.
- `docs/certification/Stage-4.4-plan.md` (this file).

Edited: `scos/commercial/__init__.py` — added Stage 4.4 lazy exports only, preserving the
Stage 4.3 PEP 562 lazy-export architecture (no eager imports, no knowledge import at
package import time).

## Assumptions

- The Stage 3.9 `KnowledgeService` is passed in by the caller and treated as opaque.
- `report_type` is fixed to `"run_summary"` (the only type the Stage 4.1 builder supports).
- `created_at` is always an explicit injected string; there is no real clock.
- Stage 4.2 owns the delivery-package directory layout; Stage 4.4 references it, never
  rearranges it.

## Architecture boundary

- Orchestration only: no report-building or package-building logic is duplicated, and no
  new business recommendations are inferred.
- `run_orchestrator.py` never imports the knowledge access layer or its engines. The
  `knowledge_service` object flows straight into `build_commercial_report`.
- Reuses the Stage 4.1 `FrozenMap`; no duplicate implementation.

## No-SaaS / no-network / no-LLM rules

- Python stdlib only (`json`, `pathlib`, `typing`, `dataclasses`).
- No network / cloud / SaaS / auth / payment / LLM behavior.
- URL paths (`http://`, `https://`) are rejected at validation.
- Source artifacts are never mutated.
- Static forbidden tokens verified absent in `run_orchestrator.py`: `requests`, `httpx`,
  `urllib.request`, `boto3`, `socket`, `http.client`, `openai`, `anthropic`,
  `KnowledgeQueryEngine`, `KnowledgeExplainEngine`, `KnowledgeInsightEngine`,
  `query_engine`, `explain_engine`, `insight_engine`.

## Test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

## Remaining risks

- `package_path` nests the Stage 4.2 folder under `delivery_package/` (one level deeper
  than the "recommended" flat layout). This is intentional — Stage 4.2 output is not
  rearranged, and the manifest references the real path.
- Determinism of `report.json` depends entirely on the Stage 4.1 builder remaining
  deterministic under a fixed `now_fn` (already certified in Stage 4.1).

## PASS criteria

- All nine suites above pass with 0 failures.
- Stage 4.4 orchestrator suite covers: success flow, deterministic manifest/result/error,
  report-build failure, package-build failure, missing optional inputs, overwrite
  semantics, no source mutation, no knowledge/network import leak, URL rejection, manifest
  references exist, created_at consistency, step coverage, path containment.
- `.gitignore` untouched/unstaged; no Certified Core, `scos/knowledge` implementation, or
  Stage 4.1/4.2/4.3 contract changes.

## Note

Stage 4.4 is **orchestration-only** and does not alter the Stage 4.1, 4.2, or 4.3
contracts. It adds new public symbols behind the existing lazy-export mechanism and leaves
every prior export and behavior unchanged.
