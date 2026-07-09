"""Stage 7.5 read surface transport decision gate tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.read_surface_transport_decision import (
    build_read_surface_transport_decision,
    export_transport_decision_markdown,
    validate_transport_decision_gate,
)
from scos.control_center.transport_decision_models import (
    TransportDecisionError,
    TransportDecisionRecord,
)

_NOW = "2026-07-10T00:00:00Z"


def _decision(requested_decision: str = "NO_LIVE_TRANSPORT") -> TransportDecisionRecord:
    result = build_read_surface_transport_decision(
        decided_at=_NOW,
        requested_decision=requested_decision,
    )
    assert isinstance(result, TransportDecisionRecord)
    return result


def test_no_live_transport_decision_returns_go_100_and_accepted() -> None:
    result = validate_transport_decision_gate(decided_at=_NOW)

    assert isinstance(result, TransportDecisionRecord)
    assert result.decision == "NO_LIVE_TRANSPORT"
    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.readiness_score == 100
    assert result.default_transport == "STATIC_MOCK_FALLBACK"
    assert result.blockers == ()
    assert any("forbidden until a later explicit implementation stage" in warning for warning in result.warnings)


def test_websocket_allowed_later_does_not_implement_websocket() -> None:
    result = _decision("WEBSOCKET_ALLOWED_LATER")

    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.readiness_score == 90
    assert result.default_transport == "STATIC_MOCK_FALLBACK"
    assert "operator approval before implementation" in result.required_next_stage_controls
    assert "WEBSOCKET" in result.forbidden_until_next_approval
    assert any(analysis.option == "WEBSOCKET" and analysis.allowed is False for analysis in result.analyses)


def test_sse_allowed_later_does_not_implement_sse_or_eventsource() -> None:
    result = _decision("SSE_ALLOWED_LATER")

    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.readiness_score == 90
    assert "SSE EVENT STREAM" in result.forbidden_until_next_approval
    assert any(analysis.option == "SSE" and analysis.allowed is False for analysis in result.analyses)


def test_polling_allowed_later_does_not_implement_polling_or_timers() -> None:
    result = _decision("POLLING_ALLOWED_LATER")

    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.readiness_score == 90
    assert "POLLING" in result.forbidden_until_next_approval
    assert "TIMER LOOPS" in result.forbidden_until_next_approval
    assert any(analysis.option == "POLLING" and analysis.allowed is False for analysis in result.analyses)


def test_immediate_implementation_request_returns_no_go_blocker() -> None:
    result = build_read_surface_transport_decision(
        decided_at=_NOW,
        requested_decision="WEBSOCKET_ALLOWED_LATER",
        allow_transport_implementation=True,
    )

    assert isinstance(result, TransportDecisionRecord)
    assert result.accepted is False
    assert result.go_no_go == "NO_GO"
    assert result.readiness_score <= 50
    assert result.blockers


def test_invalid_requested_decision_returns_error() -> None:
    result = build_read_surface_transport_decision(
        decided_at=_NOW,
        requested_decision="WEBSOCKET_NOW",
    )

    assert isinstance(result, TransportDecisionError)
    assert result.error_code == "INVALID_REQUESTED_DECISION"


def test_decided_at_is_caller_supplied_and_required() -> None:
    result = build_read_surface_transport_decision(decided_at="")

    assert isinstance(result, TransportDecisionError)
    assert result.error_code == "INVALID_DECIDED_AT"


def test_decision_id_is_deterministic_for_identical_inputs() -> None:
    first = _decision()
    second = _decision()

    assert first.decision_id == second.decision_id
    assert first.to_dict() == second.to_dict()


def test_export_transport_decision_markdown_is_deterministic() -> None:
    decision = _decision()

    first = export_transport_decision_markdown(decision=decision)
    second = export_transport_decision_markdown(decision=decision)

    assert first == second
    assert decision.decision_id in first
    assert "STATIC_MOCK_FALLBACK" in first


def test_stage7_5_source_uses_no_forbidden_runtime_tokens() -> None:
    source_paths = (
        Path("scos/control_center/transport_decision_models.py"),
        Path("scos/control_center/read_surface_transport_decision.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    forbidden = (
        "socket",
        "websocket",
        "WebSocket",
        "EventSource",
        "setInterval",
        "setTimeout",
        "fetch(",
        "XMLHttpRequest",
        "axios",
        "http.server",
        "fastapi",
        "flask",
        "django",
        "requests",
        "urllib.request",
        "subprocess",
        "shell=True",
        "time.time",
        "datetime.now",
        "uuid",
        "random",
    )
    for token in forbidden:
        assert token not in combined
