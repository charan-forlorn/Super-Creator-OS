# Stage 8 Handoff

## Implemented Stage 7 Capabilities

- Local Control Center read/query surface.
- Read surface coherence gate.
- Operator health and activity read models.
- Controlled frontend UI projection from deterministic local fixture data.
- Read surface transport decision.
- Approval-aware operator command views.
- Adapter activation preflight gate with real dispatch blocked.
- Stage 7 final closure gate.

## Deferred Items

- Live transport remains deferred because Stage 7.5 did not approve a runtime
  WebSocket, SSE, polling, timer, or background-worker implementation.
- Real adapter activation remains deferred because Stage 7.7 is preflight-only.
- API-key and secret handling remains deferred until a dedicated security
  design and operator approval.
- Cloud/SaaS/payment/CRM/customer portal integrations remain outside the
  approved local-first scope.

## Open Decisions Requiring Operator Approval

- Whether Stage 8 may introduce live local transport.
- Whether Stage 8 may activate real ChatGPT, Claude Code, Codex, or Hermes
  adapters.
- Whether Stage 8 may define an API-key handling boundary.
- Whether any external integration belongs in Stage 8 at all.

## Current Test and Security Evidence

Stage 8 starts from the Stage 7.8 certification evidence:

- focused closure model tests
- focused closure gate tests
- full Control Center backend regression
- security scan baseline
- smoke script
- release script
- frontend test, lint, and build checks when available

## Known Risks and Blockers

- Treating read-only visibility as execution permission would violate the
  Stage 6 approval boundary.
- Treating adapter preflight as activation would bypass the Stage 7.7 contract.
- Treating the transport decision as implementation approval would bypass
  Stage 7.5.
- Optional local runtime files may be absent on a clean checkout.

## Transport Status

Transport remains deferred. No live transport is approved by this handoff.

## Real Adapter Activation Status

Real adapter activation remains deferred. No real adapter dispatch is approved
by this handoff.

## Recommended Stage 8.0 Planning Task

Create Stage 8.0 planning docs that define the Stage 8 mission, explicit
operator-approved scope, non-goals, acceptance criteria, and first safe
implementation step.

## Strict Stage 8 Non-Goals Until Approved

- no WebSocket, SSE/EventSource, polling, timers, or background workers
- no real AI dispatch
- no real adapter activation
- no API-key flow
- no network/API calls
- no command execution bypass
- no browser/GUI/clipboard automation
- no mutation of approval, audit, queue, event, or state stores outside
  existing contracts
- no cloud/SaaS/payment/CRM/customer portal behavior
