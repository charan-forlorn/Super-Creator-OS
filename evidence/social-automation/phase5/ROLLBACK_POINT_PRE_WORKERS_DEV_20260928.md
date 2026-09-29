# Phase 5 rollback point — pre-workers.dev publication
Recorded: 2026-09-28T03:53:09+07:00

## Scope
This record is the rollback point before any Cloudflare Worker, Workers subdomain, BrightBean environment, or origin-tunnel mutation for the /goal /x10 run.

## Cloudflare read-only snapshot
- Account ID: cb98ff5a98ddb6c0f09450505be7c3f5
- Workers subdomain: charan254311 (account-provided hostname: charan254311.workers.dev)
- Existing account Worker scripts: none (GET /accounts/{account_id}/workers/scripts returned an empty result)
- Existing named tunnel: 08a4e3a2-48fa-4464-8688-a79dac8a6773; no route mutation performed in this run before this point.
- No zone/custom-domain dependency is assumed.

## Local runtime snapshot
- BrightBean pinned SHA: 6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8
- BrightBean app: 127.0.0.1:18100
- BrightBean PostgreSQL: 127.0.0.1:15433 (private host bind)
- brightbean-edge: Docker-only, no host port, attached to woodpecker-net
- Woodpecker: http://127.0.0.1:8000
- WOODPECKER_HOST: http://127.0.0.1:8000
- WOODPECKER_EXPERT_WEBHOOK_HOST: empty
- Quick Tunnel dependency: no active Quick Tunnel container present in the current docker container list; existing named cloudflared connector is separate and remains running.

## Rollback actions
1. If a Worker is created: delete only the newly-created Worker script after capturing its ID/name and confirming no unrelated route references it.
2. If the Workers subdomain is changed: restore the recorded `charan254311` subdomain state; do not delete it unless the pre-run state was not active.
3. If a BrightBean origin Quick Tunnel is created: stop/remove only the new origin container and restore the prior no-Quick-Tunnel state.
4. If BrightBean `.env` is changed: restore the pre-run file from the separately-created backup and restart only the BrightBean stack.
5. Do not modify or delete the named tunnel, unrelated Cloudflare routes, PostgreSQL, or Woodpecker local binding.

No credentials, tokens, or secret values are stored in this record.
