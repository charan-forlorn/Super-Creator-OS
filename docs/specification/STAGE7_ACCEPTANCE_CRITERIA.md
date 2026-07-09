# Stage 7 Acceptance Criteria

Normative acceptance criteria for Stage 7. Companion to
`docs/roadmap/STAGE7_EXECUTION_PLAN.md` and
`docs/specification/STAGE7_SCOPE_BOUNDARY.md`. Defined by Stage 7.0.

## 1. Stage 7 entry criteria

Stage 7 implementation may begin only when:

- Stage 4 is closed.
- Stage 5 is certified and closed.
- Stage 6 is closed with the Stage 6.10 final integration gate documented as
  `GO`, `readiness_score == 100`, `stage_closed == True`, and zero blockers.
- `docs/roadmap/STAGE7_HANDOFF.md` exists.
- Stage 7.0 planning artifacts are committed before implementation begins.
- Working tree is clean, branch is `main`, and `HEAD == origin/main` at the
  start of each implementation stage.
- The specific Stage 7.x task is explicitly approved by the operator.

## 2. Per-stage acceptance template

Every Stage 7.x item closes only when:

1. **Goal met** - the stated goal in the Stage 7 execution plan is
   demonstrably achieved.
2. **Scope respected** - changes stay within the approved Stage 7.x scope and
   `STAGE7_SCOPE_BOUNDARY.md`.
3. **Read-only where required** - read/query surfaces do not mutate state,
   events, queues, audit records, approval records, or schemas.
4. **Deterministic evidence** - outputs and tests are deterministic or record
   any operator-supplied timestamp/input explicitly.
5. **Tests green** - focused tests, relevant regressions, smoke/security
   checks, and frontend checks when UI is touched pass locally.
6. **Safety preserved** - local-first, operator approval, manual fallback,
   and no uncontrolled AI dispatch remain intact.
7. **Docs updated** - contracts, certification docs, and roadmap records
   affected by the stage are updated.
8. **Git safety** - no commit/push/tag/release happens without explicit
   operator approval; final status and diff are reported.

## 3. Per-stage acceptance criteria

### Stage 7.1 - Local Control Center Read API / Query Surface

- Read-only query functions exist for approved Stage 6 artifacts.
- Tests prove queries do not mutate state, event, approval, audit, or queue
  stores.
- Query outputs are deterministic for identical local inputs.
- Invalid paths, missing artifacts, and malformed inputs return explicit
  errors.
- No UI, transport, adapter dispatch, cloud, or external API behavior is
  introduced.

### Stage 7.2 - Read Surface Contract and Coherence Gate

- Read surface contract documents schemas, errors, determinism, and
  non-mutation rules.
- Coherence checks compare read outputs against Stage 6 source artifacts.
- Gate failures produce explicit blockers, never silent fallbacks.
- Smoke/security checks remain green.

### Stage 7.3 - Operator Health and Activity Read Models

- Health, host metrics, recent activity, and drift status are available
  through stable read models.
- Read models include enough freshness/coherence metadata for operator trust.
- Drift or stale evidence is surfaced as warning/error state, not hidden.
- Tests cover healthy, degraded, missing, and stale artifact cases.

### Stage 7.4 - Controlled UI Projection from Read Models

- Selected UI panels render from approved local read projections.
- Existing static/mock fallback is preserved until the new path is verified.
- Frontend tests cover loading, empty, error, degraded, and populated states.
- `pnpm lint`, `pnpm build`, and the frontend test script pass when
  dependencies are available.
- No live transport is introduced unless Stage 7.5 has already approved it.

### Stage 7.5 - Explicit UI Sync Transport Decision

- A decision record states whether WebSocket, SSE, polling, or no live
  transport is permitted.
- The decision includes security analysis, localhost boundary, rollback plan,
  test expectations, and forbidden behaviors.
- No transport implementation is included in the decision stage unless a
  later approved implementation task explicitly allows it.

### Stage 7.6 - Approval-Aware Operator Command Views

- UI/read models expose pending, approved, denied, executed, and audit states
  without changing command execution behavior.
- Tests prove no UI path bypasses validation, command runner allowlists, or
  approval persistence.
- Denial and missing-approval states are visible and terminal for the action
  instance.
- Audit records remain append-only and inspectable.

### Stage 7.7 - Adapter Activation Preflight, No Dispatch

- Preflight checklist covers approval evidence, secret handling, simulator
  fallback, manual fallback, audit records, rollback, and security review.
- Tests or static checks reject accidental real dispatch imports/calls where
  practical.
- No adapter activation, API-key flow, network call, or AI dispatch occurs.
- "Do not activate" remains an acceptable outcome.

### Stage 7.8 - Stage 7 Closure Gate and Stage 8 Handoff

- Final gate or closure record verifies all accepted Stage 7 work items.
- Stage 4, Stage 5, and Stage 6 public contracts remain compatible.
- Smoke, security, relevant control-center tests, and frontend checks pass or
  have documented skip reasons.
- Stage 8 or next-stage handoff identifies only unimplemented/deferred work.
- Closure rejects unapproved WebSocket/SSE/polling, real AI dispatch,
  cloud/SaaS/payment/CRM, external API integration, and Stage 7.9+ feature
  creep.

## 4. Test expectations

- Focused unit tests for every new read/query module and read model.
- Contract tests for schemas, error models, deterministic output, and
  non-mutation guarantees.
- Regression tests for affected Stage 6 modules when a Stage 7 surface reads
  their artifacts.
- Frontend tests for any `apps/control-center/` changes.
- `scripts/test_smoke.py` and `scripts/security_scan_baseline.py` remain
  required close checks once Stage 7 implementation begins.

## 5. Security expectations

- No secrets, tokens, credentials, cookies, or private environment values in
  code, docs, logs, snapshots, or test output.
- No arbitrary shell execution, subprocess bypass, or command runner bypass.
- No network/cloud behavior unless a later approved stage explicitly defines
  it.
- Local path inputs are validated and URL paths rejected where inappropriate.
- Security scan findings are fixed or recorded as accepted only with explicit
  rationale.

## 6. Observability expectations

- Read outputs expose health, drift, stale data, and degraded states
  explicitly.
- Operator-facing views do not convert unknown or missing evidence into
  healthy status.
- Any generated reports are deterministic and reproducible from local
  artifacts plus recorded inputs.

## 7. Operator approval expectations

- Read surfaces can inspect approval state but cannot approve, deny, or
  execute actions.
- Command-related UI must preserve the Stage 6 approval lifecycle.
- No real adapter dispatch can occur without prior persisted per-dispatch
  approval and append-only audit evidence.
- Manual fallback remains available for AI-related workflows.

## 8. Regression expectations

- Stage 4, Stage 5, and Stage 6 closure assumptions remain intact.
- Existing Stage 6 tests relevant to touched artifacts remain green.
- Frontend lint/build/test checks run when UI changes occur and dependencies
  are available.
- Security baseline remains green before closing security-relevant stages.

## 9. Stage 7 final closure criteria

Stage 7 closes only when:

- All accepted Stage 7.x work items meet their acceptance criteria.
- Final closure evidence proves local-first, deterministic, approval-first
  behavior.
- No unapproved transport, dispatch, cloud, SaaS, payment, CRM, or external
  API behavior exists.
- Stage 7 closure gate or certification record reports PASS/GO with zero
  unresolved blockers.
- Stage 8 or next-stage handoff exists and separates implemented,
  in-progress, planned, deferred, and forbidden work.

## 10. Handoff criteria to Stage 8 or next stage

The Stage 7 handoff must include:

- Implemented Stage 7 capabilities.
- Deferred items and why they remain deferred.
- Open decisions requiring operator approval.
- Current test/security evidence.
- Known risks and blockers.
- Explicit confirmation of whether transport and adapter activation remain
  forbidden, approved, or deferred.
