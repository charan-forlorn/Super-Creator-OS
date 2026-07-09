# Stage 8.3 Plan - Runtime Credential and Secret Handling Policy

Predecessor Stage 8.2:
`docs/certification/Stage-8.2-plan.md`.

## Scope

Implement local-only, policy-first credential and secret handling rules before
any API-key use, adapter activation, external integration, or real dispatch.

Allowed Python files:

- `scos/control_center/credential_policy_models.py`
- `scos/control_center/credential_redaction.py`
- `scos/control_center/credential_policy_validation.py`
- `scos/control_center/tests/test_credential_policy_models.py`
- `scos/control_center/tests/test_credential_redaction.py`
- `scos/control_center/tests/test_credential_policy_validation.py`
- `scos/control_center/__init__.py` lazy exports only

Allowed docs:

- `docs/specification/STAGE8_CREDENTIAL_SECRET_POLICY.md`
- `docs/certification/Stage-8.3-plan.md`

## Assumptions

- Stage 8.2 is manual local file snapshot refresh only.
- Stage 8.3 may define policy but must not implement a secret store or API-key
  flow.
- All examples and tests use synthetic data only.
- Caller-supplied timestamps are required for deterministic evidence.

## Architecture

```text
synthetic caller payload
  -> immutable Stage 8.3 policy model
  -> pure redaction helper
  -> pure leak validator
  -> operator approval boundary validator
  -> deterministic policy evidence
```

## Tests

Required verification commands:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_redaction.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py scos/control_center/tests/test_file_snapshot_transport_validation.py scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
```

Frontend checks are not required because Stage 8.3 must not touch frontend
files.

## Risks

- Redaction rules could miss a future secret shape.
- A later stage could mistake policy evidence for credential-use approval.
- File snapshots could be misused as credential channels.
- Tests could accidentally include realistic secret-looking values.

## PASS Criteria

Stage 8.3 passes only if:

- preflight passes
- policy models are deterministic and immutable
- redaction returns new payloads and does not mutate inputs
- validators reject unredacted synthetic secret-like fields and values
- validators accept redacted payloads and non-secret audit metadata
- operator approval validation rejects missing, denied, blanket, default, or
  ambiguous credential approval
- Stage 8.2 file snapshot behavior remains compatible
- no real secrets are committed, logged, echoed, persisted, or used
- no API-key flow, secret store, adapter activation, external API call, live
  transport, frontend feature, subprocess, shell, timer, polling, or
  background worker is introduced
- relevant focused tests, control-center regression, security scan, and smoke
  checks pass or exact environment blockers are documented
- no commit, push, tag, or release occurs

## No Commit / Push Rule

No commit, push, tag, release, branch switch, merge, rebase, reset, stash, or
clean operation is authorized by Stage 8.3.

## Would-Be Commit Message

```text
feat(control-center): add Stage 8.3 credential policy and redaction boundary
```
