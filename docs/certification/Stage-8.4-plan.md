# Stage 8.4 Plan - Secret-Safe Adapter Activation Preflight Gate

Predecessor Stage 8.3 commit:
`fbd3dc9d935d9a08caf64237ff0f11728003b4ff`.

## Scope

Create a deterministic, backend-only, read-only gate that evaluates whether a
proposed adapter activation package is secret-safe and complete enough to
present to an operator for a later explicit decision.

Allowed Python files:

- `scos/control_center/secret_safe_adapter_preflight_models.py`
- `scos/control_center/secret_safe_adapter_preflight_validation.py`
- `scos/control_center/secret_safe_adapter_preflight_gate.py`
- `scos/control_center/tests/test_secret_safe_adapter_preflight_models.py`
- `scos/control_center/tests/test_secret_safe_adapter_preflight_validation.py`
- `scos/control_center/tests/test_secret_safe_adapter_preflight_gate.py`
- `scos/control_center/__init__.py` lazy exports only

Allowed docs:

- `docs/specification/SECRET_SAFE_ADAPTER_ACTIVATION_PREFLIGHT_CONTRACT.md`
- `docs/specification/STAGE8_ADAPTER_ACTIVATION_SECURITY_MATRIX.md`
- `docs/certification/Stage-8.4-plan.md`

## Architecture

```text
SecretSafeAdapterPreflightRequest
  -> request validation
  -> Stage 7.7 generic preflight evidence
  -> Stage 8.1 transport decision evidence
  -> Stage 8.2 manual snapshot boundary evidence
  -> Stage 8.3 credential policy and leak validation
  -> approval, audit, rollback, simulator, and manual fallback checks
  -> SecretSafeAdapterPreflightResult
```

## Tests

Required commands:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_secret_safe_adapter_preflight_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_secret_safe_adapter_preflight_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_secret_safe_adapter_preflight_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_preflight_models.py scos/control_center/tests/test_adapter_activation_preflight_validation.py scos/control_center/tests/test_adapter_activation_preflight_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_activation_decision_models.py scos/control_center/tests/test_transport_activation_decision_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py scos/control_center/tests/test_file_snapshot_transport_validation.py scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_models.py scos/control_center/tests/test_credential_redaction.py scos/control_center/tests/test_credential_policy_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

## Risks

- A ready result could be mistaken for activation authorization.
- Governance field names can look credential-like to broad redaction rules.
- Future stages could weaken fallback or approval semantics.
- Optional report writing could be mistaken for audit mutation.

## PASS Criteria

Stage 8.4 passes only if:

- git preflight passes
- changes stay in the allowed file list
- public models are immutable and deterministic
- complete synthetic evidence returns `READY_FOR_OPERATOR_DECISION`
- ready results still keep activation, dispatch, external calls, credentials,
  and runtime mutation blocked
- missing, denied, blanket, default, ambiguous, or stale approval cannot pass
- unredacted secret-like evidence cannot pass
- unapproved transport cannot pass
- audit, rollback, simulator fallback, and manual fallback evidence are
  required
- report writing is explicit, contained, deterministic, and secret-safe
- Stage 7.7 and Stage 8.1-8.3 regressions pass
- security, smoke, and release checks pass or dirty-tree warning is documented
- no commit, push, tag, or release occurs

## No Commit / Push Rule

No commit, push, tag, release, branch switch, merge, rebase, reset, stash, or
clean operation is authorized by Stage 8.4.

## Would-Be Commit Message

```text
feat(control-center): add Stage 8.4 secret-safe adapter activation preflight gate
```
