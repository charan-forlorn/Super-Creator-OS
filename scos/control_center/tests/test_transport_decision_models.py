"""Stage 7.5 transport decision model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.transport_decision_models import (
    TransportDecisionError,
    TransportDecisionRecord,
    TransportOptionAnalysis,
)

_NOW = "2026-07-10T00:00:00Z"


def test_option_analysis_to_dict_is_stable_and_immutable() -> None:
    analysis = TransportOptionAnalysis(
        option="NO_LIVE_TRANSPORT",
        allowed=True,
        security_risk="low",
        operational_risk="low",
        localhost_boundary="manual only",
        required_controls=("z", "a"),
        forbidden_behaviors=("b", "a"),
        test_expectations=("deterministic",),
        rollback_requirements=("fallback",),
        notes=("preferred",),
    )

    assert analysis.required_controls == ("a", "z")
    assert list(analysis.to_dict()) == [
        "option",
        "allowed",
        "security_risk",
        "operational_risk",
        "localhost_boundary",
        "required_controls",
        "forbidden_behaviors",
        "test_expectations",
        "rollback_requirements",
        "notes",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        analysis.allowed = False  # type: ignore[misc]


def test_decision_record_sorts_nested_values() -> None:
    websocket = TransportOptionAnalysis(
        option="WEBSOCKET",
        allowed=False,
        security_risk="high",
        operational_risk="high",
        localhost_boundary="local only later",
        required_controls=(),
        forbidden_behaviors=(),
        test_expectations=(),
        rollback_requirements=(),
        notes=(),
    )
    none = TransportOptionAnalysis(
        option="NO_LIVE_TRANSPORT",
        allowed=True,
        security_risk="low",
        operational_risk="low",
        localhost_boundary="manual only",
        required_controls=(),
        forbidden_behaviors=(),
        test_expectations=(),
        rollback_requirements=(),
        notes=(),
    )

    record = TransportDecisionRecord(
        decision_id="decision-1",
        decision="NO_LIVE_TRANSPORT",
        decided_at=_NOW,
        accepted=True,
        go_no_go="GO",
        readiness_score=100,
        default_transport="STATIC_MOCK_FALLBACK",
        analyses=(websocket, none),
        blockers=(),
        warnings=("z", "a"),
        required_next_stage_controls=("operator approval",),
        forbidden_until_next_approval=("WEBSOCKET",),
        rollback_plan=("fallback",),
    )

    assert [item.option for item in record.analyses] == ["NO_LIVE_TRANSPORT", "WEBSOCKET"]
    assert record.warnings == ("a", "z")
    assert record.to_dict()["default_transport"] == "STATIC_MOCK_FALLBACK"


def test_error_to_dict_is_stable() -> None:
    error = TransportDecisionError.of(
        "INVALID_REQUESTED_DECISION",
        "bad decision",
        checked_at=_NOW,
        blockers=("b2", "b1"),
    )

    assert error.blockers == ("b1", "b2")
    assert list(error.to_dict()) == ["error_code", "message", "checked_at", "blockers"]


def test_invalid_model_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        TransportOptionAnalysis(
            option="BAD",
            allowed=False,
            security_risk="bad",
            operational_risk="bad",
            localhost_boundary="bad",
            required_controls=(),
            forbidden_behaviors=(),
            test_expectations=(),
            rollback_requirements=(),
            notes=(),
        )
    with pytest.raises(ValueError):
        TransportDecisionRecord(
            decision_id="decision-1",
            decision="BAD",
            decided_at=_NOW,
            accepted=False,
            go_no_go="NO_GO",
            readiness_score=0,
            default_transport="STATIC_MOCK_FALLBACK",
            analyses=(),
            blockers=("bad",),
            warnings=(),
            required_next_stage_controls=(),
            forbidden_until_next_approval=(),
            rollback_plan=(),
        )
