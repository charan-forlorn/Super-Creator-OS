# File Snapshot Refresh Transport Contract

Stage: 8.2 - File Snapshot Refresh Transport Foundation.

## Purpose

Stage 8.2 creates the first local-only file snapshot refresh transport
foundation for the Control Center. It lets an operator or caller manually
build and, when explicitly requested, write a deterministic local JSON
snapshot from approved read surfaces.

This is not live transport. It creates no server, route, socket, file watcher,
timer, polling loop, frontend feature, adapter activation, command execution,
network call, or cloud behavior.

## Architecture

```text
Stage 7 read/query surface
  -> Stage 7 operator health/activity read models
  -> Stage 7 approval-aware command view snapshot
  -> Stage 8.1 transport activation decision evidence
  -> FileSnapshotRefreshTransport
  -> explicit local JSON snapshot file
```

The snapshot is generated only when the caller invokes
`build_file_snapshot_transport_payload(...)` or
`refresh_file_snapshot_transport(...)`.

## Non-Goals

- no WebSocket
- no SSE/EventSource
- no polling
- no timers or background workers
- no file watchers
- no localhost HTTP route
- no backend socket server
- no Next.js API route
- no frontend UI
- no command execution
- no adapter activation
- no AI dispatch
- no API-key or secret handling
- no external APIs
- no cloud, SaaS, payment, CRM, customer portal, Buffer, or external
  publishing behavior

## Public API

```python
build_file_snapshot_transport_payload(
    *,
    repo_root,
    checked_at: str,
    include_read_surface: bool = True,
    include_operator_health: bool = True,
    include_approval_commands: bool = True,
    include_transport_decision: bool = True,
    metadata=None,
) -> FileSnapshotTransportResult | FileSnapshotTransportError
```

Builds the deterministic payload and manifest in memory only. It writes no
files.

```python
refresh_file_snapshot_transport(
    *,
    repo_root,
    output_path,
    checked_at: str,
    include_read_surface: bool = True,
    include_operator_health: bool = True,
    include_approval_commands: bool = True,
    include_transport_decision: bool = True,
    metadata=None,
    overwrite: bool = False,
) -> FileSnapshotTransportResult | FileSnapshotTransportError
```

Writes exactly one deterministic UTF-8 JSON file to the explicit local
`output_path` when validation passes and no required-source blockers exist.

```python
validate_file_snapshot_transport_boundary(
    *,
    repo_root,
    checked_at: str,
) -> dict
```

Returns deterministic boundary evidence and static forbidden-behavior findings.

## Model Schema

Models are frozen dataclasses with deterministic `to_dict()` output:

- `FileSnapshotTransportSource`
- `FileSnapshotTransportManifest`
- `FileSnapshotTransportResult`
- `FileSnapshotTransportError`
- `FrozenMap`

`FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION = 1`.

## Snapshot JSON Schema

The written JSON document contains:

- `schema_version`
- `snapshot_id`
- `generated_at`
- `transport_mode`
- `manifest`
- `payload`
- `warnings`
- `blockers`

`transport_mode` is always `FILE_SNAPSHOT_REFRESH`.

## Manifest Schema

The manifest contains:

- `schema_version`
- `snapshot_id`
- `generated_at`
- `transport_mode`
- `repo_root`
- `output_path`
- `source_count`
- `payload_sha256`
- `sources`
- `warnings`
- `blockers`
- `metadata`

Every source records its type, status, required flag, checksum, warnings,
blockers, and metadata.

## Deterministic ID and Checksum Rules

- `checked_at` is caller-supplied.
- No clock, random, or UUID source is used.
- `snapshot_id` is SHA-256-derived from schema version, `checked_at`,
  transport mode, source statuses/checksums, and normalized output path when
  writing.
- `payload_sha256` is computed from stable JSON payload text.
- JSON writes use sorted keys, indentation, UTF-8, LF newlines, and a trailing
  newline.

## Allowed Local Paths

- `repo_root` must be a local existing directory.
- `output_path` must be local and resolve inside `repo_root`.
- URL-like paths are rejected, including `http://`, `https://`, `ws://`,
  `wss://`, `ftp://`, and `file://`.
- Traversal outside `repo_root` is rejected.

## Output Behavior

- `build_file_snapshot_transport_payload(...)` writes nothing.
- `refresh_file_snapshot_transport(...)` writes exactly one JSON file.
- Parent directories for the explicit output file may be created.
- No source artifact, SQLite database, JSONL log, approval store, event log,
  queue, or audit ledger is mutated.

## Missing-Source Behavior

- Missing required sources create blockers and `NO_GO`.
- Missing optional sources create warnings.
- Optional source blockers are captured as source metadata and warnings where
  possible; they do not crash the transport foundation.

Required sources:

- Stage 7 read surface
- Stage 8.1 transport decision evidence

Optional sources:

- operator health/activity read models
- approval-aware command views
- static fallback evidence

## Overwrite Behavior

If `output_path` exists and `overwrite=False`, refresh returns
`FILE_SNAPSHOT_OUTPUT_EXISTS` and writes nothing. If `overwrite=True`, refresh
may replace the same explicit output file with deterministic content.

## Security Rules

- manual refresh only
- explicit output path only
- local path containment only
- read-only source access
- no command execution
- no adapter activation
- no network/cloud/API behavior
- no secrets or credentials
- no frontend behavior

## Forbidden Behavior

Stage 8.2 source must not introduce WebSocket, EventSource, timers, polling,
fetch/XHR/axios behavior, subprocess or shell calls, HTTP servers, socket
servers, external requests, adapters, API keys, secrets, or tokens.

## Rollback Strategy

Rollback is a single-stage revert of the Stage 8.2 files. Since Stage 8.2 has
no schema migration, no background process, and no persistent source-store
mutation, rollback does not require data repair. Operators can delete generated
snapshot files manually if they no longer want them.

## Stage 8.3 Handoff

Stage 8.3 should remain policy-only for runtime credentials and secrets. It
must not use the file snapshot transport as an API-key, secret, adapter, or
external integration channel.
