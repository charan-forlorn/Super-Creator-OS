# Phase 18 — Production Readiness Gate — 2026-09-28

Status: BLOCKED / NOT_READY

## Gates
- G1 reproducible local BrightBean build: historical PASS at pinned baseline; current source commit b2ec479 is committed but not promoted as a new release artifact.
- G2 secure deployment: local security baseline PASS.
- G3 persistent PostgreSQL: local PASS.
- G4 backup/restore: local PASS.
- G5 stable HTTPS: FAIL / BLOCKED because Workers VPC is intermittent.
- G6 Facebook publish verification: BLOCKED; no live OAuth credentials.
- G7 Instagram publish verification: BLOCKED; no live OAuth credentials.
- G8 TikTok private/audit-aware test: BLOCKED; no live authorization prerequisites.
- G9 TikTok public path: BLOCKED; audit/authorization prerequisites absent.
- G10 MCP integration: local boundary PASS; external Hermes end-to-end not verified.
- G11 Hermes automation: NOT_READY until external execution path is stable.
- G12 idempotency: PARTIAL; generic API idempotency exists, publish identity is not a dedicated deterministic persisted key.
- G13 webhook/status reconciliation: PARTIAL; local webhook/retry/reconciliation code tested, remote verification absent.
- G14 failure recovery: local restart recovery PASS; external recovery not verified.
- G15 security validation: PARTIAL.
- G16 chaos testing: PARTIAL.
- G17 evidence package: PARTIAL / actively maintained.
- G18 rollback: local source rollback path exists; full production rollback not externally verified.

## Decision
Do not activate autonomous publishing. The external VPC boundary and live social authorization/publish verification are hard production gates.
