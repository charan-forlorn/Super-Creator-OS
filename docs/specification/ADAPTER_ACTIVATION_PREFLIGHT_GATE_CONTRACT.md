# Adapter Activation Preflight Gate Contract

Stage: 7.7 - Adapter Activation Preflight Gate.

## Purpose

Stage 7.7 determines whether the existing local adapter layer is ready for a
future explicit activation stage. It reports readiness evidence only. It does
not activate adapters, dispatch prompts, call APIs, open browsers, automate a
GUI, read secrets, or mutate runtime state.

## Public API

```text
run_adapter_activation_preflight(...) -> AdapterActivationPreflightResult | AdapterActivationPreflightError
```

Accepted target adapters:

- `chatgpt`
- `claude_code`
- `codex`
- `hermes`
- `all`
- `None`

Accepted activation modes:

- `preflight_only`
- `do_not_activate`
- `simulator_only`
- `manual_handoff_only`

Forbidden activation modes include real dispatch, live adapter, API dispatch,
cloud dispatch, browser automation, GUI automation, and clipboard automation.

## Result Fields

The result report contains these deterministic fields:

1. `gate_id`
2. `gate_name`
3. `checked_at`
4. `target_adapter`
5. `requested_activation_mode`
6. `go_no_go`
7. `readiness_score`
8. `accepted`
9. `can_activate_now`
10. `activation_allowed_later`
11. `dispatch_blocked`
12. `approval_evidence_status`
13. `audit_evidence_status`
14. `secret_handling_status`
15. `simulator_fallback_status`
16. `manual_fallback_status`
17. `rollback_status`
18. `security_review_status`
19. `transport_boundary_status`
20. `adapter_contract_status`
21. `blockers`
22. `warnings`
23. `checks`
24. `inspected_artifacts`
25. `forbidden_behavior_findings`

The implementation may also include `next_manual_actions` and `report_path`
for operator workflow clarity.

## Evidence Inputs

The gate inspects local repo artifacts from prior stages:

- Stage 5.3 adapter models, contracts, registry, and simulator
- Stage 5.5 manual handoff package
- Stage 6.6 approval and audit evidence models/store
- Stage 6.8 security scan baseline
- Stage 6.10 final integration contract
- Stage 7.1 through 7.6 read-only surface and operator command evidence docs
- Stage 7.0 scope, acceptance, execution plan, and handoff review docs

Optional runtime evidence may be absent and should produce warnings rather than
blockers.

## Safety Rules

- `can_activate_now` is always `False`.
- `dispatch_blocked` is always `True`.
- `allow_real_dispatch=True` returns a blocked result.
- Forbidden activation modes return `AdapterActivationPreflightError`.
- Caller-supplied values must be local strings and must not contain URL,
  remote path, or credential markers.
- The gate is read-only except for an optional caller-supplied `output_path`
  inside `repo_root`.
- Output reports are stable JSON with sorted keys.

## Non-Goals

- No real adapter activation.
- No AI prompt dispatch.
- No network, cloud, SaaS, external API, browser, GUI, or clipboard automation.
- No API key, OAuth, token, cookie, or secret handling flow.
- No frontend work.
- No queue, event log, approval, audit, database, or command execution
  mutation.

## Acceptance Criteria

- Public models are frozen and deterministic.
- The public gate function accepts all allowed target adapters and safe modes.
- Real dispatch and forbidden modes are blocked.
- Required evidence is reported as pass or blocker.
- Optional runtime evidence is reported as pass or warning.
- No implicit file write occurs.
- Explicit report output is written only when `output_path` is supplied.
- Focused tests and relevant Stage 7 regression tests pass.
