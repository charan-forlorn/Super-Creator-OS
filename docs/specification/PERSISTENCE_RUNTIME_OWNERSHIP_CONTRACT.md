# Persistence Runtime Ownership Contract

## Scope

This contract records the authoritative owner, lifecycle, mutation model, and
recovery behavior for the mutable SCOS runtime persistence namespaces that are
present in the repository today. It does not migrate live operator data.

## Ownership Map

| Resource | Backend | Class | Authoritative writer | Readers | Mutation model | Recovery behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `memory/database.json` | JSON array | Persistent canonical runtime data, currently tracked | `integrations/learning/memory_writer.safe_append` through `memory_store.append_canonical_record` or approved adapters | Learning/evaluator/recommendation readers | Advisory sidecar lock, validate existing database, backup, atomic replace, integrity marker | Malformed or integrity-mismatched state blocks writes; operator must inspect from backup. Existing valid state remains readable. |
| `memory/runtime/practice-render.jsonl` | JSONL | Runtime-only local learning journal | `integrations/learning/runtime_journal.append_runtime_record` through `memory_store.append_runtime_record` and `scripts/practice_render_loop.py` | Explicit runtime or combined memory reads | Advisory sidecar lock, deterministic record id, append + flush/fsync, integrity marker | Malformed lines or marker mismatch block writes; no truncation or repair is attempted. |
| `memory/telemetry.json` | JSON array | Persistent observed telemetry sidecar | `integrations/learning/telemetry.append_telemetry` through `telemetry_capture.capture` or telemetry CLI | Telemetry joins/evaluators | Advisory sidecar lock, validate existing store, backup, atomic replace | Missing file bootstraps as empty; malformed or non-array state fails closed and is not rewritten. |
| `memory/jobs.jsonl` | JSONL | Persistent local revenue/job tracker | `scripts/revenue_ops.add_job` and `scripts/revenue_ops.update_job` | Revenue summaries/dashboard | Advisory sidecar lock; appends flush/fsync; updates use locked atomic replace | Missing file bootstraps as empty; malformed/non-object lines fail closed and preserve bytes. |
| `scos/work/control_center/state/control_center.sqlite3` | SQLite WAL | Generated local Control Center durable state | `scos/control_center/sqlite_state_store.SQLiteStateStore` through repository/facade callers | Control Center snapshots/health/read surfaces | SQLite transactions, WAL mode, parameterized inserts, duplicate primary-key rejection | Malformed/unreadable DB surfaces storage errors or health blockers; recovery is operator removal of generated `scos/work` state. |
| `scos/work/control_center/events/command_events.jsonl` | JSONL | Generated local Control Center event log | `scos/control_center/event_log.append_command_event` | Command runner/read surfaces/backend health | Shared command-queue JSONL writer: advisory sidecar lock, append + flush/fsync | Missing file reads empty; malformed line fails closed on read; no repair. |
| `scos/work/control_center/queue/approved_commands.jsonl` | JSONL | Generated local Control Center command queue | `scos/control_center/command_queue.append_approved_command` | Command runner/read surfaces/backend health | Advisory sidecar lock, append + flush/fsync | Missing file reads empty; malformed line fails closed on read; no repair. |

## Path Resolution

Default production paths are derived from module locations or documented
repository-relative paths, not from the caller's current working directory.
Tests must pass explicit temporary paths or monkeypatch defaults to temporary
roots. No test may write to the live `memory/` namespace.

## Tracked Runtime Database Decision

`memory/database.json` is still both a mutable runtime database and a tracked
repository file. Cohort 9E deliberately retains that behavior for compatibility:
moving live writes to an ignored runtime location would require an explicit live
data migration and an operator rollback procedure. The safer current boundary is:

- preserve existing valid tracked state;
- route all canonical writes through `memory_writer.safe_append`;
- document runtime-only practice state separately in `memory/runtime/`;
- keep tests isolated from the live file;
- treat dirty tracked live data as operator-owned when explicitly authorized.

Adding `memory/database.json` to `.gitignore` while it remains tracked would not
change Git ownership and is not a persistence fix.

## Conflict and Concurrency Model

JSON and JSONL stores use the existing stdlib advisory sidecar lock. This proves
serialization only for in-repository writers that use the shared boundary. It is
not a mandatory filesystem lock against arbitrary external editors. Out-of-band
writes are detected for canonical memory and the practice runtime journal via
integrity markers; other stores fail closed when malformed state is encountered.

SQLite state relies on SQLite WAL and transaction semantics. It does not use a
second repository lock.

## Startup, Shutdown, and Restart

There is no daemon owner for these stores. Ownership is acquired per mutation
when a writer opens the store and, where applicable, takes the sidecar lock.
Shutdown is release of the file handle/lock or SQLite connection. Restart reads
from disk and validates the existing store before accepting new mutations.

## Health and Read-Only Surfaces

Control Center health/read-surface code must remain read-only: it may inspect
SQLite/JSONL artifacts and report missing, malformed, degraded, unavailable, or
unknown states, but it must not initialize stores or create replacement state as
a side effect of health reporting.

## Known Limitations

- `memory/database.json` remains tracked live data until an explicit migration is
authorized.
- JSON/JSONL locks are advisory and protect cooperating SCOS writers only.
- Revenue job updates rewrite the small JSONL projection atomically but are not
append-only historical events.
- Missing runtime sidecars bootstrap as empty only where documented; malformed
state does not.
