# BrightBean + Hermes Social Automation — End-to-End Roadmap

**Project:** Social Distribution Automation Layer for Hermes / Super Creator OS  
**Primary Platforms:** Instagram, Facebook, TikTok  
**Primary Execution Layer:** BrightBean Studio — Self-Hosted  
**Primary Orchestrator:** Hermes  
**Document Role:** Single Source of Truth (SSOT) for roadmap + real execution status  
**Owner:** Human Owner  
**Engineering / Execution:** Hermes + Codex / approved engineering tools  
**Document Version:** 1.0.0  
**Research Baseline:** 2026-09-28 (Asia/Bangkok)  
**Approval State:** APPROVED — execution may proceed beginning at Phase 1  

---

## 0. Operating Rules for This Roadmap

This file is the authoritative working record for the project. Every meaningful implementation, verification, failure, recovery, or scope change must update this document in the same work cycle.

### Status values

- `NOT_STARTED` — phase has not begun.
- `IN_PROGRESS` — active implementation or investigation.
- `BLOCKED` — cannot proceed until a documented blocker is resolved.
- `PASS` — acceptance criteria verified with evidence.
- `PARTIAL` — some acceptance criteria pass, others remain open.
- `FAILED` — implementation/test failed and requires remediation.
- `SKIPPED` — intentionally omitted with documented reason.
- `DEFERRED` — intentionally postponed; not considered complete.

### Evidence rule

A phase is not `PASS` because code exists, a container starts, a UI opens, or one manual test succeeds.

A phase is `PASS` only when:

1. The implementation exists in the intended environment.
2. The relevant tests were executed.
3. The observed result matches the acceptance criteria.
4. The evidence location is recorded.
5. No unresolved blocker invalidates the conclusion.

### False-green prevention

Never record `PASS` from an assumed result. Never infer remote social-platform success from a local API response alone. Publishing must be reconciled against the remote platform state where technically possible.

### Scope rule

Human approval remains required for destructive, irreversible, financial, public, security-sensitive, or ambiguous-authority operations. Autonomous publishing must remain gated until the dedicated production approval phase passes.

### Cost rule

Prefer free, self-hosted, open-source, local-first, and low-cost infrastructure. External services are allowed only where required by the social platforms or production connectivity constraints.

---

# 1. Phase 1 — Reconcile & Baseline

**Status:** `PASS`
**Objective:** Establish the actual machine, Hermes, network, storage, and integration baseline before changing anything.

## 1.1 Scope

- Inspect current Windows environment.
- Verify Docker / Docker Compose / WSL2 availability.
- Verify PostgreSQL capability and existing instances.
- Verify available disk space and backup space.
- Inspect existing Hermes installation and gateway state.
- Inspect current Hermes MCP configuration.
- Identify existing reverse proxy, tunnel, domains, ports, and firewall rules.
- Check whether any existing social automation components already occupy required resources.
- Identify current Super Creator OS integration points.
- Record current versions and paths.

## 1.2 Required outputs

- `SYSTEM_BASELINE.md`
- `ENVIRONMENT_MATRIX.md`
- `RISK_REGISTER.md`
- Initial evidence bundle

## 1.3 Acceptance criteria

- All required host dependencies are known.
- All required ports and endpoints are accounted for.
- Hermes MCP integration point is known.
- Backup destination is known.
- No existing service conflict remains unexplained.

## 1.4 Blockers

Do not install or modify the production integration if a dependency is unknown, conflicting, or destructive to resolve without approval.

---

# 2. Phase 2 — BrightBean Source Reconciliation & Pinning

**Status:** `PASS`
**Objective:** Convert the active BrightBean source tree into a reproducible, testable dependency.

## 2.1 Scope

- Inspect repository state.
- Identify current default-branch commit.
- Review Docker and Compose definitions.
- Review application, worker, migration, database, media, API, webhook, and MCP components.
- Inspect test suite and CI configuration.
- Record open issues relevant to Meta, Instagram, TikTok, media upload, authentication, and deployment.
- Select a specific tested commit SHA.

## 2.2 Mandatory rule

Production must not depend on an unpinned moving `main` branch.

Required chain:

`Repository -> pinned commit SHA -> tested build -> deployed image -> evidence`

## 2.3 Acceptance criteria

- Exact source commit recorded.
- Build is reproducible.
- Test suite is understood.
- Known upstream risks are recorded.
- Rollback target is defined.

---

# 3. Phase 3 — Self-Hosted Core Deployment

**Status:** `PASS`
**Objective:** Deploy BrightBean locally/self-hosted with persistent application, worker, PostgreSQL, and media services.

## 3.1 Target topology

```text
BrightBean App
     |
     +--> Worker
     |
     +--> PostgreSQL
     |
     +--> Persistent Media Storage
```

## 3.2 Scope

- Build pinned version.
- Start app, worker, PostgreSQL, and required supporting services.
- Run migrations.
- Create administration account.
- Verify health and basic login.
- Verify worker execution.
- Verify persistent media storage.
- Verify restart persistence.

## 3.3 Acceptance criteria

- App healthy.
- Worker healthy.
- PostgreSQL healthy.
- Migrations clean.
- Login works.
- Restart does not lose application state.
- Worker resumes after restart.

---

# 4. Phase 4 — Security Hardening

**Status:** `PASS`
**Objective:** Create a safe baseline before connecting social credentials.

## 4.1 Scope

- Generate unique `SECRET_KEY`.
- Generate unique encryption salt/key material as required by deployment.
- Disable debug in production.
- Restrict allowed hosts.
- Use HTTPS for production callbacks and MCP.
- Ensure PostgreSQL is not internet-exposed.
- Review credential/token storage.
- Review log redaction.
- Review media exposure.
- Ensure `.env` and secrets are not committed.
- Define least-privilege service accounts.

## 4.2 Acceptance criteria

- No social credential is present in source control.
- No secret is exposed in normal logs.
- Database is isolated from the public internet.
- Production configuration is reproducible without copying secret values into the repository.

---

# 5. Phase 5 — Public HTTPS / Connectivity Boundary

**Status:** `BLOCKED`
**Objective:** Provide stable HTTPS for OAuth callbacks, webhooks, MCP, and remote platform access.

## 5.1 Preferred architecture

```text
Internet
   |
HTTPS
   |
Cloudflare Tunnel / approved secure tunnel
   |
BrightBean
```

## 5.2 Modes

### Development

- Temporary/test tunnel is acceptable.
- Callback URLs are treated as disposable.

### Production

- Stable hostname.
- Named tunnel or equivalent stable secure ingress.
- No direct exposure of internal application/database ports.

## 5.3 Acceptance criteria

- HTTPS reachable from external network.
- OAuth callback works through the public hostname.
- Webhook endpoint is reachable.
- MCP endpoint is reachable.
- Internal ports remain private.

## 5.4 Cost note

The software stack can remain free/self-hosted, but production public connectivity may require a domain or equivalent stable public endpoint. This dependency must be recorded before production activation.

---

# 6. Phase 6 — Meta / Facebook Integration

**Status:** `BLOCKED`
**Objective:** Establish first-party Meta publishing using our own application credentials and self-hosted OAuth flow.

## 6.1 Scope

- Create/use controlled Meta developer application.
- Configure required products and permissions.
- Configure redirect URIs.
- Connect Facebook Page.
- Validate token exchange and token storage.
- Validate account discovery.
- Publish test content.
- Verify remote state.
- Test re-authentication.
- Test permission failures.

## 6.2 Test matrix

| Capability | Required | Status |
|---|---:|---|
| OAuth | YES | `NOT_STARTED` |
| Account discovery | YES | `NOT_STARTED` |
| Text post | YES | `NOT_STARTED` |
| Image post | YES | `NOT_STARTED` |
| Video post | YES | `NOT_STARTED` |
| Scheduling | YES | `NOT_STARTED` |
| Verification | YES | `NOT_STARTED` |
| Re-auth | YES | `NOT_STARTED` |
| Permission failure | YES | `NOT_STARTED` |

## 6.3 Acceptance criteria

At least one complete publish -> remote verification cycle passes without manual intervention after authorization.

---

# 7. Phase 7 — Instagram Integration

**Status:** `BLOCKED`  
**Objective:** Validate supported Instagram connection paths and choose the operational path with the lowest unnecessary dependency.

## 7.1 Candidate paths

- Instagram through Meta/Facebook path.
- Instagram Login path supported by the current BrightBean implementation where applicable.

## 7.2 Test matrix

| Capability | Path A | Path B |
|---|---:|---:|
| OAuth | `NOT_STARTED` | `NOT_STARTED` |
| Professional account discovery | `NOT_STARTED` | `NOT_STARTED` |
| Image publishing | `NOT_STARTED` | `NOT_STARTED` |
| Carousel | `NOT_STARTED` | `NOT_STARTED` |
| Reel/video | `NOT_STARTED` | `NOT_STARTED` |
| Story, where supported | `NOT_STARTED` | `NOT_STARTED` |
| Comments | `NOT_STARTED` | `NOT_STARTED` |
| Insights | `NOT_STARTED` | `NOT_STARTED` |
| Re-auth | `NOT_STARTED` | `NOT_STARTED` |
| Failure recovery | `NOT_STARTED` | `NOT_STARTED` |

## 7.3 Acceptance criteria

- At least one supported Instagram path passes end-to-end.
- The chosen path is documented with its prerequisites and limitations.
- The non-selected path is documented as an alternative/fallback, not silently discarded.

---

# 8. Phase 8 — TikTok Integration

**Status:** `BLOCKED`  
**Objective:** Implement and verify TikTok Content Posting under TikTok's current authorization, audit, processing, and visibility rules.

## 8.1 State model

```text
DRAFT
  -> VALIDATING
  -> READY
  -> APPROVED
  -> SCHEDULED
  -> UPLOADING
  -> PLATFORM_PROCESSING
  -> PUBLISHED / PRIVATE_TEST / FAILED
```

## 8.2 Scope

- Create/configure TikTok developer app.
- Configure redirect and required scopes.
- Complete creator authorization.
- Validate creator/account information.
- Test content initialization.
- Test media upload.
- Test status reconciliation.
- Test webhook where supported.
- Record audit requirement.
- Separate private/unaudited test behavior from public production behavior.

## 8.3 Acceptance criteria

- Upload outcome is not treated as final publish success.
- Final remote state is verified.
- Retry behavior does not create duplicates.
- Public publishing path is explicitly marked `AUDIT_REQUIRED` until TikTok requirements are satisfied.

---

# 9. Phase 9 — Unified Publishing State Machine

**Status:** `PARTIAL`  
**Objective:** Create a canonical cross-platform state model that prevents false success and duplicate publishing.

## 9.1 Canonical states

```text
DRAFT
VALIDATING
INVALID
READY
APPROVED
SCHEDULED
PUBLISHING
PLATFORM_PROCESSING
PUBLISHED
FAILED
RETRYING
REAUTH_REQUIRED
BLOCKED
QUARANTINED
```

## 9.2 Rules

- Local accepted/uploaded != remotely published.
- Platform-specific async states must be represented.
- Authentication errors stop automatic retry.
- Unsupported-capability errors stop automatic retry.
- Unknown errors move to quarantine after bounded retries.

## 9.3 Acceptance criteria

All tested failure classes produce deterministic state transitions.

---

# 10. Phase 10 — Idempotency & Duplicate Prevention

**Status:** `PARTIAL`  
**Objective:** Make retries safe.

## 10.1 Required key strategy

Use a deterministic publish identity composed from stable identifiers such as:

`content_id + platform + account_id + media_hash + publish_slot`

Hash to a deterministic idempotency key.

## 10.2 Failure tests

- Worker crash before acknowledgment.
- Network timeout after platform acceptance.
- Client retry.
- Duplicate webhook.
- Duplicate scheduler event.
- Manual re-run after uncertain status.

## 10.3 Acceptance criteria

Repeated attempts for the same logical publication do not create duplicate posts when the underlying platform/API semantics permit idempotent reconciliation.

---

# 11. Phase 11 — Media Validation & Preparation Pipeline

**Status:** `PARTIAL`  
**Objective:** Reject incompatible media before social API calls.

## 11.1 Pipeline

```text
Source media
 -> FFprobe / metadata read
 -> codec/resolution/fps/audio validation
 -> platform-specific validation
 -> transcode only when needed
 -> content hash
 -> upload
```

## 11.2 Acceptance criteria

- Unsupported media fails before publishing.
- Required media variants are deterministic.
- Media hash is recorded.
- Large-file behavior is verified.
- Temporary files are cleaned up safely.

---

# 12. Phase 12 — Hermes MCP Integration

**Status:** `PARTIAL`  
**Objective:** Connect Hermes to BrightBean through MCP without exposing raw social credentials.

## 12.1 Initial tool surface

Start with low-risk tools:

- list accounts
- inspect account status
- create draft
- inspect post
- read analytics

Do not initially expose destructive or autonomous actions.

## 12.2 Controlled progression

```text
Read-only MCP
   -> Draft creation
   -> Scheduling
   -> Publishing after approval
   -> Autonomous publishing only after production gate
```

## 12.3 Acceptance criteria

- Hermes connects successfully.
- Only intended tools are exposed.
- Credentials are scoped.
- MCP failures are observable.
- Hermes cannot access raw Meta/TikTok credentials.

---

# 13. Phase 13 — Hermes Automation Layer

**Status:** `PARTIAL`  
**Objective:** Build repeatable social automation above the verified execution layer.

## 13.1 Target workflow

```text
Content Idea
 -> Hermes planning
 -> Platform-specific adaptation
 -> Media validation
 -> BrightBean draft
 -> Quality gate
 -> Human approval where required
 -> Schedule
 -> Publish
 -> Verify
 -> Collect analytics
```

## 13.2 Guardrails

- No infinite retries.
- No publish without valid target account.
- No publish with invalid media.
- No publish when authorization is stale.
- No silent fallback to browser automation.

## 13.3 Acceptance criteria

At least one complete multi-step Hermes-driven workflow passes in staging.

---

# 14. Phase 14 — Webhook / Verification / Reconciliation

**Status:** `PARTIAL`  
**Objective:** Reconcile asynchronous platform outcomes reliably.

## 14.1 Strategy

```text
Webhook = primary signal where supported
Status API = fallback / reconciliation
Scheduled sweep = final recovery mechanism
```

## 14.2 Scope

- Webhook verification.
- Signature/secret validation where applicable.
- Duplicate-event protection.
- Event ordering tolerance.
- Delayed processing.
- Final-state sweep.

## 14.3 Acceptance criteria

A temporary webhook outage does not leave the local state permanently incorrect.

---

# 15. Phase 15 — Backup, Restore & Disaster Recovery

**Status:** `NOT_STARTED`  
**Objective:** Prove that the system can recover without corrupting scheduled work or publishing duplicates.

## 15.1 Backup scope

- PostgreSQL data.
- Media data.
- Deployment manifests.
- Non-secret configuration.
- Hermes MCP configuration structure.
- Automation definitions.

Secrets must remain separately protected and must not be dumped into ordinary backup artifacts.

## 15.2 Restore drill

```text
Simulated loss
 -> restore
 -> migrate
 -> restore media
 -> start worker
 -> reconcile pending jobs
 -> verify no duplicate publish
```

## 15.3 Acceptance criteria

The restore drill passes with documented evidence.

---

# 16. Phase 16 — Security Validation & Adversarial Testing

**Status:** `NOT_STARTED`  
**Objective:** Attempt to break authorization, isolation, webhook handling, and secret handling.

## 16.1 Test set

- Invalid MCP credential.
- Expired credential.
- Wrong workspace.
- Wrong social account.
- Missing permission.
- Replayed request.
- Replayed webhook.
- Spoofed webhook.
- Malformed payload.
- Oversized upload.
- Secret leakage in logs.
- Unauthorized direct database access.
- Public media exposure beyond intended paths.

## 16.2 Acceptance criteria

No critical security issue remains open for production activation.

---

# 17. Phase 17 — Reliability / Chaos Testing

**Status:** `NOT_STARTED`  
**Objective:** Verify recovery under realistic failure conditions.

## 17.1 Failure injection

- Kill worker.
- Restart PostgreSQL.
- Interrupt network.
- Expire token.
- Force 429.
- Force 5xx.
- Interrupt media upload.
- Restart BrightBean.
- Restart Hermes.
- Restart tunnel.

## 17.2 Required outcomes

- No duplicate publishing.
- No silent data loss.
- No infinite retry.
- No false success.
- State converges to truth after recovery.

---

# 18. Phase 18 — Production Readiness Gate

**Status:** `NOT_STARTED`  
**Objective:** Decide whether the integrated system is ready for controlled production automation.

## 18.1 Gate checklist

| Gate | Requirement | Status |
|---|---|---|
| G1 | Reproducible BrightBean build | `NOT_STARTED` |
| G2 | Secure deployment | `NOT_STARTED` |
| G3 | Persistent PostgreSQL | `NOT_STARTED` |
| G4 | Backup/restore | `NOT_STARTED` |
| G5 | Stable HTTPS | `NOT_STARTED` |
| G6 | Facebook publish verification | `NOT_STARTED` |
| G7 | Instagram publish verification | `NOT_STARTED` |
| G8 | TikTok private/audit-aware test | `NOT_STARTED` |
| G9 | TikTok public path when authorized | `NOT_STARTED` |
| G10 | MCP integration | `NOT_STARTED` |
| G11 | Hermes automation | `NOT_STARTED` |
| G12 | Idempotency | `NOT_STARTED` |
| G13 | Webhook/status reconciliation | `NOT_STARTED` |
| G14 | Failure recovery | `NOT_STARTED` |
| G15 | Security validation | `NOT_STARTED` |
| G16 | Chaos testing | `NOT_STARTED` |
| G17 | Evidence package | `NOT_STARTED` |
| G18 | Rollback | `NOT_STARTED` |

## 18.2 Production activation rule

Autonomous publishing remains disabled until all required gates pass or an explicit human exception is documented.

---

# 19. Phase 19 — Controlled Production Rollout

**Status:** `NOT_STARTED`  
**Objective:** Move from staging to production with bounded risk.

## 19.1 Rollout order

1. Read-only analytics.
2. Draft creation.
3. Manual approval + scheduled publishing.
4. Single-account automation.
5. Multi-account automation.
6. Broader autonomous workflows only after stability evidence.

## 19.2 Rollback

Rollback must be possible by:

- pinning a previous known-good BrightBean build;
- disabling autonomous publish tools in Hermes;
- stopping the worker if necessary;
- restoring configuration and/or database state when required.

---

# 20. Phase 20 — Optimization, Learning & Skill Promotion

**Status:** `NOT_STARTED`  
**Objective:** Convert repeated operational work into deterministic tools or reusable skills.

## 20.1 Analyze after every meaningful milestone

Look for repeated:

- environment checks;
- path checks;
- token validation;
- publish verification;
- retry/recovery loops;
- evidence collection;
- state reconciliation;
- deployment validation;
- media validation.

## 20.2 Promotion rule

A repeated task becomes a deterministic tool or Hermes skill only when the pattern is demonstrated repeatedly and the automation does not preserve a false-green or stale-state bug.

## 20.3 Target future automations

- environment preflight checker;
- social credential health checker;
- media preflight validator;
- publish-state reconciler;
- evidence pack generator;
- deployment verifier;
- backup/restore verifier;
- Hermes MCP smoke-test runner.

---

# 21. Final Target Architecture

```text
                         HUMAN OWNER
                              |
                         Goal / Approval
                              v
                     +------------------+
                     |      HERMES      |
                     | Root Orchestrator|
                     +--------+---------+
                              |
                       MCP / REST / Event
                              |
                              v
                  +-------------------------+
                  |  BRIGHTBEAN SELF-HOSTED |
                  |-------------------------|
                  | Scheduler               |
                  | Publisher               |
                  | Retry / Idempotency     |
                  | Account / RBAC          |
                  | Audit                   |
                  | Analytics               |
                  | Webhooks                |
                  | REST API                |
                  | MCP                     |
                  +-----------+-------------+
                              |
                  First-party platform APIs
                 +------------+-------------+
                 |            |             |
                 v            v             v
             Instagram     Facebook      TikTok
                 |            |             |
                 +------------+-------------+
                              |
                       Remote verification
                              |
                              v
                            Hermes
                              |
                       Analytics / Learning
                              |
                              v
                     Super Creator OS
```

---

# 22. Current Execution State

**Current overall project status:** `IN_PROGRESS / PHASE 5 BLOCKED`  
**Current active phase:** `Phase 5 — Public HTTPS / Connectivity Boundary`  
**Autonomous publishing:** `DISABLED`  
**Production status:** `NOT_READY`  
**Next action:** Resolve the verified Workers VPC connectivity blocker, then open the Phase 6 OAuth gate.

### Current known constraints

1. BrightBean source is active and open-source, but production must use a tested commit rather than an unpinned moving branch.
2. Meta/Facebook/Instagram OAuth must be tested on the self-hosted deployment using our own application credentials.
3. TikTok public posting depends on TikTok's current authorization/audit requirements.
4. Stable public HTTPS is required for production OAuth/webhooks/MCP; domain/tunnel availability is an environment dependency.
5. No social-platform credential should be exposed to Hermes directly.

---

# 23. Execution Update Protocol

Every execution cycle must update these fields before the cycle is considered closed:

```text
Phase status
Actual implementation state
Tests executed
Observed result
Evidence path / reference
Open issues
Blockers
Decision
Next phase / next action
Timestamp
```

### Required update sequence

```text
Reconcile
 -> Execute
 -> Test
 -> Verify
 -> Remediate (if needed)
 -> Re-test
 -> Update this file
 -> Close current work
 -> Select next work
```

Never update the roadmap first and perform the work later. The roadmap must reflect observed system truth.

---

# 24. Change Log

| Date/Time | Phase | Change | Evidence | Status |
|---|---|---|---|---|
| 2026-09-28 | Planning | End-to-end architecture and phased roadmap approved by Human Owner | This document | APPROVED |

---

# 25. Research Snapshot / Source Register

The following sources were used to establish the roadmap baseline. Because external APIs and repositories change, these are research references, not permanent guarantees.

- BrightBean repository: https://github.com/brightbeanxyz/brightbean-studio
- BrightBean releases: https://github.com/brightbeanxyz/brightbean-studio/releases
- BrightBean security guidance: https://github.com/brightbeanxyz/brightbean-studio/blob/main/SECURITY.md
- BrightBean current issues: https://github.com/brightbeanxyz/brightbean-studio/issues
- Hermes MCP documentation: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/
- TikTok Content Posting API: https://developers.tiktok.com/docs/en/content-posting-api-get-started
- TikTok Direct Post reference: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- TikTok status reference: https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status
- Meta Pages API: https://developers.facebook.com/documentation/pages-api/manage-pages
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/get-started/
- Cloudflare Quick Tunnels: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/

---

# 26. Important Correction / Evidence Notes

The earlier evaluation identified BrightBean as the preferred execution layer. This roadmap intentionally does **not** record BrightBean as universally or permanently “100% stable.” Stability is a property to be established for the exact pinned build, exact environment, exact platform credentials, and exact workflows through the phases above.

In particular, current upstream issues include Meta/Facebook/Instagram connection problems in hosted deployments and media-upload enhancements. These are treated as risks to verify rather than ignored.

Likewise, TikTok integration is not considered complete merely because an upload API call returns successfully. The final platform state must be reconciled, and public visibility must respect TikTok's audit/authorization rules.

---

# 27. Completion Definition

This project is complete only when the final production workflow can demonstrate:

- Instagram publishing verified.
- Facebook publishing verified.
- TikTok publishing verified within the applicable account/audit constraints.
- Scheduling verified.
- Idempotent retry verified.
- Async status reconciliation verified.
- Webhook or fallback reconciliation verified.
- Token/authentication recovery verified.
- Hermes MCP verified.
- Hermes automation verified.
- Backup/restore verified.
- Security validation verified.
- Chaos/recovery validation verified.
- Rollback verified.
- Evidence recorded.
- Roadmap status synchronized with actual system state.

**Final principle:** the system is not considered healthy because it reports success; it is considered healthy when independent verification confirms the external state matches the expected state.


---

## Execution Update — 2026-09-28 01:34 +07:00

### Phase 1 — Reconcile & Baseline: PASS
- Real Windows host verified: Windows 10.0.26200.0, Docker 29.8.0, Compose v5.5.1, WSL2 Ubuntu-26.04.
- Hermes 0.21.5+3724.g14c4b62 verified; gateway is running.
- Existing Hermes MCP inventory recorded; Buffer is present; BrightBean is not configured.
- Workspace .mcp.json contains only the local scos-video MCP.
- C: has about 188.9 GB free; D: about 8.0 GB free.
- TCP 8000 is occupied by Woodpecker; 18100-18102 verified free for future isolation.
- HTTPS egress to GitHub, Meta Graph and TikTok developer/API endpoints verified.
- Existing Cloudflare containers are running; BrightBean route/domain remains intentionally unselected until Phase 5.
- Existing SCOS git tree is substantially dirty; no unrelated cleanup was performed.

Evidence: evidence/social-automation/phase1/SYSTEM_BASELINE.md, ENVIRONMENT_MATRIX.md, RISK_REGISTER.md

### Phase 2 activated
Next work: reconcile BrightBean source, Docker/Compose, current commit, tests, open integration issues, and select a tested pinned SHA.



---

## Execution Update — Phase 2 PASS

**Verified:** 2026-09-28 Asia/Bangkok

- BrightBean pinned at 6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8; detached checkout is clean.
- Compose configuration validates successfully with services: postgres, migrate, app, worker, tailwind.
- Reproducible image build succeeded: rightbean-studio:6c56e1f.
- Image digest: sha256:88871c9a3a84d4c0fd3ccf7a0257b60731aa34f716444cbef12627e4d0dead3d.
- Image revision label matches pinned source SHA.
- python manage.py check passed with 0 system-check issues.
- Full pytest: 2236 passed, 1 skipped, 73 warnings; exit 0; 2237 collected.
- Temporary PostgreSQL used for tests was removed; no production BrightBean service was started.
- No Meta/TikTok credentials were added and no social publishing was attempted.

**Evidence:** evidence/social-automation/phase2/SOURCE_RECONCILIATION.md`r

### Phase 3 activated
Next objective: deploy BrightBean locally in an isolated Compose project, bind only to localhost:18100, verify migrations/app/worker/health, then prepare the HTTPS/MCP boundary.





---

## Execution Update — Phase 3 + Phase 4 PASS / Phase 5 IN_PROGRESS

**Verified:** 2026-09-28 Asia/Bangkok

### Phase 3 — Self-Hosted Core Deployment: PASS
- Isolated Compose project `brightbean-phase3` deployed from pinned SHA `6c56e1f9190fb3e2571ee3f0c1d99b2d818aa9f8`.
- App is bound to `127.0.0.1:18100`; PostgreSQL to `127.0.0.1:15433`; existing TCP 8000 remains untouched.
- `migrate --check` exited 0.
- `/health/` returned HTTP 200 with `{"status": "ok"}`.
- `/accounts/login/` returned HTTP 200 when accessed with simulated HTTPS proxy headers; no temporary credential was created.
- App/worker restart preserved service health.
- Media persistence sentinel survived an app/worker restart and was removed after verification.
- Full stack down/up preserving volumes returned healthy/running services and HTTP 200 health.
- Initial port-merge issue and UTF-8 BOM issue were found and remediated before final pass.
- Initial `.env` inclusion in the deployment image was detected, then remediated with local `.dockerignore`, secret rotation and no-cache rebuild. Final image check: `ENV_IN_IMAGE=NO`.

**Evidence:** `evidence/social-automation/phase3/DEPLOYMENT.md`

### Phase 4 — Security Hardening: PASS (local pre-social gate)
- Random `SECRET_KEY` and `ENCRYPTION_KEY_SALT` generated and rotated after the initial image exposure was detected.
- `DEBUG=false`; `ALLOWED_HOSTS=127.0.0.1,localhost`.
- `.env` is Git-ignored; current secret values have zero matches in tracked Git content.
- Normal logs showed no tested secret/token patterns.
- PostgreSQL and BrightBean are localhost-only.
- No Meta/Instagram/Facebook/TikTok credentials or OAuth tokens configured.

**Evidence:** `evidence/social-automation/phase4/SECURITY_BASELINE.md`

### Phase 5 — Public HTTPS / Connectivity Boundary: IN_PROGRESS
- Existing named Cloudflare tunnel `08a4e3a2-48fa-4464-8688-a79dac8a6773` is dedicated to the existing Woodpecker infrastructure and was not modified.
- A temporary dedicated Quick Tunnel to BrightBean succeeded in creating an HTTPS edge, but the application returned HTTP 400 because `ALLOWED_HOSTS` intentionally rejects the unapproved trycloudflare hostname. This proves the edge reaches the app while the host-header boundary remains restrictive.
- Temporary Quick Tunnel was removed immediately after testing.
- Stable BrightBean hostname: NOT ESTABLISHED.
- Dedicated named BrightBean tunnel/route: NOT ESTABLISHED.
- Meta/Instagram/TikTok OAuth remains disabled until a stable HTTPS callback boundary exists.

**Evidence:** `evidence/social-automation/phase5/CONNECTIVITY.md`

### Current execution
**Phase 5 — establish dedicated HTTPS/public boundary for BrightBean without changing the existing Woodpecker route.**


### Phase 5 preflight update
- Production Compose configuration validated with a placeholder domain (exit 0).
- Caddyfile validated successfully (exit 0).
- Host ports 80/443 are free; public binding is intentionally deferred until the final hostname/route exists.
- Read-only inspection of the existing named Cloudflare tunnel could not resolve route metadata because the token-run container has no origin-certificate context; no workaround or route mutation was attempted.

### Phase 6 preflight (prepared, not active)
- BrightBean source-level social callback contract verified: `/social_accounts/callback/<platform>/` and onboarding connection callback `/onboarding/connect/callback/<platform>/`.
- BrightBean builds redirect URIs from the incoming request, so final public HTTPS origin must be stable before OAuth.
- MCP endpoint contract verified: `/api/v1/mcp` plus protected-resource metadata under `/.well-known/oauth-protected-resource/api/v1/mcp`.
- Provider tests for Facebook, Instagram and TikTok were included in the full pinned-SHA test suite that passed.
- No real Meta/TikTok credentials or OAuth sessions have been created.

**Phase 6 remains gated by Phase 5.**


## Execution Update — Woodpecker Gateway Reallocation / BrightBean Edge

Verified: 2026-09-28 Asia/Bangkok

- Woodpecker `.env` encoding was repaired from UTF-8 BOM to UTF-8 without BOM so `woodpecker-cli` can parse it again.
- Woodpecker host binding changed from `0.0.0.0:8000` to `127.0.0.1:8000`; local `/health` remains HTTP 200.
- Woodpecker server/agent remain running and the internal `woodpecker-net` path to `woodpecker-server:8000` returns HTTP 200.
- Existing named Cloudflare tunnel `08a4e3a2-48fa-4464-8688-a79dac8a6773` remains running and was not modified yet at the Cloudflare control plane.
- Added a local-only BrightBean edge container `brightbean-edge`, attached to both the BrightBean Compose network and existing `woodpecker-net`.
- `brightbean-edge` has no host port published; it serves only as the private service target for the named tunnel.
- Verified from `woodpecker-net`: `http://brightbean-edge/health/` -> HTTP 200 with BrightBean security headers; Caddy reverse proxy is functioning.
- Caddy image is pinned by digest `sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b`.
- Existing Woodpecker Quick Tunnel remains temporarily active pending an audit of any active webhook dependency.
- Hermes Cloudflare MCP connectivity was tested successfully: OAuth connected and tool discovery succeeded. The control-plane route/DNS change is therefore delegated to Hermes in the handoff prompt.

### Architecture decision
Woodpecker becomes a local/internal CI service. The existing named Cloudflare tunnel becomes the shared secure ingress gateway, targeting `brightbean-edge:80` over `woodpecker-net`. BrightBean remains isolated from host public ports and PostgreSQL remains private.

### Current Phase 5 gate
Still IN_PROGRESS until Hermes establishes and verifies a stable BrightBean public hostname, Cloudflare published route, public HTTPS health, MCP metadata, callback reachability and safe Quick Tunnel retirement.

### Hermes handoff
`evidence/social-automation/phase5/HERMES_HANDOFF_PROMPT.md`


---

## Final Execution Update — Local Work Closed

Verified: 2026-09-28 Asia/Bangkok

- Phases 1-4 remain PASS.
- Woodpecker is localhost-only on 127.0.0.1:8000 and remains healthy.
- Woodpecker Quick Tunnel was removed because WOODPECKER_EXPERT_WEBHOOK_HOST is empty.
- BrightBean app remains healthy on 127.0.0.1:18100.
- brightbean-edge reaches BrightBean over woodpecker-net and returns HTTP 200.
- No social OAuth credentials are configured.
- Phase 5 is BLOCKED only by missing Cloudflare control-plane authorization needed to create/update the remotely-managed tunnel published route and DNS.
- Phase 6 stays NOT_STARTED until public HTTPS/MCP/callback verification passes.
- Deterministic completion script: evidence/social-automation/phase5/Finalize-BrightBeanCloudflare.ps1



## Execution Update — Phase 5 VPC Verification / Final Blocker

Verified: 2026-09-28 Asia/Bangkok

- Cloudflare OAuth/control-plane access is now authenticated through the existing Chrome/Cloudflare account; the earlier authorization blocker is resolved.
- Existing named tunnel `08a4e3a2-48fa-4464-8688-a79dac8a6773` is healthy and uses QUIC; cloudflared prechecks pass.
- Current production cloudflared remains pinned to `cloudflare/cloudflared:2026.8.3` after an A/B check of `2026.9.3`; the upgrade did not eliminate the intermittent failure.
- HAIOS Cloudflare tunnel route is configured as `*/* -> http://brightbean-edge:80` and BrightBean edge is attached to `woodpecker-net`.
- `brightbean-edge` has static `172.18.0.6` on `woodpecker-net`; cloudflared is `172.18.0.4`.
- Direct origin verification from a container on `woodpecker-net`: `http://brightbean-edge:80/health/` -> HTTP 200.
- Direct verification from the cloudflared network namespace to `172.18.0.6:80/health/` -> HTTP 200.
- Worker `brightbean-social-edge-20260928` has stable public `workers.dev` HTTPS and a VPC Service binding to service `01a0e4c6-ae62-74e0-8cbf-4df204bec536`.
- A temporary VPC Network binding to tunnel `08a4e3a2-48fa-4464-8688-a79dac8a6773` was dry-run/deployed for A/B testing, then reverted.
- Worker source/config were returned to the original VPC Service baseline after the A/B test.
- A temporary second cloudflared connector was tested and removed; redundancy alone did not remove the failure.
- Final public stability test after rollback: 6 requests to `/health/` -> 3 HTTP 200 and 3 connection timeouts; failed calls returned no bytes after ~5 seconds.
- No Meta/Facebook/Instagram/TikTok OAuth credentials or tokens were created.
- No custom DNS zone was present in the Cloudflare account, so no fabricated custom hostname was created.

**Phase 5 status: BLOCKED.** The remaining blocker is intermittent Workers VPC -> tunnel/origin connectivity despite confirmed healthy local origin reachability and healthy QUIC tunnel transport. Cloudflare documents these failures as VPC connection errors and recommends using VPC Service Metrics to distinguish `connection_timeout`, `destination_unavailable`, `destination_ip_unroutable`, `proxy_internal_error`, and related classes before further architecture changes. Evidence: `evidence/social-automation/phase5/PHASE5_VPC_BLOCKER_20260928.md`.

**Decision:** Stop blind infrastructure mutation. Next execution must inspect the Cloudflare VPC Service Metrics/error class, then apply only the evidence-supported remediation. Phase 6 remains gated.

## Execution Update — Phase 5 VPC Runtime Classification / Stability Recheck

**Verified:** 2026-09-28 10:17 +07:00

### Reconcile / Research
- VPC Service 01a0e4c6-ae62-74e0-8cbf-4df204bec536 re-read with Wrangler: brightbean-edge, HTTP:80, 172.18.0.6, tunnel 08a4e3a2-48fa-4464-8688-a79dac8a6773.
- Cloudflare VPC documentation states connection failures are exposed in VPC Service Metrics and grouped as Bad Upstream, Client, or Internal.
- Cloudflare defines connection_timeout as a connection attempt timeout and proxy_internal_error as a Cloudflare proxy infrastructure error.
- Cloudflare Status currently reports Workers VPC Operational with no active incident explaining this failure.

### Diagnose
- Live Worker tail captured the failure from the production Worker.
- Observed runtime exception: HandshakeTimeoutError: handshake timeout.
- Failed invocation wall time was approximately 5000-5017 ms; successful VPC requests were approximately 96-315 ms.
- Diagnostic probe exposed name=Error, message=handshake timeout, code=null, ownKeys=[message,remote], cause=null.
- The exception is thrown by env.BRIGHTBEAN.fetch() before BrightBean returns an HTTP response.
- This points to VPC connection establishment rather than a BrightBean application-level response failure.

### Stability Test
- Public HTTPS after restoring the baseline Worker: 12 requests -> 6 HTTP 200, 6 HTTP 503.
- Failed requests: approximately 5149-5187 ms; successful requests: approximately 251-315 ms.
- Local BrightBean /health/: HTTP 200 twice.
- Internal brightbean-edge /health/: {"status":"ok"}.

### Remediation Safety
- A temporary Worker diagnostic logging change was deployed only for error-shape inspection.
- Diagnostic deployment: ec49f11e-3d06-49f5-b803-1ea938942593.
- Source was restored to the original Worker implementation and redeployed.
- Restored Worker deployment: f36baf70-e57e-448d-8528-a784ce0459cc.
- No BrightBean, Docker topology, OAuth, DNS, VPC Service, or production tunnel architecture was changed.

### Classification Decision
- Direct VPC Service Metrics-tab classification remains UNCONFIRMED because the dashboard requires an explicit existing-profile CUA grant; that security-sensitive grant was not silently approved.
- Observed runtime class is HandshakeTimeoutError: handshake timeout.
- Cloudflare's documented semantics make connection_timeout the matching documented class, but this is a semantic mapping, not a directly observed Metrics label.
- No evidence of connection_refused, destination_ip_unroutable, or proxy_internal_error was observed in the runtime exception.
- Do not perform additional speculative infrastructure changes while the Metrics label is unverified.

### Decision
**Phase 5 remains `BLOCKED`.**
**Phase 6 remains `NOT_STARTED` and gated by Phase 5.**

Preserve the healthy local BrightBean and tunnel architecture.

Next action: obtain the VPC Service Metrics classification for service `01a0e4c6-ae62-74e0-8cbf-4df204bec536`. Use that exact class to choose the next diagnostic/remediation path; do not infer a Cloudflare internal incident from the current runtime error alone.

Evidence: `evidence/social-automation/phase5/PHASE5_VPC_BLOCKER_20260928.md`

Sources:
- https://developers.cloudflare.com/workers-vpc/reference/troubleshooting/
- https://www.cloudflarestatus.com/services
## Execution Update — Social Automation Layer Reconciliation — 2026-09-28 11:18 +07:00

- Production Worker restored to baseline deployment `3f58cb0b-b681-4054-9cff-f8b1d52a3fb7` after all temporary diagnostics.
- Targeted Social Automation acceptance suite: `516 passed`.
- Corrected one OAuth callback test contract to simulate HTTPS (`secure=True`) because production has `SECURE_SSL_REDIRECT=True`; rerun passed.
- Local MCP boundary verified: protected-resource metadata HTTP 200, unauthenticated initialize POST HTTP 401, MCP GET 405 under HTTPS-proxy context.
- Roadmap status reconciled: Phase 5 `BLOCKED`; Phases 6-8 `BLOCKED`; Phases 9-14 `PARTIAL`; Phases 15-18 `NOT_STARTED`.
- Autonomous publishing remains disabled.
- Evidence package: `evidence/social-automation/phase5/EXECUTION_CYCLE_20260928_1118.md`.

### End-of-cycle decision
- Local BrightBean social execution, publisher safety, provider adapters, webhook handling, and MCP boundary are verified by the targeted suite.
- External production completion cannot be truthfully closed while the public VPC boundary remains intermittently unavailable and social-platform OAuth credentials/remote publish verification are absent.
- Next action remains evidence-first VPC classification, followed by Phase 6-8 remote OAuth/publish verification.

## Execution Update — End-to-End Closure Pass — 2026-09-28 11:50 +07:00
- Local source changes committed at b2ec479c2b0ba1ed21289ac1b1fd4aefe4f6d98b.
- Targeted Social Automation acceptance: 516 passed / 516.
- Publisher/state persistence acceptance: 77 passed / 77.
- Local MCP boundary: metadata 200, GET 405, health 200, unauthenticated initialize POST 401.
- Backup/restore: PASS locally; PostgreSQL restore verified 155 django_migrations rows and 92 public tables; media restore verified 81 files.
- Local restart recovery: worker, app, PostgreSQL all recovered with HTTP 200 health.
- Gitleaks source scan: no leaks found.
- Latest public VPC stability sample: 5x HTTP 200 / 3x HTTP 503; failures approximately 5.16-5.19s.
- Exact VPC Metrics error class remains unconfirmed. Cloudflare MCP Connectivity Directory reads return error 10000 Authentication error, and the current MCP catalog exposes no VPC metrics/analytics/logs tool.
- Phase 5 BLOCKED; Phases 6-8 BLOCKED; Phases 9-14 PARTIAL; Phase 15 PASS; Phases 16-17 PARTIAL; Phase 18 BLOCKED / NOT_READY; Phase 19 NOT_STARTED; Phase 20 PARTIAL.
- Autonomous publishing remains disabled.
- Human security gate remains open; no Cloudflare OAuth permission grant was approved automatically.

Evidence: phase15/BACKUP_RESTORE_DRILL_20260928.md; phase16/SECURITY_VALIDATION_20260928.md; phase17/CHAOS_RECOVERY_20260928.md; phase20/TARGETED_ACCEPTANCE_25690928_114832.txt

## Execution Update — VPC isolation and production readiness recheck — 2026-09-28

- Direct VPC Network binding reproduces handshake timeout with remote=true.
- Existing production VPC Service reproduces HandshakeTimeoutError: handshake timeout with remote=false.
- Failures were observed from BKK and SIN Worker colos.
- cloudflared telemetry shows 4 active QUIC connections, 0 closed connections, 0 tunnel request errors, stable RTT, and failed VPC calls do not increment tunnel proxied-request count.
- Raw TCP VPC connect did not provide a stable bypass; the canary also exhibited approximately 5s timeout behavior.
- Latest production Worker 8-request sample: 7 HTTP 200 and 1 timeout; one successful call took about 5.9s. This is not accepted as stable HTTPS.
- Current BrightBean container environment has empty Meta/Facebook/Instagram/TikTok app credential variables and the SocialAccount table is empty.
- Exact VPC Metrics error-code label remains UNCONFIRMED; no further speculative infrastructure mutation is justified.
- Phase 5 remains BLOCKED.
- Phases 6-8 remain BLOCKED until public boundary and real social OAuth/application prerequisites are available.
- Phase 15 PASS; Phases 16-17 PARTIAL; Phase 18 BLOCKED/NOT_READY; Phase 19 NOT_STARTED; Phase 20 PARTIAL.
- Evidence: phase5/CLOUDFLARE_VPC_ISOLATION_EVIDENCE_20260928.md and phase5/CLOUDFLARE_VPC_ESCALATION_PACKET_20260928.md.

