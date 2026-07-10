# Stage 8.5 Plan

Stage: Explicit Operator Adapter Activation Authorization Gate.

## Entry Criteria

- Branch is `main`.
- Working tree is clean before implementation.
- `HEAD == origin/main`.
- Latest local commit is `62c8b9f` or later approved Stage 8.4 work.
- Stage 8.4 public result semantics are available.

## Scope

Create:

- `scos/control_center/adapter_activation_authorization_models.py`
- `scos/control_center/adapter_activation_authorization_validation.py`
- `scos/control_center/adapter_activation_authorization_gate.py`
- `scos/control_center/tests/test_adapter_activation_authorization_models.py`
- `scos/control_center/tests/test_adapter_activation_authorization_validation.py`
- `scos/control_center/tests/test_adapter_activation_authorization_gate.py`
- `docs/specification/EXPLICIT_ADAPTER_ACTIVATION_AUTHORIZATION_CONTRACT.md`
- `docs/specification/STAGE8_OPERATOR_AUTHORIZATION_SECURITY_MATRIX.md`
- `docs/certification/Stage-8.5-plan.md`

Modify only:

- `scos/control_center/__init__.py` for lazy Stage 8.5 exports.

## Implementation Plan

1. Add failing Stage 8.5 tests for immutable models, validation semantics, gate
   decisions, report writing, determinism, and forbidden behavior.
2. Add frozen deterministic public models.
3. Add validation for human operator identity, exact activation scope, approval
   binding, timestamp coherence, credential-reference safety, audit readiness,
   rollback acknowledgement, and fallback acknowledgement.
4. Add the authorization gate over Stage 8.4 public result semantics.
5. Add optional contained JSON report writing.
6. Add docs and lazy exports.
7. Run focused tests, regressions, and quality gates.

## Acceptance Criteria

- Valid exact human authorization returns `AUTHORIZED_IN_PRINCIPLE`.
- Explicit denial returns `DENIED`.
- Invalid or unsafe requests return `BLOCKED`.
- Expired or stale authorization evidence returns `EXPIRED`.
- `can_activate_now`, `activation_executed`, `credentials_materialized`,
  `external_calls_made`, and `runtime_mutated` are always false.
- No real credentials are accessed.
- No adapter is activated.
- No network or external calls occur.
- No runtime or existing audit store is mutated.
- Stage 8.1 through Stage 8.4 regressions pass.
- Full control center tests pass.
- Security, smoke, and release gates pass or report only pre-existing
  non-blocking warnings.

## Verification Commands

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_authorization_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_authorization_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_authorization_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_preflight_models.py scos/control_center/tests/test_adapter_activation_preflight_validation.py scos/control_center/tests/test_adapter_activation_preflight_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_transport_activation_decision_models.py scos/control_center/tests/test_transport_activation_decision_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py scos/control_center/tests/test_file_snapshot_transport_validation.py scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_models.py scos/control_center/tests/test_credential_policy_validation.py scos/control_center/tests/test_credential_redaction.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_secret_safe_adapter_preflight_models.py scos/control_center/tests/test_secret_safe_adapter_preflight_validation.py scos/control_center/tests/test_secret_safe_adapter_preflight_gate.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

Use a workspace-contained `--basetemp` on Windows if the default pytest temp
directory has ACL restrictions.

## Exit Criteria

Stage 8.5 exits only after focused tests, relevant regressions, full
`scos/control_center/tests`, and security/smoke/release gates have been run and
reported.
