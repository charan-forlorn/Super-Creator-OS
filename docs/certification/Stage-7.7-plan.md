# Stage 7.7 Plan - Adapter Activation Preflight Gate

Predecessor: Stage 7.6, confirmed at commit
`978638464de03a107a1918d755f15c132a80d7c5`.

## Objective

Add a deterministic backend-only preflight gate that evaluates adapter
activation readiness without activating adapters or dispatching any work.

## Scope

Backend files:

- `scos/control_center/adapter_activation_preflight_models.py`
- `scos/control_center/adapter_activation_preflight_validation.py`
- `scos/control_center/adapter_activation_preflight_gate.py`
- focused tests for those modules
- lazy exports in `scos/control_center/__init__.py`

Docs:

- `docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md`
- `docs/specification/ADAPTER_ACTIVATION_SECURITY_READINESS.md`
- `docs/certification/Stage-7.7-plan.md`

## Non-Goals

- no frontend work
- no adapter activation
- no AI dispatch
- no network, cloud, SaaS, external API, browser, GUI, or clipboard automation
- no API key, token, OAuth, cookie, or secret handling flow
- no command execution
- no queue, event, approval, audit, database, or runtime-state mutation
- no commit, push, tag, or release

## Implementation Summary

Stage 7.7 adds frozen preflight models, input validation, and a read-only gate.
The gate inspects local evidence from prior stages, validates that required
controls are represented, blocks real dispatch, and may write a stable JSON
report only when the caller supplies a contained `output_path`.

## Test Plan

Run:

```text
.venv\Scripts\python.exe -m pytest scos/control_center/tests/test_adapter_activation_preflight_models.py scos/control_center/tests/test_adapter_activation_preflight_validation.py scos/control_center/tests/test_adapter_activation_preflight_gate.py -q
.venv\Scripts\python.exe -m pytest scos/control_center/tests -q
.venv\Scripts\python.exe scripts/security_scan_baseline.py
.venv\Scripts\python.exe scripts/test_smoke.py
.venv\Scripts\python.exe scripts/test_release.py
```

On restricted Windows temp directories, set `TMP` and `TEMP` to a workspace
directory before running pytest.

## Acceptance Criteria

- Required git preflight passes.
- Models are immutable and deterministic.
- Allowed target adapters and safe activation modes are accepted.
- Forbidden activation modes return errors.
- `allow_real_dispatch=True` produces a blocked result.
- `can_activate_now` remains `False`.
- `dispatch_blocked` remains `True`.
- Required and optional evidence statuses are represented.
- No implicit output write occurs.
- Explicit output writes only to a caller-supplied path inside `repo_root`.
- Focused tests and relevant regressions pass or exact failure evidence is
  documented.
- Docs match implementation.
- No commit, push, tag, or release is performed.

## Would-Be Commit Message

```text
feat(control-center): add Stage 7.7 adapter activation preflight gate
```
