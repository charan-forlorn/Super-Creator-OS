"""test_prompt_result_packet_builder.py - SCOS Stage 5.4 packet builder suite.

Plain executable script (no pytest). Covers deterministic id derivation,
error_kind precision on invalid input, the full 5-stage routing chain, and
the "no clock/random/uuid" static-source guarantee.

Run: python scos/control_center/tests/test_prompt_result_packet_builder.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from prompt_result_packet_builder import (  # noqa: E402
    create_followup_prompt_from_result,
    create_prompt_packet,
    create_result_packet,
    create_routing_decision,
    recommend_routing,
)
from prompt_result_packet_models import (  # noqa: E402
    PacketRoutingDecision,
    PromptPacket,
    PromptResultPacketError,
    ResultPacket,
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


def _prompt_kwargs(**overrides):
    kwargs = dict(
        session_id="session-1",
        task_id="task-1",
        packet_type="planning_prompt",
        source_agent="chatgpt",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        title="Implement Stage 5.4",
        objective="Build the packet layer",
        prompt_body="Implement the packet models per spec.",
        created_at="2026-07-06T10:00:00Z",
    )
    kwargs.update(overrides)
    return kwargs


def test_1_create_prompt_packet_success_and_deterministic_id() -> None:
    print("\n[1] create_prompt_packet success + deterministic id")
    first = create_prompt_packet(**_prompt_kwargs())
    second = create_prompt_packet(**_prompt_kwargs())
    check("returns a PromptPacket", isinstance(first, PromptPacket))
    check("identical kwargs produce identical packet_id", first.packet_id == second.packet_id)

    kwargs = _prompt_kwargs()
    expected_digest = hashlib.sha256(
        "|".join(
            (
                kwargs["session_id"],
                kwargs["task_id"],
                kwargs["packet_type"],
                kwargs["source_agent"],
                kwargs["target_agent"],
                kwargs["title"],
                kwargs["created_at"],
            )
        ).encode("utf-8")
    ).hexdigest()[:16]
    check("packet_id matches pinned sha256 formula", first.packet_id == f"pp-{expected_digest}")
    check("status always drafted", first.status == "drafted")


def test_2_create_prompt_packet_id_changes_with_created_at() -> None:
    print("\n[2] packet_id changes with created_at")
    first = create_prompt_packet(**_prompt_kwargs())
    second = create_prompt_packet(**_prompt_kwargs(created_at="2026-07-06T11:00:00Z"))
    check("different created_at yields different packet_id", first.packet_id != second.packet_id)


def test_3_create_prompt_packet_rejects_invalid_agent() -> None:
    print("\n[3] create_prompt_packet rejects invalid agent")
    result = create_prompt_packet(**_prompt_kwargs(target_agent="not-an-agent"))
    check("returns PromptResultPacketError", isinstance(result, PromptResultPacketError))
    check("error_kind is invalid_agent", result.error_kind == "invalid_agent")


def test_4_create_prompt_packet_rejects_unsupported_packet_type() -> None:
    print("\n[4] create_prompt_packet rejects unsupported packet_type")
    result = create_prompt_packet(**_prompt_kwargs(packet_type="not-a-type"))
    check("error_kind is invalid_packet_type", result.error_kind == "invalid_packet_type")


def test_5_create_prompt_packet_rejects_empty_required_strings() -> None:
    print("\n[5] create_prompt_packet rejects empty required strings")
    for field in ("objective", "prompt_body"):
        result = create_prompt_packet(**_prompt_kwargs(**{field: ""}))
        check(f"empty {field} -> empty_required_field", result.error_kind == "empty_required_field")


def test_6_create_prompt_packet_rejects_non_tuple_context_refs() -> None:
    print("\n[6] create_prompt_packet rejects non-tuple context_refs")
    result = create_prompt_packet(**_prompt_kwargs(context_refs="not-a-list"))
    check("error_kind is invalid_collection_type", result.error_kind == "invalid_collection_type")


def test_7_create_result_packet_success_derives_from_prompt_packet() -> None:
    print("\n[7] create_result_packet derives source/target from prompt")
    prompt = create_prompt_packet(**_prompt_kwargs())
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    check("returns a ResultPacket", isinstance(result, ResultPacket))
    check("prompt_packet_id linked", result.prompt_packet_id == prompt.packet_id)
    check("source_agent is prompt's target_agent", result.source_agent == prompt.target_agent)
    check("target_agent is prompt's source_agent", result.target_agent == prompt.source_agent)
    check("status always received", result.status == "received")


def test_8_create_result_packet_rejects_invalid_verdict() -> None:
    print("\n[8] create_result_packet rejects invalid verdict")
    prompt = create_prompt_packet(**_prompt_kwargs())
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="not-a-verdict",
        summary="x",
        created_at="2026-07-06T10:05:00Z",
    )
    check("error_kind is invalid_verdict", result.error_kind == "invalid_verdict")


def test_9_create_routing_decision_success_and_id_pinned() -> None:
    print("\n[9] create_routing_decision deterministic id")
    prompt = create_prompt_packet(**_prompt_kwargs())
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    decision = create_routing_decision(
        result_packet=result,
        next_agent="claude_code",
        next_packet_type="implementation_prompt",
        reason="Plan approved.",
    )
    check("returns a PacketRoutingDecision", isinstance(decision, PacketRoutingDecision))
    expected_digest = hashlib.sha256(
        "|".join(
            (result.result_packet_id, "claude_code", "implementation_prompt", "Plan approved.", "normal")
        ).encode("utf-8")
    ).hexdigest()[:16]
    check("decision_id matches pinned sha256 formula", decision.decision_id == f"rd-{expected_digest}")
    check("requires_operator_approval defaults True", decision.requires_operator_approval is True)


def test_10_create_followup_prompt_from_result_inherits_session_task() -> None:
    print("\n[10] create_followup_prompt_from_result inherits session/task")
    prompt = create_prompt_packet(**_prompt_kwargs())
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    followup = create_followup_prompt_from_result(
        result_packet=result,
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        packet_type="implementation_prompt",
        title="Implement the plan",
        objective="Implement Stage 5.4 per the approved plan.",
        prompt_body="Implement the packet layer.",
        created_at="2026-07-06T10:10:00Z",
    )
    check("returns a PromptPacket", isinstance(followup, PromptPacket))
    check("session_id inherited", followup.session_id == result.session_id)
    check("task_id inherited", followup.task_id == result.task_id)
    check("source_agent is result's target_agent", followup.source_agent == result.target_agent)


def test_11_recommend_routing_full_chain() -> None:
    print("\n[11] recommend_routing full chain")
    check(
        "planning PASS -> claude_code implementation",
        recommend_routing(result_type="planning_result", verdict="PASS")
        == ("claude_code", "implementation_prompt"),
    )
    check(
        "implementation PASS -> codex review",
        recommend_routing(result_type="implementation_result", verdict="PASS")
        == ("codex", "review_prompt"),
    )
    check(
        "implementation NEEDS_FIX -> claude_code implementation",
        recommend_routing(result_type="implementation_result", verdict="NEEDS_FIX")
        == ("claude_code", "implementation_prompt"),
    )
    check(
        "review PASS (primary) -> hermes audit",
        recommend_routing(result_type="review_result", verdict="PASS")
        == ("hermes", "audit_prompt"),
    )
    check(
        "review PASS (alternate) -> chatgpt status_update",
        recommend_routing(result_type="review_result", verdict="PASS", alternate=True)
        == ("chatgpt", "status_update_prompt"),
    )
    check(
        "review NEEDS_FIX -> claude_code implementation",
        recommend_routing(result_type="review_result", verdict="NEEDS_FIX")
        == ("claude_code", "implementation_prompt"),
    )
    check(
        "audit PASS -> chatgpt status_update",
        recommend_routing(result_type="audit_result", verdict="PASS")
        == ("chatgpt", "status_update_prompt"),
    )
    check(
        "audit BLOCKED -> operator manual_handoff",
        recommend_routing(result_type="audit_result", verdict="BLOCKED")
        == ("operator", "manual_handoff_prompt"),
    )
    check(
        "any FAIL -> operator manual_handoff",
        recommend_routing(result_type="status_update_result", verdict="FAIL")
        == ("operator", "manual_handoff_prompt"),
    )
    check(
        "any BLOCKED -> operator manual_handoff",
        recommend_routing(result_type="result_summary", verdict="BLOCKED")
        == ("operator", "manual_handoff_prompt"),
    )
    check(
        "unknown combo returns None",
        recommend_routing(result_type="status_update_result", verdict="INFO") is None,
    )


def test_12_full_5_stage_routing_chain_buildable() -> None:
    print("\n[12] full 5-stage routing chain buildable end to end")
    planning_prompt = create_prompt_packet(**_prompt_kwargs())
    planning_result = create_result_packet(
        prompt_packet=planning_prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=planning_result.result_type, verdict=planning_result.verdict
    )
    check("stage 1->2 recommendation", (next_agent, next_type) == ("claude_code", "implementation_prompt"))
    impl_prompt = create_followup_prompt_from_result(
        result_packet=planning_result,
        target_agent=next_agent,
        target_runtime_id="claude_code_cli",
        packet_type=next_type,
        title="Implement the plan",
        objective="Implement Stage 5.4 per the approved plan.",
        prompt_body="Implement the packet layer.",
        created_at="2026-07-06T10:10:00Z",
    )
    check("implementation prompt targets claude_code", impl_prompt.target_agent == "claude_code")

    impl_result_needs_fix = create_result_packet(
        prompt_packet=impl_prompt,
        result_type="implementation_result",
        verdict="NEEDS_FIX",
        summary="Missing tests.",
        created_at="2026-07-06T10:20:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=impl_result_needs_fix.result_type, verdict=impl_result_needs_fix.verdict
    )
    check("NEEDS_FIX loops back to claude_code", (next_agent, next_type) == ("claude_code", "implementation_prompt"))

    impl_prompt_v2 = create_followup_prompt_from_result(
        result_packet=impl_result_needs_fix,
        target_agent=next_agent,
        target_runtime_id="claude_code_cli",
        packet_type=next_type,
        title="Fix the implementation",
        objective="Add the missing tests.",
        prompt_body="Add tests for the packet layer.",
        created_at="2026-07-06T10:25:00Z",
    )
    impl_result_pass = create_result_packet(
        prompt_packet=impl_prompt_v2,
        result_type="implementation_result",
        verdict="PASS",
        summary="Tests added, implementation complete.",
        created_at="2026-07-06T10:35:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=impl_result_pass.result_type, verdict=impl_result_pass.verdict
    )
    check("stage 2->3 recommendation", (next_agent, next_type) == ("codex", "review_prompt"))

    review_prompt = create_followup_prompt_from_result(
        result_packet=impl_result_pass,
        target_agent=next_agent,
        target_runtime_id="codex_cli",
        packet_type=next_type,
        title="Review the implementation",
        objective="Review Stage 5.4 implementation.",
        prompt_body="Review the packet layer implementation.",
        created_at="2026-07-06T10:40:00Z",
    )
    review_result = create_result_packet(
        prompt_packet=review_prompt,
        result_type="review_result",
        verdict="PASS",
        summary="Review passed.",
        created_at="2026-07-06T10:50:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=review_result.result_type, verdict=review_result.verdict
    )
    check("stage 3->4 recommendation", (next_agent, next_type) == ("hermes", "audit_prompt"))

    audit_prompt = create_followup_prompt_from_result(
        result_packet=review_result,
        target_agent=next_agent,
        target_runtime_id="hermes_cli",
        packet_type=next_type,
        title="Audit the implementation",
        objective="Audit repo health for Stage 5.4.",
        prompt_body="Audit the packet layer implementation.",
        created_at="2026-07-06T10:55:00Z",
    )
    audit_result_pass = create_result_packet(
        prompt_packet=audit_prompt,
        result_type="audit_result",
        verdict="PASS",
        summary="Audit passed.",
        created_at="2026-07-06T11:00:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=audit_result_pass.result_type, verdict=audit_result_pass.verdict
    )
    check("stage 4->5 recommendation", (next_agent, next_type) == ("chatgpt", "status_update_prompt"))

    audit_result_blocked = create_result_packet(
        prompt_packet=audit_prompt,
        result_type="audit_result",
        verdict="BLOCKED",
        summary="Audit found a blocking issue.",
        created_at="2026-07-06T11:00:00Z",
    )
    next_agent, next_type = recommend_routing(
        result_type=audit_result_blocked.result_type, verdict=audit_result_blocked.verdict
    )
    check("BLOCKED audit escalates to operator", (next_agent, next_type) == ("operator", "manual_handoff_prompt"))


def test_13_builder_never_touches_clock_random_uuid() -> None:
    print("\n[13] static source check: no clock/random/uuid in builder")
    source = (_PACKAGE / "prompt_result_packet_builder.py").read_text(encoding="utf-8")
    for forbidden in ("import random", "import uuid", "time.time", "datetime.now", "uuid.uuid4"):
        check(f"builder source does not contain {forbidden!r}", forbidden not in source)


def main() -> int:
    test_1_create_prompt_packet_success_and_deterministic_id()
    test_2_create_prompt_packet_id_changes_with_created_at()
    test_3_create_prompt_packet_rejects_invalid_agent()
    test_4_create_prompt_packet_rejects_unsupported_packet_type()
    test_5_create_prompt_packet_rejects_empty_required_strings()
    test_6_create_prompt_packet_rejects_non_tuple_context_refs()
    test_7_create_result_packet_success_derives_from_prompt_packet()
    test_8_create_result_packet_rejects_invalid_verdict()
    test_9_create_routing_decision_success_and_id_pinned()
    test_10_create_followup_prompt_from_result_inherits_session_task()
    test_11_recommend_routing_full_chain()
    test_12_full_5_stage_routing_chain_buildable()
    test_13_builder_never_touches_clock_random_uuid()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
