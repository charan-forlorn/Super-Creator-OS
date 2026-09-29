# Phase 6 — Meta / Facebook Integration — Preflight
Date: 2026-09-28 Asia/Bangkok
Status: PREPARED / NOT_ACTIVE

## Source-level callback contract
- BrightBean builds OAuth redirect URIs from the incoming request host.
- Main social callback route: `/social_accounts/callback/<platform>/`.
- Connection-link callback route: `/onboarding/connect/callback/<platform>/`.
- OAuth token exchange reuses the exact callback URI, so the public origin must be stable and HTTPS.
- Current source includes provider implementations/tests for Facebook, Instagram and TikTok.
## MCP contract
- Public MCP endpoint: `/api/v1/mcp`.
- Protected-resource metadata: `/.well-known/oauth-protected-resource/api/v1/mcp`.
- `MCP_PUBLIC_BASE_URL` advertises the resource origin.
- `MCP_OAUTH_ISSUER_URL` identifies the authorization-server origin.
- BrightBean documents that the MCP server requires a public HTTPS URL for external native OAuth connectors.
## Current gate
- Provider unit/e2e tests at pinned SHA passed as part of the Phase 2 suite.
- No real Meta credentials have been configured.
- No Facebook/Instagram OAuth flow has been attempted.
- Phase 6 cannot activate until Phase 5 supplies a stable public HTTPS origin.
