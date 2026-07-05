# Control Center Command API — Design Only (Stage 4.18)

**Status: design document. Nothing in this file is implemented in Stage 4.**
Stage 4.18 deliberately ships no API routes, no backend server, no database,
no WebSocket, no live integration. This design exists so Stage 5 can
implement the command boundary without re-deriving it.

## Purpose

Define how the local Control Center UI will eventually issue commands to the
SCOS engine (dispatch work, review results, approve gates) through a single
deterministic, auditable command boundary — instead of the UI reading static
JSON snapshots as it does in Stage 4.

## Non-goals

- No CRM, payment, billing, invoicing, SaaS, or customer portal.
- No cloud service, no remote access, no multi-tenant anything.
- No autonomous outward-facing actions: every command that could affect a
  human outside the machine requires `operator_approval`.
- No replacement of the Stage 4 artifact contracts; commands produce and
  consume the same deterministic JSON artifacts.

## Command boundary

One boundary, one direction: the UI submits **commands**; the engine emits
**events**. The UI never mutates engine state directly and never reaches
around the boundary to files it does not own. All state remains local,
deterministic JSON on disk; the boundary is a thin, replayable layer over
it.

## Future command types

| Command | Effect (Stage 5) |
| --- | --- |
| `dispatch` | Enqueue a unit of engine work (e.g. run a commercial stage) with explicit inputs. |
| `review` | Record an operator review verdict for a produced artifact. |
| `merge` | Accept a reviewed result into the durable project state. |
| `rollback` | Restore the prior durable state for a named artifact/stage, using manifest checksums as proof of the restore point. |
| `event_stream` | Subscribe to the ordered event log for a run (read-only). |
| `operator_approval` | Human sign-off gate; required before any outward-facing action a command could imply. |

## Deterministic event contract (sketch)

Commands and events are stable JSON objects, serialized with the Stage 4.18
`stable_json_dumps` rules (sorted keys, LF, trailing newline).

```json
{
  "command_id": "cmd-<sha256-of-canonical-payload>",
  "command_type": "dispatch",
  "schema_version": 1,
  "issued_at": "<caller-supplied ISO-8601>",
  "payload": { "stage": "4.x", "inputs": {} },
  "requires_operator_approval": true
}
```

```json
{
  "event_id": "evt-<sha256>",
  "command_id": "cmd-...",
  "sequence": 7,
  "event_type": "check_completed",
  "schema_version": 1,
  "occurred_at": "<engine-recorded ISO-8601>",
  "body": { "check": { } }
}
```

Rules: ids are content-derived (SHA-256), never random; `sequence` is a
strictly increasing integer per command; event bodies reuse the shared
domain models (`CommercialCheck`, `CommercialBlocker`,
`CommercialArtifactReference`, `CommercialManualAction` from
`scos.commercial.domain_models`); replaying the same command list yields the
same event log.

## Local-first design

- Transport in Stage 5 starts as an append-only local file queue (commands
  in, events out) readable without any server; a localhost-only HTTP layer
  is an optional later convenience, never a requirement.
- No cloud dependency: everything must work offline on the operator's
  machine.
- The event log doubles as the immutable audit log described in
  `docs/security/SECURITY_HARDENING_BASELINE.md` (hash-chained records).

## Security considerations

- Single local operator; no network listener by default. If a localhost
  listener is added, it binds to `127.0.0.1` only.
- Every command is validated with the Stage 4.18 validation helpers
  (required keys, manual-only flags, sensitive-metadata rejection, path
  containment for any path-bearing payload).
- `rollback` and `merge` are gated by `operator_approval` and verified
  against manifest checksums before and after.
- Command handlers may not delete outside their contained output roots
  (`validate_path_containment`).

## Why Stage 4.18 does not implement this

Stage 4 ends at 4.19 as a manual-only commercial foundation. Implementing a
backend now would (a) add a live mutation surface before the audit log and
approval gates exist, (b) violate the Stage 4 hard rules (no backend/API,
no database, no WebSocket, no polling, no real agent dispatch), and (c)
freeze an API shape before Stage 5's real dispatch requirements are known.
Designing now and implementing later costs one document; implementing now
and re-doing it later costs a migration.

## Stage 5 implementation prerequisites

1. Stage 4.19 release gate passed (full regression + security baseline).
2. Immutable audit log implemented (hash-chained, append-only).
3. Operator identity/approval mechanism decided.
4. Command/event schema finalized from this sketch and versioned
   (`schema_version` starts at 1, additive evolution only).
5. Replay test: identical command lists must produce identical event logs
   before any UI is wired to the boundary.
