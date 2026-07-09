"""Stage 8.1 transport activation decision model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.transport_activation_decision_models import (
    TRANSPORT_ACTIVATION_DECISIONS,
    TRANSPORT_ACTIVATION_OPTIONS,
    LocalTransportActivationDecisionError,
    TransportDecisionBlocker,
    TransportDecisionRecord,
    TransportOptionAnalysis,
    TransportSafetyRequirement,
)


def _analysis(option: str = "NO_TRANSPORT") -> TransportOptionAnalysis:
    return TransportOptionAnalysis(
        option=option,
        description="description",
        security_risk="risk",
        operational_risk="risk",
        localhost_boundary="local",
        approval_requirements=("b", "a"),
        audit_requirements=("audit",),
        rollback_requirements=("rollback",),
        test_requirements=("test",),
        forbidden_behaviors=("forbidden",),
        recommendation="recommend",
        locality_boundary="local",
        origin_csrf_local_exposure_risk="risk",
        stale_data_risk="risk",
        event_ordering_risk="risk",
        accidental_command_execution_risk="none",
        adapter_dispatch_risk="none",
        credential_exposure_risk="none",
        rollback_kill_switch_requirement="required",
        operator_approval_preservation="preserved",
        deterministic_testability="stable",
    )


def test_transport_option_analysis_is_frozen_and_deterministic() -> None:
    analysis = _analysis()

    assert analysis.approval_requirements == ("a", "b")
    assert analysis.to_dict()["option"] == "NO_TRANSPORT"
    with pytest.raises(FrozenInstanceError):
        analysis.option = "POLLING"  # type: ignore[misc]


def test_transport_option_values_cover_required_options() -> None:
    assert TRANSPORT_ACTIVATION_OPTIONS == (
        "NO_TRANSPORT",
        "FILE_SNAPSHOT_REFRESH",
        "LOCAL_HTTP",
        "WEBSOCKET",
        "SSE_EVENTSOURCE",
        "POLLING",
    )
    assert "BLOCK_TRANSPORT_ACTIVATION" in TRANSPORT_ACTIVATION_DECISIONS


def test_invalid_transport_option_is_rejected() -> None:
    with pytest.raises(ValueError):
        _analysis("REMOTE_TRANSPORT")


def test_safety_requirement_normalizes_tuple_fields() -> None:
    requirement = TransportSafetyRequirement(
        requirement_id="r1",
        category="locality",
        requirement="required",
        status="pass",
        applies_to=("WEBSOCKET", "NO_TRANSPORT"),
        evidence=("b", "a"),
        metadata=(("z", "2"), ("a", "1")),
    )

    assert requirement.applies_to == ("NO_TRANSPORT", "WEBSOCKET")
    assert requirement.evidence == ("a", "b")
    assert requirement.metadata == (("a", "1"), ("z", "2"))


def test_invalid_requirement_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        TransportSafetyRequirement(
            requirement_id="r1",
            category="locality",
            requirement="required",
            status="unknown",
            applies_to=(),
            evidence=(),
            metadata=(),
        )


def test_decision_record_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError):
        TransportDecisionRecord(
            decision_id="d1",
            decision="IMPLEMENT_NOW",
            requested_decision="NO_TRANSPORT",
            decided_at="2026-07-10T00:00:00Z",
            allow_future_implementation=False,
            future_implementation_requires_later_stage=False,
            recommended_next_stage="none",
            decision_summary="summary",
        )


def test_blocker_and_error_to_dict_are_stable() -> None:
    blocker = TransportDecisionBlocker(
        blocker_id="b1",
        code="CODE",
        severity="error",
        message="message",
        evidence=("z", "a"),
    )
    error = LocalTransportActivationDecisionError.of(
        "ERR",
        "message",
        decided_at="",
        blockers=("b", "a"),
    )

    assert blocker.to_dict()["evidence"] == ["a", "z"]
    assert error.to_dict()["blockers"] == ["a", "b"]
