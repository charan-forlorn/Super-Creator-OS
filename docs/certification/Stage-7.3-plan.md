# Stage 7.3 Certification Plan

## Entry Criteria

- Branch is `main`.
- `HEAD == origin/main`.
- Working tree is clean before implementation.
- Latest commit is Stage 7.2 or an approved later Stage 7.2 commit.
- Stage 4 is closed, Stage 5 is certified and closed, Stage 6 is closed and certified, and Stage 7.1/7.2 are complete.

## Implementation Scope

- Add immutable operator read model dataclasses.
- Add deterministic operator health/activity snapshot builder.
- Add public facade for query and read-only validation.
- Add focused tests for model immutability, determinism, activity limiting, missing evidence, blockers, facade behavior, and forbidden runtime tokens.
- Add Stage 7.3 contract and boundary documentation.

## Test Gates

- `python -m pytest scos/control_center/tests/test_operator_read_models.py -q`
- `python -m pytest scos/control_center/tests/test_operator_health_activity.py -q`
- `python -m pytest scos/control_center/tests/test_operator_health_activity_facade.py -q`
- `python -m pytest scos/control_center/tests -q`
- `python scripts/test_smoke.py`
- `python scripts/security_scan_baseline.py`
- `python scripts/test_release.py`

## Acceptance Criteria

- Operator models are frozen and deterministic.
- Health signals cover backend, state, event, approval, audit, security, drift, and host metrics evidence.
- Recent activity is deterministic and limited by `activity_limit`.
- Freshness/coherence metadata is present.
- Missing required evidence blocks.
- Missing optional evidence is surfaced as warning or missing/degraded signal.
- Stale, drifted, malformed, and incoherent evidence is not hidden.
- Unknown evidence is never marked healthy.
- Read-only validation proves no output path or write operation is allowed.
- No SQLite mutation, JSONL append/write, command execution, adapter dispatch, frontend, transport, or background worker is introduced.
- Stage 4/5/6/7.1/7.2 public contracts remain intact.

## Exit Criteria

Stage 7.3 exits only after targeted tests, control center regression tests, smoke, security baseline, and release checks pass or failures are reported with exact evidence. No commit, push, tag, release, merge, reset, rebase, stash, clean, or branch switch is performed.

## Stage 7.4 Handoff

Stage 7.4 can build UI projection from `OperatorReadModelSnapshot.to_dict()`. It must remain a consumer of these read models and must not bypass Stage 7.1/7.2 evidence boundaries.
