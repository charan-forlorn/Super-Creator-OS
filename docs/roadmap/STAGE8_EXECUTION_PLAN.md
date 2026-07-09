# Stage 8 Execution Plan

## Stage 8 Mission

Build controlled local integration activation readiness for the SCOS Control
Center without weakening the Stage 4, Stage 5, Stage 6, or Stage 7 safety
contracts. Stage 8 should decide and, only where later approved, implement the
smallest local-only runtime activation steps needed for operator use.

## Stage 8 Success Criteria

Stage 8 succeeds when:

- Every activation decision is explicit, documented, local-first, and
  operator-approved.
- Transport remains absent unless a Stage 8 decision approves a later
  implementation stage.
- Real adapter activation remains absent unless a later stage approves a
  simulator-first, audited, per-dispatch pilot.
- Credential and secret handling is governed before any API-key use.
- Manual fallback, rollback, local evidence, observability, and audit
  continuity remain available.
- Stage 4, Stage 5, Stage 6, and Stage 7 public contracts remain compatible.
- Stage 8 closes through a deterministic local readiness gate.

## Source of Truth Docs

- `docs/roadmap/STAGE8_HANDOFF.md`
- `docs/roadmap/STAGE8_HANDOFF_REVIEW.md`
- `docs/specification/STAGE8_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md`
- `docs/certification/Stage-8.0-plan.md`
- `docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md`
- `docs/specification/STAGE7_SCOPE_BOUNDARY.md`
- `docs/specification/STAGE7_ACCEPTANCE_CRITERIA.md`
- `docs/architecture/SCOS_ARCHITECTURE_BOUNDARY_CONSTITUTION.md`

## Proposed Stage 8 Work Items

Stage 8 is limited to eight focused work items. Patch stages are allowed only
for blocker, build failure, security failure, certification failure, or wrong
decision data.

### Stage 8.1 - Local Transport Activation Decision & Safety Contract

- **Goal:** Decide whether Stage 8 may implement local UI sync transport.
- **Scope:** docs, decision record, safety contract, risk analysis, rollback
  plan, and test expectations.
- **Must compare:** no transport, file snapshot refresh, local HTTP,
  WebSocket, SSE/EventSource, and polling.
- **Non-goals:** no transport implementation, no timers, no background
  workers, no backend routes, no frontend feature.
- **Classification:** approved for Stage 8 planning.

### Stage 8.2 - Local Transport Implementation Foundation

- **Goal:** Implement the smallest approved local-only transport, if Stage
  8.1 explicitly approves one.
- **Scope:** limited to the approved local transport boundary and tests.
- **Non-goals:** no remote bind, public network, auth bypass, cloud, external
  API, real adapter dispatch, or command execution change.
- **Classification:** proposed but not yet approved.

### Stage 8.3 - Runtime Credential & Secret Handling Policy

- **Goal:** Define local operator-owned credential handling policy before any
  API-key use.
- **Scope:** policy, threat model, `.env.example` expectations if a later
  implementation stage needs variables, logging redaction rules, and test
  expectations.
- **Non-goals:** no secrets committed, no secret store implementation, no
  API-key use, no external calls.
- **Classification:** approved for Stage 8 planning.

### Stage 8.4 - Adapter Simulator-to-Activation Bridge

- **Goal:** Connect adapter preflight evidence to simulator and manual
  fallback paths.
- **Scope:** activation readiness checks, simulator/manual fallback evidence,
  audit expectations, rollback requirements.
- **Non-goals:** no real adapter dispatch, no API calls, no credentials.
- **Classification:** proposed but not yet approved.

### Stage 8.5 - First Real Adapter Activation Pilot, If Approved

- **Goal:** Pilot one real adapter only if security and operator approval
  evidence are sufficient.
- **Scope:** one named adapter, persisted per-dispatch approval, append-only
  audit record, rollback, and manual fallback.
- **Non-goals:** no blanket approvals, no multiple adapters, no autonomous
  dispatch, no customer-facing action.
- **Classification:** forbidden until explicit operator approval.

### Stage 8.6 - Operator Runtime Runbook and Recovery Flow

- **Goal:** Document startup, shutdown, rollback, degraded states, failed
  activation, and manual fallback for local operator use.
- **Scope:** local SOP, evidence checklist, recovery commands, decision tree.
- **Non-goals:** no runtime implementation unless separately approved.
- **Classification:** approved for Stage 8 planning.

### Stage 8.7 - Local Production Readiness Gate

- **Goal:** Add a deterministic gate proving Stage 8 local integration is safe
  to operate.
- **Scope:** local checks, docs, tests, safety scans, and closure evidence.
- **Non-goals:** no new feature work inside the gate.
- **Classification:** proposed but not yet approved.

### Stage 8.8 - Stage 8 Final Closure and Stage 9 Handoff

- **Goal:** Close Stage 8 and create the next-stage handoff.
- **Scope:** closure record, final evidence, deferred items, open decisions,
  and Stage 9 or next-stage recommendation.
- **Non-goals:** no new feature work.
- **Classification:** proposed but not yet approved.

## Recommended Sequence

```text
8.1  Local transport activation decision and safety contract
  -> 8.2  Local transport implementation foundation, only if approved
      -> 8.3  Runtime credential and secret handling policy
          -> 8.4  Adapter simulator-to-activation bridge
              -> 8.5  First real adapter activation pilot, only if approved
                  -> 8.6  Operator runtime runbook and recovery flow
                      -> 8.7  Local production readiness gate
                          -> 8.8  Final closure and Stage 9 handoff
```

Sequencing rules:

- 8.1 must precede any WebSocket, SSE/EventSource, polling, timer, background
  worker, or local HTTP transport implementation.
- 8.3 must precede any API-key use, credential persistence, or external
  adapter call.
- 8.4 must precede any real adapter activation pilot.
- 8.5 may remain `NO_GO` if security, approval, audit, or rollback evidence is
  insufficient.
- 8.8 runs last and must reject unapproved cloud, SaaS, payment, CRM,
  customer portal, external API, Buffer, real dispatch, and unapproved
  transport behavior.

## Rollback and Recovery Strategy

- Prefer additive docs, contracts, gates, and local modules so each Stage 8.x
  item can be reverted independently.
- Keep manual fallback available for every adapter-related workflow.
- Preserve deterministic file snapshot or no-transport operation as the
  fallback if live transport fails or is not approved.
- Require append-only audit records and persisted operator approval for any
  later real adapter pilot.
- Do not alter Stage 4, Stage 5, Stage 6, or Stage 7 public contracts unless a
  later patch proves backward compatibility.
- Stop feature work and create a patch stage only for blockers, build
  failures, security failures, certification failures, or wrong decision data.

## Deferred Beyond Stage 8

- Cloud hosting, SaaS, multi-tenant operation, remote administration, customer
  portal, payment, billing, CRM, and sales automation.
- External publishing, Buffer integration, and third-party platform APIs.
- Multiple real adapter activations or autonomous dispatch.
- Hosted databases, external queues, pub/sub, cloud storage, and telemetry
  export.
- Any outward-facing send, spend, publish, or customer action.

## Would-Be Commit Message

```text
docs(roadmap): add Stage 8.0 execution plan, scope boundary, and acceptance criteria
```
