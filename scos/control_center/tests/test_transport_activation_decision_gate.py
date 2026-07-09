"""Stage 8.1 local transport activation decision gate tests."""

from __future__ import annotations

import json
import atexit
import shutil
from pathlib import Path

from scos.control_center import transport_activation_decision_gate
from scos.control_center.transport_activation_decision_gate import (
    run_local_transport_activation_decision_gate,
)
from scos.control_center.transport_activation_decision_models import (
    LocalTransportActivationDecisionError,
    LocalTransportActivationDecisionResult,
)

_NOW = "2026-07-10T05:00:00Z"


def _workspace_tmp(name: str) -> Path:
    root = Path("work") / "stage8_1_transport_activation_tests" / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    atexit.register(lambda target=root: shutil.rmtree(target, ignore_errors=True))
    return root


def _result(
    requested_decision: str = "NO_TRANSPORT",
    *,
    allow_future_implementation: bool = False,
) -> LocalTransportActivationDecisionResult:
    result = run_local_transport_activation_decision_gate(
        repo_root=Path("."),
        decided_at=_NOW,
        requested_decision=requested_decision,
        allow_future_implementation=allow_future_implementation,
    )
    assert isinstance(result, LocalTransportActivationDecisionResult)
    return result


def test_default_no_transport_returns_go_100_and_accepted() -> None:
    result = _result()

    assert result.go_no_go == "GO"
    assert result.readiness_score == 100
    assert result.accepted is True
    assert result.decision_record.decision == "NO_TRANSPORT"
    assert result.can_implement_now is False
    assert result.transport_implemented is False
    assert result.dispatch_blocked is True
    assert result.blockers == ()


def test_all_six_transport_options_are_analyzed() -> None:
    result = _result()

    assert {analysis.option for analysis in result.option_analyses} == {
        "NO_TRANSPORT",
        "FILE_SNAPSHOT_REFRESH",
        "LOCAL_HTTP",
        "WEBSOCKET",
        "SSE_EVENTSOURCE",
        "POLLING",
    }
    for analysis in result.option_analyses:
        assert analysis.locality_boundary
        assert analysis.origin_csrf_local_exposure_risk
        assert analysis.stale_data_risk
        assert analysis.event_ordering_risk
        assert analysis.accidental_command_execution_risk
        assert analysis.adapter_dispatch_risk
        assert analysis.credential_exposure_risk
        assert analysis.rollback_kill_switch_requirement
        assert analysis.operator_approval_preservation
        assert analysis.deterministic_testability


def test_allowed_later_decisions_never_allow_implementation_now() -> None:
    decisions = (
        "FILE_SNAPSHOT_REFRESH_ALLOWED_LATER",
        "LOCAL_HTTP_ALLOWED_LATER",
        "WEBSOCKET_ALLOWED_LATER",
        "SSE_EVENTSOURCE_ALLOWED_LATER",
        "POLLING_ALLOWED_LATER",
    )
    for decision in decisions:
        result = _result(decision, allow_future_implementation=True)

        assert result.go_no_go == "GO"
        assert result.accepted is True
        assert result.decision_record.decision == decision
        assert result.decision_record.future_implementation_requires_later_stage is True
        assert result.can_implement_now is False
        assert result.transport_implemented is False
        assert result.dispatch_blocked is True


def test_allowed_later_decision_without_future_flag_is_blocked() -> None:
    result = _result("LOCAL_HTTP_ALLOWED_LATER")

    assert result.go_no_go == "BLOCKED"
    assert result.accepted is False
    assert any(
        blocker.code == "TRANSPORT_IMPLEMENTATION_NOT_APPROVED_IN_STAGE_8_1"
        for blocker in result.blockers
    )
    assert result.can_implement_now is False
    assert result.transport_implemented is False


def test_explicit_block_transport_activation_returns_no_go_without_implementation() -> None:
    result = _result("BLOCK_TRANSPORT_ACTIVATION")

    assert result.go_no_go == "NO_GO"
    assert result.accepted is False
    assert result.decision_record.decision == "BLOCK_TRANSPORT_ACTIVATION"
    assert result.can_implement_now is False
    assert result.transport_implemented is False


def test_decided_at_is_required() -> None:
    result = run_local_transport_activation_decision_gate(repo_root=Path("."), decided_at="")

    assert isinstance(result, LocalTransportActivationDecisionError)
    assert result.error_code == "INVALID_LOCAL_TRANSPORT_ACTIVATION_DECISION_INPUT"
    assert any("decided_at" in blocker for blocker in result.blockers)


def test_invalid_requested_decision_is_rejected() -> None:
    result = run_local_transport_activation_decision_gate(
        repo_root=Path("."),
        decided_at=_NOW,
        requested_decision="LOCAL_HTTP_NOW",
    )

    assert isinstance(result, LocalTransportActivationDecisionError)
    assert result.error_code == "INVALID_LOCAL_TRANSPORT_ACTIVATION_DECISION_INPUT"


def test_output_path_outside_repo_root_is_rejected() -> None:
    outside = Path("..") / "stage8_1_outside_report.json"
    result = run_local_transport_activation_decision_gate(
        repo_root=Path("."),
        decided_at=_NOW,
        output_path=outside,
    )

    assert isinstance(result, LocalTransportActivationDecisionError)
    assert any("output_path" in blocker for blocker in result.blockers)


def test_optional_output_write_is_explicit_and_deterministic() -> None:
    temp_root = _workspace_tmp("explicit_output")
    output_path = temp_root / "repo" / "reports" / "decision.json"
    repo_root = temp_root / "repo"
    repo_root.mkdir()
    for rel_path in transport_activation_decision_gate._REQUIRED_EVIDENCE:
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel_path, encoding="utf-8")
    for rel_path in transport_activation_decision_gate._STAGE8_SOURCE_FILES:
        path = repo_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("VALUE = 'clean'\n", encoding="utf-8")

    first = run_local_transport_activation_decision_gate(
        repo_root=repo_root,
        decided_at=_NOW,
        output_path=output_path.resolve(),
    )
    second = run_local_transport_activation_decision_gate(
        repo_root=repo_root,
        decided_at=_NOW,
        output_path=output_path.resolve(),
    )

    assert isinstance(first, LocalTransportActivationDecisionResult)
    assert isinstance(second, LocalTransportActivationDecisionResult)
    assert first.report_path == str(output_path.resolve())
    assert second.report_path == str(output_path.resolve())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["gate_id"] == second.gate_id
    assert payload["report_path"] is None


def test_missing_compatibility_evidence_blocks() -> None:
    temp_root = _workspace_tmp("missing_evidence")
    result = run_local_transport_activation_decision_gate(
        repo_root=temp_root,
        decided_at=_NOW,
    )

    assert isinstance(result, LocalTransportActivationDecisionResult)
    assert result.go_no_go == "BLOCKED"
    assert any(
        blocker.code == "STAGE_4_5_6_7_CONTRACT_COMPATIBILITY_EVIDENCE_MISSING"
        for blocker in result.blockers
    )


def test_forbidden_behavior_scan_blocks(monkeypatch) -> None:
    temp_root = _workspace_tmp("forbidden_scan")
    for rel_path in transport_activation_decision_gate._REQUIRED_EVIDENCE:
        path = temp_root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel_path, encoding="utf-8")
    bad_path = temp_root / "bad.py"
    bad_path.write_text("VALUE = 'fetch('\n", encoding="utf-8")
    monkeypatch.setattr(transport_activation_decision_gate, "_STAGE8_SOURCE_FILES", ("bad.py",))

    result = run_local_transport_activation_decision_gate(repo_root=temp_root, decided_at=_NOW)

    assert isinstance(result, LocalTransportActivationDecisionResult)
    assert result.go_no_go == "BLOCKED"
    assert result.forbidden_behavior_findings
    assert any(blocker.code == "FORBIDDEN_STAGE_8_1_SOURCE_BEHAVIOR" for blocker in result.blockers)


def test_result_is_deterministic_for_identical_inputs() -> None:
    first = _result()
    second = _result()

    assert first.to_dict() == second.to_dict()


def test_stage8_1_implementation_source_has_no_forbidden_runtime_markers() -> None:
    source_paths = (
        Path("scos/control_center/transport_activation_decision_models.py"),
        Path("scos/control_center/transport_activation_decision_gate.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    forbidden = (
        "Web" + "Socket",
        "Event" + "Source",
        "set" + "Interval",
        "set" + "Timeout",
        "fet" + "ch(",
        "axi" + "os",
        "route" + ".ts",
        "sub" + "process",
        "os." + "system",
        "socket" + "server",
        "http." + "server",
        "uvi" + "corn",
        "fast" + "api",
        "fla" + "sk",
        "requ" + "ests",
        "open" + "ai",
        "anth" + "ropic",
        "api" + "_key",
        "sec" + "ret",
        "tok" + "en",
    )
    for marker in forbidden:
        assert marker not in combined
