# Stage 7 Final Closure Gate Contract

Stage: 7.8 - Stage 7 Closure Gate and Stage 8 Handoff.

## Purpose

Stage 7.8 is the final deterministic certification layer for Stage 7. It
answers whether Stage 7 is complete, locally verifiable, approval-safe,
read-surface coherent, transport-bounded, adapter-dispatch-safe, and ready to
hand off to Stage 8.

It is a closure and handoff stage only. It does not add a product feature.

## Public API

```text
run_stage7_final_closure_gate(
    *,
    repo_root,
    checked_at: str,
    output_path=None,
    require_clean_git: bool = True,
    run_control_center_tests: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_release_script: bool = True,
    run_frontend_checks: bool = True,
) -> Stage7ClosureResult | Stage7ClosureError
```

The function is read-only except for an explicit caller-supplied `output_path`
inside `repo_root`.

## Result Schema

The result includes:

- `gate_id`
- `gate_name`
- `checked_at`
- `go_no_go`
- `readiness_score`
- `accepted`
- `stage_closed`
- `stage_number`
- `latest_commit`
- `required_artifacts`
- `optional_artifacts`
- `stage_results`
- `compatibility_results`
- `safety_results`
- `test_results`
- `frontend_check_results`
- `security_results`
- `blockers`
- `warnings`
- `inspected_artifacts`
- `deferred_items`
- `forbidden_items_rejected`
- `stage8_handoff_path`
- `report_path`

All models are frozen dataclasses with deterministic `to_dict()` output.

## Required Evidence

The gate requires Stage 7.0 through Stage 7.7 docs, contracts, modules, tests,
and the Stage 7.8 closure docs/tests. It also requires Stage 4, Stage 5, and
Stage 6 closure evidence plus the Stage 8 handoff document.

## Optional Evidence

Live runtime data files such as SQLite state, event logs, and approved command
queues are optional. If absent, they are warnings rather than blockers.

## Scoring Rules

- `GO` requires zero blockers and zero warnings and always scores `100`.
- `NO_GO` means no blockers exist, but non-critical warnings remain. Scores
  are in the `70-99` range.
- `BLOCKED` means at least one required artifact, compatibility, safety, or
  handoff check failed. Scores are in the `0-69` range.
- `stage_closed=True` is allowed only for `GO` with `accepted=True`.

## Blocker and Warning Semantics

Blockers prevent Stage 7 closure. Warnings require operator review but do not
prove a public contract break.

Missing optional runtime artifacts are warnings. Missing Stage 7 source,
contract, test, closure, or Stage 8 handoff artifacts are blockers.

## Test Strategy

The closure gate records required certification commands as external checks.
It does not execute commands itself because Stage 7.8 forbids command
execution inside the implementation.

Required external evidence:

- focused Stage 7.8 model tests
- focused Stage 7.8 gate tests
- full `scos/control_center/tests`
- security scan baseline
- smoke script
- release script
- frontend `pnpm test`, `pnpm lint`, and `pnpm build` when scripts and
  dependencies are available

## Security Strategy

The gate scans Stage 7 implementation and frontend projection files for
unapproved live transport, network/API calls, command execution, browser/GUI
automation, clipboard automation, nondeterministic runtime behavior, and
credential markers.

## No-Feature Guarantee

Stage 7.8 creates only certification, closure, and handoff artifacts. It does
not add Stage 7.9 work or any new product feature.

## No-Dispatch Guarantee

Stage 7.8 never marks real AI dispatch or real adapter activation as allowed.
Stage 7.7 remains a preflight-only adapter readiness layer.

## No-Unapproved-Transport Guarantee

Stage 7.5 remains the active transport boundary. Live transport is deferred
until a later explicit operator-approved stage.

## Output Path Behavior

No report is written when `output_path=None`. If supplied, `output_path` must
resolve inside `repo_root`. Directory paths receive
`stage7_final_closure_report.json`.

## Stage 8 Handoff Behavior

The Stage 8 handoff must separate implemented Stage 7 capabilities, deferred
items, forbidden items, open decisions, risks, and the recommended Stage 8.0
planning task.
