# Phase 5 VPC Connectivity Blocker — 2026-09-28

Status: BLOCKED / external platform connectivity
Verified: 2026-09-28 Asia/Bangkok

## Final local state
- BrightBean pinned source: 6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8
- BrightBean app: 127.0.0.1:18100 -> HTTP 200 /health/
- brightbean-edge: private only, no host port
- woodpecker-server: 127.0.0.1:8000 -> HTTP 200
- cloudflared: cloudflare/cloudflared:2026.8.3, QUIC, healthy
- Named tunnel: 08a4e3a2-48fa-4464-8688-a79dac8a6773
- VPC Service: brightbean-edge / HTTP:80 / 172.18.0.6
- Worker: brightbean-social-edge-20260928
- Public Worker URL: https://brightbean-social-edge-20260928.charan254311.workers.dev

## Evidence
- From woodpecker-net: http://brightbean-edge:80/health/ -> HTTP 200.
- From cloudflared network namespace: 172.18.0.6:80/health/ -> HTTP 200.
- cloudflared startup reports QUIC and healthy prechecks.
- Production Worker uses the original VPC Service binding.
- Final public test: 6 requests -> 3 successful HTTP 200, 3 connection timeouts (curl code 000); failed requests waited ~5s.
- Worker returns "BrightBean edge unavailable" on VPC fetch failure.
- Temporary VPC Network binding was tested and reverted.
- cloudflared 2026.9.3 was A/B tested and reverted; it did not eliminate intermittent failures.

## Conclusion
The origin/container/network namespace are healthy. The unresolved failure is intermittent Workers VPC -> tunnel/origin connectivity. No social OAuth was enabled and no public custom domain was created.

## Required next action
Use Cloudflare VPC Service Metrics / error codes to determine whether failures are connection_timeout, destination_unavailable, destination_ip_unroutable, or proxy_internal_error before any further production architecture change.

## Execution Update — 2026-09-28 10:17 +07:00

### Reconcile / Research
- VPC Service 01a0e4c6-ae62-74e0-8cbf-4df204bec536 re-read with Wrangler; target is brightbean-edge, HTTP:80, 172.18.0.6, tunnel 08a4e3a2-48fa-4464-8688-a79dac8a6773.
- Cloudflare Workers VPC troubleshooting docs state runtime connection errors are also exposed in the VPC Service Metrics tab and classify them as Bad Upstream, Client, or Internal.
- Cloudflare documents connection_timeout as a connection attempt timeout; proxy_internal_error is the distinct Cloudflare-infrastructure class.
- Current Cloudflare status page reports Workers VPC Operational with no active incident explaining this failure.

### Diagnose
- Live Worker tail captured the failure directly from the production Worker.
- Observed runtime exception: HandshakeTimeoutError: handshake timeout.
- Observed timing: failure wall time about 5000-5017 ms; successful requests were about 96-315 ms.
- Diagnostic probe showed exception fields: name=Error, message=handshake timeout, code=null, ownKeys=[message,remote], cause=null.
- The error occurs inside env.BRIGHTBEAN.fetch() before any BrightBean HTTP response is returned.
- This evidence rules out a normal BrightBean application response as the source of the failure and is consistent with a VPC connection-establishment timeout.

### Stability Test
- Public HTTPS test after restoring the baseline Worker: 12 external requests -> 6 HTTP 200 and 6 HTTP 503.
- Failed requests waited approximately 5149-5187 ms; successful requests completed approximately 251-315 ms.
- Local BrightBean verification during the same cycle: 127.0.0.1:18100/health/ -> HTTP 200 twice.
- Private edge verification: brightbean-edge internal /health/ -> {"status":"ok"}.

### Remediation / Rollback Safety
- A temporary Worker-side diagnostic logging change was used only to expose the VPC runtime exception shape.
- Diagnostic deployment version: ec49f11e-3d06-49f5-b803-1ea938942593.
- Worker source was restored to the original non-diagnostic implementation and redeployed.
- Restored production Worker version: f36baf70-e57e-448d-8528-a784ce0459cc.
- No BrightBean, Docker topology, OAuth, DNS, VPC Service, or production tunnel architecture was changed.

### Classification Decision
- Direct Cloudflare VPC Metrics-tab classification: NOT independently observed in this cycle because the dashboard requires an explicit existing-profile browser grant; granting that access is a security-sensitive authorization boundary and was not silently approved.
- Observed runtime class: HandshakeTimeoutError: handshake timeout.
- Documented Cloudflare mapping: this is semantically consistent with connection_timeout, but the dashboard label itself remains UNCONFIRMED.
- No evidence of connection_refused, destination_ip_unroutable, or proxy_internal_error was observed in the Worker runtime exception.
- Because the exact Metrics class is not directly verified, no further speculative infrastructure remediation is justified.

### Decision
- Phase 5 remains BLOCKED.
- Phase 6 remains NOT_STARTED and gated by Phase 5.
- Preserve the current healthy local architecture and tunnel configuration.
- Smallest actionable next step: obtain the VPC Service Metrics classification for service 01a0e4c6-ae62-74e0-8cbf-4df204bec536; if the dashboard reports connection_timeout, continue only with evidence-backed VPC/tunnel investigation; if it reports proxy_internal_error, treat it as a Cloudflare-side infrastructure issue and escalate rather than mutating local infrastructure.

### Sources
- https://developers.cloudflare.com/workers-vpc/reference/troubleshooting/
- https://www.cloudflarestatus.com/services

## Execution Update — 2026-09-28 11:18 +07:00

### New evidence
- Worker runtime diagnostic confirmed `HandshakeTimeoutError: handshake timeout` with `code=null` and `remote=false`.
- Cloudflare VPC Metrics route loaded in the authenticated dashboard, but the Metrics data area remained blank after refresh and a 10-second wait.
- Public Cloudflare status currently shows no active incidents; scheduled maintenance only.
- 8-request external stability test after diagnostic rollback: 5x HTTP 200, 3x HTTP 503.
- Failures remained approximately 5.16-5.19 seconds; successes approximately 0.27-0.36 seconds.
- Local BrightBean and private edge health remained HTTP 200.
- Exact VPC Metrics error class remains UNCONFIRMED.

### Decision
- Continue to classify the observed runtime as `handshake timeout`; `connection_timeout` is the documented semantic match, not a dashboard-confirmed label.
- Do not mutate the VPC Service, tunnel, DNS, Docker topology, or BrightBean application while the exact Metrics classification is unavailable.
- Phase 5 remains `BLOCKED`.
## Execution Update — 2026-09-28 11:50 +07:00

- Latest external stability sample: 8 requests -> 5 HTTP 200, 3 HTTP 503. Failure latency approximately 5158-5190 ms; success latency approximately 273-360 ms.
- Local BrightBean /health remains HTTP 200 and the private edge remains healthy.
- Read-only Hermes Cloudflare MCP diagnosis attempted Connectivity Directory service reads; both returned Cloudflare API error 10000 Authentication error.
- Current Cloudflare MCP catalog exposes no VPC metrics, analytics, or logs tool. No Cloudflare resource mutation was attempted.
- Cloudflare OAuth re-auth page is available for Human review; no permission grant was approved automatically.
- Exact VPC Metrics class remains UNCONFIRMED. The observed runtime remains HandshakeTimeoutError: handshake timeout; Cloudflare docs describe connection_timeout as a connection-attempt timeout, but the dashboard label was not independently observed.
- Phase 5 remains BLOCKED. No further speculative VPC/tunnel/DNS mutation is justified without an exact supported telemetry classification.
