"""test_operator_packet_review.py - SCOS Stage 5.5 review logic suite.

Run: python scos/control_center/tests/test_operator_packet_review.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_packet_review import (  # noqa: E402
    review_prompt_packet,
    review_result_packet,
    validate_packet_for_operator_review,
)
from operator_packet_review_models import (  # noqa: E402
    OperatorPacketReviewError,
    OperatorPacketReviewResult,
)
from prompt_result_packet_builder import (  # noqa: E402
    create_prompt_packet,
    create_result_packet,
    create_routing_decision,
)
from prompt_result_packet_models import PacketContextReference  # noqa: E402

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


def _prompt_packet(**overrides):
    kwargs = dict(
        session_id="session-55",
        task_id="task-55",
        packet_type="implementation_prompt",
        source_agent="chatgpt",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        title="Implement Stage 5.5",
        objective="Implement the operator packet review layer.",
        prompt_body="Implement Stage 5.5 per the approved plan.",
        created_at="2026-07-06T12:00:00Z",
        constraints=("local only", "no dispatch"),
        expected_artifacts=("implementation_report", "test_output"),
    )
    kwargs.update(overrides)
    return create_prompt_packet(**kwargs)


def _result_packet(verdict: str = "PASS"):
    prompt = _prompt_packet()
    return create_result_packet(
        prompt_packet=prompt,
        result_type="implementation_result",
        verdict=verdict,
        summary="Implementation is ready for review.",
        created_at="2026-07-06T12:10:00Z",
        recommended_next_agent="codex",
    )


def _routing_decision(result_packet):
    return create_routing_decision(
        result_packet=result_packet,
        next_agent="codex",
        next_packet_type="review_prompt",
        reason="Implementation complete; route to Codex review.",
    )


def test_1_validate_packet_success() -> None:
    print("\n[1] validate_packet_for_operator_review")
    packet = _prompt_packet()
    checks = validate_packet_for_operator_review(packet=packet)
    check("all checks are non-failure", all(check.status != "failure" for check in checks))
    check("packet_id_present emitted", any(check.check_name == "packet_id_present" for check in checks))


def test_2_approve_prompt_packet() -> None:
    print("\n[2] review_prompt_packet approve")
    packet = _prompt_packet()
    result = review_prompt_packet(
        prompt_packet=packet,
        decision="approve",
        decided_at="2026-07-06T12:20:00Z",
        reason="Packet is safe to route.",
    )
    check("returns OperatorPacketReviewResult", isinstance(result, OperatorPacketReviewResult))
    check("decision is approve", result.decision.decision == "approve")
    check("does not create handoff by default", result.handoff_package is None)


def test_3_reject_request_changes_blocked() -> None:
    print("\n[3] reject/request_changes/blocked")
    packet = _prompt_packet()
    reject = review_prompt_packet(
        prompt_packet=packet,
        decision="reject",
        decided_at="2026-07-06T12:21:00Z",
        reason="Wrong target agent.",
    )
    request_changes = review_prompt_packet(
        prompt_packet=packet,
        decision="request_changes",
        decided_at="2026-07-06T12:22:00Z",
        reason="Add missing constraints.",
    )
    blocked = review_prompt_packet(
        prompt_packet=packet,
        decision="blocked",
        decided_at="2026-07-06T12:23:00Z",
        reason="Operator blocked pending review.",
    )
    check("reject supported", isinstance(reject, OperatorPacketReviewResult) and reject.decision.decision == "reject")
    check(
        "request_changes supported",
        isinstance(request_changes, OperatorPacketReviewResult)
        and request_changes.decision.decision == "request_changes",
    )
    check("blocked supported", isinstance(blocked, OperatorPacketReviewResult) and blocked.decision.decision == "blocked")
    check("reject never creates handoff", reject.handoff_package is None)


def test_4_result_packet_manual_handoff() -> None:
    print("\n[4] review_result_packet manual_handoff")
    result_packet = _result_packet(verdict="NEEDS_FIX")
    routing = _routing_decision(result_packet)
    with tempfile.TemporaryDirectory() as temp_dir:
        result = review_result_packet(
            result_packet=result_packet,
            routing_decision=routing,
            decision="manual_handoff",
            decided_at="2026-07-06T12:30:00Z",
            reason="Operator will hand this to Codex manually.",
            target_agent="codex",
            target_runtime_id="codex_cli",
            create_handoff=True,
            handoff_output_dir=temp_dir,
        )
        check("returns result", isinstance(result, OperatorPacketReviewResult))
        check("handoff package exists", result.handoff_package is not None)
        if isinstance(result, OperatorPacketReviewResult) and result.handoff_package:
            check("prompt.md written", Path(result.handoff_package.prompt_path).is_file())
            check("manifest written", Path(result.handoff_package.manifest_path).is_file())
            check("requires manual handoff", result.decision.requires_manual_handoff is True)


def test_5_manual_handoff_requires_flags() -> None:
    print("\n[5] manual_handoff validation")
    packet = _prompt_packet()
    missing_create = review_prompt_packet(
        prompt_packet=packet,
        decision="manual_handoff",
        decided_at="2026-07-06T12:31:00Z",
        reason="Need manual work.",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        create_handoff=False,
    )
    check("manual_handoff requires create_handoff", isinstance(missing_create, OperatorPacketReviewError))
    missing_dir = review_prompt_packet(
        prompt_packet=packet,
        decision="manual_handoff",
        decided_at="2026-07-06T12:32:00Z",
        reason="Need manual work.",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        create_handoff=True,
    )
    check("create_handoff requires output dir", isinstance(missing_dir, OperatorPacketReviewError))


def test_6_invalid_decision_and_metadata() -> None:
    print("\n[6] invalid decision and secret metadata")
    packet = _prompt_packet()
    invalid = review_prompt_packet(
        prompt_packet=packet,
        decision="send_now",
        decided_at="2026-07-06T12:40:00Z",
        reason="bad",
    )
    check("unsupported decision returns error", isinstance(invalid, OperatorPacketReviewError))
    unsafe = review_prompt_packet(
        prompt_packet=packet,
        decision="approve",
        decided_at="2026-07-06T12:41:00Z",
        reason="bad metadata",
        metadata={"api_key": "x"},
    )
    check("secret metadata blocks approve", isinstance(unsafe, OperatorPacketReviewError))
    check("unsafe metadata error kind", unsafe.error_kind == "validation_failed")


def test_7_url_path_check_with_duck_packet() -> None:
    print("\n[7] URL path rejected by validator")

    class Ref:
        ref_id = "ref-1"
        path = "https://example.com/context"
        metadata = ()

    class Packet:
        packet_id = "pp-duck"
        context_refs = (Ref(),)
        artifacts = ()
        metadata = ()

    checks = validate_packet_for_operator_review(packet=Packet())
    check("URL path produces failure", any(check.error_kind == "unsafe_path" for check in checks))


def test_8_context_reference_fixture_still_valid() -> None:
    print("\n[8] Stage 5.4 context ref fixture")
    ref = PacketContextReference.of(
        "ref-safe",
        "specification",
        "Spec",
        "Local spec summary",
        path="docs/specification/OPERATOR_PACKET_REVIEW_CONTRACT.md",
    )
    packet = _prompt_packet(context_refs=(ref,))
    result = review_prompt_packet(
        prompt_packet=packet,
        decision="approve",
        decided_at="2026-07-06T12:42:00Z",
        reason="Safe local context.",
    )
    check("safe local context approves", isinstance(result, OperatorPacketReviewResult))


def main() -> int:
    test_1_validate_packet_success()
    test_2_approve_prompt_packet()
    test_3_reject_request_changes_blocked()
    test_4_result_packet_manual_handoff()
    test_5_manual_handoff_requires_flags()
    test_6_invalid_decision_and_metadata()
    test_7_url_path_check_with_duck_packet()
    test_8_context_reference_fixture_still_valid()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
