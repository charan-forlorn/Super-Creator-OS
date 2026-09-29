# Phase 3 — Self-Hosted Core Deployment
Date: 2026-09-28 Asia/Bangkok
Status: PASS

## Deployment
- Isolated Compose project: brightbean-phase3.
- Source checkout: C:\\Workspace\\brightbean-studio at pinned SHA 6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8.
- App is bound to 127.0.0.1:18100 -> container 8000.
- PostgreSQL is bound only to 127.0.0.1:15433 -> container 5432 for local administrative/testing access.
- Project volumes: brightbean-phase3_postgres_data and brightbean-phase3_media_data.
- Existing Woodpecker port 8000 remains untouched.
## Verification
- PostgreSQL healthcheck: PASS.
- Migration service exits successfully.
- python manage.py migrate --check: exit 0.
- /health/ endpoint: HTTP 200, body {"status": "ok"}.
- App Gunicorn running on container port 8000.
- Worker process running after start and restart.
- App/worker restart: PASS; /health/ remained HTTP 200.
- Full stack down/up without removing volumes: PASS; database, migration, app and worker returned healthy/running and /health/ remained HTTP 200.
- No unexpected Traceback/ERROR/Exception/invalid-env-line entries in final app/worker/migrate logs.
## Deployment hardening discovered and remediated
- Initial Phase 3 merge retained base port 8000; resolved with Compose !override so BrightBean cannot conflict with Woodpecker.
- Initial local .env was written with a UTF-8 BOM; this caused django-environ invalid-line warnings. Rewritten as UTF-8 without BOM.
- Initial Phase 3 image contained /app/.env because the upstream checkout had no .dockerignore. This was detected before declaring Phase 3 complete.
- Remediation: added local deployment .dockerignore excluding .env and .env.* except .env.example; rotated local SECRET_KEY and ENCRYPTION_KEY_SALT; rebuilt the deployment images with --no-cache; verified ENV_IN_IMAGE=NO.
- These hardening changes are local deployment-layer changes and are not committed upstream.

## Boundary
- No Meta, Instagram, Facebook or TikTok credentials were configured.
- No social publication or OAuth connection was attempted.
## Evidence
- Source: C:\\Workspace\\brightbean-studio
- Deployment compose override: docker-compose.phase3.yml
- Secure local .dockerignore: C:\\Workspace\\brightbean-studio\\.dockerignore
- Roadmap: C:\\Workspace\\super-creator-os\\docs\\architecture\\social-automation\\BrightBean_Hermes_Social_Automation_Roadmap.md

## Conclusion
Phase 3 PASS. BrightBean core is running locally with isolated ports, persistent volumes, working migrations, worker recovery and verified health.

## Additional acceptance verification
- Login route under simulated HTTPS proxy headers: HTTP 200 from /accounts/login/; no test credential was created.
- Media persistence: wrote a phase3 sentinel into /app/media, restarted app and worker, read the sentinel successfully, then removed the sentinel.
- Worker remained running after the test restart.

## Acceptance caveat
- Credential-authentication itself was not exercised because creating a temporary admin credential was not necessary to validate the deployment layer and the credential-creation automation path was intentionally not used. The login route is verified separately.
