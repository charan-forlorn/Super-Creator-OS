# Phase 5 — Public HTTPS / Connectivity Boundary
Date: 2026-09-28 Asia/Bangkok

Status: BLOCKED_EXTERNAL_AUTH

## Completed
- Woodpecker host binding is localhost-only.
- Woodpecker server and agent remain healthy.
- Woodpecker Quick Tunnel was removed after verifying WOODPECKER_EXPERT_WEBHOOK_HOST is empty.
- BrightBean edge is attached to woodpecker-net and reaches BrightBean with HTTP 200.
- Production Compose and Caddy validation passed.
- No social OAuth credentials are configured.
- PostgreSQL has no public bind.

## Blocker
Cloudflare named tunnel 08a4e3a2-48fa-4464-8688-a79dac8a6773 is remotely managed. The machine has a connector token but no control-plane API token/cert.pem for editing published routes/DNS through cloudflared.

## Completion path
Run Finalize-BrightBeanCloudflare.ps1 with an authorized Cloudflare API token and exact user-owned hostname/zone, then verify public HTTPS, MCP metadata, callbacks and webhook reachability before changing Phase 5 to PASS.