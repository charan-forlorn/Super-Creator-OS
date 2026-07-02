# Delivery Package Contract

Status: Stage 4.2 implemented contract
Schema version: 1

## Purpose

The Delivery Package Contract defines the deterministic, local client-
deliverable folder generated from one Stage 4.1 `CommercialReport`. The
generator turns an existing commercial report (plus optional local asset
files) into a folder that can be manually sent to a client. It does not create
knowledge, infer recommendations, call an LLM, upload data, perform network
requests, or serve a web dashboard.

## Folder Layout

Given a base output directory (by convention `scos/work/deliveries/`), one
package is created per delivery:

```
<output_dir>/<package_folder>/
  manifest.json
  report.json
  report.md
  qa_summary.md
  improvement_plan.md
  assets/
    video.mp4              (optional, copied only if provided)
    source_manifest.json   (optional, copied only if provided)
```

The default `delivery_id` is deterministic:
`delivery:<report_type>:<source_run_id>`.

Windows forbids `:` in file names, so the on-disk `<package_folder>` is the
`delivery_id` with each `:` replaced by `_` (e.g.
`delivery_run_summary_run_a1`). The manifest always records the raw
`delivery_id`.

## Manifest Schema

`manifest.json` serializes `DeliveryPackageManifest` with stable key order:

- `delivery_id`
- `schema_version` (`DELIVERY_PACKAGE_SCHEMA_VERSION = 1`)
- `created_at` (from injected `now_fn` only)
- `source_run_id`
- `style_id`
- `report_id`
- `package_status` (`complete` on success)
- `files` — list of `{path, kind, required}` sorted by `path`; kinds:
  `report_json`, `report_markdown`, `qa_summary`, `improvement_plan`,
  `video` (optional), `source_manifest` (optional)
- `checksums` — mapping of relative file path to SHA256 hex digest
- `metadata` — builder identity and report projection facts

Paths in `files` and `checksums` are package-relative with forward slashes.

## Deterministic Guarantees

- `created_at` comes only from the injected `now_fn`; no wall clock is read.
- `report.json` is exactly `CommercialReport.to_dict()` serialized with sorted
  keys.
- `report.md`, `qa_summary.md`, and `improvement_plan.md` are rendered purely
  from report fields; identical inputs produce byte-identical files.
- If no evidence-backed recommendations exist, the deterministic line
  "No evidence-backed recommendations available." is written.
- If no evidence-backed risks exist, the deterministic line
  "No evidence-backed risks available." is written.
- Manifest file ordering is stable (sorted by path); manifest serialization has
  fixed key order.

## Checksum Behavior

SHA256 digests are computed for every generated and copied file and recorded in
`checksums`. `manifest.json` itself is written last and is not self-
checksummed (a file cannot contain its own hash). Checksum computation failure
returns `CHECKSUM_FAILED`.

## Overwrite Behavior

- If the package directory already exists and `overwrite=False`, the generator
  returns `PACKAGE_ALREADY_EXISTS` and writes nothing.
- With `overwrite=True`, only the computed package directory is deleted and
  regenerated — never the base output directory, never parent directories, and
  never any source file.

## Path Safety

Every generated or copied file resolves inside the computed package directory.
A `delivery_id` that resolves outside the base output directory (path
traversal) is rejected with `INVALID_OUTPUT_DIR`. If the base output directory
exists as a file it is rejected; if missing it is created.

## Error Contract

Expected failures return a frozen `DeliveryPackageError`
(`ok=False, error_kind, error_detail, metadata`), never raw exceptions:

- `INVALID_REPORT` — input is not a Stage 4.1 `CommercialReport`
- `INVALID_OUTPUT_DIR` — unusable base directory or unsafe package path
- `PACKAGE_ALREADY_EXISTS` — package dir exists and `overwrite=False`
- `SOURCE_VIDEO_NOT_FOUND` — explicit `video_path` missing or not a file
- `SOURCE_MANIFEST_NOT_FOUND` — explicit `source_manifest_path` missing or not
  a file
- `WRITE_FAILED` — package files could not be written or replaced
- `CHECKSUM_FAILED` — checksum computation failed

Optional inputs left as `None` never fail; only explicitly provided asset
paths are validated.

## Boundary Rules

Delivery package code must not import or consume:

- `KnowledgeIndex`, `KnowledgeQueryEngine`, `KnowledgeExplainEngine`,
  `KnowledgeInsightEngine`
- `query_engine`, `explain_engine`, `insight_engine`
- lower-layer knowledge model modules or raw knowledge artifacts
- any network, cloud, or SaaS SDK

It may consume only Stage 4.1 commercial report models
(`scos/commercial/report_models.py`), Stage 4.2 package models, and the Python
standard library (`pathlib`, `json`, `hashlib`, `shutil`, `dataclasses`,
`typing`).

## Immutability And Serialization

All package models are frozen dataclasses. Nested payloads are tuple-backed
(`FrozenMap`) at construction. `to_dict()` emits plain JSON-safe dictionaries
and lists with stable ordering; internal state is never exposed as mutable
dict/list.

## Out Of Scope

Stage 4.2 does not implement SaaS behavior, web UI or dashboards, cloud
delivery or storage, network transfer, auth, payment, LLM-generated report
writing, inferred recommendations, or mutation of any source artifact.
