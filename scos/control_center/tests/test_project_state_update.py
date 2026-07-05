"""test_project_state_update.py - SCOS Stage 5.7 project state update suite.

Plain executable script (no pytest). Covers deterministic state/next-action
summary rendering and visibility of the operator approval requirement.

Run: python scos/control_center/tests/test_project_state_update.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from project_state_update import (  # noqa: E402
    prepare_next_action_decision,
    prepare_project_state_update,
    render_project_state_summary,
)
from result_intake_builder import build_result_intake_record  # noqa: E402
from result_intake_models import (  # noqa: E402
    AIResultIntakeRecord,
    NextActionDecision,
    ProjectStateUpdate,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _raises(fn, exc_type=ValueError) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True


def _make_record(**overrides) -> AIResultIntakeRecord:
    kwargs = dict(
        session_id="sess-1",
        task_id="task-1",
        source_agent="codex",
        source_runtime_id="runtime-1",
        raw_result_text="Review complete. All tests pass. Verdict: PASS",
        created_at="2026-07-06T00:00:00Z",
        title="Review result",
    )
    kwargs.update(overrides)
    record = build_result_intake_record(**kwargs)
    assert isinstance(record, AIResultIntakeRecord), record
    return record


def _make_state_and_decision(record=None):
    record = record or _make_record()
    state = prepare_project_state_update(
        intake_record=record,
        previous_stage="5.6",
        current_stage="5.7",
        updated_at="2026-07-06T00:10:00Z",
    )
    decision = prepare_next_action_decision(intake_record=record, created_at="2026-07-06T00:15:00Z")
    assert isinstance(state, ProjectStateUpdate), state
    assert isinstance(decision, NextActionDecision), decision
    return state, decision


def test_1_deterministic_state_summary() -> None:
    print("\n[1] deterministic state summary")
    state, decision = _make_state_and_decision()
    first = render_project_state_summary(state, decision)
    second = render_project_state_summary(state, decision)
    check("rendering is deterministic", first == second)
    check("rejects non-ProjectStateUpdate", _raises(lambda: render_project_state_summary({"not": "state"}, decision)))
    check("rejects non-NextActionDecision", _raises(lambda: render_project_state_summary(state, {"not": "decision"})))


def test_2_deterministic_next_action_summary() -> None:
    print("\n[2] deterministic next action summary")
    state, decision = _make_state_and_decision()
    summary = render_project_state_summary(state, decision)
    check("includes recommended action", decision.recommended_action in summary)
    check("includes target agent", (decision.target_agent or "None") in summary)
    check("includes priority", decision.priority in summary)
    check("includes reason", decision.reason in summary)
    check("includes task status", state.task_status in summary)
    check("includes stage status", state.stage_status in summary)
    check("includes current stage", state.current_stage in summary)


def test_3_approval_requirement_visible() -> None:
    print("\n[3] approval requirement visible")
    state, decision = _make_state_and_decision()
    summary = render_project_state_summary(state, decision)
    check("approval requirement text present", "Operator Approval Required" in summary)
    check(
        "approval line reflects requires_operator_approval",
        ("Yes — operator approval required" in summary) == decision.requires_operator_approval,
    )

    blocked_record = _make_record(raw_result_text="Blocked: waiting on operator decision.")
    blocked_state, blocked_decision = _make_state_and_decision(blocked_record)
    blocked_summary = render_project_state_summary(blocked_state, blocked_decision)
    check("blocked decision also requires approval", blocked_decision.requires_operator_approval is True)
    check("blocked summary shows approval required", "Yes — operator approval required" in blocked_summary)


def main() -> int:
    test_1_deterministic_state_summary()
    test_2_deterministic_next_action_summary()
    test_3_approval_requirement_visible()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
