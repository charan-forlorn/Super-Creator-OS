# Stage 8 Transport Safety Contract

This contract defines the safety boundary for any future Stage 8 local
transport implementation. Stage 8.1 itself is decision-only and implements no
transport.

## Localhost-Only Future Boundary

Any later approved transport must:

- operate only on the operator's local machine
- avoid public network exposure
- reject remote paths and URLs where local paths are expected
- preserve deterministic no-transport or file snapshot fallback
- expose degraded, stale, and unavailable states explicitly
- be removable by a single-stage rollback

Remote bind, external pub/sub, cloud transport, hosted queues, and third-party
transport services are forbidden until a later explicit stage changes this
contract.

## Operator Approval Requirements

Transport may observe approved read models, but it must not approve, deny, or
execute actions. Any action that affects runtime state must still require the
existing persisted operator approval boundary.

Future transport implementation must prove:

- read synchronization cannot bypass approval
- UI state cannot mutate backend stores directly
- denial states remain terminal for the action instance
- manual fallback remains available

## Audit Requirements

Future transport must preserve append-only audit evidence. If transport emits
runtime evidence later, that evidence must be local, deterministic, ordered,
and inspectable.

Minimum future audit expectations:

- decision evidence records the approved transport option
- startup and shutdown states are observable
- degraded and rollback states are observable
- real adapter dispatch remains separately audited if ever approved later

## Rollback and Kill Switch Requirements

Any later transport implementation must include:

- immediate operator-visible fallback to no transport
- deterministic file snapshot or manual refresh fallback where applicable
- a documented rollback path
- tests proving transport-disabled behavior remains usable
- no schema migration required for rollback

If rollback fails or stale evidence cannot be surfaced clearly, the transport
must remain `NO_GO`.

## Secret Handling Restrictions

Stage 8.1 implements no secret handling. Future transport must not read,
store, log, expose, or transmit credentials. API-key policy must be defined by
a dedicated Stage 8 credential stage before any credential use.

Forbidden until explicit later approval:

- committed secrets
- secret storage
- credential logs
- API-key use
- external API calls
- credential values in event streams, snapshots, tests, or reports

## Adapter Dispatch Restrictions

Transport is not adapter activation. Future transport must not activate
ChatGPT, Claude Code, Codex, Hermes, or other AI adapters. Adapter dispatch
requires a separate explicit stage, one named adapter, persisted per-dispatch
operator approval, append-only audit evidence, rollback, and manual fallback.

## Accepted Future Implementation Conditions

A later Stage 8 implementation item may proceed only if all are true:

- Stage 8.1 explicitly allows exactly one future transport option.
- The later task explicitly names that option.
- The working tree starts clean on `main` with `HEAD == origin/main`.
- The affected-file scope is declared before implementation.
- Focused tests and relevant regression tests are defined.
- Security scan expectations are defined.
- Rollback and manual fallback are documented.
- No cloud, SaaS, payment, CRM, customer portal, Buffer, external API, real
  adapter dispatch, or command execution behavior is introduced.

The preferred first future candidate, if implementation is approved at all, is
`FILE_SNAPSHOT_REFRESH_ALLOWED_LATER` because it keeps transport local,
deterministic, and easiest to roll back.
