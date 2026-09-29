# Phase 5 — Workers VPC Isolation Evidence — 2026-09-28

## Executive finding
- Local BrightBean origin, private edge, Docker network, and cloudflared connector are healthy.
- Intermittent failures reproduce in BOTH the existing VPC Service binding and a direct VPC Network binding to the same Cloudflare Tunnel.
- Direct VPC Network failures are reported by Workers with `handshake timeout`, `code=null`, `remote=true`.
- Failures occur from multiple Worker edge colos (BKK and SIN).
- Cloudflared Prometheus metrics show 4 healthy QUIC connections, zero closed connections, zero tunnel request errors, and only successful VPC requests increasing `cloudflared_tunnel_total_requests`.
- Therefore the observed failure is strongly isolated to the Workers VPC data plane before the request reaches the local cloudflared connector. Exact Cloudflare Metrics-tab error-code label remains unconfirmed.

## Reproduction A — Existing VPC Service
- Worker: brightbean-social-edge-20260928
- VPC Service: 01a0e4c6-ae62-74e0-8cbf-4df204bec536
- Runtime failure observed: `HandshakeTimeoutError: handshake timeout`.
- Runtime exception code: null; remote=false.
- Public sample immediately before this packet: 8 requests -> 7 successful/1 timeout (HTTP 000, ~8s); one successful response also took ~5.9s.

## Reproduction B — Direct VPC Network
- Temporary canary Worker: brightbean-vpc-network-canary-20260928
- Direct tunnel binding: 08a4e3a2-48fa-4464-8688-a79dac8a6773
- Target: http://172.18.0.6/health/
- Tail-observed failures: `handshake timeout`, `code=null`, `remote=true`.
- Latest 8-request sample: 4 HTTP 200 / 4 HTTP 503; 503 latency ~5.17-5.31s; 200 latency ~0.30-0.35s.
- Tail evidence contains failures from both BKK and SIN Worker colos.
- This eliminates the VPC Service host/port registration layer as the unique cause.

## Reproduction C — VPC Network TCP connect()
- Temporary canary Worker: brightbean-vpc-connect-canary-20260928
- Same direct tunnel binding.
- `connect("172.18.0.6:80")` canary also produced ~5s `socket_read_timeout` failures, confirming that switching from VPC HTTP fetch to VPC raw TCP does not currently provide a stable bypass.
- Some faster failures were local parser errors (`invalid_http_response`) from the intentionally minimal canary implementation and are not used as a production classification.

## Connector telemetry during VPC failures
- Metrics endpoint: cloudflared Prometheus metrics on 127.0.0.1:20241 inside the cloudflared network namespace.
- `cloudflared_tunnel_ha_connections = 4`.
- `cloudflared_tunnel_request_errors = 0`.
- `quic_client_closed_connections = 0`.
- Tunnel locations: connection 0=sin14, 1=bkk07, 2=bkk09, 3=sin12.
- `quic_client_latest_rtt` observed in the ~10-41ms range; `packet_too_big_dropped=0`.
- Before a 6-request VPC Network sample: `cloudflared_tunnel_total_requests=26`.
- After that sample (4 successes / 2 VPC handshake failures): `cloudflared_tunnel_total_requests=30`.
- The two failed VPC requests therefore did not reach cloudflared as proxied requests.

## Cloudflare documentation correlation
- Cloudflare documents `connection_timeout` as a connection attempt timing out and says VPC error codes are visible in the VPC Service Metrics tab.
- Cloudflare documents `proxy_internal_error` as a distinct Cloudflare infrastructure class and recommends support escalation if it persists.
- Cloudflare documents direct VPC Network tunnel binding with `tunnel_id` and `remote=true` and marks Workers VPC as beta.

## Decision
- Do not mutate BrightBean, Docker topology, cloudflared, DNS, VPC Service, or production Worker architecture further on speculation.
- Keep Phase 5 BLOCKED until either Cloudflare VPC Metrics gives an exact supported classification/remediation path or an independently verified stable public ingress replacement is available.
- Current evidence is sufficient to prepare a Cloudflare escalation packet because origin/tunnel health is independently verified and the failures stop before cloudflared.

Sources:
- https://developers.cloudflare.com/workers-vpc/reference/troubleshooting/
- https://developers.cloudflare.com/workers-vpc/configuration/vpc-networks/
- https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/monitor-tunnels/metrics/
