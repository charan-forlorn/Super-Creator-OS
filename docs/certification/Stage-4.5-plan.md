# Stage 4.5 Certification Plan — Commercial Acceptance Gate

## Scope

Stage 4.5 adds a local-only certification and readiness layer over the
Stage 4 commercial pipeline:

- `scos/commercial/acceptance_models.py` — immutable acceptance models
  (`AcceptanceCheck`, `CommercialAcceptanceReport`, `CommercialAcceptanceError`,
  `COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION = 1`).
- `scos/commercial/acceptance_gate.py` — `run_commercial_acceptance_gate(...)`.
- `scos/commercial/tests/test_acceptance_gate.py` — plain-script suite.
- `docs/specification/COMMERCIAL_ACCEPTANCE_GATE_CONTRACT.md` — contract.
- `scos/commercial/__init__.py` — Stage 4.5 lazy exports only.

Stage 4.5 **certifies Stage 4.1–4.4 readiness but does not alter their
contracts**. It is evidence-based: it only inspects artifacts that already
exist and reports PASS / FAIL / BLOCKED with a deterministic readiness score.

## Assumptions

- Stage 4.1–4.4 are certified and unchanged (report contract, delivery
  package layout, CLI, run orchestrator manifest).
- A commercial run to certify is available as a `CommercialRunResult` object,
  its `to_dict()` dict, or a `commercial_run_manifest.json` path.
- Stage 4.4 manifests store absolute local paths and five run steps
  (`validate_inputs`, `build_report`, `write_report`, `build_package`,
  `write_manifest`).

## Architecture boundary

- Consumes Stage 4.4 outputs only; never calls the Stage 4.1 report builder,
  the Stage 4.2 package builder, the Stage 4.3 CLI, or the Stage 4.4
  orchestrator.
- Never imports the Stage 3 knowledge layer (`scos/knowledge` untouched).
- Never mutates or deletes inspected artifacts; writes exactly one new file
  per evaluation: `<output_dir>/<certification_id>/commercial_acceptance_report.json`.
- Certified Core (Stages 1–3) is not modified.

## No-SaaS / no-network / no-LLM rules

- Python stdlib only; no network, cloud, SaaS, auth, payment, or LLM code.
- `http://` / `https://` paths rejected as inputs and failed as evidence.
- Static forbidden-token scan enforced by tests over `acceptance_gate.py`
  (network/cloud libraries, knowledge engine symbols, Stage 4 builder
  imports).
- Deterministic only: injected `created_at`, derived certification id,
  no clock/random/UUID, sorted JSON with LF newlines.

## Test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

## PASS criteria

- All ten suites above pass with 0 failures.
- A successful Stage 4.4 run certifies as `overall_status = PASS`,
  `readiness_score = 100`, and writes a byte-deterministic
  `commercial_acceptance_report.json`.
- Missing evidence (report, package, required delivery files) produces
  deterministic FAIL; a failed run produces BLOCKED; invalid inputs produce
  `CommercialAcceptanceError` with the documented error kinds.
- No source artifact bytes change during certification.
- Only allowed Stage 4.5 files changed; Stage 4.1–4.4 contracts and
  `scos/knowledge` implementation untouched.

## Certification meaning

A PASS certification asserts, from local evidence only, that the commercial
run completed successfully, every required client deliverable exists, all
paths are local, timestamps are explicit and stable, and the readiness score
meets the required threshold. It does not judge content quality and it does
not repair, rebuild, or re-run anything.

## Remaining risks

- The gate verifies artifact existence and structure, not the semantic
  quality of report content (out of scope by design; no LLM evaluation).
- Checksums inside the package manifest are not re-verified in Stage 4.5;
  Stage 4.2 owns checksum generation. A future stage could add re-hash
  verification without changing this contract.
- Evidence paths in Stage 4.4 manifests are absolute; certifying a manifest
  copied to another machine/path will correctly FAIL on missing evidence
  rather than guess.
