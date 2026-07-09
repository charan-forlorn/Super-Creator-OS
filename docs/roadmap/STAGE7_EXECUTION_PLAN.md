# Stage 7 Execution Plan

## 1. Executive summary

Stage 7 turns the certified Stage 6 local Control Center foundation into an
operator-facing read and integration surface without weakening the Stage 6
safety boundary. It starts with deterministic read-only inspection over local
state, event, approval, audit, health, and drift artifacts. Only after that
exists should UI projection, transport decisions, approval-aware command
views, or adapter preflight work begin.

This document is a Stage 7.0 planning artifact. It authorizes no
implementation by itself; each Stage 7.x work item requires its own approved
task before code changes begin.

## 2. Stage 7 mission

Build a local-first, deterministic, approval-preserving operator read surface
and controlled integration path on top of the Stage 6 foundation, while
deferring real-time transport and real AI dispatch until explicit Stage 7
decisions approve them.

## 3. Stage 7 success criteria

Stage 7 succeeds when:

- Operators can inspect local backend state, events, approvals, audit records,
  health, and drift status through documented read-only surfaces.
- UI panels that are activated in Stage 7 render from local backend/query
  projections rather than hardcoded mock data.
- Any sync transport choice is documented before implementation and remains
  local-first.
- Any adapter activation work is approval-gated, audited, optional, and
  reversible.
- Stage 4, Stage 5, and Stage 6 public contracts remain backward compatible.
- Security, smoke, focused unit, frontend, and regression gates appropriate to
  each stage pass locally.
- A final Stage 7 closure record proves no forbidden cloud, SaaS, payment,
  CRM, uncontrolled AI dispatch, or unapproved transport behavior was added.

## 4. Source of truth

- `docs/roadmap/STAGE7_HANDOFF.md` - primary Stage 7 handoff.
- `docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md` - binding
  Stage 6 closure and handoff contract.
- `docs/certification/Stage-6-final-integration-release.md` - Stage 6 final
  delivered capability map and deferred item list.
- `docs/certification/Stage-6.10-plan.md` - Stage 6.10 implementation and
  verification record.
- `docs/roadmap/STAGE6_EXECUTION_PLAN.md`,
  `docs/specification/STAGE6_ACCEPTANCE_CRITERIA.md`, and
  `docs/specification/STAGE6_SCOPE_BOUNDARY.md` - inherited planning,
  acceptance, and boundary patterns.

## 5. Proposed Stage 7 work items

Stage 7 is limited to eight focused work items. Patch stages are allowed only
for blocker, build failure, deploy failure, security failure, certification
failure, or wrong decision data.

### Stage 7.1 - Local Control Center Read API / Query Surface

- **Goal:** Implement a deterministic, read-only query surface over existing
  Stage 6 state, event, approval, audit, health, and drift artifacts.
- **Scope:** `scos/control_center/` read/query modules, tests, contracts, and
  certification evidence only.
- **Non-goals:** no writes, no UI feature, no WebSocket/SSE/polling, no
  adapter dispatch, no cloud/network behavior.
- **Owner recommendation:** Claude Code implements; Codex reviews regression
  and security; ChatGPT confirms scope gates; Hermes records evidence.
- **Dependencies:** Stage 7.0 closed.

### Stage 7.2 - Read Surface Contract and Coherence Gate

- **Goal:** Add the contract and coherence checks that prove the read surface
  is read-only, deterministic, and aligned with Stage 6 artifacts.
- **Scope:** specification docs, focused tests, smoke/security integration as
  needed.
- **Non-goals:** no new read capabilities beyond 7.1 except blocker fixes.
- **Owner recommendation:** Codex owns review/regression/security
  verification; Hermes owns evidence; ChatGPT resolves gate decisions.
- **Dependencies:** 7.1.

### Stage 7.3 - Operator Health and Activity Read Models

- **Goal:** Promote Stage 6.9 health, host metrics, recent activity, and drift
  evidence into stable read models suitable for operator display.
- **Scope:** read-model modules and tests in `scos/control_center/`;
  contracts and certification docs.
- **Non-goals:** no frontend panels yet unless explicitly included in 7.4; no
  live transport.
- **Owner recommendation:** Claude Code implements; Codex verifies; Hermes
  records operational evidence.
- **Dependencies:** 7.1 and 7.2.

### Stage 7.4 - Controlled UI Projection from Read Models

- **Goal:** Render selected Control Center panels from local read projections
  while keeping the UI local-first and testable.
- **Scope:** `apps/control-center/` components and tests, read-only client
  adapter to the approved local surface, docs.
- **Non-goals:** no command execution changes, no real-time transport unless
  already approved by 7.5, no external API calls.
- **Owner recommendation:** Claude Code implements; Codex verifies frontend
  regression; ChatGPT decides panel scope.
- **Dependencies:** 7.1 through 7.3.

### Stage 7.5 - Explicit UI Sync Transport Decision

- **Goal:** Decide whether Stage 7 permits WebSocket, SSE, polling, or no live
  transport for UI sync.
- **Scope:** decision document, threat model, acceptance criteria, and
  rollback plan.
- **Non-goals:** no transport implementation in this stage unless a later
  approved task explicitly authorizes it.
- **Owner recommendation:** ChatGPT owns planning/gate decision; Codex reviews
  security/regression risk; Hermes records audit evidence.
- **Dependencies:** 7.1 and evidence from 7.4 needs.

### Stage 7.6 - Approval-Aware Operator Command Views

- **Goal:** Surface command, approval, denial, and audit status in the UI from
  read models without changing command execution behavior.
- **Scope:** read models, UI panels, frontend tests, approval/audit contract
  references.
- **Non-goals:** no new execution path, no bypass of Stage 6 command runner or
  approval boundary, no real adapter dispatch.
- **Owner recommendation:** Claude Code implements; Codex verifies approval
  boundary and tests; Hermes checks audit evidence.
- **Dependencies:** 7.4 and transport decision documented in 7.5.

### Stage 7.7 - Adapter Activation Preflight, No Dispatch

- **Goal:** Define the preflight checklist, approval evidence, secret handling
  boundary, rollback path, and simulator/manual fallback requirements for any
  future real adapter activation.
- **Scope:** docs, tests for gates if appropriate, and read-only inspection of
  existing adapter contracts.
- **Non-goals:** no real AI dispatch, no API-key flow, no network calls, no
  adapter activation.
- **Owner recommendation:** ChatGPT owns decision framework; Codex verifies
  security boundary; Hermes records workflow evidence; Claude Code implements
  only gate/check code if approved.
- **Dependencies:** 7.6.

### Stage 7.8 - Stage 7 Closure Gate and Stage 8 Handoff

- **Goal:** Add a deterministic final Stage 7 closure gate and handoff record
  proving Stage 7 scope, tests, security, approval, and local-first
  constraints held.
- **Scope:** certification gate, tests, release record, next-stage handoff.
- **Non-goals:** no new product feature work.
- **Owner recommendation:** ChatGPT owns gate criteria; Codex owns
  regression/security verification; Hermes owns evidence review.
- **Dependencies:** all accepted Stage 7 implementation and decision stages.

## 6. Recommended sequence

```
7.1  Local read/query surface
  -> 7.2  Read surface contract and coherence gate
      -> 7.3  Health/activity read models
          -> 7.4  Controlled UI projection
              -> 7.5  UI sync transport decision
                  -> 7.6  Approval-aware command views
                      -> 7.7  Adapter activation preflight, no dispatch
                          -> 7.8  Closure gate and Stage 8 handoff
```

Sequencing rules:

- 7.1 must happen before UI projection or adapter preflight.
- 7.5 must happen before any WebSocket, SSE, polling, timer, or live transport
  implementation.
- 7.7 must not activate real adapters; it prepares the decision boundary only.
- 7.8 runs last and must reject unapproved cloud/SaaS/payment/CRM,
  uncontrolled dispatch, and unapproved transport behavior.

## 7. Rollback and recovery strategy

- Prefer additive modules, contracts, and panels so each Stage 7.x item can be
  reverted independently if it fails verification.
- Keep query surfaces read-only and side-effect-free so rollback does not
  require state migration.
- Do not alter Stage 6 schema or audit formats unless a later stage explicitly
  proves backward-compatible migration.
- For UI stages, keep existing static/mock fallback fixtures until the
  read-model path is proven and tested.
- For any failed gate, stop feature work, record the blocker, and create only
  a patch stage if the failure is a blocker, build fail, security fail,
  certification fail, or wrong decision data.

## 8. Deferred beyond Stage 7

- Real AI adapter dispatch.
- External API integrations and Buffer integration.
- Cloud hosting, SaaS, telemetry, customer portal, payment, billing, or CRM.
- Multi-user remote access or remote administration.
- Hosted database, external queue, third-party pub/sub, or cloud storage.
- Autonomous outward-facing send/spend/publish/customer actions.
- Commercial productization beyond local operator read/control surfaces.

## 9. Stage 7.1 recommendation

Stage 7.1 should be **Local Control Center Read API / Query Surface**. It best
preserves local-first execution, operator approval, deterministic state,
testability, no uncontrolled AI dispatch, and incremental integration. It also
creates the stable inspection boundary required by later UI, health, approval,
transport, and adapter stages.

## 10. Would-be commit message

```
docs(roadmap): add Stage 7.0 execution plan, scope boundary, and acceptance criteria
```
