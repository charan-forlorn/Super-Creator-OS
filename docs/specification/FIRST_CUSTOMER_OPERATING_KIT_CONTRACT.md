# First Customer Operating Kit Contract (Stage 4.6)

## Purpose

Stage 4.6 converts an **accepted** Stage 4.5 commercial acceptance result into a
deterministic local folder — the *First Customer Operating Kit* — that an operator
uses to serve the first real customer. It is an operating-kit layer only. It
inspects artifacts that already exist on the local filesystem, generates customer-
and operator-facing markdown documents plus a JSON kit manifest, and optionally
copies evidence. It never rebuilds reports, never rebuilds packages, never re-runs
any Stage 4 flow, never contacts the Stage 3 knowledge layer, and never mutates or
deletes any inspected artifact.

This is NOT SaaS, a dashboard, a web UI, a payment/auth/customer portal, email
sending, cloud upload, or LLM-generated sales copy.

## Architecture

```
commercial_acceptance_report.json  (Stage 4.5, accepted)
        │
        ▼
generate_first_customer_kit(...)
        │  validate arguments
        │  load + validate acceptance report
        │  confirm accepted (ok && overall_status == "PASS")
        │  resolve source artifacts via the Stage 4.4 run manifest
        │  prepare deterministic kit folder
        ▼
<output_dir>/<kit_id>/
   customer_kit_manifest.json + operating markdown + optional evidence/
```

The generator lives in `scos/commercial/customer_kit.py`; models in
`scos/commercial/customer_kit_models.py`. Both reuse the Stage 4.1 `FrozenMap`
(no duplicate implementation) and depend only on the Python standard library.

## Input adaptation (real Stage 4.5 schema)

The real Stage 4.5 artifact (`CommercialAcceptanceReport.to_dict()`) does **not**
carry `accepted`, `acceptance_id`, `checked_at`, or top-level artifact paths.
Stage 4.6 adapts to the real schema:

| Kit concept    | Source key in acceptance report          |
|----------------|-------------------------------------------|
| `acceptance_id`| `certification_id`                        |
| `accepted`     | `ok is True and overall_status == "PASS"` |
| `checked_at`   | `created_at`                              |
| `run_id`       | `run_id`                                  |
| `delivery_id`  | `delivery_id`                             |

Source artifact paths (report / package / package manifest) are **not** stored in
the acceptance report. They are read from the Stage 4.4 run manifest
(`commercial_run_manifest.json`), which is either passed explicitly via
`run_manifest_path` or auto-discovered from the acceptance report's
`evidence_paths` (the first entry whose filename is `commercial_run_manifest.json`,
chosen deterministically by sort order).

## Public API

```python
generate_first_customer_kit(
    *,
    acceptance_report_path: str | pathlib.Path,
    output_dir: str | pathlib.Path,
    customer_id: str,
    created_at: str,
    kit_id: str | None = None,
    customer_name: str | None = None,
    offer_name: str = "SCOS Commercial Delivery",
    overwrite: bool = False,
    copy_evidence: bool = True,
    run_manifest_path: str | pathlib.Path | None = None,
) -> CustomerKitResult | CustomerKitError
```

- `customer_id` and `created_at` are required non-empty strings.
- `created_at` is an explicit injected string; no real clock, random, or UUID is
  ever consulted.
- `http://` and `https://` paths are rejected for `acceptance_report_path`,
  `output_dir`, and `run_manifest_path`.
- `kit_id` is deterministic: used verbatim when provided, else derived as
  `first-customer-kit-{customer_id}`.
- Output folder is `<output_dir>/<kit_id>/` (with `:` replaced by `_`). If it
  exists and `overwrite=False`, a deterministic `OUTPUT_ALREADY_EXISTS` error is
  returned. With `overwrite=True`, only Stage 4.6-created files inside the kit
  folder are overwritten; no source artifact is ever deleted or modified.

## Output folder layout

```
<output_dir>/<kit_id>/
   customer_kit_manifest.json
   customer_intake_checklist.md
   operator_sop.md
   delivery_handoff.md
   acceptance_certificate.md
   pricing_offer_checklist.md
   customer_followup_checklist.md
   files_to_send.md
   evidence/                      (only when copy_evidence=True)
      acceptance_report.json
      commercial_run_manifest.json
      package_manifest.json
```

## `customer_kit_manifest.json` schema

Written with `json.dumps(..., sort_keys=True, indent=2)` + trailing newline.

| Key | Meaning |
|-----|---------|
| `schema_version` | `CUSTOMER_KIT_SCHEMA_VERSION` (1) |
| `customer_id` | provided customer id |
| `customer_name` | provided name, else falls back to `customer_id` |
| `kit_id` | resolved kit id |
| `acceptance_id` | acceptance report `certification_id` |
| `run_id` | run id |
| `delivery_id` | delivery id |
| `created_at` | injected kit timestamp |
| `source_acceptance_report_path` | inspected acceptance report path |
| `source_run_manifest_path` | resolved run manifest path |
| `source_report_path` | commercial report path (from run manifest) |
| `source_package_path` | delivery package directory (from run manifest) |
| `source_package_manifest_path` | package manifest path (from run manifest) |
| `generated_files` | sorted list of file names written into the kit folder |
| `metadata` | generator id, `overall_status`, `checked_at`, `copy_evidence`, `offer_name` |

## Generated markdown files

All markdown is produced from deterministic static templates — no LLM, no random
text, no current time, no sales claims beyond the provided
`customer_id`/`customer_name`/`offer_name`, and no inference from the artifacts
beyond fields explicitly present in them.

- `customer_intake_checklist.md` — pre-work checklist (identity, business goal,
  source materials, input readiness, delivery expectation, approval status).
- `operator_sop.md` — operator workflow (pre-run checks, run commercial delivery,
  run acceptance gate, generate customer kit, manual review, handoff).
- `delivery_handoff.md` — customer-facing handoff note (what is included, how to
  review, what to approve, next step).
- `acceptance_certificate.md` — human-readable certificate filled from the
  accepted report (acceptance id, run id, delivery id, checked at, acceptance
  status, and a required-checks summary derived from the report `checks`).
- `pricing_offer_checklist.md` — operator readiness checklist (offer name, price,
  scope, deposit/payment status placeholder, delivery date placeholder, follow-up
  owner placeholder). Checklist/template only — **no payment logic**.
- `customer_followup_checklist.md` — Day 0 / Day 1 / Day 3 / Day 7 follow-up flow.
- `files_to_send.md` — checklist referencing the Stage 4 delivery-package files and
  the operating-kit files.

## Evidence copy / reference behavior

- `copy_evidence=True` (default): copies the acceptance report, run manifest, and
  package manifest into `evidence/` via `shutil.copy2`.
- `copy_evidence=False`: copies nothing; the source paths are still referenced in
  `customer_kit_manifest.json`.

## Error kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `INVALID_ACCEPTANCE_REPORT`,
`ACCEPTANCE_NOT_PASSED`, `MISSING_SOURCE_ARTIFACT`, `OUTPUT_ALREADY_EXISTS`,
`OUTPUT_WRITE_FAILED`, `VALIDATION_FAILED`. Each is returned as a deterministic
`CustomerKitError` with `error_kind`, `error_detail`, `failed_step`, and metadata.

## Determinism guarantees

- No real clock, random, or UUID. `created_at` and `kit_id` fully determine
  time/identity-bearing outputs.
- Repeated runs of the same accepted report with the same arguments produce
  byte-identical manifest and markdown content.
- All JSON is UTF-8 with LF newlines and `sort_keys=True, indent=2`.

## Local-only restrictions & boundary rules

- Python standard library only (`json`, `pathlib`, `shutil`, `typing`,
  `dataclasses`) plus `FrozenMap` and `customer_kit_models`.
- No network / cloud / SaaS / auth / payment / LLM behavior.
- Does not call the Stage 3 knowledge layer, the Stage 4.1 report builder, the
  Stage 4.2 package builder, the Stage 4.4 orchestrator, or the Stage 4.5 gate.
- Does not alter any Stage 4.1/4.2/4.3/4.4/4.5 contract or output.
- Never mutates or deletes inspected artifacts; only writes inside the kit folder.

## Examples

```python
from scos.commercial import generate_first_customer_kit

result = generate_first_customer_kit(
    acceptance_report_path="out/cert/commercial-acceptance-run_a1/commercial_acceptance_report.json",
    output_dir="out/kits",
    customer_id="acme_co",
    created_at="2026-07-03T02:00:00Z",
    customer_name="Acme Co.",
    offer_name="Launch Video Package",
)
if result.ok:
    print(result.manifest_path)
```

## Out of scope

SaaS, dashboards, web UIs, customer portals, authentication, payment processing or
validation, email sending, cloud upload, LLM-generated copy, rebuilding any Stage 4
artifact, and any mutation of upstream artifacts.
