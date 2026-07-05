# Project State Update Contract (Stage 5.7)

## Project State Model

`scos/control_center/result_intake_models.py` defines two models for local
project bookkeeping, both produced from an `AIResultIntakeRecord`:

- `ProjectStateUpdate` — a snapshot: previous/current stage, `task_status`,
  `stage_status`, latest agent/verdict, a one-line summary, evidence
  references, and `updated_at`.
- `NextActionDecision` — a conservative, non-executing recommendation:
  `recommended_action`, optional `target_agent` / `target_runtime_id`,
  `priority`, `reason`, and `requires_operator_approval`.

Both are built by `result_intake_builder.py`
(`build_project_state_update`, `build_next_action_decision`) and re-exposed
via thin wrappers in `project_state_update.py`
(`prepare_project_state_update`, `prepare_next_action_decision`). Neither
function mutates any Stage 4 or Stage 5.1-5.6 record — they only produce new,
independent Stage 5.7 records.

## Verdict to Status Mapping

`build_project_state_update` maps `AIResultIntakeRecord.verdict` to
`(task_status, stage_status)` via a fixed table:

| Verdict | task_status | stage_status |
| --- | --- | --- |
| `BLOCKED` | `blocked` | `blocked` |
| `FAIL` | `needs_fix` | `needs_review` |
| `NEEDS_FIX` | `needs_fix` | `needs_review` |
| `NEEDS_REVIEW` | `review_required` | `needs_review` |
| `PARTIAL` | `review_required` | `needs_review` |
| `PASS` | `approved` | `active` |
| `UNKNOWN` | `review_required` | `needs_review` |

Only two caller-supplied metadata flags may override this table, and only
for a `PASS` verdict:

- `ready_for_commit: true` -> `task_status = "ready_for_commit"` instead of
  `"approved"`.
- `stage_complete: true` -> `stage_status = "complete"` instead of
  `"active"`.

All other metadata keys are ignored for routing/state decisions — this keeps
the mapping deterministic and auditable from the verdict and the two named
flags alone.

## Next Action Rules

`build_next_action_decision` applies rules in this precedence order:

1. `verdict == "BLOCKED"` -> `hold_blocked`, no target agent.
2. `ready_for_commit: true` metadata flag and `verdict == "PASS"` ->
   `prepare_commit_gate`.
3. `stage_complete: true` metadata flag and `verdict == "PASS"` ->
   `mark_stage_complete`.
4. `verdict in (FAIL, NEEDS_FIX)` and `source_agent in (codex, hermes)` ->
   `send_to_claude_fix`, target `claude_code`.
5. `verdict in (FAIL, NEEDS_FIX)` and `source_agent == claude_code` ->
   `request_operator_review` (the conservative default — Claude Code
   fixing its own reported failure is not auto-recommended).
6. `verdict == PASS` and `source_agent == claude_code` ->
   `send_to_codex_review`, target `codex`.
7. `verdict == PASS` and `source_agent == codex` -> `send_to_hermes_audit`,
   target `hermes`.
8. `verdict == PASS` and `source_agent == hermes` ->
   `send_to_chatgpt_status_update`, target `chatgpt`.
9. `verdict == NEEDS_REVIEW` -> `request_operator_review`.
10. Fallback (any other verdict/agent combination, including `PARTIAL` and
    `UNKNOWN`) -> `request_operator_review`.

The explicit `ready_for_commit` / `stage_complete` operator flags take
precedence over the verdict/agent routing table because they represent an
explicit human signal, not an inference from the result text.

## Approval Rule

Every `NextActionDecision` except `recommended_action == "no_action"` must
have `requires_operator_approval == true` — this is enforced at the model
level (`NextActionDecision.__post_init__` raises if a non-`no_action`
decision claims `false`). No recommended action in this stage is ever
dispatched automatically; the Control Center UI always renders the approval
requirement alongside the recommendation
(`NextActionDecisionPanel` / `render_project_state_summary`).

## Stage 5.8 Handoff

Recommended next stage: **Stage 5.8 — Git Commit / Push Approval Gate**. It
should consume `ProjectStateUpdate.task_status` (specifically
`ready_for_commit`) and `NextActionDecision.recommended_action` as local,
deterministic inputs to an operator-gated commit/push workflow, without
introducing any automatic git write operation.
