"""test_workflow_router.py - SCOS Stage 5.6 cross-agent workflow router suite.

Run: python scos/control_center/tests/test_workflow_router.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

import workflow_router as router  # noqa: E402


def _base_source(packet_id="p1", agent="chatgpt", packet_type="planning_prompt"):
    return {"packet_id": packet_id, "source_agent": agent, "packet_type": packet_type}


def test_chatgpt_planning_routes_to_claude():
    src = _base_source()
    plan = router.plan_next_agent_route(
        session_id="s1",
        task_id="t1",
        source_packet=src,
        result_packet={"result_status": "success"},
        created_at="2026-07-06T00:00:00Z",
    )
    assert plan.next_decision.target_agent == "claude_code"
    assert plan.next_decision.next_packet_type == "implementation_prompt"


def test_claude_impl_success_routes_to_codex():
    src = _base_source(packet_id="p2", agent="claude_code", packet_type="implementation_prompt")
    plan = router.plan_next_agent_route(
        session_id="s2",
        task_id="t2",
        source_packet=src,
        result_packet={"result_status": "success", "id": "r2"},
        created_at="2026-07-06T00:00:00Z",
    )
    assert plan.next_decision.target_agent == "codex"
    assert plan.next_decision.next_packet_type == "review_prompt"


def test_claude_blocked_routes_to_chatgpt_status():
    src = _base_source(packet_id="p3", agent="claude_code", packet_type="implementation_prompt")
    plan = router.plan_next_agent_route(
        session_id="s3",
        task_id="t3",
        source_packet=src,
        result_packet={"result_status": "blocked", "id": "r3"},
        created_at="2026-07-06T00:00:00Z",
    )
    assert plan.next_decision.target_agent == "chatgpt"
    assert plan.next_decision.next_packet_type == "status_update_prompt"


def test_operator_rejected_blocks_route():
    src = _base_source()
    plan = router.plan_next_agent_route(
        session_id="s4",
        task_id="t4",
        source_packet=src,
        result_packet={"result_status": "success"},
        operator_review={"decision": "rejected"},
        created_at="2026-07-06T00:00:00Z",
    )
    assert plan.next_decision.target_agent == "operator"


if __name__ == "__main__":
    test_chatgpt_planning_routes_to_claude()
    test_claude_impl_success_routes_to_codex()
    test_claude_blocked_routes_to_chatgpt_status()
    test_operator_rejected_blocks_route()
    print("RESULT: 4 passed, 0 failed")
