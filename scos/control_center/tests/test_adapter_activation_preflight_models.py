"""Stage 7.7 adapter activation preflight model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.adapter_activation_preflight_models import (
    AdapterActivationArtifact,
    AdapterActivationPreflightCheck,
    AdapterActivationPreflightError,
    AdapterActivationPreflightResult,
)

_NOW = "2026-07-10T02:00:00Z"


def _check(check_id: str = "check-b") -> AdapterActivationPreflightCheck:
    return AdapterActivationPreflightCheck(
        check_id=check_id,
        check_name="adapter_contract",
        status="pass",
        summary="adapter contract is represented",
        required=True,
        source_stage="Stage 5.3",
        references=("b", "a"),
        metadata=(("z", "last"), ("a", "first")),
    )


def _artifact(artifact_id: str = "artifact-b") -> AdapterActivationArtifact:
    return AdapterActivationArtifact(
        artifact_id=artifact_id,
        artifact_type="adapter_contract",
        path="scos/control_center/agent_adapter_models.py",
        required=True,
        exists=True,
        readable=True,
        digest="a" * 64,
    )


def test_check_and_artifact_to_dict_are_stable_and_immutable() -> None:
    check = _check()
    artifact = _artifact()

    assert check.references == ("a", "b")
    assert check.metadata == (("a", "first"), ("z", "last"))
    assert list(check.to_dict()) == [
        "check_id",
        "check_name",
        "status",
        "summary",
        "required",
        "source_stage",
        "references",
        "metadata",
    ]
    assert list(artifact.to_dict()) == [
        "artifact_id",
        "artifact_type",
        "path",
        "required",
        "exists",
        "readable",
        "digest",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        check.status = "blocker"  # type: ignore[misc]


def test_result_sorts_nested_values_and_serializes_stably() -> None:
    result = AdapterActivationPreflightResult(
        gate_id="gate-1",
        gate_name="Gate",
        checked_at=_NOW,
        target_adapter="all",
        requested_activation_mode="preflight_only",
        go_no_go="NO_GO",
        readiness_score=90,
        accepted=True,
        can_activate_now=False,
        activation_allowed_later=True,
        dispatch_blocked=True,
        approval_evidence_status="pass",
        audit_evidence_status="pass",
        secret_handling_status="pass",
        simulator_fallback_status="pass",
        manual_fallback_status="pass",
        rollback_status="pass",
        security_review_status="pass",
        transport_boundary_status="pass",
        adapter_contract_status="pass",
        blockers=(),
        warnings=("z", "a"),
        checks=(_check("check-b"), _check("check-a")),
        inspected_artifacts=(_artifact("artifact-b"), _artifact("artifact-a")),
        forbidden_behavior_findings=(),
        next_manual_actions=("b", "a"),
        report_path=None,
    )

    assert [check.check_id for check in result.checks] == ["check-a", "check-b"]
    assert [artifact.artifact_id for artifact in result.inspected_artifacts] == ["artifact-a", "artifact-b"]
    assert result.warnings == ("a", "z")
    assert result.to_dict()["can_activate_now"] is False


def test_error_to_dict_is_stable() -> None:
    error = AdapterActivationPreflightError.of(
        "INVALID_ADAPTER_PREFLIGHT_INPUT",
        "bad",
        checked_at=_NOW,
        blockers=("b2", "b1"),
    )

    assert error.blockers == ("b1", "b2")
    assert list(error.to_dict()) == ["error_code", "message", "checked_at", "blockers"]


def test_invalid_status_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        AdapterActivationPreflightCheck(
            check_id="bad",
            check_name="bad",
            status="bad",
            summary="bad",
            required=True,
            source_stage="Stage 7.7",
            references=(),
            metadata=(),
        )
