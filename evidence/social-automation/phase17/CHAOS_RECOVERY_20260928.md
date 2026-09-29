# Phase 17 — Reliability / Chaos Recovery

Verified: 2026-09-28 11:47 +07:00

## Precondition
PlatformPost table in isolated BrightBean database was empty; no scheduled work was due. This prevented the recovery drill from accidentally publishing real test content.

## Failure injection and recovery
- Restarted BrightBean worker container: recovery successful; health endpoint returned HTTP 200.
- Restarted BrightBean app container: recovery successful; health endpoint returned HTTP 200.
- Restarted BrightBean PostgreSQL container: recovery successful; health endpoint returned HTTP 200.
- Final container state: app, worker, postgres running.

## Observed restart timings
- Worker restart: ~3357 ms.
- App restart: ~3423 ms.
- PostgreSQL restart: ~449 ms; database reported healthy after recovery.

## Result
PARTIAL. Local restart recovery is verified. Full chaos matrix remains open for tunnel restart, token expiry, forced 429/5xx, interrupted media upload, and post-disaster remote-state reconciliation.

