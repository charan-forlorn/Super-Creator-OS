"""SCOS Stage 5.7 project state / next action helper renderers.

Thin wrappers around ``result_intake_builder.build_project_state_update`` and
``result_intake_builder.build_next_action_decision``, plus a deterministic
text renderer that summarizes both together for the operator. This module
never mutates any Stage 5.1-5.6 record, never executes AI, and never
dispatches the recommended action automatically.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

try:
    from .result_intake_builder import (
        build_next_action_decision,
        build_project_state_update,
    )
    from .result_intake_models import (
        AIResultIntakeError,
        NextActionDecision,
        ProjectStateUpdate,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from result_intake_builder import (
        build_next_action_decision,
        build_project_state_update,
    )
    from result_intake_models import (
        AIResultIntakeError,
        NextActionDecision,
        ProjectStateUpdate,
    )

PROJECT_STATE_UPDATE_SCHEMA_VERSION = 1


def prepare_project_state_update(
    *,
    intake_record,
    previous_stage: str,
    current_stage: str,
    updated_at: str,
    metadata=None,
) -> ProjectStateUpdate | AIResultIntakeError:
    return build_project_state_update(
        intake_record=intake_record,
        previous_stage=previous_stage,
        current_stage=current_stage,
        updated_at=updated_at,
        metadata=metadata,
    )


def prepare_next_action_decision(
    *,
    intake_record,
    created_at: str,
    target_runtime_id_map=None,
    metadata=None,
) -> NextActionDecision | AIResultIntakeError:
    return build_next_action_decision(
        intake_record=intake_record,
        created_at=created_at,
        target_runtime_id_map=target_runtime_id_map,
        metadata=metadata,
    )


def render_project_state_summary(
    update: ProjectStateUpdate, decision: NextActionDecision
) -> str:
    """Render a deterministic operator-facing summary of state + next action."""
    if not isinstance(update, ProjectStateUpdate):
        raise ValueError(
            "NOT_A_PROJECT_STATE_UPDATE: update must be a ProjectStateUpdate instance"
        )
    if not isinstance(decision, NextActionDecision):
        raise ValueError(
            "NOT_A_NEXT_ACTION_DECISION: decision must be a NextActionDecision instance"
        )

    evidence_lines = (
        "\n".join(f"- {ref}" for ref in update.evidence_refs)
        if update.evidence_refs
        else "- None"
    )
    target_agent = decision.target_agent or "None"
    target_runtime_id = decision.target_runtime_id or "None"
    approval_line = (
        "Yes — operator approval required before dispatch."
        if decision.requires_operator_approval
        else "No — no dispatch is recommended."
    )

    return (
        f"# Project State Update — {update.task_id}\n"
        "\n"
        f"- **Session:** {update.session_id}\n"
        f"- **Previous Stage:** {update.previous_stage}\n"
        f"- **Current Stage:** {update.current_stage}\n"
        f"- **Task Status:** {update.task_status}\n"
        f"- **Stage Status:** {update.stage_status}\n"
        f"- **Latest Agent:** {update.latest_agent}\n"
        f"- **Latest Verdict:** {update.latest_verdict}\n"
        "\n"
        "## Summary\n"
        "\n"
        f"{update.summary}\n"
        "\n"
        "## Evidence\n"
        "\n"
        f"{evidence_lines}\n"
        "\n"
        "## Next Action\n"
        "\n"
        f"- **Recommended Action:** {decision.recommended_action}\n"
        f"- **Target Agent:** {target_agent}\n"
        f"- **Target Runtime:** {target_runtime_id}\n"
        f"- **Priority:** {decision.priority}\n"
        f"- **Reason:** {decision.reason}\n"
        f"- **Operator Approval Required:** {approval_line}\n"
    )
