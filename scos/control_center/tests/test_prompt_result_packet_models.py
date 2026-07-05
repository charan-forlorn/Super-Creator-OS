"""test_prompt_result_packet_models.py - SCOS Stage 5.4 packet model suite.

Plain executable script (no pytest). Covers to_dict key order, frozen
immutability, tuple serialization, enum enforcement, URL/secret-metadata
rejection, and deterministic serialization for all six Stage 5.4 models.

Run: python scos/control_center/tests/test_prompt_result_packet_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from prompt_result_packet_models import (  # noqa: E402
    PROMPT_RESULT_PACKET_SCHEMA_VERSION,
    PacketContextReference,
    PacketRoutingDecision,
    PromptPacket,
    PromptResultPacketError,
    ResultArtifactReference,
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


def _raises_frozen_error(fn) -> bool:
    try:
        fn()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def _make_context_ref(**overrides) -> PacketContextReference:
    kwargs = dict(
        ref_id="ref-1",
        ref_type="session",
        title="Session context",
        summary="Session state at handoff time",
    )
    kwargs.update(overrides)
    return PacketContextReference.of(**kwargs)


def _make_prompt_packet(**overrides) -> PromptPacket:
    kwargs = dict(
        packet_id="pp-0000000000000000",
        packet_type="planning_prompt",
        session_id="session-1",
        task_id="task-1",
        source_agent="chatgpt",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        title="Implement Stage 5.4",
        objective="Build the packet layer",
        prompt_body="Implement the packet models per spec.",
        created_at="2026-07-06T10:00:00Z",
        status="drafted",
    )
    kwargs.update(overrides)
    return PromptPacket.of(**kwargs)


def _make_result_packet(**overrides) -> ResultPacket:
    kwargs = dict(
        result_packet_id="rp-0000000000000000",
        prompt_packet_id="pp-0000000000000000",
        session_id="session-1",
        task_id="task-1",
        source_agent="claude_code",
        target_agent="chatgpt",
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted successfully.",
        created_at="2026-07-06T10:05:00Z",
        status="received",
    )
    kwargs.update(overrides)
    return ResultPacket.of(**kwargs)


def test_1_context_reference() -> None:
    print("\n[1] PacketContextReference")
    ref = _make_context_ref()
    check(
        "to_dict key order",
        list(ref.to_dict().keys())
        == ["ref_id", "ref_type", "title", "path", "summary", "required", "sha256", "metadata"],
    )
    check("path defaults to None", ref.path is None)
    check("frozen", _raises_frozen_error(lambda: setattr(ref, "ref_id", "x")))
    try:
        _make_context_ref(ref_type="not-a-type")
        check("invalid ref_type rejected", False)
    except ValueError:
        check("invalid ref_type rejected", True)
    try:
        _make_context_ref(title="")
        check("empty title rejected", False)
    except ValueError:
        check("empty title rejected", True)
    try:
        _make_context_ref(path="https://example.com/x")
        check("URL path rejected", False)
    except ValueError:
        check("URL path rejected", True)


def test_2_prompt_packet_valid_and_dict_order() -> None:
    print("\n[2] PromptPacket valid + to_dict key order")
    packet = _make_prompt_packet()
    check(
        "to_dict key order",
        list(packet.to_dict().keys())
        == [
            "ok",
            "schema_version",
            "packet_id",
            "packet_type",
            "session_id",
            "task_id",
            "source_agent",
            "target_agent",
            "target_runtime_id",
            "title",
            "objective",
            "prompt_body",
            "context_refs",
            "constraints",
            "expected_result_format",
            "expected_artifacts",
            "created_at",
            "status",
            "metadata",
        ],
    )
    check("constraints serialized as list", packet.to_dict()["constraints"] == [])
    check("context_refs serialized as list", packet.to_dict()["context_refs"] == [])
    check("schema_version defaults", packet.schema_version == PROMPT_RESULT_PACKET_SCHEMA_VERSION)
    check("frozen", _raises_frozen_error(lambda: setattr(packet, "status", "blocked")))


def test_3_prompt_packet_rejects_invalid_enums() -> None:
    print("\n[3] PromptPacket rejects invalid enums")
    for field, value in (
        ("packet_type", "not-a-type"),
        ("source_agent", "not-an-agent"),
        ("target_agent", "not-an-agent"),
        ("status", "not-a-status"),
    ):
        try:
            _make_prompt_packet(**{field: value})
            check(f"invalid {field} rejected", False)
        except ValueError:
            check(f"invalid {field} rejected", True)


def test_4_prompt_packet_rejects_empty_required_strings() -> None:
    print("\n[4] PromptPacket rejects empty required strings")
    for field in ("prompt_body", "objective", "target_agent"):
        try:
            _make_prompt_packet(**{field: ""})
            check(f"empty {field} rejected", False)
        except ValueError:
            check(f"empty {field} rejected", True)


def test_5_prompt_packet_rejects_url_in_prompt_body_and_path() -> None:
    print("\n[5] URL rejection in prompt_body and context ref path")
    try:
        _make_prompt_packet(prompt_body="See https://example.com for details.")
        check("URL in prompt_body rejected", False)
    except ValueError:
        check("URL in prompt_body rejected", True)
    try:
        _make_context_ref(path="http://example.com/file")
        check("http URL in context ref path rejected", False)
    except ValueError:
        check("http URL in context ref path rejected", True)


def test_6_metadata_rejects_secret_keys_and_urls() -> None:
    print("\n[6] metadata rejects secret keys and URLs")
    try:
        _make_prompt_packet(metadata={"api_key": "sk-123"})
        check("secret metadata key rejected on PromptPacket", False)
    except ValueError:
        check("secret metadata key rejected on PromptPacket", True)
    try:
        _make_prompt_packet(metadata={"note": "https://evil.example.com"})
        check("URL metadata value rejected on PromptPacket", False)
    except ValueError:
        check("URL metadata value rejected on PromptPacket", True)
    try:
        _make_result_packet(metadata={"password": "hunter2"})
        check("secret metadata key rejected on ResultPacket", False)
    except ValueError:
        check("secret metadata key rejected on ResultPacket", True)


def test_7_result_packet_valid_and_verdict_enum() -> None:
    print("\n[7] ResultPacket valid + verdict enum")
    for verdict in ("PASS", "PASS_WITH_WARNINGS", "NEEDS_FIX", "BLOCKED", "FAIL", "INFO"):
        result = _make_result_packet(verdict=verdict)
        check(f"verdict {verdict} accepted", result.verdict == verdict)
    try:
        _make_result_packet(verdict="not-a-verdict")
        check("invalid verdict rejected", False)
    except ValueError:
        check("invalid verdict rejected", True)
    result = _make_result_packet()
    check(
        "to_dict key order",
        list(result.to_dict().keys())
        == [
            "ok",
            "schema_version",
            "result_packet_id",
            "prompt_packet_id",
            "session_id",
            "task_id",
            "source_agent",
            "target_agent",
            "result_type",
            "verdict",
            "summary",
            "artifacts",
            "blockers",
            "next_action",
            "recommended_next_agent",
            "created_at",
            "status",
            "metadata",
        ],
    )


def test_8_result_packet_recommended_next_agent_validation() -> None:
    print("\n[8] ResultPacket.recommended_next_agent validation")
    valid = _make_result_packet(recommended_next_agent="operator")
    check("valid recommended_next_agent accepted", valid.recommended_next_agent == "operator")
    try:
        _make_result_packet(recommended_next_agent="not-an-agent")
        check("invalid recommended_next_agent rejected", False)
    except ValueError:
        check("invalid recommended_next_agent rejected", True)


def test_9_routing_decision_valid_and_priority_enum() -> None:
    print("\n[9] PacketRoutingDecision valid + priority enum")
    decision = PacketRoutingDecision.of(
        "rd-0000000000000000",
        "rp-0000000000000000",
        "claude_code",
        "implementation_prompt",
        "Plan approved, ready for implementation.",
    )
    check("requires_operator_approval defaults True", decision.requires_operator_approval is True)
    check(
        "to_dict key order",
        list(decision.to_dict().keys())
        == [
            "decision_id",
            "source_result_packet_id",
            "next_agent",
            "next_packet_type",
            "reason",
            "priority",
            "requires_operator_approval",
            "metadata",
        ],
    )
    try:
        PacketRoutingDecision.of(
            "rd-x", "rp-x", "claude_code", "implementation_prompt", "reason", priority="not-a-priority"
        )
        check("invalid priority rejected", False)
    except ValueError:
        check("invalid priority rejected", True)


def test_10_error_dataclass_enum_and_dict() -> None:
    print("\n[10] PromptResultPacketError enum + to_dict")
    error = PromptResultPacketError.of("invalid_agent", "bad agent", "create_prompt_packet")
    check(
        "to_dict key order",
        list(error.to_dict().keys())
        == ["ok", "schema_version", "error_kind", "error_detail", "failed_step", "metadata"],
    )
    check("ok defaults to False", error.ok is False)
    try:
        PromptResultPacketError.of("not-a-kind", "detail", "step")
        check("invalid error_kind rejected", False)
    except ValueError:
        check("invalid error_kind rejected", True)


def test_11_no_mutable_containers_exposed() -> None:
    print("\n[11] no mutable containers exposed")
    packet = _make_prompt_packet(constraints=("must be local",), metadata={"a": "b"})
    check("context_refs is a tuple", type(packet.context_refs) is tuple)
    check("constraints is a tuple", type(packet.constraints) is tuple)
    check("metadata is a tuple", type(packet.metadata) is tuple)
    first = packet.to_dict()
    first["constraints"].append("mutated")
    second = packet.to_dict()
    check("to_dict returns a fresh list each call", second["constraints"] == ["must be local"])


def test_12_deterministic_serialization_same_inputs_same_dict() -> None:
    print("\n[12] deterministic serialization")
    first = _make_prompt_packet()
    second = _make_prompt_packet()
    check("identical inputs produce identical to_dict", first.to_dict() == second.to_dict())


def main() -> int:
    test_1_context_reference()
    test_2_prompt_packet_valid_and_dict_order()
    test_3_prompt_packet_rejects_invalid_enums()
    test_4_prompt_packet_rejects_empty_required_strings()
    test_5_prompt_packet_rejects_url_in_prompt_body_and_path()
    test_6_metadata_rejects_secret_keys_and_urls()
    test_7_result_packet_valid_and_verdict_enum()
    test_8_result_packet_recommended_next_agent_validation()
    test_9_routing_decision_valid_and_priority_enum()
    test_10_error_dataclass_enum_and_dict()
    test_11_no_mutable_containers_exposed()
    test_12_deterministic_serialization_same_inputs_same_dict()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
