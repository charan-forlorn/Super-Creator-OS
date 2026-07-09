# Stage 8 Acceptance Criteria

Normative acceptance criteria for Stage 8. Companion to
`docs/roadmap/STAGE8_EXECUTION_PLAN.md` and
`docs/specification/STAGE8_SCOPE_BOUNDARY.md`. Defined by Stage 8.0.

## Stage 8 Entry Criteria

Stage 8 implementation may begin only when:

- Stage 4 is closed.
- Stage 5 is certified and closed.
- Stage 6 is closed and certified.
- Stage 7 is closed with `GO`, score `100`, `accepted=True`,
  `stage_closed=True`, and zero blockers.
- `docs/roadmap/STAGE8_HANDOFF.md` exists.
- Stage 8.0 planning artifacts are committed before implementation begins.
- Working tree is clean, branch is `main`, and `HEAD == origin/main` at the
  start of each implementation stage.
- The specific Stage 8.x task is explicitly approved by the operator.

## Per-Stage Acceptance Template

Every Stage 8.x item closes only when:

1. **Goal met** - the stated goal in the Stage 8 execution plan is
   demonstrably achieved.
2. **Scope respected** - changes stay within the approved Stage 8.x scope and
   `STAGE8_SCOPE_BOUNDARY.md`.
3. **Decision respected** - no implementation exceeds the preceding approved
   decision or contract.
4. **Local-first preserved** - no data leaves the operator machine unless a
   later explicit stage approves the exact action.
5. **Approval and audit preserved** - operator approval, denial, audit,
   rollback, and manual fallback remain intact.
6. **Deterministic evidence** - outputs and tests are deterministic or record
   operator-supplied inputs explicitly.
7. **Tests green** - focused tests, relevant regressions, smoke/security
   checks, and frontend checks when UI is touched pass locally.
8. **Docs updated** - affected contracts, certification docs, and roadmap
   records are accurate.
9. **Git safety** - no commit, push, tag, release, merge, rebase, reset,
   stash, clean, or branch switch happens without explicit approval.

## Stage 8.1 - Local Transport Activation Decision & Safety Contract

- Decision record compares no transport, file snapshot refresh, local HTTP,
  WebSocket, SSE/EventSource, and polling.
- Safety contract defines local-only binding, rollback, fallback, security
  scan coverage, test expectations, and forbidden behaviors.
- Decision states whether a later Stage 8 item may implement a transport.
- No transport, backend route, frontend feature, WebSocket, SSE/EventSource,
  polling, timer, or background worker is implemented.

## Stage 8.2 - Local Transport Implementation Foundation

- Runs only if Stage 8.1 approves one transport option.
- Implements the smallest approved local-only transport.
- Preserves deterministic fallback to no transport or file snapshot refresh.
- Tests cover healthy, stale, missing, malformed, unavailable, and rollback
  states.
- No remote bind, public network, external API, cloud transport, command
  execution change, or approval bypass is introduced.

## Stage 8.3 - Runtime Credential & Secret Handling Policy

- Policy defines operator-owned local secret handling, redaction, logging,
  evidence, `.env.example` rules, and prohibited storage locations.
- Tests or static checks are specified for secret leak prevention.
- No secret is committed, logged, echoed, persisted, or used.
- No API-key flow, secret store, external call, or real adapter call is
  implemented.

## Stage 8.4 - Adapter Simulator-to-Activation Bridge

- Bridge connects adapter preflight evidence to simulator and manual fallback
  readiness.
- Tests prove real dispatch remains blocked.
- Audit, rollback, and failure states are explicit.
- No API keys, credentials, network calls, or real adapter dispatch occur.

## Stage 8.5 - First Real Adapter Activation Pilot, If Approved

- Runs only if a later operator approval explicitly authorizes one named
  adapter pilot.
- Requires persisted per-dispatch approval before the call.
- Requires append-only audit evidence after the decision.
- Requires rollback, failure recovery, rate-limit handling, and manual
  fallback.
- May close as `NO_GO` if security, approval, audit, or recovery evidence is
  insufficient.
- No blanket approval, multi-adapter activation, customer action, Buffer
  integration, external publishing, or autonomous dispatch is allowed.

## Stage 8.6 - Operator Runtime Runbook and Recovery Flow

- Runbook documents startup, shutdown, rollback, degraded states, failed
  activation, manual fallback, and evidence capture.
- Recovery flow identifies safe operator actions for transport failure,
  adapter failure, secret failure, and audit mismatch.
- No runtime implementation is included unless separately approved.

## Stage 8.7 - Local Production Readiness Gate

- Gate verifies all accepted Stage 8 work items, contracts, docs, tests,
  security checks, approval boundaries, rollback evidence, and forbidden
  behavior rejection.
- Gate is deterministic and local-first.
- Gate writes no output unless caller explicitly supplies a repo-local output
  path.
- Gate adds no feature behavior.

## Stage 8.8 - Stage 8 Final Closure and Stage 9 Handoff

- Closure record verifies Stage 8 acceptance criteria.
- Handoff separates implemented, planned, deferred, forbidden, and open
  decision items.
- Closure rejects unapproved transport, real dispatch, API-key/secret
  implementation, network/API calls, cloud/SaaS/payment/CRM/customer portal,
  Buffer, external integrations, and Stage 8.9+ feature creep.
- No new feature work is included.

## Test Expectations

- Focused tests for every new runtime module, gate, or contract module.
- Contract tests for schemas, errors, deterministic output, and non-mutation.
- Frontend tests when `apps/control-center/` is touched.
- Security baseline after security-relevant changes.
- Smoke checks for local operator readiness changes.
- Full control-center regression when shared Control Center behavior is
  touched.
- No dependency installation during verification unless explicitly approved.

## Security Expectations

- No secrets, tokens, credentials, cookies, or private environment values in
  source, docs, logs, snapshots, event streams, or test output.
- No arbitrary shell execution, command runner bypass, approval bypass, or
  direct UI mutation of backend stores.
- No network, external API, cloud, SaaS, payment, CRM, customer portal, Buffer,
  or external publishing behavior unless a later explicit stage authorizes it.
- Local path inputs are validated and URL paths rejected where inappropriate.
- Any listener later approved is localhost-only and security-reviewed.

## Observability Expectations

- Operator-facing views and gates expose stale, missing, degraded, failed, and
  rollback states explicitly.
- Unknown evidence is never reported as healthy.
- Runtime activation evidence remains local, deterministic, and auditable.

## Operator Approval Expectations

- No action executes without the applicable persisted approval.
- Real adapter dispatch requires per-dispatch approval, not blanket approval.
- Denials and failed approvals are terminal for the action instance.
- Manual fallback remains available and documented.

## Regression Expectations

- Stage 4, Stage 5, Stage 6, and Stage 7 closure assumptions remain intact.
- Existing read/query, approval, audit, command, event, health, drift, and UI
  contracts remain backward-compatible.
- Relevant focused and regression tests pass before closing any implementation
  item.

## Final Closure Criteria

Stage 8 closes only when:

- All accepted Stage 8.x work items meet their acceptance criteria.
- A deterministic local readiness or closure gate reports `GO`/PASS with zero
  unresolved blockers.
- Forbidden behavior scans reject unapproved transport, real AI dispatch,
  API-key/secret implementation, network/API calls, cloud/SaaS/payment/CRM,
  customer portal, Buffer, and external integrations.
- Manual fallback, rollback, audit, and operator approval evidence are
  documented.
- Stage 9 or next-stage handoff exists.

## Handoff Criteria to Stage 9 or Next Stage

The Stage 8 handoff must include:

- Implemented Stage 8 capabilities.
- Deferred items and reasons.
- Open decisions requiring operator approval.
- Current test and security evidence.
- Known risks and blockers.
- Explicit status for transport, adapter activation, API-key/secret handling,
  external integrations, cloud/SaaS/payment/CRM/customer portal behavior, and
  Buffer integration.
