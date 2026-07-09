# Local UI Sync Activation Gate

Stage: 7.5 - Local UI Sync Activation Gate.

## Activation Conditions

Live UI sync transport is not activated in Stage 7.5.

A future implementation stage may request activation only when all conditions
are satisfied:

- operator approval is recorded before implementation begins
- the transport decision names the exact transport and scope
- localhost-only boundary is documented and tested
- authentication and CSRF review is complete for any HTTP route
- deterministic event or projection schema is documented
- frontend loading, empty, degraded, error, fallback, and recovery states are
  tested
- rollback and kill-switch behavior is documented and tested
- security scan and focused Control Center regression tests pass
- Stage 7.4 static/mock fallback remains available

## Localhost Boundary

Any future transport must be local-first and operator-machine-only. It must
not expose remote administration, cloud sync, external API behavior,
multi-tenant access, SaaS behavior, payment, CRM, customer portal behavior,
or telemetry.

Localhost transport, if later approved, must bind only to localhost and must
be treated as untrusted input at the route or listener boundary.

## Approval Requirements

Future activation requires an explicit stage/task that states:

- selected transport
- approved files
- public contract changes
- threat model
- test plan
- rollback plan
- security scan expectations
- operator approval evidence

Stage 7.5 does not grant blanket approval for any later transport.

## Required Controls Before Future Implementation

- operator approval before implementation
- localhost-only bind and origin policy
- auth and CSRF review for HTTP-based transport
- deterministic message schema
- schema compatibility with Stage 7.4 read projections
- no direct frontend reads from SQLite
- no state, event, approval, audit, or queue mutation through read surfaces
- bounded failure and stale-data states
- fallback to deterministic static/mock projection
- test coverage for recovery and rollback
- security scan before activation

## Forbidden Behaviors

Until a later explicit approval stage exists, the following remain forbidden:

- WebSocket
- Server-Sent Events and EventSource
- polling
- timers and background workers
- frontend `fetch`, `XMLHttpRequest`, or `axios`
- Next.js API routes
- localhost HTTP routes
- backend socket servers
- runtime transport dependencies
- real AI adapter dispatch
- command execution behavior changes
- direct frontend SQLite reads
- state, event, approval, audit, or queue mutation
- cloud, network, SaaS, payment, CRM, or customer portal behavior

## Rollback Plan

Stage 7.5 rollback is documentation and gate-code rollback only because it
does not implement runtime transport.

Future transport implementation must provide:

- a single-stage revert path
- a kill switch or explicit disable flag
- static/mock fallback restoration
- test command sequence proving fallback is restored
- security scan evidence after rollback

## Manual Static Fallback Guarantee

Stage 7.4 deterministic static/mock projection remains valid and unmodified.
Manual/static fallback is the default behavior after Stage 7.5.
