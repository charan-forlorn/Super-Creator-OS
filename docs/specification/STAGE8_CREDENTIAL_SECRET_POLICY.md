# Stage 8 Credential and Secret Policy

Stage: 8.3 - Runtime Credential and Secret Handling Policy.

## Purpose

Stage 8.3 defines the local policy boundary for credentials and secrets before
any later API-key use, adapter activation, external integration, or dispatch
pilot. It adds deterministic policy models, redaction helpers, validation
functions, documentation, and tests using synthetic data only.

This stage does not implement credential storage, credential loading, secret
manager behavior, API-key flow, external calls, adapter activation, live
transport, or frontend behavior.

## Scope

Allowed runtime policy modules:

- `scos/control_center/credential_policy_models.py`
- `scos/control_center/credential_redaction.py`
- `scos/control_center/credential_policy_validation.py`

Allowed docs and tests:

- `docs/specification/STAGE8_CREDENTIAL_SECRET_POLICY.md`
- `docs/certification/Stage-8.3-plan.md`
- `scos/control_center/tests/test_credential_policy_models.py`
- `scos/control_center/tests/test_credential_redaction.py`
- `scos/control_center/tests/test_credential_policy_validation.py`

## Policy Model

Stage 8.3 models are frozen dataclasses with deterministic `to_dict()` output.
They define:

- credential categories
- sensitivity levels
- forbidden output surfaces
- allowed local evidence locations
- redaction findings
- policy violations
- validation results
- operator approval boundary statuses

`STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION = 1`.

## Redaction Rules

Secret-like fields are redacted when their names contain configured markers
such as token, password, credential, cookie, authorization, bearer, or the API
key marker.

Secret-like scalar values are redacted when they match synthetic secret
sentinels, bearer-like values, key-like values, assignment-like secret text, or
private-key-like text.

Redaction:

- returns a new payload
- does not mutate caller input
- preserves non-secret audit context
- uses the stable marker `[REDACTED:SECRET]`
- records deterministic redaction findings

## Validation Rules

Validation functions inspect local data supplied by the caller and return
structured `PolicyValidationResult` objects. They do not read environment
variables, files, network resources, or process state.

Validation rejects unredacted secret-like fields or values in:

- logs
- events
- snapshots
- approval evidence
- certification evidence

Unknown surfaces are classified as `UNKNOWN` and must not be silently treated
as healthy.

## Operator Approval Boundary

Stage 8.3 does not authorize credential use. It only models the approval
boundary. Credential use remains blocked unless a later explicit stage defines
and approves an implementation.

The policy rejects:

- missing approval for requested credential use
- denied approval
- blanket approval
- default approval
- ambiguous approval
- credential use without later-stage authorization
- approval evidence containing unredacted secret-like values

## File Snapshot Boundary

Stage 8.2 file snapshots must never become credential channels. Snapshot
payloads may be inspected by Stage 8.3 validators, but Stage 8.3 does not add
credential data to Stage 8.2 snapshot payloads and does not change snapshot
refresh behavior.

## Prohibited Storage Locations

Secrets must not appear in:

- source files
- docs
- logs
- event streams
- snapshots
- tests
- certification evidence
- approval evidence
- committed environment files
- frontend files

## Environment Variable Expectations

Stage 8.3 does not update `.env.example` and does not declare new runtime
environment variables. A later explicitly approved implementation stage may
document required variable names, but must still avoid committing secret
values.

## Threat Model Summary

Primary risks:

- secret values leaking through logs or snapshots
- adapter activation treating policy as credential authorization
- blanket operator approval bypassing per-dispatch review
- tests or docs normalizing fake examples into real secret handling
- file snapshots being repurposed as credential transport

Mitigations:

- deterministic redaction and validation
- deny-by-default output surfaces
- caller-supplied timestamps only
- structured blockers for leaks
- policy-only operator approval modeling
- no persistence, network, environment reads, or external calls

## Rollback

Rollback is limited to the Stage 8.3 policy modules, tests, and docs. No data
repair is required because Stage 8.3 adds no persistence, migration, network
behavior, adapter activation, or secret store.

## Verification

Required focused checks:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_redaction.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_validation.py
```

Required regressions:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py scos/control_center/tests/test_file_snapshot_transport_validation.py scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
```
