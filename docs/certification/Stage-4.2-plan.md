# Stage 4.2 Certification Plan — Local Delivery Package Generator

Status: implementation plan (pre-certification)
Stage 4.1 baseline: cb790f84506953ec804d35fe95b9196d7c1671b1

## Scope

Stage 4.2 adds a fully local delivery package generator that turns one Stage
4.1 `CommercialReport` (plus optional local asset files) into a deterministic
client-deliverable folder under a caller-provided output directory
(by convention `scos/work/deliveries/`).

New files:

- `scos/commercial/package_models.py`
- `scos/commercial/delivery_package.py`
- `scos/commercial/tests/test_delivery_package.py`
- `docs/specification/DELIVERY_PACKAGE_CONTRACT.md`
- `docs/certification/Stage-4.2-plan.md`

Changed files:

- `scos/commercial/__init__.py` — additive Stage 4.2 exports only; Stage 4.1
  exports unchanged.

## Assumptions

- Stage 4.1 `CommercialReport` is the only report input; its contract is
  unchanged.
- The caller injects `now_fn`; the generator never reads the wall clock.
- Optional assets (video, source manifest) already exist locally when
  provided; the generator only copies them.
- The repo test convention is plain-assert scripts run directly with the
  project virtualenv Python.

## Architecture Boundary

- Consumes only commercial-owned models (`report_models`, `package_models`)
  and the Python standard library.
- Never imports `KnowledgeService`, `KnowledgeIndex`, `KnowledgeQueryEngine`,
  `KnowledgeExplainEngine`, `KnowledgeInsightEngine`, engine modules, or raw
  knowledge artifacts.
- Never mutates source artifacts; writes only inside the computed package
  directory; `overwrite=True` deletes only that directory.
- Certified Core and Stage 1-3 certified behavior are untouched.

## No-SaaS / No-Network / No-LLM Rules

- No network requests, no cloud storage, no web UI, no auth, no payment, no
  SaaS behavior.
- No LLM-generated text; every output byte derives deterministically from the
  input report fields and copied asset bytes.
- No inferred or hidden recommendations; empty recommendation/risk sets emit
  fixed fallback lines.

## Expected Test Commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
```

Stage 3.5-3.9 regression:

```
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
```

## Remaining Risks

- Markdown rendering is a fixed projection; future report fields will not
  appear in Markdown until the renderer is extended (report.json always
  carries the full report).
- Filesystem-name sanitization only maps `:` to `_`; other exotic characters
  in caller-provided delivery ids are rejected by the containment guard rather
  than sanitized.
- Large asset copies are synchronous local copies; no resume/partial handling
  (acceptable for local-first delivery).

## PASS Criteria For Later Certification

- All Stage 4.2 tests pass with 0 failures.
- Stage 4.1 report builder suite passes unchanged.
- Stage 3.5-3.9 knowledge suites pass unchanged.
- Static dependency check confirms no lower-layer or network imports in
  `delivery_package.py`.
- Two runs with identical inputs and fixed `now_fn` produce byte-identical
  `manifest.json`, `report.json`, `report.md`, `qa_summary.md`, and
  `improvement_plan.md`.
- Checksums in `manifest.json` match the SHA256 of every listed file on disk.
