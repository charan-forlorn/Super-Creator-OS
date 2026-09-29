# Phase 15 — Backup / Restore Drill

Verified: 2026-09-28 11:46 +07:00

## Scope
Local isolated BrightBean stack only. No production/social credentials were included.

## Backup artifacts
- PostgreSQL custom-format backup: brightbean-phase3.dump
- Media archive: brightbean-media.tar.gz
- PostgreSQL backup SHA-256: 38E972B8F96E804CFFF27AFFB347035C7C645D53FC1ED35F737D2CFA9F009064
- Media backup SHA-256: 8E24802444BFE551B4E242DE2A299723CC5D76B315009CC41CED7CDD6ACED5E2
- Source/deployment configuration is version-controlled; secret-bearing .env backup files were excluded from git commit.

## Restore drill
- Restored PostgreSQL backup into disposable PostgreSQL 16 container with --no-owner and --exit-on-error.
- Restore completed successfully.
- Restored django_migrations rows: 155.
- Restored public table count: 92.
- Restored media archive into disposable Docker volume.
- Restored media files: 81; restored media size: approximately 984K.
- Disposable restore resources were removed after verification.

## Result
PASS for local backup/restore acceptance. No duplicate publishing state existed in the isolated database during the drill (PlatformPost count was 0 before chaos/restore tests).

## Limitations
This does not prove remote-social duplicate prevention during a disaster; that remains gated by Phase 18 external publish verification.

