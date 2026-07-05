"""test_result_intake_models.py - SCOS Stage 5.7 result intake model suite.

Plain executable script (no pytest). Covers deterministic serialization,
tuple/FrozenMap immutability, invalid enum rejection, and explicit key
ordering for all six Stage 5.7 models.

Run: python scos/control_center/tests/test_result_intake_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from result_intake_models import (  # noqa: E402
    AI_RESULT_INTAKE_SCHEMA_VERSION,
    AIResultIntakeError,
    AIResultIntakeRecord,
    ChatGPTStatusUpdatePacket,
    NextActionDecision,
    ProjectStateUpdate,
    ResultIntakeArtifact,
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


def _raises_frozen_error(fn) -> bool:
    try:
        fn()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def _make_artifact(**overrides) -> ResultIntakeArtifact:
    kwargs = dict(
        artifact_id="art-1",
        artifact_type="test_report",
        title="Test report",
        summary="All tests passed",
    )
    kwargs.update(overrides)
    return ResultIntakeArtifact.of(**kwargs)


def _make_intake_record(**overrides) -> AIResultIntakeRecord:
    kwargs = dict(
        intake_id="ri-abc123",
        session_id="sess-1",
        task_id="task-1",
        source_agent="claude_code",
        source_runtime_id="runtime-1",
        title="Stage 5.7 implementation result",
        raw_result_summary="All tests passed. Verdict: PASS",
        normalized_summary="All tests passed. Verdict: PASS",
        verdict="PASS",
        confidence="high",
        created_at="2026-07-06T00:00:00Z",
        status="intake_recorded",
    )
    kwargs.update(overrides)
    return AIResultIntakeRecord.of(**kwargs)


def _make_chatgpt_packet(**overrides) -> ChatGPTStatusUpdatePacket:
    kwargs = dict(
        update_packet_id="cgu-abc123",
        intake_id="ri-abc123",
        session_id="sess-1",
        task_id="task-1",
        target_runtime_id="chatgpt-web",
        title="Status update",
        status_update_body="Session: sess-1\nVerdict: PASS",
        result_verdict="PASS",
        result_summary="All tests passed",
        requested_chatgpt_action="summarize_status",
        created_at="2026-07-06T00:00:00Z",
        status="ready_for_chatgpt_update",
    )
    kwargs.update(overrides)
    return ChatGPTStatusUpdatePacket.of(**kwargs)


def _make_state_update(**overrides) -> ProjectStateUpdate:
    kwargs = dict(
        state_update_id="psu-abc123",
        intake_id="ri-abc123",
        session_id="sess-1",
        task_id="task-1",
        previous_stage="5.6",
        current_stage="5.7",
        task_status="approved",
        stage_status="active",
        latest_agent="claude_code",
        latest_verdict="PASS",
        summary="claude_code reported PASS",
        updated_at="2026-07-06T00:00:00Z",
    )
    kwargs.update(overrides)
    return ProjectStateUpdate.of(**kwargs)


def _make_next_action(**overrides) -> NextActionDecision:
    kwargs = dict(
        next_action_id="nad-abc123",
        intake_id="ri-abc123",
        session_id="sess-1",
        task_id="task-1",
        recommended_action="send_to_codex_review",
        priority="normal",
        reason="claude_code reported PASS",
        created_at="2026-07-06T00:00:00Z",
        target_agent="codex",
    )
    kwargs.update(overrides)
    return NextActionDecision.of(**kwargs)


def test_1_artifact_valid_and_dict_order() -> None:
    print("\n[1] ResultIntakeArtifact valid and dict order")
    artifact = _make_artifact(metadata={"a": "b"})
    check("frozen dataclass", _raises_frozen_error(lambda: setattr(artifact, "title", "x")))
    payload = artifact.to_dict()
    check(
        "key order",
        list(payload.keys())
        == [
            "artifact_id",
            "artifact_type",
            "title",
            "path",
            "summary",
            "sha256",
            "required",
            "metadata",
        ],
    )
    check("metadata serializes as dict", payload["metadata"] == {"a": "b"})


def test_2_artifact_rejects_invalid_type_and_url_path() -> None:
    print("\n[2] ResultIntakeArtifact rejects invalid type / URL path")
    check(
        "invalid artifact_type rejected",
        _raises(lambda: _make_artifact(artifact_type="bogus")),
    )
    check(
        "url path rejected",
        _raises(lambda: _make_artifact(path="https://example.com/report.txt")),
    )
    check("empty artifact_id rejected", _raises(lambda: _make_artifact(artifact_id="  ")))


def test_3_intake_record_valid_and_dict_order() -> None:
    print("\n[3] AIResultIntakeRecord valid and dict order")
    record = _make_intake_record(artifacts=(_make_artifact(),), blockers=("b1",))
    payload = record.to_dict()
    check(
        "key order",
        list(payload.keys())
        == [
            "ok",
            "schema_version",
            "intake_id",
            "session_id",
            "task_id",
            "source_agent",
            "source_runtime_id",
            "source_packet_id",
            "source_result_packet_id",
            "title",
            "raw_result_summary",
            "normalized_summary",
            "verdict",
            "confidence",
            "artifacts",
            "blockers",
            "warnings",
            "tests_summary",
            "changed_files_summary",
            "operator_review_required",
            "created_at",
            "status",
            "metadata",
        ],
    )
    check("artifacts is a tuple", type(record.artifacts) is tuple)
    check("blockers is a tuple", type(record.blockers) is tuple)
    check("artifacts serialize as list of dicts", payload["artifacts"] == [record.artifacts[0].to_dict()])
    check("schema_version default", record.schema_version == AI_RESULT_INTAKE_SCHEMA_VERSION)


def test_4_intake_record_rejects_invalid_enums() -> None:
    print("\n[4] AIResultIntakeRecord rejects invalid enums")
    check(
        "invalid source_agent rejected",
        _raises(lambda: _make_intake_record(source_agent="gemini")),
    )
    check("invalid verdict rejected", _raises(lambda: _make_intake_record(verdict="MAYBE")))
    check(
        "invalid confidence rejected",
        _raises(lambda: _make_intake_record(confidence="extreme")),
    )
    check("invalid status rejected", _raises(lambda: _make_intake_record(status="unknown_status")))
    check(
        "non ResultIntakeArtifact rejected",
        _raises(lambda: _make_intake_record(artifacts=({"not": "an artifact"},))),
    )


def test_5_intake_record_rejects_empty_required_strings() -> None:
    print("\n[5] AIResultIntakeRecord rejects empty required strings")
    check("empty session_id rejected", _raises(lambda: _make_intake_record(session_id=" ")))
    check("empty task_id rejected", _raises(lambda: _make_intake_record(task_id="")))
    check(
        "empty normalized_summary rejected",
        _raises(lambda: _make_intake_record(normalized_summary="  ")),
    )


def test_6_chatgpt_packet_valid_and_target_agent_enforced() -> None:
    print("\n[6] ChatGPTStatusUpdatePacket valid and target_agent enforced")
    packet = _make_chatgpt_packet(evidence_refs=("ref-1",))
    payload = packet.to_dict()
    check("target_agent is chatgpt", packet.target_agent == "chatgpt")
    check(
        "non-chatgpt target_agent rejected",
        _raises(lambda: _make_chatgpt_packet(target_agent="claude_code")),
    )
    check("evidence_refs is a tuple", type(packet.evidence_refs) is tuple)
    check("evidence_refs serializes as list", payload["evidence_refs"] == ["ref-1"])
    check(
        "invalid requested_chatgpt_action rejected",
        _raises(lambda: _make_chatgpt_packet(requested_chatgpt_action="do_everything")),
    )
    check(
        "invalid result_verdict rejected",
        _raises(lambda: _make_chatgpt_packet(result_verdict="MAYBE")),
    )


def test_7_project_state_update_valid_and_enums() -> None:
    print("\n[7] ProjectStateUpdate valid and enum enforcement")
    update = _make_state_update()
    payload = update.to_dict()
    check(
        "key order",
        list(payload.keys())
        == [
            "ok",
            "schema_version",
            "state_update_id",
            "intake_id",
            "session_id",
            "task_id",
            "previous_stage",
            "current_stage",
            "task_status",
            "stage_status",
            "latest_agent",
            "latest_verdict",
            "summary",
            "updated_at",
            "evidence_refs",
            "metadata",
        ],
    )
    check(
        "invalid task_status rejected",
        _raises(lambda: _make_state_update(task_status="in_progress")),
    )
    check(
        "invalid stage_status rejected",
        _raises(lambda: _make_state_update(stage_status="unstarted")),
    )
    check(
        "invalid latest_agent rejected",
        _raises(lambda: _make_state_update(latest_agent="gpt4")),
    )


def test_8_next_action_decision_valid_and_approval_rule() -> None:
    print("\n[8] NextActionDecision valid and approval rule")
    decision = _make_next_action()
    check("requires_operator_approval defaults true", decision.requires_operator_approval is True)
    no_action = _make_next_action(
        recommended_action="no_action",
        target_agent=None,
        requires_operator_approval=False,
    )
    check("no_action allows false approval", no_action.requires_operator_approval is False)
    check(
        "non-no_action with false approval rejected",
        _raises(
            lambda: _make_next_action(
                recommended_action="hold_blocked",
                target_agent=None,
                requires_operator_approval=False,
            )
        ),
    )
    check(
        "invalid recommended_action rejected",
        _raises(lambda: _make_next_action(recommended_action="do_magic")),
    )
    check("invalid priority rejected", _raises(lambda: _make_next_action(priority="critical")))


def test_9_error_dataclass_enum_and_dict() -> None:
    print("\n[9] AIResultIntakeError enum and dict")
    error = AIResultIntakeError.of("invalid_verdict", "verdict=MAYBE", "verdict", intake_id="ri-1")
    check("ok is False by default", error.ok is False)
    check("error_kind stored", error.error_kind == "invalid_verdict")
    check("invalid error_kind rejected", _raises(lambda: AIResultIntakeError.of("bogus_kind", "x", "y")))
    payload = error.to_dict()
    check(
        "key order",
        list(payload.keys())
        == [
            "ok",
            "schema_version",
            "error_kind",
            "error_detail",
            "failed_step",
            "intake_id",
            "metadata",
        ],
    )


def test_10_no_mutable_containers_exposed() -> None:
    print("\n[10] no mutable containers exposed")
    record = _make_intake_record(blockers=("b1",), artifacts=(_make_artifact(),))
    check("blockers is a tuple", type(record.blockers) is tuple)
    check("artifacts is a tuple", type(record.artifacts) is tuple)
    first = record.to_dict()
    first["blockers"].append("mutated")
    second = record.to_dict()
    check("to_dict returns a fresh list each call", second["blockers"] == ["b1"])


def test_11_frozen_map_immutability() -> None:
    print("\n[11] FrozenMap immutability")
    record = _make_intake_record(metadata={"env": "ci"})
    check("metadata value readable", record.metadata["env"] == "ci")
    check(
        "metadata does not support item assignment",
        _raises(lambda: record.metadata.__setitem__("env", "prod"), AttributeError),
    )


def test_12_deterministic_serialization_same_inputs_same_dict() -> None:
    print("\n[12] deterministic serialization")
    first = _make_intake_record()
    second = _make_intake_record()
    check("identical inputs produce identical to_dict", first.to_dict() == second.to_dict())


def main() -> int:
    test_1_artifact_valid_and_dict_order()
    test_2_artifact_rejects_invalid_type_and_url_path()
    test_3_intake_record_valid_and_dict_order()
    test_4_intake_record_rejects_invalid_enums()
    test_5_intake_record_rejects_empty_required_strings()
    test_6_chatgpt_packet_valid_and_target_agent_enforced()
    test_7_project_state_update_valid_and_enums()
    test_8_next_action_decision_valid_and_approval_rule()
    test_9_error_dataclass_enum_and_dict()
    test_10_no_mutable_containers_exposed()
    test_11_frozen_map_immutability()
    test_12_deterministic_serialization_same_inputs_same_dict()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
