# Commercial CLI Contract — SCOS Stage 4.3

## Purpose

The Local Commercial CLI is a thin, deterministic, **local-only** command-line
wrapper over the Stage 4.1 commercial report builder and the Stage 4.2 delivery
package generator. It lets an operator build reports, assemble delivery packages,
and validate package inputs without writing Python.

It adds **no** business logic. It performs no network, cloud, SaaS, auth, payment,
or LLM behavior, and mutates no source artifacts.

Entrypoint:

```
python -m scos.commercial.cli <command> [options]
```

`COMMERCIAL_CLI_SCHEMA_VERSION = 1`.

## Commands

| Command    | Purpose                                                             |
|------------|--------------------------------------------------------------------|
| `version`  | Print CLI schema version and the supported command list.           |
| `report`   | Build a Stage 4.1 commercial report from a persisted knowledge index. |
| `package`  | Build a Stage 4.2 delivery package from a `report.json`.           |
| `validate` | Validate package inputs and print a would-write plan; writes nothing. |

A subcommand is required. Omitting it, or using an unknown one, is an argparse
usage error (exit 2).

## Arguments

### `version`
No arguments.

### `report`
Required: `--index-path`, `--report-type`, `--output`, `--created-at`.
Conditional: `--run-id` (required for `--report-type run_summary`).
Optional: `--qa-status` (default `unknown`).

Only `run_summary` is supported by the Stage 4.1 builder. `style_summary`,
`portfolio`, and `system` are rejected as `INVALID_ARGUMENTS` with detail
`"report-type not supported by Stage 4.1 builder"`.

### `package`
Required: `--report-json`, `--output-dir`, `--created-at`.
Optional: `--delivery-id`, `--video-path`, `--source-manifest-path`, `--overwrite`.

### `validate`
Required: `--report-json`, `--output-dir`, `--created-at`.
Optional: `--video-path`, `--source-manifest-path`.

## stdout JSON contract

All commands print JSON only to stdout via `json.dumps(obj, sort_keys=True, indent=2)`.

**Success (report / package / validate):**

```json
{
  "ok": true,
  "command": "...",
  "schema_version": 1,
  "output_path": "...",
  "delivery_id": "...",
  "report_id": "...",
  "metadata": {}
}
```

`delivery_id` is `null` for `report`. `validate` returns a `metadata.would_write`
plan (planned `delivery_id`, `package_dir`, and file list).

**Failure:**

```json
{
  "ok": false,
  "command": "...",
  "schema_version": 1,
  "error_kind": "...",
  "error_detail": "...",
  "metadata": {}
}
```

`version` uses a distinct fixed shape:

```json
{
  "ok": true,
  "cli_schema_version": 1,
  "supported_commands": ["package", "report", "validate", "version"]
}
```

## Exit codes

| Code | Meaning                                                            |
|------|-------------------------------------------------------------------|
| `0`  | Success.                                                           |
| `1`  | Expected validation/runtime failure (deterministic error JSON).   |
| `2`  | Argparse usage failure (missing/unknown command or argument).     |

Expected failures never emit a traceback; they always return the failure JSON.

## Determinism guarantees

- All JSON is emitted with `sort_keys=True, indent=2`.
- Written report files use UTF-8 with LF newlines.
- Timestamps come only from `--created-at`, converted via
  `_now_fn(created_at)` into a zero-argument callable returning that exact string.
- No real clock, no UUID, no randomness anywhere in the CLI.

## Boundary rules

- The Stage 3.9 knowledge access layer (`IndexStore`, `KnowledgeService`) and the
  Stage 4.1 `build_commercial_report` are imported **lazily inside `_cmd_report`
  only**. `scos/knowledge` is inserted on `sys.path` there and nowhere else.
- `version`, `package`, and `validate` never import the knowledge layer.
- `package` uses only `create_delivery_package` (Stage 4.2) and the commercial
  models; its source contains neither `KnowledgeService` nor `build_commercial_report`.
- `cli.py` contains none of the forbidden lower-layer or network tokens
  (`KnowledgeIndex`, `KnowledgeQueryEngine`, `KnowledgeExplainEngine`,
  `KnowledgeInsightEngine`, `query_engine`, `explain_engine`, `insight_engine`,
  `requests`, `httpx`, `urllib.request`, `boto3`, `socket`, `http.client`,
  `openai`, `anthropic`).

## Local-only restrictions

- Any path beginning with `http://` or `https://` is rejected as
  `INVALID_ARGUMENTS`. All paths are local filesystem paths.
- `validate` never creates directories and never writes files.
- `report` / `package` create output parents only as required.
- The CLI never deletes files directly; the only removal is Stage 4.2's guarded
  overwrite of an existing package directory (via `--overwrite`).

## Error kinds (9)

| Error kind           | When                                                        |
|----------------------|-------------------------------------------------------------|
| `INVALID_COMMAND`    | Command dispatch fallthrough (no handler resolved).         |
| `INVALID_ARGUMENTS`  | URL path, unsupported report-type, or missing `--run-id`.   |
| `INPUT_NOT_FOUND`    | `package` report-json does not exist.                       |
| `INVALID_REPORT_JSON`| report-json unparseable or missing required fields.         |
| `INVALID_INDEX_PATH` | index path missing/unreadable or index fails to load.       |
| `REPORT_BUILD_FAILED`| Stage 4.1 builder returned a `CommercialReportError`.       |
| `PACKAGE_BUILD_FAILED`| Stage 4.2 returned a `DeliveryPackageError` (kind carried). |
| `OUTPUT_WRITE_FAILED`| OSError writing the report output.                          |
| `VALIDATION_FAILED`  | Any `validate` precondition failed.                         |

## Examples

```bash
# version
python -m scos.commercial.cli version

# report (run_summary only)
python -m scos.commercial.cli report \
  --index-path scos/work/knowledge/index.json \
  --report-type run_summary --run-id run_a1 \
  --output out/report.json --created-at 2026-07-02T00:00:00Z --qa-status PASS

# package
python -m scos.commercial.cli package \
  --report-json out/report.json --output-dir out/deliveries \
  --created-at 2026-07-02T00:00:00Z --overwrite

# validate (writes nothing)
python -m scos.commercial.cli validate \
  --report-json out/report.json --output-dir out/deliveries \
  --created-at 2026-07-02T00:00:00Z
```

## Out of scope

No SaaS, no authentication, no payment, no customer portal, no network or cloud
calls, no LLM calls, no source artifact mutation, no Certified Core changes, and
no changes to the Stage 3.9 knowledge implementation or the Stage 4.1 / 4.2
contracts. Report types other than `run_summary` are out of scope until the
Stage 4.1 builder supports them.
