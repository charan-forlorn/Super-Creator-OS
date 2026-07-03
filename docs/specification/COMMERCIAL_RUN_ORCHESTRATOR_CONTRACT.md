# Stage 4.4 — Local Commercial Run Orchestrator Contract

## Purpose

Stage 4.4 provides a single deterministic, local-first library call that runs the full
commercial delivery flow end to end:

```
validate inputs → build commercial report → build delivery package
→ write commercial run manifest → return CommercialRunResult / CommercialRunError
```

It is an **orchestration layer only**. It duplicates no Stage 4.1 report logic and no
Stage 4.2 package logic, changes no existing contract, mutates no source artifact, and
performs no network, cloud, SaaS, auth, payment, or LLM behavior.

## Architecture

```
KnowledgeService (Stage 3.9, opaque to this layer)
    ↓  build_commercial_report(...)            # Stage 4.1
CommercialReport
    ↓  create_delivery_package(...)            # Stage 4.2
DeliveryPackageResult
    ↓  commercial_run_manifest.json            # Stage 4.4
CommercialRunResult
```

The `knowledge_service` argument is received as an opaque object and handed straight to
the Stage 4.1 builder. The orchestrator never imports the Stage 3.9 knowledge access
layer or any of its engines.

## Public API

```python
from scos.commercial import run_commercial_delivery

result = run_commercial_delivery(
    *,
    knowledge_service,                 # Stage 3.9 KnowledgeService (opaque)
    run_id: str,                       # required, non-empty
    output_dir: str | pathlib.Path,    # required
    created_at: str,                   # required, explicit timestamp string (no clock)
    delivery_id: str | None = None,    # optional; else derived by Stage 4.2
    video_path=None,                   # optional str/Path; must exist if provided
    source_manifest_path=None,         # optional str/Path; must exist if provided
    overwrite: bool = False,           # passed through to Stage 4.2
    qa_status: str = "unknown",
    risks=None,                        # optional tuple of risk dicts
) -> CommercialRunResult | CommercialRunError
```

`report_type` is fixed to `"run_summary"` (the only type the Stage 4.1 builder supports).

## Model contracts

All models are immutable `@dataclass(frozen=True)` and reuse the Stage 4.1 `FrozenMap`
(no duplicate implementation). `COMMERCIAL_RUN_SCHEMA_VERSION = 1`.

### CommercialRunStep
`step_name`, `status`, `output_path | None`, `error_kind | None`, `error_detail | None`,
`metadata: FrozenMap`.

### CommercialRunResult
`ok` (always `True`), `schema_version`, `run_id`, `report_id`, `delivery_id`,
`output_dir`, `report_path`, `package_path`, `manifest_path`, `created_at`,
`steps: tuple[CommercialRunStep, ...]`, `metadata: FrozenMap`.

### CommercialRunError
`ok` (always `False`), `schema_version`, `error_kind`, `error_detail`, `failed_step`,
`steps: tuple[CommercialRunStep, ...]`, `metadata: FrozenMap`.

Every model exposes `to_dict()`. Serialization is deterministic: tuples render as lists,
`FrozenMap` renders as a plain dict, and callers apply
`json.dumps(..., sort_keys=True, indent=2)`.

## Run flow

Each stage records exactly one `CommercialRunStep` (success or failure). Step names:
`validate_inputs`, `build_report`, `write_report`, `build_package`, `write_manifest`.

1. **validate_inputs** — `run_id`, `output_dir`, `created_at` required; URL values for
   `output_dir` / `video_path` / `source_manifest_path` are rejected; optional
   `video_path` / `source_manifest_path` must exist and be files. No directory is created
   before this passes.
2. **run directory** — `run_dir = output_dir / fs_safe(delivery_id or
   "local-commercial-run-<run_id>")`, with a containment guard so it cannot escape
   `output_dir`. Created only after validation.
3. **build_report** — delegates to `build_commercial_report(...)` with an injected
   `now_fn` returning `created_at`.
4. **write_report** — writes `report.json` (report `to_dict()`).
5. **build_package** — delegates to `create_delivery_package(..., output_dir=run_dir /
   "delivery_package", overwrite=overwrite)`. Stage 4.2 output is referenced, never
   rearranged.
6. **write_manifest** — writes `commercial_run_manifest.json`, then returns
   `CommercialRunResult`.

## Output layout

```
<output_dir>/<delivery_id-or-derived-id>/
    commercial_run_manifest.json
    report.json
    delivery_package/
        <fs-safe delivery id>/
            manifest.json
            report.json
            report.md
            qa_summary.md
            improvement_plan.md
            assets/          # only if video/source_manifest provided
```

`package_path` in the result/manifest is exactly the path Stage 4.2 returns.

## commercial_run_manifest.json schema

```json
{
  "schema_version": 1,
  "run_id": "...",
  "report_id": "...",
  "delivery_id": "...",
  "created_at": "...",
  "report_path": "...",
  "package_path": "...",
  "package_manifest_path": "...",
  "steps": [ { "step_name": "...", "status": "...", "output_path": "...",
              "error_kind": null, "error_detail": null, "metadata": {} } ],
  "metadata": { "orchestrator": "scos.commercial.run_orchestrator", "output_dir": "..." }
}
```

Written UTF-8, LF newlines, `sort_keys=True`, `indent=2`.

## Error kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `REPORT_BUILD_FAILED`, `PACKAGE_BUILD_FAILED`,
`OUTPUT_WRITE_FAILED`, `VALIDATION_FAILED`. Expected failures return `CommercialRunError`;
raw exceptions never leak.

## Determinism guarantees

- `created_at` is an explicit injected string; no real clock, no `random`/`uuid`.
- Identical inputs into the same directory (`overwrite=True`) produce byte-identical
  `report.json`, `commercial_run_manifest.json`, and `result.to_dict()`.
- Errors serialize deterministically for identical inputs.

## Local-only restrictions & boundary rules

- Python stdlib only (`json`, `pathlib`, `typing`, `dataclasses`).
- No network / cloud / SaaS / auth / payment / LLM behavior.
- The Stage 3.9 knowledge access layer is never imported here.
- Source artifacts are never mutated; provided `video_path` / `source_manifest_path` are
  copied by Stage 4.2, never moved or altered.
- Static forbidden tokens in `run_orchestrator.py`: `requests`, `httpx`,
  `urllib.request`, `boto3`, `socket`, `http.client`, `openai`, `anthropic`,
  `KnowledgeQueryEngine`, `KnowledgeExplainEngine`, `KnowledgeInsightEngine`,
  `query_engine`, `explain_engine`, `insight_engine`.

## Examples

```python
from scos.commercial import run_commercial_delivery

result = run_commercial_delivery(
    knowledge_service=service,
    run_id="run_a1",
    output_dir="output/commercial",
    created_at="2026-07-03T00:00:00Z",
)
if result.ok:
    print(result.manifest_path, result.package_path)
else:
    print(result.error_kind, result.failed_step)
```

## Out of scope

SaaS, dashboards, web UI, payment/auth/customer portal, network/cloud behavior, LLM
calls, Certified Core changes, `scos/knowledge` implementation changes, and any change to
the Stage 4.1 / 4.2 / 4.3 contracts.
