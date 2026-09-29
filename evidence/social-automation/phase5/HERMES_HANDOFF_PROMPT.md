# Hermes Handoff — BrightBean Public HTTPS via Existing Woodpecker Tunnel
Date: 2026-09-28 Asia/Bangkok

## Run this in
- Hermes Desktop / primary operator profile.
- Allowed working roots:
  - C:\Workspace\super-creator-os
  - C:\Workspace\brightbean-studio
  - C:\Workspace\_haios-local-woodpecker

## Current verified state
- BrightBean pinned SHA: 6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8.
- BrightBean app: 127.0.0.1:18100.
- BrightBean PostgreSQL: 127.0.0.1:15433.
- BrightBean edge: container `brightbean-edge`, attached to `brightbean-phase3_default` and `woodpecker-net`.
- Edge service target: `http://brightbean-edge:80`.
- Edge-to-BrightBean test from `woodpecker-net`: HTTP 200 on /health/.
- Woodpecker server: localhost-only `127.0.0.1:8000`; server and agent remain healthy.
- Existing named Cloudflare tunnel: `08a4e3a2-48fa-4464-8688-a79dac8a6773`.
- Existing named tunnel container: `haios-woodpecker-cloudflared` on `woodpecker-net`.
- Existing Quick Tunnel remains temporarily active for Woodpecker until dependency audit is complete.
## Primary goal
Re-purpose the existing named Woodpecker Cloudflare gateway so BrightBean gets a stable public HTTPS hostname without creating a second tunnel and without breaking Woodpecker local operation.

## Execution rules
1. Inspect current Cloudflare zones, DNS records, named tunnel routes and hostname collisions using the authenticated Cloudflare MCP. Do not infer a domain from old Quick Tunnel URLs.
2. Prefer an existing user-owned zone. Preferred hostname pattern: `brightbean.<existing-zone>`; otherwise `studio.<existing-zone>` if that is the cleanest available collision-free hostname.
3. Do not expose BrightBean directly from host ports. Cloudflare must target `http://brightbean-edge:80` over `woodpecker-net`.
4. Do not expose PostgreSQL.
5. Do not reveal, print, commit, or copy any Cloudflare token, OAuth token, GitHub secret, Woodpecker secret, or BrightBean secret.
6. Before disabling the Woodpecker Quick Tunnel, audit active repositories/hooks/builds. If any active webhook depends on it, preserve it until a safe migration is verified.
## Cloudflare work
- Inspect tunnel `08a4e3a2-48fa-4464-8688-a79dac8a6773`.
- Add/update exactly one BrightBean published application route for the selected stable hostname -> `http://brightbean-edge:80`.
- Ensure the DNS record/route is attached to the named tunnel.
- Do not delete unrelated Woodpecker routes without first proving they are unused.
- Verify the public hostname resolves and Cloudflare reaches `brightbean-edge`.
## BrightBean configuration work
After the hostname is known, update only the local deployment environment needed for production-like public access:
- APP_URL=https://<selected-hostname>
- ALLOWED_HOSTS must include the selected hostname.
- MCP_PUBLIC_BASE_URL=https://<selected-hostname>
- MCP_OAUTH_ISSUER_URL=https://<selected-hostname>
- Keep local admin access on 127.0.0.1:18100.
- Keep PostgreSQL on 127.0.0.1:15433.
- Preserve existing SECRET_KEY and ENCRYPTION_KEY_SALT; never print them.

Restart only the BrightBean deployment stack after editing environment values. Do not perform unrelated Hermes updates.
## Woodpecker cleanup
- Keep `WOODPECKER_HOST=http://127.0.0.1:8000`.
- Keep Woodpecker host binding localhost-only.
- `WOODPECKER_EXPERT_WEBHOOK_HOST` and the Quick Tunnel may be removed/disabled only after the active hook audit proves they are not needed.
- If disabled, create a rollback backup and verify server + agent + local health before and after.
## Public verification gates
Run all gates and preserve raw evidence:
A. https://<selected-hostname>/health/ -> HTTP 200 and JSON status ok.
B. https://<selected-hostname>/accounts/login/ -> HTTP 200.
C. https://<selected-hostname>/.well-known/oauth-protected-resource/api/v1/mcp -> valid JSON with the selected public origin.
D. POST/GET reachability to /api/v1/mcp according to the source contract; unauthenticated rejection is acceptable, network/routing failure is not.
E. OAuth callback route reachability for Facebook, Instagram and TikTok without creating real provider credentials.
F. Webhook callback route reachability without sending a real provider event.
G. Internal 127.0.0.1:8000 Woodpecker health remains HTTP 200.
H. Existing named tunnel remains connected.
I. No PostgreSQL public bind.
J. No Quick Tunnel remains unless the dependency audit proves it is still required.
## Test gate
Run targeted tests from `C:\Workspace\brightbean-studio` after configuration changes:
- MCP OAuth/metadata tests.
- OAuth alias/PKCE tests.
- Facebook/Instagram/TikTok provider tests.
- Media routing tests.
- Relevant social account view tests.
- Then run the smallest broader regression set needed to prove the routing/config change did not regress the pinned build.

Do not claim PASS from configuration inspection alone. Require live HTTP evidence.
## Evidence / SSOT
Update:
- `C:\Workspace\super-creator-os\docs\architecture\social-automation\BrightBean_Hermes_Social_Automation_Roadmap.md`
- `C:\Workspace\super-creator-os\evidence\social-automation\phase5\CONNECTIVITY.md`
- create a Phase 5 verification record with the exact hostname, tunnel ID, route target, test timestamps/results, rollback point and remaining risks.

If and only if every Phase 5 acceptance criterion passes, change Phase 5 to PASS and activate Phase 6. Otherwise keep Phase 5 IN_PROGRESS and state the exact blocker.
## Failure/recovery
On any failure:
Reconcile -> capture evidence -> identify root cause -> remediate -> re-test -> re-verify.
If Cloudflare control-plane access is insufficient, do not fabricate the hostname or route. Report the precise missing permission and leave the local deployment healthy.
