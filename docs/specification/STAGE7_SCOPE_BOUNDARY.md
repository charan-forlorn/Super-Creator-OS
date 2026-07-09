# Stage 7 Scope Boundary

Normative boundary specification for Stage 7 (Local Control Center Read
Surface & Operator-Facing Integration Activation). Defined by Stage 7.0 and
subordinate to existing Stage 4, Stage 5, and Stage 6 public contracts.

## 1. Stage 7 in scope

- Deterministic read-only query surfaces over Stage 6 local backend state,
  event stream artifacts, approval records, audit ledger, health metrics, and
  drift evidence.
- Read surface contracts, tests, and coherence gates.
- Operator-facing read models for health, activity, approvals, audit status,
  and drift status.
- Controlled UI projection from approved local read models.
- A documented decision on whether WebSocket, SSE, polling, or no live
  transport is permitted for UI sync.
- Approval-aware command status views that display existing command and audit
  state without adding execution paths.
- Adapter activation preflight documentation and gates, without real
  dispatch.
- Stage 7 closure gate and Stage 8 or next-stage handoff.

## 2. Stage 7 out of scope

- Runtime product behavior changes outside the Control Center boundary.
- Stage 4, Stage 5, or Stage 6 public contract changes except
  backward-compatible defect fixes explicitly approved for a patch.
- Database schema changes unless a Stage 7.x task explicitly proves
  backward-compatible read-only migration requirements.
- Real AI adapter dispatch.
- External API integrations, including Buffer.
- Cloud hosting, SaaS, telemetry, customer portal, payment, billing, or CRM.
- Multi-tenant or remote-user surfaces.
- Browser, GUI, or clipboard automation.
- Commit, push, tag, release, branch switch, merge, rebase, reset, stash, or
  clean operations unless separately and explicitly approved.

## 3. Forbidden behaviors

Stage 7 work must not introduce:

- Writes through a read surface.
- Mutation of Stage 6 state, event, queue, audit, or approval stores from
  inspection APIs.
- WebSocket, SSE, polling, timers, or background sync before the Stage 7
  transport decision permits them.
- Real AI dispatch before a later approved activation stage creates persisted
  per-dispatch operator approval and audit evidence.
- Uncontrolled autonomous outward-facing actions.
- Secrets in source, docs, logs, event streams, test output, or certification
  evidence.
- Network/cloud/SaaS/payment/CRM/customer portal behavior.
- Direct frontend file mutation of backend stores.
- Arbitrary shell execution or command runner bypass.

## 4. Local-first boundary

- Stage 7 runs on the operator's machine.
- All required checks are local and offline by default.
- Persistence remains local files and existing Stage 6 stores.
- No data leaves the local machine unless a later explicitly approved stage
  documents the exact action, approval record, and security boundary.
- Localhost transport, if later approved, must be opt-in, test-covered, and
  documented before implementation.

## 5. Adapter boundary

- Adapters remain inactive by default.
- Simulator and manual handoff paths remain available.
- Stage 7 may define activation preflight requirements, but it must not
  perform real dispatch unless a later stage explicitly approves activation.
- Any future real dispatch requires a persisted operator approval record
  before the call and an append-only audit record after the decision.
- Adapter credentials are local, operator-owned, never committed, and never
  logged.

## 6. Event, backend, and UI sync boundary

- Stage 7.1 may read event stream artifacts and expose deterministic
  read-only projections.
- UI projection may consume approved read models only.
- The UI never executes work itself and never mutates backend stores directly.
- WebSocket, SSE, polling, timers, or background sync require a prior Stage 7
  decision. Until then, deterministic read/query invocation is the only
  allowed sync path.
- Replayability and deterministic output take priority over live transport.

## 7. Security boundary

- Existing security scan coverage for `scos/control_center` and
  `apps/control-center` must remain green.
- New read surfaces must validate paths and inputs and must reject URLs or
  remote paths where local filesystem roots are expected.
- No secrets may be printed, persisted in docs, or exposed through read
  outputs.
- No arbitrary subprocess or shell execution may be added.
- Any listener or transport later approved must be localhost-only and covered
  by tests and security review.

## 8. Operator approval boundary

- Operator approval remains the permanent safety boundary.
- Read surfaces may display approval state, but must not approve, deny, or
  execute actions.
- Approval-aware UI may submit only typed commands through existing command
  contracts, and only if a later Stage 7 task explicitly includes that scope.
- Denials, pending decisions, and audit records must remain append-only and
  inspectable.
- No batch blanket approval or default approval state is allowed.

## 9. No cloud, SaaS, payment, CRM rule

Stage 7 does not authorize cloud hosting, SaaS conversion, telemetry,
customer portal, payment, billing, CRM, or external integration work. Such
work requires a later separately approved boundary, acceptance criteria, and
security review.

## 10. No uncontrolled AI dispatch rule

Stage 7 does not authorize direct ChatGPT, Claude Code, Codex, Hermes, or
other AI adapter dispatch. Any future dispatch path must be explicit,
operator-approved per dispatch, audited, reversible, and preserve manual
fallback.
