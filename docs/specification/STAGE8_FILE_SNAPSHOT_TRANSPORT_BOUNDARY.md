# Stage 8 File Snapshot Transport Boundary

This boundary governs Stage 8.2 file snapshot refresh transport.

## Manual Only

File snapshot refresh happens only when the caller invokes
`refresh_file_snapshot_transport(...)`. There is no implicit refresh during
import, test discovery, UI load, or background runtime.

## No Live Transport

Stage 8.2 introduces no:

- WebSocket
- SSE/EventSource
- polling
- timers
- background workers
- file watchers
- localhost HTTP routes
- backend socket servers
- Next.js API routes

The generated JSON file is a local artifact for future consumers, not a live
sync channel.

## No Frontend Live Binding

Stage 8.2 does not modify `apps/control-center/` and does not bind the
frontend to the snapshot file. Any future UI consumption requires a separate
approved Stage 8 item with its own acceptance criteria and tests.

## No Adapter Activation

The snapshot may include Stage 8.1 transport decision evidence, but it must not
activate ChatGPT, Claude Code, Codex, Hermes, or any other adapter. It must not
dispatch AI work.

## No API-Key or Secret Handling

Stage 8.2 does not read, write, store, log, or expose credentials. It adds no
API-key flow and no secret store.

## No Network, Cloud, SaaS, Payment, CRM, or Buffer

Stage 8.2 is local-only. It adds no network calls, external APIs, cloud
services, SaaS behavior, payment, CRM, customer portal, Buffer integration, or
external publishing behavior.

## Allowed Local File Boundary

Allowed writes are limited to exactly one explicit local JSON snapshot file
under `repo_root`. Source stores remain read-only:

- no SQLite mutation
- no JSONL append
- no event log write
- no approval or audit ledger write
- no queue write
- no schema migration

Output paths must reject URL-like strings and traversal outside `repo_root`.

## Future Upgrade Gates

Before any future live transport, Stage 8 must add a new explicit gate for the
specific transport. A file snapshot foundation does not authorize HTTP,
WebSocket, SSE/EventSource, polling, timers, file watchers, background workers,
or frontend runtime binding.
