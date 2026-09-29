# Phase 5 — Final Status — 2026-09-28

## Verified infrastructure
- Cloudflare tunnel: HAIOS Cloudflare.
- Tunnel ID: 08a4e3a2-48fa-4464-8688-a79dac8a6773
- Status observed: Healthy
- Replicas observed: 2
- Connector version observed: 2026.9.1
- Published application route: */* -> http://brightbean-edge:80
- Workers VPC binding: BRIGHTBEAN -> brightbean-edge
- Local brightbean-edge: running, host 127.0.0.1:18080 -> container :80
- Direct origin checks: / = 200/302 login redirect, /health/ = 200 JSON {"status":"ok"}, /accounts/login/ = 200
- Worker public URL: https://brightbean-social-edge-20260928.charan254311.workers.dev

## Verified public failure
- Worker public /health/ => HTTP 503 "BrightBean edge unavailable"
- Worker public /accounts/login/ => HTTP 503 "BrightBean edge unavailable"
- Worker public / => HTTP 302 from Caddy with Location /accounts/login/?next=/ and Caddy Via header observed.
- This proves Cloudflare tunnel/origin connectivity exists; remaining failure is Worker-edge logic/runtime behavior.

## Deployment state
- Active deployment observed: version eb2fff11, 100% traffic.
- Version history observed:
  - eb2fff11 — "BrightBean stable public edge via Workers VPC v3"
  - 68c27de3 — "BrightBean stable public edge via Workers VPC"
  - 64420640 — "BrightBean stable public edge via Workers VPC"
- Deployment history also contains message "Rollback to verified BrightBean edge v1".
- Worker has VPC Service binding BRIGHTBEAN -> brightbean-edge.

## Security gate
- Cloudflare Quick Edit / Wrangler requested OAuth consent for 28 permissions, including 21 Developer Platform permissions plus additional Account & Billing, DNS & Zones, Cache & Performance, and App Security permissions.
- Authorization was NOT granted.
- Observability was temporarily enabled for diagnosis and verified back off/unchecked before handoff.
- No Cloudflare tunnel/DNS mutation was made during this diagnostic pass.

## Closure
Infrastructure/routing/origin is verified.
Worker public edge is NOT verified healthy; production remains 503 for /health/ and /accounts/login/.
Required next action: inspect/fix/promote/rollback Worker source using an authorized deployment path. Wrangler OAuth approval must be explicitly authorized by the human owner because it grants new account-level permissions.
