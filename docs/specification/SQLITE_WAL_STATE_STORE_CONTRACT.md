# SQLite WAL State Store Contract (Stage 6.3)

## Why sqlite3 stdlib

SCOS is local-first and stdlib-only for backend/local state code. `sqlite3`
ships with CPython, requires no package install, no dependency changes, and
no network access -- it satisfies the durable-state requirement (a real
transactional file-backed store, not another JSON/JSONL append log) while
keeping the project's zero-new-dependency constraint intact.

## Why WAL Mode

Write-Ahead Logging is required (not just allowed) because:

- It allows concurrent readers while a write transaction is open, which
  matters once Stage 6.4 reads state while a write is committing.
- It is more crash-resistant for the operator's local machine (a single
  `fsync`-backed WAL file, not overwriting the main database page-by-page).
- It is the standard recommendation for any local SQLite file that expects
  more than one short-lived connection over its lifetime.

`SQLiteStateStore` sets `PRAGMA journal_mode=WAL` on every connection it
opens (idempotent - SQLite persists WAL mode in the database file itself
after the first call) and `health_snapshot()` re-reads `PRAGMA journal_mode`
so `wal_enabled` is always verified against the live database, not assumed.

## PRAGMA Configuration

Applied via `sqlite_state_schema.get_pragmas()` on every connection:

| PRAGMA | Value | Reason |
| --- | --- | --- |
| `journal_mode` | `WAL` | Required durability/concurrency mode |
| `synchronous` | `NORMAL` | Safe with WAL; avoids the extra fsync cost of `FULL` while still durable across app crashes |
| `foreign_keys` | `ON` | Defensive; no FK constraints are declared yet, but enabling now avoids a silent behavior change later |
| `busy_timeout` | `5000` | Local single-operator use; avoids `SQLITE_BUSY` errors racing a slow writer instead of surfacing a deterministic error |

## Table Schema

Six tables, defined in `sqlite_state_schema.get_schema_statements()`:

- `state_schema` (schema_name PK, schema_version, applied_at, metadata_json)
- `commands` (command_id PK, command_type, status, request_id, session_id, payload_json, created_at, updated_at, metadata_json)
- `sessions` (session_id PK, task_id, agent_id, runtime_id, status, created_at, updated_at, metadata_json)
- `events` (event_id PK, event_type, source, subject_type, subject_id, payload_json, created_at, sequence, metadata_json)
- `approvals` (approval_id PK, approval_type, subject_type, subject_id, decision, decided_by, decided_at, reason, metadata_json)
- `results` (result_id PK, result_type, subject_type, subject_id, verdict, payload_json, created_at, metadata_json)

All statements use `CREATE TABLE IF NOT EXISTS`, so `initialize()` is safe
to call repeatedly against an existing database.

## Indexes

Defined in `sqlite_state_schema.get_index_statements()`:

- `events(subject_type, subject_id, sequence)` and `events(created_at)`
- `commands(status)` and `commands(session_id)`
- `sessions(status)`
- `approvals(subject_type, subject_id)` and `approvals(decision)`
- `results(subject_type, subject_id)` and `results(verdict)`

These match the query patterns the store and repository actually issue
(`list_*` filtering by status/subject, `list_events` ordering by sequence).

## Path Safety

`sqlite_state_schema.validate_database_path(repo_root, db_path)`:

- Rejects any path recognizable as a URL (`http://`, `https://`, `ftp://`,
  `ws://`, `wss://`), including the collapsed form `pathlib.Path` produces
  on Windows when a URL string is wrapped in `Path(...)` before validation
  (`https:\example.com`) -- matched against the same known scheme list, and
  never against a bare single-letter drive prefix (`C:\...`), so real
  Windows absolute paths are never misclassified as URLs.
- Resolves `db_path` against `repo_root` (if relative) and requires the
  resolved path to be inside the resolved `repo_root`, rejecting `..`
  traversal that would escape it.
- The default path, `scos/work/control_center/state/control_center.sqlite3`,
  always resolves inside the repo and under `scos/work/`, matching the
  project convention that generated/local-only state lives under `scos/work/`.

`SQLiteStateStore.__init__` calls this validator immediately and raises
`ValueError` on an unsafe path before any file or directory is touched.

## Transaction Strategy

Every write method (`insert_command`, `insert_session`, `append_event`,
`insert_approval`, `insert_result`, and `initialize`) opens a connection,
wraps its statement(s) in `with connection:` (commit on success, rollback
on exception), and closes the connection before returning. There is no
long-lived connection held across calls, and no implicit autocommit gap.

## Deterministic Ordering

- `commands`: `ORDER BY created_at ASC, command_id ASC`
- `sessions`: `ORDER BY created_at ASC, session_id ASC`
- `events`: `ORDER BY sequence ASC, event_id ASC`
- `approvals`: `ORDER BY decided_at ASC, approval_id ASC`
- `results`: `ORDER BY created_at ASC, result_id ASC`

The secondary key on each type's own id guarantees a total order even when
two rows share the same timestamp/sequence.

## Duplicate Handling

Every table's primary key is the natural id (`command_id`, `session_id`,
`event_id`, `approval_id`, `result_id`). Inserting a duplicate id raises
`sqlite3.IntegrityError`, which every insert method catches and converts to
`DurableStateError(error_kind="duplicate_id")` -- callers never see a raw
`sqlite3` exception.

## Corruption / Recovery Notes

If the SQLite file or its `-wal`/`-shm` sidecars become corrupted (e.g. the
process is killed mid-write on a filesystem without proper fsync), the
store surfaces this as `DurableStateError(error_kind="storage_unavailable")`
from any store method that catches `sqlite3.Error`. Because the file lives
entirely under `scos/work/control_center/state/` (generated, non-Certified
Core, not committed), recovery is: stop the process, delete the database
file and its sidecars, and re-run `initialize()`. No other part of SCOS
depends on this database surviving a wipe.

## No ORM / No External Dependency

All queries in `sqlite_state_store.py` are written as parameterized SQL
strings (`?` placeholders) executed via `sqlite3.Connection.execute()`.
There is no ORM layer, no query builder, and no third-party dependency of
any kind -- only `sqlite3` from the Python standard library.
