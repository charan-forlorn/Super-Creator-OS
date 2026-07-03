# Stage 4.3 — Local Commercial CLI — Certification Plan

## Scope

Add a local-only, stdlib `argparse` command-line interface over the Stage 4.1
commercial report builder and the Stage 4.2 delivery package generator.

Deliverables:

- `scos/commercial/cli.py` — the CLI (`report`, `package`, `validate`, `version`).
- `scos/commercial/tests/test_cli.py` — plain-script test suite (no pytest).
- `scos/commercial/__init__.py` — refactored to PEP 562 lazy exports; adds
  `COMMERCIAL_CLI_SCHEMA_VERSION` export only.
- `docs/specification/COMMERCIAL_CLI_CONTRACT.md` — the CLI contract.
- This plan.

## Assumptions

- Stage 4.0/4.1/4.2 are complete and unchanged. Their public signatures were
  re-verified against source before implementation and match exactly.
- A persisted knowledge index (`IndexStore` JSON) already exists for `report`.
- The Stage 4.1 builder supports **only** `report_type == "run_summary"`.
- `CommercialReport` has no `from_dict`; the CLI reconstructs it from
  `report.json` via public constructors (`CommercialReport`, `ReportEvidence`,
  `ReportRisk`, `FrozenMap.from_mapping`).

## Architecture boundary

- The knowledge access layer (`IndexStore`, `KnowledgeService`) and
  `build_commercial_report` are imported **lazily inside `_cmd_report` only**;
  `scos/knowledge` is added to `sys.path` there and nowhere else.
- `version` / `package` / `validate` never import the knowledge layer.
- `_cmd_package` uses only `create_delivery_package` and the commercial models.
- **Package-import refactor (required):** `scos/commercial/__init__.py` previously
  imported `report_builder` eagerly, which unconditionally imports
  `knowledge_service`. That made `python -m scos.commercial.cli` fail at package
  import unless `scos/knowledge` was on `sys.path` — breaking the knowledge-free
  commands. The `__init__` now resolves all existing exports lazily via module
  `__getattr__` (PEP 562), so importing the package pulls in nothing eager. No
  existing export was removed or renamed; `report_builder.py`,
  `delivery_package.py`, `report_models.py`, `package_models.py`, and the
  knowledge implementation are untouched.

## No-SaaS / No-network / No-LLM rules

- Python stdlib only; local-first.
- URL paths (`http://`, `https://`) are rejected as `INVALID_ARGUMENTS`.
- `validate` never creates directories and never writes files; `report`/`package`
  create output parents only as required; the CLI never deletes files directly
  (only Stage 4.2's guarded `--overwrite` may replace an existing package dir).
- Determinism: JSON via `sort_keys=True, indent=2`; timestamps only from
  `--created-at` through `_now_fn`; no clock, UUID, or randomness.
- `cli.py` is statically scanned to be free of all forbidden lower-layer and
  network tokens.

## Test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

Smoke: `.venv\Scripts\python.exe -m scos.commercial.cli version`

`test_cli.py` covers the 20 required behaviors plus a static forbidden-token scan
of `cli.py` and an unsupported-report-type check.

## Remaining risks

- Only `run_summary` is exercisable end-to-end; other report types are rejected
  deterministically by design, not implemented.
- `report` depends on a well-formed persisted index; malformed indexes surface as
  `INVALID_INDEX_PATH` (no traceback), but index schema evolution is out of scope.
- The lazy `__init__` changes *how* existing exports are imported (first-access,
  not import-time). Callers using documented public names are unaffected;
  code relying on eager import side effects at package import would need review
  (none found in-repo).

## PASS criteria

- All eight listed test suites pass with 0 failures.
- `python -m scos.commercial.cli version` prints the exact deterministic version
  JSON.
- No Certified Core, knowledge implementation, or Stage 4.1/4.2 contract files
  modified (only the `__init__` lazy-export refactor, which preserves all exports).
- No commit/push/tag/release; `.gitignore` untouched and unstaged.

## Note

Only `run_summary` is supported by the Stage 4.1 builder. The CLI rejects
`style_summary`, `portfolio`, and `system` as `INVALID_ARGUMENTS` with detail
`"report-type not supported by Stage 4.1 builder"`.
