# Stage 8 Scope Boundary

Normative boundary specification for Stage 8 (Controlled Local Integration
Activation & Operator Runtime Readiness). Defined by Stage 8.0 and
subordinate to existing Stage 4, Stage 5, Stage 6, and Stage 7 public
contracts.

## In Scope

- Stage 8 planning, scope, acceptance criteria, and certification evidence.
- Local transport activation decision and safety contract.
- Smallest approved local-only transport implementation, only if a later
  Stage 8 item explicitly approves it.
- Credential and secret handling policy before any API-key use.
- Adapter simulator-to-activation readiness, without real dispatch unless a
  later explicit pilot approves it.
- Operator runtime runbook, recovery flow, rollback model, local evidence, and
  audit continuity.
- Deterministic local production readiness gate.
- Stage 8 final closure and Stage 9 or next-stage handoff.

## Out of Scope

- Stage 8.1 implementation during Stage 8.0.
- Runtime product behavior changes during Stage 8.0.
- Stage 4, Stage 5, Stage 6, or Stage 7 public contract changes except
  backward-compatible defect patches that are separately approved.
- Database schema changes, migrations, package changes, or dependency changes
  unless a later approved Stage 8 item explicitly requires them.
- Cloud hosting, SaaS, remote administration, multi-user remote surfaces,
  customer portal, payment, billing, CRM, Buffer, or external publishing
  integration.
- Browser, GUI, clipboard, or customer-facing automation.

## Forbidden Behaviors

Stage 8 work must not introduce:

- WebSocket, SSE/EventSource, polling, timers, background workers, or local
  HTTP transport before a Stage 8 decision approves a later implementation
  stage.
- Real ChatGPT, Claude Code, Codex, Hermes, or other AI adapter dispatch
  before a persisted per-dispatch approval and audit path is approved.
- API-key handling, secret persistence, external API calls, or credential use
  before a dedicated policy and later implementation approval.
- Network/cloud/SaaS/payment/CRM/customer portal behavior.
- External API or Buffer integration.
- Command execution bypass, approval bypass, direct store mutation from UI,
  or arbitrary shell execution.
- Secrets in source, docs, logs, event streams, snapshots, tests, or
  certification evidence.

## Local-First Boundary

- Stage 8 operates on the operator's local machine.
- Required checks must be local and offline unless a later explicit stage
  approves a named network action.
- Any approved listener must bind only to a local interface and must not
  expose a public network surface.
- No data leaves the local machine without an explicit operator-approved
  stage, documented action, audit record, and security boundary.

## Transport Boundary

- Stage 8.0 authorizes no transport implementation.
- Stage 8.1 may compare no transport, file snapshot refresh, local HTTP,
  WebSocket, SSE/EventSource, and polling.
- A later Stage 8 item may implement only the option explicitly approved by
  Stage 8.1.
- Transport must preserve deterministic fallback, local-only operation,
  rollback, security scan coverage, and test coverage.
- Remote bind, public network exposure, auth bypass, external pub/sub, and
  cloud transport are forbidden.

## Adapter Boundary

- Adapters remain inactive by default.
- Simulator and manual fallback remain mandatory until a later explicit pilot
  approves one real adapter.
- Adapter activation cannot proceed from preflight alone.
- Any real pilot requires one named adapter, persisted per-dispatch operator
  approval, append-only audit record, rollback, failure recovery, and manual
  fallback.
- Multiple adapters, blanket approvals, autonomous dispatch, and customer
  actions are forbidden.

## Credential and Secret Boundary

- Stage 8.0 implements no credential flow.
- Stage 8.3 may define policy before any implementation.
- Secrets are operator-owned, local, never committed, never logged, and never
  included in docs, events, snapshots, test output, or certification evidence.
- `.env.example` may be updated only by a later approved implementation stage
  that needs declared environment variables.
- Secret storage, API-key use, and external calls require later explicit
  approval.

## Event, Backend, and UI Sync Boundary

- Existing Stage 7 read surfaces remain the source for operator visibility.
- UI sync may consume only approved local read models and approved transport,
  if any.
- The UI must not mutate backend stores directly.
- Event, approval, queue, audit, and state stores remain protected.
- Missing, stale, or degraded evidence must remain visible and must not be
  silently converted into healthy status.

## Approval and Audit Boundary

- Operator approval remains the permanent safety boundary for actions.
- Read surfaces may display approval and audit state but may not approve,
  deny, or execute actions.
- Any later real dispatch requires persisted pre-dispatch approval and
  append-only post-decision audit evidence.
- Denial, rollback, failure, and manual fallback states must remain
  inspectable.

## Cloud, SaaS, Payment, CRM Boundary

Stage 8 does not authorize cloud hosting, SaaS conversion, remote
administration, telemetry export, customer portal, payment, billing, CRM,
Buffer, external publishing, or third-party platform API integration. Such
work requires a later separately approved stage with its own scope boundary,
acceptance criteria, threat model, and security review.

## Implementation Authorization Rules

- Stage 8.0 authorizes docs only.
- Each Stage 8.x item requires a clean preflight, an explicit operator task,
  affected-file scope, acceptance criteria, and verification evidence.
- A planning or decision document does not authorize runtime behavior.
- A later implementation stage may implement only the behavior explicitly
  approved by the immediately preceding decision or contract stage.
- No commit, push, tag, release, branch switch, merge, rebase, reset, stash,
  or clean operation is authorized without explicit operator approval.

## Patch Policy

Patch stages are allowed only for blocker, build failure, security failure,
certification failure, or wrong decision data. Patches must be minimal,
backward-compatible, documented, and verified with focused tests plus
regression checks relevant to the touched boundary.
