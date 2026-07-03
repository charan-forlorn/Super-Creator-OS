# Commercial Acceptance Gate Contract (Stage 4.5)

Status: certified contract, schema version 1
Module: `scos/commercial/acceptance_gate.py`, `scos/commercial/acceptance_models.py`

## Purpose

Stage 4.5 is a local-only certification and readiness layer over the Stage 4
commercial pipeline. It answers one question deterministically: **is a
completed commercial run ready for real client delivery?** It inspects the
artifacts that Stage 4.1–4.4 already produced, records evidence-based checks,
computes a readiness score, and writes exactly one certification file.

It introduces no new commercial features and changes no Stage 4.1/4.2/4.3/4.4
contract.

## Architecture

```
Stage 4.1 CommercialReport
        ↓
Stage 4.2 DeliveryPackage
        ↓
Stage 4.3 CLI
        ↓
Stage 4.4 CommercialRunOrchestrator  →  CommercialRunResult / run manifest
        ↓
Stage 4.5 CommercialAcceptanceGate
        ↓
CommercialAcceptanceReport (PASS / FAIL / BLOCKED)
        ↓
<output_dir>/<certification_id>/commercial_acceptance_report.json
```

The gate is strictly read-only over Stage 4 outputs: it never rebuilds
reports, never rebuilds packages, never re-runs orchestration, never imports
the Stage 3 knowledge layer, and never mutates or deletes inspected files.

## Public API

```python
from scos.commercial import run_commercial_acceptance_gate

run_commercial_acceptance_gate(
    *,
    commercial_run_result,          # object with to_dict() | dict | path to commercial_run_manifest.json
    output_dir,                     # str | pathlib.Path (local only)
    created_at: str,                # explicit injected timestamp string
    certification_id: str | None = None,
    min_readiness_score: int = 100,
    require_assets: bool = False,
    require_video: bool = False,
) -> CommercialAcceptanceReport | CommercialAcceptanceError
```

## Input contract

`commercial_run_result` may be:

1. A Stage 4.4 `CommercialRunResult`-like object exposing `to_dict()`.
2. A plain dict (typically `CommercialRunResult.to_dict()` output).
3. A `str`/`pathlib.Path` pointing at a `commercial_run_manifest.json` file.

The normalized run data must contain non-empty string fields
`run_id`, `delivery_id`, `created_at`, `report_path`, `package_path`.
Run success is taken from `ok` when present, otherwise from the manifest
`steps` (all five Stage 4.4 steps present with status `success`).
The package manifest path resolves from `package_manifest_path`,
`metadata.package_manifest_path`, or `<package_path>/manifest.json`.

## Output contract

For every completed evaluation (PASS, FAIL, or BLOCKED) the gate writes
exactly one file:

```
<output_dir>/<fs_safe(certification_id)>/commercial_acceptance_report.json
```

- `fs_safe` replaces `":"` with `"_"` (Windows-safe, deterministic).
- JSON is written with `json.dumps(data, sort_keys=True, indent=2) + "\n"`,
  UTF-8 encoding, LF line endings.
- Hard failures (`CommercialAcceptanceError`) write nothing.
- No other file is created, modified, or deleted.

## Model contracts

`COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION = 1`. All models are immutable
dataclasses reusing the Stage 4.1 `FrozenMap` (never a duplicate
implementation) and provide deterministic `to_dict()` (tuples → lists,
`FrozenMap` → plain dict, stable explicit key order).

### AcceptanceCheck

| Field | Type | Notes |
| --- | --- | --- |
| `check_name` | str | one of the check names below |
| `status` | str | `PASS` / `FAIL` / `BLOCKED` / `SKIPPED` |
| `severity` | str | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `INFO` |
| `evidence` | str \| None | artifact path inspected |
| `error_kind` | str \| None | machine-readable failure kind |
| `error_detail` | str \| None | human-readable failure detail |
| `metadata` | FrozenMap | deterministic extras |

### CommercialAcceptanceReport

`ok` (True only for overall PASS), `schema_version`, `certification_id`,
`run_id`, `delivery_id`, `created_at` (the injected string),
`overall_status`, `readiness_score` (int 0–100),
`checks: tuple[AcceptanceCheck, ...]`, `evidence_paths: tuple[str, ...]`
(sorted, local paths only), `blocking_reasons: tuple[str, ...]`,
`metadata: FrozenMap`.

### CommercialAcceptanceError

`ok` (always False), `schema_version`, `error_kind`, `error_detail`,
`failed_check`, `checks: tuple[AcceptanceCheck, ...]`, `metadata: FrozenMap`.

## Acceptance checks

| # | Check | Severity | PASS condition |
| --- | --- | --- | --- |
| 1 | `run_result_is_successful` | CRITICAL | commercial run `ok == true` (or all manifest steps successful); otherwise **BLOCKED** |
| 2 | `report_json_exists` | CRITICAL | `report_path` exists as a file |
| 3 | `delivery_package_exists` | CRITICAL | `package_path` exists as a directory |
| 4 | `commercial_run_manifest_exists` | HIGH | run manifest file exists |
| 5 | `package_manifest_exists` | HIGH | package manifest file exists |
| 6 | `required_delivery_files_exist` | CRITICAL | `report.json`, `report.md`, `qa_summary.md`, `improvement_plan.md`, `manifest.json` all exist in the package |
| 7 | `deterministic_timestamps` | MEDIUM | injected `created_at` and the run's `created_at` are explicit non-empty strings |
| 8 | `local_only_paths` | CRITICAL | no evidence path starts with `http://` or `https://` |
| 9 | `no_missing_blocking_evidence` | CRITICAL | all critical evidence paths exist |
| 10 | `readiness_score_threshold` | HIGH | `readiness_score >= min_readiness_score` |
| 11 | `video_asset_exists` (optional) | HIGH when `require_video=True`, else SKIPPED/INFO | `assets/video.mp4` exists in the package |
| 12 | `asset_folder_exists` (optional) | HIGH when `require_assets=True`, else SKIPPED/INFO | `assets/` directory exists in the package |

When check 1 is BLOCKED, evidence checks 2–6 and 9 are recorded as SKIPPED
(their evidence cannot meaningfully exist) and the overall status is BLOCKED.

## Readiness score rules

Deterministic integer 0–100. Start at 100; for each FAILed check subtract:
CRITICAL 100, HIGH 25, MEDIUM 10, LOW 3. Never below 0. SKIPPED and BLOCKED
checks subtract nothing. `readiness_score_threshold` is computed from all
prior checks and does not feed its own score.

## PASS / FAIL / BLOCKED rules

- Any BLOCKED check ⇒ `overall_status = BLOCKED`.
- Otherwise any CRITICAL FAIL ⇒ `overall_status = FAIL`.
- Otherwise PASS only if there is no CRITICAL/HIGH/MEDIUM failure **and**
  `readiness_score >= min_readiness_score`; otherwise FAIL.
- `ok == (overall_status == "PASS")`.
- `blocking_reasons` lists every BLOCKED check and every CRITICAL FAIL.

## Evidence path rules

- Evidence paths are the local filesystem paths the gate actually inspected
  (report, package, manifests, required deliverables, optional assets).
- They are recorded as a sorted tuple of strings.
- Any evidence path starting with `http://` or `https://` fails
  `local_only_paths`.

## Error kinds

| Kind | Meaning |
| --- | --- |
| `INVALID_ARGUMENTS` | missing/empty `created_at` or `output_dir`, URL path, bad `min_readiness_score` |
| `INPUT_NOT_FOUND` | run manifest path does not exist / is not a file; also used as check-level kind for missing evidence |
| `INVALID_RUN_RESULT` | unparseable manifest JSON, wrong input type, or missing required run fields |
| `ACCEPTANCE_FAILED` | check-level kind when the readiness threshold is not met |
| `OUTPUT_WRITE_FAILED` | the certification file could not be written |
| `VALIDATION_FAILED` | check-level kind for blocked runs, timestamp, and local-path violations |

## Determinism guarantees

- `created_at` is an explicit injected string; the gate never reads a real
  clock and never uses random or UUID.
- `certification_id` is caller-provided or derived as
  `commercial-acceptance-{run_id}`.
- Identical inputs produce byte-identical certification files.
- JSON output uses `sort_keys=True, indent=2`, UTF-8, LF.

## Local-only restrictions

- No network, cloud, SaaS, auth, payment, or LLM behavior.
- `http://` / `https://` paths are rejected as inputs and fail as evidence.
- Only Python stdlib (`json`, `pathlib`, `typing`, `dataclasses`) plus the
  Stage 4.5 models and the Stage 4.1 `FrozenMap`.

## Boundary rules

- Does not rebuild reports or packages, and does not re-run orchestration.
- Does not import the Stage 3 knowledge layer or any Stage 4 builder module.
- Does not mutate or delete any inspected artifact.
- Does not infer business recommendations or add monetization features.
- Does not change any Stage 4.1/4.2/4.3/4.4 contract.

## Example

```python
from pathlib import Path
from scos.commercial import run_commercial_acceptance_gate

result = run_commercial_acceptance_gate(
    commercial_run_result=Path("output/local-commercial-run-run_a1/commercial_run_manifest.json"),
    output_dir="output/certifications",
    created_at="2026-07-03T00:00:00Z",
)
if result.ok:
    print("READY:", result.certification_id, result.readiness_score)
else:
    print(result.to_dict())
```

Output file:
`output/certifications/commercial-acceptance-run_a1/commercial_acceptance_report.json`

## Out of scope

- SaaS, dashboards, web UI, customer portals.
- Payments, authentication, account management.
- LLM/AI evaluation of report content.
- Rebuilding or repairing Stage 4 artifacts.
- Network or cloud storage of certification results.
