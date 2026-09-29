# Phase 1 — Environment Matrix
Date: 2026-09-28 Asia/Bangkok

| Dependency | Observed | State | Decision |
|---|---|---|---|
| Windows host | 10.0.26200.0 | PASS | Use current host |
| Docker Engine | 29.8.0 | PASS | Use Docker |
| Docker Compose | v5.5.1 | PASS | Use Compose |
| WSL2 | Ubuntu-26.04 | PASS | Available |
| PostgreSQL host service | none | PASS | Use isolated BrightBean PostgreSQL |
| TCP 8000 | Woodpecker | CONFLICT | Do not use |
| TCP 18100 | free | PASS | Candidate BrightBean host port |
| TCP 18101 | free | PASS | Reserve as secondary candidate |
| C disk | ~188.9 GB free | PASS | Primary local storage |
| D disk | ~8.0 GB free | LIMITED | Not suitable for media |
| Cloudflare | containerized, running | PASS/UNKNOWN ROUTING | Reconcile routes later |
| Hermes gateway | running | PASS | Preserve current gateway |
| Hermes MCP | active, many servers | PASS | Add BrightBean only after Phase 3 |
| Project git state | dirty | RISK | Do not mix changes |
| Outbound HTTPS | GitHub/Meta/TikTok all reachable | PASS | API egress available |

## Planned isolation
- BrightBean container ports: bind only to localhost during initial deployment.
- Initial candidate host port: 18100 -> container 8000.
- PostgreSQL: internal Docker network only.
- BrightBean media: persistent Docker volume.
- Production public ingress: deferred to Phase 5.
## Existing integration inventory
1. Hermes global MCP already contains Buffer. This is an existing dependency, not the selected execution layer.
2. n8n is already running and exposed on TCP 5678; it may become an optional automation bridge later, but it is not required for the initial BrightBean architecture.
3. Cloudflare containers are already present and healthy at the connector/precheck level, but their routing/domain ownership for BrightBean is not yet established.
4. Port 8000 must remain reserved for Woodpecker.
5. The current project .mcp.json is unrelated to BrightBean and should not be overwritten.

## Backup candidates
- Primary local evidence/backup root: C:\Workspace\super-creator-os\evidence\social-automation
- OneDrive exists at C:\Users\chara\OneDrive; sync/retention has not yet been verified.
- D: is too small for production media backups.
- External/off-device disaster recovery remains an open Phase 4/13 item.
