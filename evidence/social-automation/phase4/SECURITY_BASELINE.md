# Phase 4 — Security Hardening
Date: 2026-09-28 Asia/Bangkok
Status: PASS for local baseline; production HTTPS/credential integration remains later phases.

## Controls verified
- SECRET_KEY and ENCRYPTION_KEY_SALT generated randomly and rotated after the initial image-secret exposure was detected.
- DEBUG=false.
- ALLOWED_HOSTS limited to 127.0.0.1,localhost for the current local deployment.
- .env is ignored by git; git status reports !! .env and no tracked secret content.
- Current SECRET_KEY and encryption salt values do not appear in tracked Git content (0 matches each).
- Final Docker image does not contain /app/.env.
- Normal app/worker/migrate logs contain no secret-name/token patterns tested by the Phase 4 scan.
- PostgreSQL is not internet-bound; host listener is 127.0.0.1:15433.
- BrightBean app is not internet-bound; host listener is 127.0.0.1:18100.
- Existing TCP 8000 belongs to another service and remains untouched.

## Credential boundary
- No social credentials are present.
- No OAuth tokens have been created or stored.
- Platform credential environment variables remain empty.
- BrightBean remains behind a local-only boundary until Phase 5 establishes dedicated HTTPS ingress.
## Known production hardening follow-up
- A dedicated least-privilege PostgreSQL application role should be created before production instead of relying on the default postgres role.
- Production callback and MCP URLs must be HTTPS and public before social OAuth is configured.
- Production media access should use the Caddy/HTTPS boundary rather than local unauthenticated media serving.

## Acceptance
- No social credential in source control: PASS.
- No secret exposed in normal logs: PASS.
- Database isolated from public internet: PASS.
- Production configuration reproducible without copying secret values into repository: PASS for deployment pattern.

## Conclusion
Phase 4 PASS for the approved pre-social local security gate. Remaining production-only controls are tracked in later phases.
