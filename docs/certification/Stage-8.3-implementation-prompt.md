# Stage 8.3 Implementation Prompt - Runtime Credential and Secret Handling Policy

## Context

You are working in `C:\Workspace\super-creator-os` on Super Creator OS
(SCOS). Stage 8.2 is complete and introduced only a manual local file snapshot
refresh transport foundation. Stage 8.2 did not authorize live transport,
frontend binding, backend routes, adapters, AI dispatch, credential handling,
secret storage, API-key use, external calls, timers, polling, or background
workers.

Stage 8.3 must define policy-first runtime credential and secret handling
before any later adapter activation or external integration work. Treat Stage
4, Stage 5, Stage 6, Stage 7, Stage 8.1, and Stage 8.2 contracts as protected.

## Goal

Implement the smallest local-only Stage 8.3 policy layer for credential
classification, redaction, snapshot/log/event validation, and operator
approval boundaries using synthetic data only. The result must prove that
SCOS has deterministic policy models and tests for preventing secret leakage,
without storing, reading, transmitting, or using real secrets.

## Non-goals

- No real secrets, credentials, API keys, tokens, cookies, or private env
  values.
- No secret manager, vault, encrypted store, keychain integration, or API-key
  flow.
- No adapter activation, AI dispatch, external API call, network behavior,
  cloud/SaaS/payment/CRM/customer portal/Buffer behavior, or publishing.
- No WebSocket, SSE/EventSource, polling, timers, file watchers, background
  workers, backend routes, local HTTP server, or frontend feature.
- No subprocess, shell, command execution, dependency change, migration,
  commit, push, tag, release, rebase, reset, stash, clean, or branch switch.

## Preflight

1. Inspect `git status --short --untracked-files=all`.
2. Inspect `README.md`, `CLAUDE.md`, Stage 8 docs, Stage 8.2 contract docs,
   and relevant `scos/control_center` modules/tests.
3. Confirm scope is local-only, policy-first, deterministic, stdlib-only, and
   fake-data-only.
4. Stop before editing if the worktree has risky unrelated changes in files
   required for Stage 8.3.

## Hard Rules

- Use Python stdlib only.
- Use frozen dataclasses or immutable values for public policy models.
- Use caller-supplied timestamps only; no current time, random UUIDs, process
  state, or nondeterministic ordering.
- All outputs must be deterministic with stable sorted serialization where
  applicable.
- Redaction must be deny-by-default for recognized secret fields and secret
  value patterns.
- Validators must reject unredacted synthetic secret values in logs, events,
  snapshots, approval evidence, and certification evidence.
- Do not print, persist, echo, or document real secret examples. Use obviously
  fake sentinel values such as `FAKE_SECRET_DO_NOT_USE`.

## Allowed Files

Prefer this exact scope unless existing repo naming strongly indicates a
nearby equivalent:

- `scos/control_center/credential_policy_models.py`
- `scos/control_center/credential_redaction.py`
- `scos/control_center/credential_policy_validation.py`
- `scos/control_center/tests/test_credential_policy_models.py`
- `scos/control_center/tests/test_credential_redaction.py`
- `scos/control_center/tests/test_credential_policy_validation.py`
- `scos/control_center/__init__.py` lazy exports only if needed
- `docs/specification/STAGE8_CREDENTIAL_SECRET_POLICY.md`
- `docs/certification/Stage-8.3-plan.md`

Do not modify frontend, package/dependency, adapter activation, transport,
command runner, event log mutation, database schema, or `.env` files.

## Architecture

Create a local policy boundary with four separable concerns:

1. Policy models: credential categories, sensitivity levels, allowed local
   evidence locations, forbidden output surfaces, approval boundary statuses,
   and deterministic violation records.
2. Redaction: pure functions that return redacted copies of dict/list/scalar
   data without mutating caller inputs.
3. Validation: pure functions that inspect logs/events/snapshots/approval
   records and return deterministic PASS/NO_GO evidence with blockers and
   warnings.
4. Documentation: policy contract, threat model summary, forbidden storage
   locations, `.env.example` expectations for later stages, and rollback.

## Public APIs

Design APIs close to this shape:

```python
redact_credential_payload(payload, *, policy) -> RedactionResult
validate_no_secret_leak(surface, *, policy, checked_at: str) -> PolicyValidationResult
validate_operator_approval_boundary(record, *, policy, checked_at: str) -> PolicyValidationResult
build_stage83_credential_policy_evidence(*, checked_at: str, metadata=None) -> PolicyValidationResult
```

Models should expose deterministic `to_dict()` methods and stable schema
version constants. Return structured errors/results instead of raising for
ordinary policy rejection.

## Security/Redaction Rules

- Secret-like field names must redact values, including `api_key`, `token`,
  `secret`, `password`, `credential`, `cookie`, `authorization`, and `bearer`.
- Secret-like values must be rejected if present unredacted in any inspected
  output surface.
- Redaction marker must be stable, for example `[REDACTED:SECRET]`.
- Redaction must preserve non-secret context needed for auditability.
- File snapshot payloads must never become credential channels.
- Operator approval evidence may record policy status and fake credential
  references, but never secret values.
- Unknown credential handling states must be warnings or blockers, never
  silently healthy.

## Tests

Add focused tests for:

- Immutable/deterministic model serialization.
- Field-name and value-pattern redaction.
- Nested dict/list redaction without input mutation.
- Validation rejects unredacted fake secrets in logs, events, snapshots, and
  approval evidence.
- Validation accepts redacted payloads and non-secret audit metadata.
- Caller-supplied timestamp appears in evidence; no clock/random behavior.
- Operator approval boundaries reject missing, denied, blanket, or ambiguous
  approval for credential use.
- Stage 8.2 file snapshot behavior remains compatible and not credential-aware.

Run at minimum:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_models.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_redaction.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_credential_policy_validation.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_file_snapshot_transport_models.py scos/control_center/tests/test_file_snapshot_transport_validation.py scos/control_center/tests/test_file_snapshot_refresh_transport.py
.venv\Scripts\python.exe -m pytest scos/control_center/tests
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
```

## Acceptance Criteria

- Stage 8.3 policy models, redaction functions, validators, docs, and tests
  are implemented within allowed files.
- No real secrets are introduced, stored, logged, transmitted, or documented.
- Secret leaks are deterministically rejected with structured blockers.
- Redaction is deterministic, non-mutating, and audit-preserving.
- Operator approval policy rejects blanket/default approval and any credential
  use without explicit later-stage authorization.
- Stage 8.2 remains manual snapshot only and cannot carry credential data.
- Focused tests and relevant regressions pass, or exact environment blockers
  are reported with evidence.

## Final Report Format

Report:

- Current State: branch/worktree, docs inspected, affected files.
- Changes: models, redaction, validation, docs, tests.
- Tests: command, result, passing count, failing count, failure cause.
- Security Review: secret-leak checks, forbidden behavior scan, residual
  risks.
- Result: Completed, partially completed, or blocked.
- Recommended Next Step: exactly one concrete action.

## Would-be Commit Message

```text
feat(control-center): add Stage 8.3 credential policy and redaction boundary
```
