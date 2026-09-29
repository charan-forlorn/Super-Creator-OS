/goal /x10
Operate this machine and COMPLETE the BrightBean public HTTPS gateway migration now. Do not merely tell me what to do.

Verified local state:
- BrightBean repo/deployment: C:\Workspace\brightbean-studio
- BrightBean app: 127.0.0.1:18100
- BrightBean edge container: brightbean-edge:80
- brightbean-edge is attached to its BrightBean Compose network and woodpecker-net
- From woodpecker-net, http://brightbean-edge/health/ returns 200
- BrightBean PostgreSQL: 127.0.0.1:15433 only
- Woodpecker server/agent are healthy and Woodpecker is localhost-only at 127.0.0.1:8000
- Existing named Cloudflare tunnel: 08a4e3a2-48fa-4464-8688-a79dac8a6773
- Quick Tunnel may still be running and must be audited before retirement
- Roadmap: C:\Workspace\super-creator-os\docs\architecture\social-automation\BrightBean_Hermes_Social_Automation_Roadmap.md
- Evidence: C:\Workspace\super-creator-os\evidence\social-automation

Use the authenticated Cloudflare MCP to inspect actual account, zones, DNS, named tunnel and published routes. Choose a stable hostname in an existing user-owned zone with no important collision, preferably brightbean.<zone>. Create/update one route to http://brightbean-edge:80. Do not expose PostgreSQL or BrightBean host ports. Do not modify unrelated routes.

After routing, update BrightBean:
APP_URL=https://<hostname>
ALLOWED_HOSTS must include localhost and <hostname>
MCP_PUBLIC_BASE_URL=https://<hostname>
MCP_OAUTH_ISSUER_URL=https://<hostname>
Never print secrets. Restart only BrightBean if needed.

Verify externally:
1 https://<hostname>/health/ = HTTP 200 JSON ok
2 /accounts/login/ = HTTP 200
3 /.well-known/oauth-protected-resource/api/v1/mcp = valid JSON
4 /api/v1/mcp = reachable; expected auth rejection is acceptable if protocol is reached
5 Facebook/Instagram/TikTok callback routes are reachable without real credentials
6 webhook route is reachable
7 127.0.0.1:8000/health remains 200
8 PostgreSQL remains private
9 no unintended public host ports
10 named tunnel remains healthy

Audit Woodpecker webhook dependencies. Only if Quick Tunnel is proven unnecessary, remove it safely with rollback backup. Keep Woodpecker local CI functioning.

Run relevant BrightBean MCP/OAuth/social-provider tests after config changes. Update Roadmap and create timestamped Phase 5 verification evidence. If Cloudflare permission blocks the route, leave local system healthy and record the exact blocker. Do not fabricate. Do not ask questions. Execute until Phase 5 passes or a real external blocker is proven.