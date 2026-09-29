# BrightBean Social Automation — Execution Cycle Evidence

Verified: 2026-09-28 11:18 +07:00

## Scope
- Continue from Phase 5 blocker without restarting completed work.
- Diagnose the Workers VPC failure, validate the BrightBean execution layer, and reconcile roadmap status.
- No production tunnel, VPC Service, DNS, OAuth credential, Docker topology, or BrightBean runtime architecture was changed.

## Phase 5 VPC diagnosis
- VPC Service: 01a0e4c6-ae62-74e0-8cbf-4df204bec536.
- Service target: brightbean-edge / HTTP:80 / 172.18.0.6.
- Tunnel: 08a4e3a2-48fa-4464-8688-a79dac8a6773.
- Worker: brightbean-social-edge-20260928.
- Production Worker restored to baseline deployment 3f58cb0b-b681-4054-9cff-f8b1d52a3fb7.
- Temporary diagnostic deployments were rolled back after evidence capture.

## Observed VPC failure
- Worker runtime exception: HandshakeTimeoutError: handshake timeout.
- Exception code: null.
- Exception remote field: boolean false.
- No additional error classification was exposed by the runtime exception object.
- Failed public requests consistently take about 5.1-5.2 seconds; successful requests are about 0.25-0.36 seconds.
## VPC Metrics dashboard
- Direct Cloudflare Metrics route was opened in the authenticated dashboard:
  /workers/vpc/services/01a0e4c6-ae62-74e0-8cbf-4df204bec536/metrics
- The Metrics tab rendered, but the chart/data area remained blank after refresh and a 10-second wait.
- Cloudflare's public API documentation exposes VPC Service configuration endpoints but not a documented Metrics REST endpoint.
- Current public Cloudflare status shows no active incidents; only scheduled maintenance is listed.
- Therefore the exact dashboard class remains UNCONFIRMED.
- Cloudflare documentation semantically maps a connection-attempt handshake timeout to `connection_timeout`, but this is not being promoted to a dashboard-confirmed classification.

## Stability re-test after diagnostic rollback
- 8 external requests: 5 HTTP 200, 3 HTTP 503.
- Failure latency: approximately 5158-5190 ms.
- Success latency: approximately 273-360 ms.
- Local BrightBean /health/: HTTP 200.
- Private edge /health/: HTTP 200 / status ok.
- Phase 5 acceptance therefore remains unmet.
## BrightBean execution layer
- Targeted Social Automation suite: 516 passed, 0 failed.
- Covered provider tests for Facebook, Instagram and TikTok.
- Covered publisher engine, publish confirmation, first-comment retry, media handling and connection budget.
- Covered social webhook subscription tests and MCP tests.
- One test contract defect was found: the OAuth callback test did not simulate HTTPS while production enables SECURE_SSL_REDIRECT. The test was corrected with `secure=True` and the targeted suite passed 516/516.
- Broad repository regression was not used as an acceptance gate because it currently contains unrelated failures in analytics/API-key/approval areas and uses a non-isolated existing container test database.

## MCP boundary preflight
- Local BrightBean health endpoint: HTTP 200.
- MCP GET without proxy-HTTPS header redirects as expected.
- MCP GET with X-Forwarded-Proto=https returns HTTP 405, confirming the endpoint is POST-oriented.
- Protected-resource metadata with X-Forwarded-Proto=https returns HTTP 200.
- Unauthenticated MCP initialize POST returns HTTP 401.
- This verifies the local MCP boundary and authentication gate without exposing credentials.
## Current roadmap reconciliation
- Phase 1: PASS.
- Phase 2: PASS.
- Phase 3: PASS.
- Phase 4: PASS.
- Phase 5: BLOCKED.
- Phase 6 Meta/Facebook: BLOCKED by Phase 5 plus missing live social OAuth credentials.
- Phase 7 Instagram: BLOCKED by Phase 5 plus missing live social OAuth credentials.
- Phase 8 TikTok: BLOCKED by Phase 5 plus missing live authorization/audit prerequisites.
- Phases 9-14: PARTIAL; local implementation and relevant tests exist, but external publish/reconciliation/Hermes end-to-end acceptance is not verified.
- Phases 15-18: NOT_STARTED.

## Decision
- Stop speculative Cloudflare infrastructure mutations.
- Preserve the current healthy local BrightBean architecture.
- The next highest-value action is obtaining the actual VPC Metrics error classification or a Cloudflare-supported telemetry path for that classification.
- Once the public HTTPS boundary is stable, continue Phase 6-8 with real credentials and remote-state verification; do not mark social publishing complete from mocks/unit tests.

Sources:
- https://developers.cloudflare.com/workers-vpc/reference/troubleshooting/
- https://developers.cloudflare.com/changelog/post/2026-03-20-metrics-and-settings-dashboard/
- https://developers.cloudflare.com/api/resources/connectivity/
- https://www.cloudflarestatus.com/