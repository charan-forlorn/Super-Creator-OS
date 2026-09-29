# Phase 1 — Risk Register
Date: 2026-09-28 Asia/Bangkok

| ID | Risk | Evidence | Phase | Treatment |
|---|---|---|---|---|
| R1 | Port 8000 conflict | Woodpecker owns 8000 | P3 | Bind BrightBean to 18100 locally |
| R2 | Dirty SCOS workspace | Extensive existing git changes | P1-P2 | Isolate changes; no cleanup now |
| R3 | BrightBean has no pinned release baseline | Repo uses active main | P2 | Pin tested commit SHA |
| R4 | Meta OAuth may fail on provider/app config | Upstream issues previously found | P6 | Own Meta app + staged OAuth tests |
| R5 | TikTok public Direct Post depends on audit | TikTok platform policy | P9 | Separate private/public gates |
| R6 | Production callback needs stable HTTPS | OAuth/webhook requirement | P5 | Use existing Cloudflare infrastructure only after route verification |
| R7 | Local backup is same physical disk | C-only evidence storage initially | P13 | Add off-device copy before production |
| R8 | Hermes already has many MCPs | Existing global MCP inventory | P8 | Scope BrightBean tools narrowly |
| R9 | Existing Buffer MCP could cause overlapping automation | Hermes baseline | P8-P10 | Keep BrightBean as designated execution layer |
| R10 | Media may require public fetch URL | Platform server-side media fetch | P3-P5 | Isolate publish media and secure ingress |
## Phase 1 blocker assessment

No hard blocker prevents Phase 2 investigation.

Known non-blocking constraints:
- TCP 8000 must not be used.
- Workspace is dirty and must be treated as a protected existing state.
- Production backup/recovery is not yet complete.
- Stable public hostname for OAuth/webhooks is not yet selected.
- Social platform credentials have not been connected and must remain absent until their dedicated phases.

## Safety rule
No public social posting has been enabled or attempted by this Phase 1 execution.
