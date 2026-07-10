# Secret-Safe Adapter Activation Preflight Contract

Stage: 8.4 - Secret-Safe Adapter Activation Preflight Gate.

## Purpose and Boundary

Stage 8.4 adds a deterministic backend-only gate that evaluates whether a
proposed adapter activation package is safe enough to present to an operator
for a later explicit activation decision.

`READY_FOR_OPERATOR_DECISION` means evidence readiness only. It never means
adapter activation, activation authorization, dispatch permission, credential
runtime approval, external API approval, or network approval.

Every result preserves:

- `can_activate_now == False`
- `activation_authorized == False`
- `real_dispatch_blocked == True`
- `external_calls_blocked == True`
- `credentials_materialized == False`
- `runtime_mutated == False`

## Public Models

- `SafeCredentialReference`
- `SecretSafeAdapterPreflightRequest`
- `PreflightCheck`
- `PreflightValidationResult`
- `SecretSafeAdapterPreflightResult`
- `FrozenEvidenceMap`

All public models are frozen dataclasses with deterministic `to_dict()`
serialization.

## Public Functions

- `validate_secret_safe_adapter_preflight_request(...)`
- `evaluate_secret_safe_adapter_preflight(...)`
- `build_stage84_preflight_evidence(...)`
- `write_secret_safe_adapter_preflight_report(...)`

Report writing is optional, explicit, contained under `repo_root`, stable JSON
only, and does not affect gate semantics.

## Verdicts and Scores

- `READY_FOR_OPERATOR_DECISION`: score `100`; evidence is complete for later
  human review only.
- `NO_GO`: score `70-99`; valid proposal with failed safety requirements.
- `BLOCKED`: score `0-69`; missing, malformed, or untrusted required
  evidence.

Scores never authorize runtime behavior.

## Evidence Requirements

The request must include:

- Stage 7.7 generic adapter preflight evidence
- Stage 8.1 transport decision evidence
- Stage 8.2 file snapshot boundary evidence
- Stage 8.3 credential policy evidence
- operator approval evidence
- audit readiness evidence
- rollback evidence
- simulator fallback evidence
- manual fallback evidence

Unknown or missing required evidence blocks readiness.

## Credential Rules

Credential references are metadata only. `material_present` must be `False`.
Secret-like values, forbidden material fields, or unredacted synthetic secret
sentinels block the gate. Stage 8.3 no-secret-leak validation is applied to
normalized evidence values so governance field names remain representable
without becoming credential material.

## Transport Rules

Stage 8.4 accepts only Stage 8.2 manual file snapshot evidence or no
transport. WebSocket, SSE/EventSource, polling, local HTTP, timers, watchers,
background workers, and live transport claims block readiness.

## Approval and Audit Rules

Approval evidence must be explicit, adapter-specific, action-specific,
time/evidence bound, and presentation-only. Denied, blanket, default,
ambiguous, stale, or activation-authorizing evidence cannot pass.

Audit readiness must represent append-only capability and must not write audit
records during the gate.

## Rollback and Fallback Rules

Rollback must restore adapter-disabled state, require no network dependency,
and require no recovery of stored secret values. Simulator and manual fallback
must remain available and must not claim runtime activation.

## Determinism

All timestamps are caller-supplied. IDs and evidence digests are SHA-256
derived from stable normalized inputs. Collections serialize in stable order.

## Known Limitations

Stage 8.4 evaluates evidence shape and policy consistency. It does not verify
real credentials, execute adapters, perform network checks, or mutate audit
stores.

## Threat Model

Primary risks are accidental secret leakage, approval-boundary confusion,
misreading preflight as authorization, transport expansion, and fallback loss.
Mitigations are structured blockers, invariant result fields, Stage 8.3 leak
validation, transport boundary checks, and required rollback/fallback evidence.

## Rollback

Rollback is a single-stage revert of the Stage 8.4 modules, tests, and docs.
No data repair is required because the gate adds no persistence, migration,
adapter activation, network behavior, or secret store.

## Later-Stage Requirement

Any real adapter activation still requires a later explicit stage with
persisted per-dispatch operator approval, append-only audit evidence, rollback
evidence, manual fallback, and a dedicated security review.
