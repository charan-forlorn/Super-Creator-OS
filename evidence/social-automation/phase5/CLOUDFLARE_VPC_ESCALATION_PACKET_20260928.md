# Cloudflare VPC Escalation Packet — BrightBean Social Automation
Verified: 2026-09-28 Asia/Bangkok

## Request
Account ID: cb98ff5a98ddb6c0f09450505be7c3f5
VPC Service ID: 01a0e4c6-ae62-74e0-8cbf-4df204bec536
Tunnel ID: 08a4e3a2-48fa-4464-8688-a79dac8a6773
Worker: brightbean-social-edge-20260928
Direct VPC Network canary: brightbean-vpc-network-canary-20260928

## Reproduction
Existing VPC Service: HandshakeTimeoutError: handshake timeout; code=null; remote=false.
Direct VPC Network: handshake timeout; code=null; remote=true; failures observed from BKK and SIN.
Latest 8-request VPC Network sample: 4x200 / 4x503; failures about 5.17-5.31 s.

## Connector evidence
cloudflared_tunnel_ha_connections=4
cloudflared_tunnel_request_errors=0
quic_client_closed_connections=0
Tunnel edge locations: sin14, bkk07, bkk09, sin12
quic_client_packet_too_big_dropped=0
quic RTT observed about 10-41 ms
Before a 6-request VPC Network test: cloudflared_tunnel_total_requests=26
After the same test (4 success, 2 handshake failures): total_requests=30
Therefore failed VPC requests did not reach cloudflared as proxied requests.

## Origin evidence
BrightBean 127.0.0.1:18100/health = 200
brightbean-edge 172.18.0.6:80/health = 200 from woodpecker-net
cloudflared namespace -> 172.18.0.6:80/health = 200
cloudflared image cloudflare/cloudflared:2026.8.3 using QUIC

## Current public Worker sample
8 requests: 200, 200, 200, 200 (~5.88s), 200, 200, 000 timeout (~8.0s), 200
Not accepted as stable.

## Interpretation
The fault is strongly isolated to the Workers VPC data plane before the local tunnel connector. It reproduces through both VPC Service and direct VPC Network bindings and is not explained by a dead origin or connector.
Exact VPC Metrics dashboard error-code label remains unconfirmed because the dashboard data did not render and the connected Hermes Cloudflare MCP bridge does not expose VPC Metrics/Logs.

## Requested Cloudflare-side checks
1. Return the exact VPC Metrics error code/category.
2. Correlate failures with Worker edge colo and tunnel connection.
3. Check why failed connection attempts do not appear in cloudflared_tunnel_total_requests.
4. Confirm whether the behavior is connection_timeout, destination_unavailable, destination_ip_unroutable, or another class.
5. Provide supported remediation.

## References
https://developers.cloudflare.com/workers-vpc/reference/troubleshooting/
https://developers.cloudflare.com/workers-vpc/configuration/vpc-networks/
https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/monitor-tunnels/metrics/

