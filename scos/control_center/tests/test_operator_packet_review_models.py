"""test_operator_packet_review_models.py - SCOS Stage 5.5 model suite.

Run: python scos/control_center/tests/test_operator_packet_review_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_packet_review_models import (  # noqa: E402
    OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
    FrozenMap,
    ManualHandoffInstruction,
    ManualHandoffPackage,
    OperatorPacketDecision,
    OperatorPacketReviewError,
    OperatorPacketReviewResult,
    PacketReviewCheck,
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


def _raises_frozen_error(fn) -> bool:
    try:
        fn()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def _sample_check() -> PacketReviewCheck:
    return PacketReviewCheck.of(
        "packet_id_present",
        "success",
        "info",
        packet_id="pp-1",
        metadata={"b": "2", "a": "1"},
    )


def _sample_instruction(order: int = 1) -> ManualHandoffInstruction:
    return ManualHandoffInstruction.of(
        instruction_id=f"ophi-{order}",
        step_order=order,
        title=f"Step {order}",
        detail="Do this manually.",
    )


def _sample_package() -> ManualHandoffPackage:
    return ManualHandoffPackage.of(
        source_packet_id="pp-1",
        source_result_packet_id=None,
        routing_decision_id="rd-1",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        handoff_mode="manual_clipboard",
        created_at="2026-07-06T12:00:00Z",
        prompt_path="handoff/prompt.md",
        context_summary_path="handoff/context_summary.md",
        instruction_path="handoff/handoff_instructions.md",
        manifest_path="handoff/handoff_manifest.json",
        instructions=(_sample_instruction(),),
    )


def test_1_frozen_map() -> None:
    print("\n[1] FrozenMap")
    fmap = FrozenMap.of({"b": "2", "a": "1"})
    check("sorted deterministic dict", fmap.to_dict() == {"a": "1", "b": "2"})
    try:
        FrozenMap.of({"api_key": "x"})
        check("secret key rejected by model metadata", False)
    except ValueError:
        check("secret key rejected by model metadata", True)


def test_2_check_model() -> None:
    print("\n[2] PacketReviewCheck")
    review_check = _sample_check()
    check(
        "to_dict key order",
        list(review_check.to_dict().keys())
        == [
            "check_name",
            "status",
            "severity",
            "packet_id",
            "error_kind",
            "error_detail",
            "metadata",
        ],
    )
    check("metadata serializes as dict", review_check.to_dict()["metadata"] == {"a": "1", "b": "2"})
    check("frozen", _raises_frozen_error(lambda: setattr(review_check, "status", "failure")))
    try:
        PacketReviewCheck.of("x", "bad", "info")
        check("invalid status rejected", False)
    except ValueError:
        check("invalid status rejected", True)


def test_3_decision_model() -> None:
    print("\n[3] OperatorPacketDecision")
    decision = OperatorPacketDecision.of(
        packet_id="pp-1",
        routing_decision_id="rd-1",
        decision="manual_handoff",
        decided_by="operator",
        decided_at="2026-07-06T12:00:00Z",
        reason="Operator wants a manual handoff.",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        checks=(_sample_check(),),
    )
    same = OperatorPacketDecision.of(
        packet_id="pp-1",
        routing_decision_id="rd-1",
        decision="manual_handoff",
        decided_by="operator",
        decided_at="2026-07-06T12:00:00Z",
        reason="Operator wants a manual handoff.",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        checks=(_sample_check(),),
    )
    check("deterministic decision_id", decision.decision_id == same.decision_id)
    check("manual_handoff requires flag true", decision.requires_manual_handoff is True)
    check(
        "to_dict key order",
        list(decision.to_dict().keys())
        == [
            "decision_id",
            "packet_id",
            "routing_decision_id",
            "decision",
            "decided_by",
            "decided_at",
            "reason",
            "target_agent",
            "target_runtime_id",
            "requires_manual_handoff",
            "checks",
            "metadata",
        ],
    )
    try:
        OperatorPacketDecision.of(
            packet_id="pp-1",
            routing_decision_id=None,
            decision="approve",
            decided_by="operator",
            decided_at="2026-07-06T12:00:00Z",
            reason="",
        )
        check("empty reason rejected", False)
    except ValueError:
        check("empty reason rejected", True)


def test_4_handoff_instruction_and_package() -> None:
    print("\n[4] ManualHandoffInstruction + ManualHandoffPackage")
    try:
        _sample_instruction(0)
        check("non-positive step_order rejected", False)
    except ValueError:
        check("non-positive step_order rejected", True)
    package = _sample_package()
    same = _sample_package()
    check("schema version defaults", package.schema_version == OPERATOR_PACKET_REVIEW_SCHEMA_VERSION)
    check("deterministic handoff_id", package.handoff_id == same.handoff_id)
    check("instructions serialized as list", isinstance(package.to_dict()["instructions"], list))
    try:
        ManualHandoffPackage.of(
            source_packet_id="pp-1",
            source_result_packet_id=None,
            routing_decision_id=None,
            target_agent="claude_code",
            target_runtime_id="claude_code_cli",
            handoff_mode="manual_clipboard",
            created_at="2026-07-06T12:00:00Z",
            prompt_path="https://example.com/prompt.md",
            context_summary_path="x",
            instruction_path="y",
            manifest_path="z",
            instructions=(_sample_instruction(),),
        )
        check("URL path rejected", False)
    except ValueError:
        check("URL path rejected", True)


def test_5_result_and_error_models() -> None:
    print("\n[5] OperatorPacketReviewResult + OperatorPacketReviewError")
    decision = OperatorPacketDecision.of(
        packet_id="pp-1",
        routing_decision_id="rd-1",
        decision="approve",
        decided_by="operator",
        decided_at="2026-07-06T12:00:00Z",
        reason="Looks safe.",
        checks=(_sample_check(),),
    )
    result = OperatorPacketReviewResult.of(
        packet_id="pp-1",
        result_packet_id=None,
        routing_decision_id="rd-1",
        reviewed_at="2026-07-06T12:00:00Z",
        decision=decision,
        checks=(_sample_check(),),
    )
    same = OperatorPacketReviewResult.of(
        packet_id="pp-1",
        result_packet_id=None,
        routing_decision_id="rd-1",
        reviewed_at="2026-07-06T12:00:00Z",
        decision=decision,
        checks=(_sample_check(),),
    )
    check("deterministic review_id", result.review_id == same.review_id)
    check(
        "result to_dict key order",
        list(result.to_dict().keys())
        == [
            "ok",
            "schema_version",
            "review_id",
            "packet_id",
            "result_packet_id",
            "routing_decision_id",
            "reviewed_at",
            "decision",
            "handoff_package",
            "checks",
            "output_path",
            "metadata",
        ],
    )
    error = OperatorPacketReviewError.of("invalid_decision", "bad", "decision")
    check(
        "error to_dict key order",
        list(error.to_dict().keys())
        == ["ok", "schema_version", "error_kind", "error_detail", "failed_step", "checks", "metadata"],
    )
    check("error ok defaults false", error.ok is False)


def main() -> int:
    test_1_frozen_map()
    test_2_check_model()
    test_3_decision_model()
    test_4_handoff_instruction_and_package()
    test_5_result_and_error_models()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
