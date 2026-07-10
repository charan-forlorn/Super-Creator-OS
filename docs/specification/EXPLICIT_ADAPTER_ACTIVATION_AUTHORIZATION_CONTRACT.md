# Explicit Adapter Activation Authorization Contract

Stage: 8.5 - Explicit Operator Adapter Activation Authorization Gate.

## Purpose and Boundary

Stage 8.5 decides whether a named human operator has explicitly authorized one
exact adapter activation request in principle after Stage 8.4 returns
`READY_FOR_OPERATOR_DECISION`.

`AUTHORIZED_IN_PRINCIPLE` is not activation. It never means an adapter was
started, dispatch was performed, credentials were resolved, external calls were
made, or runtime state was mutated.

Every Stage 8.5 result preserves:

- `can_activate_now == False`
- `activation_executed == False`
- `credentials_materialized == False`
- `external_calls_made == False`
- `runtime_mutated == False`

## Public Models

- `OperatorIdentity`
- `AdapterActivationScope`
- `AdapterActivationAuthorizationRequest`
- `AuthorizationCheck`
- `AdapterActivationAuthorizationResult`

All public models are frozen dataclasses with deterministic `to_dict()`
serialization. Nested mappings are frozen on input and serialize in stable
sorted order.

## Public Functions

- `validate_operator_identity(...)`
- `validate_activation_scope(...)`
- `validate_adapter_activation_authorization_request(...)`
- `evaluate_adapter_activation_authorization(...)`
- `build_stage85_authorization_evidence(...)`
- `write_adapter_activation_authorization_report(...)`

Report writing is optional, explicit, contained under `repo_root`, stable JSON
only, and does not mutate Stage 8.4 artifacts or existing approval/audit stores.

## Decisions

- `AUTHORIZED_IN_PRINCIPLE`: Stage 8.4 is ready, exact human approval is
  request-bound, adapter-bound, runtime-bound, scope-bound, current, and
  evidence-bound.
- `DENIED`: the operator explicitly denies the exact request and the reason is
  preserved.
- `BLOCKED`: required preflight, operator, scope, approval, audit, rollback, or
  fallback evidence is missing, unsafe, mismatched, ambiguous, or secret-bearing.
- `EXPIRED`: the authorization expiry is not after `checked_at`, approval is
  stale, or preflight timestamp binding is stale.

## Stage 8.4 Compatibility

Stage 8.5 consumes the Stage 8.4 result model and public semantics. It does not
reconstruct Stage 8.4 logic. It requires:

- same adapter id
- `READY_FOR_OPERATOR_DECISION`
- `accepted == True`
- `ready_for_operator_decision == True`
- no Stage 8.4 blockers
- required Stage 8.4 check categories still passing
- `can_activate_now == False`
- `activation_authorized == False`
- `real_dispatch_blocked == True`
- `external_calls_blocked == True`
- `credentials_materialized == False`
- `runtime_mutated == False`

## Operator Approval Rules

Approval must be explicit and human:

- no implicit approval
- no default approval
- no inherited approval
- no wildcard adapter or runtime approval
- no blanket approval
- no reusable approval
- no AI-agent approval
- no authorization without a clear human decision

Approval evidence must bind:

- request id
- adapter id
- runtime target
- operator id
- authentication evidence reference
- approved operations
- credential reference ids
- transport mode
- Stage 8.4 preflight result id
- Stage 8.4 preflight timestamp
- authorization expiry

## Credential and Transport Rules

Stage 8.5 accepts credential references only. Plaintext values, token-like
strings, password-like fields, private-key-like material, bearer values, API-key
like values, and URLs are rejected by the Stage 8.5 material scan and Stage 8.3
no-secret-leak validation.

Transport remains limited to Stage 8.4 allowed transport modes. Stage 8.5 does
not start transport, open ports, poll, watch files, or create background work.

## Audit, Rollback, and Fallback

Audit readiness must indicate append-only capability and must not claim a write
occurred during Stage 8.5. Rollback and fallback acknowledgements are required
before authorization in principle can be granted.

## Determinism

All timestamps are caller-supplied. IDs use SHA-256 over canonical sorted
caller-supplied values. The implementation uses stdlib only and has no hidden
clock, random, UUID, subprocess, network, browser, GUI, or secret-store access.

## Known Limitations

Stage 8.5 validates authorization evidence. It does not verify real credentials,
execute adapters, persist audit records, perform network checks, or mutate
runtime state. A later activation stage is still required for any real adapter
activation.

## Rollback

Rollback is a single-stage revert of the Stage 8.5 modules, tests, and docs. No
data repair is required because Stage 8.5 adds no persistence, migration,
network behavior, adapter activation, or credential store.
