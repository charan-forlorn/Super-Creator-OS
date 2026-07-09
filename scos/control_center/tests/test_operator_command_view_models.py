"""Stage 7.6 operator command view model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.operator_command_view_models import (
    ExecutionEvidenceRecord,
    OperatorCommandApprovalState,
    OperatorCommandEvidenceReference,
    OperatorCommandView,
    OperatorCommandViewSnapshot,
    OperatorCommandViewTotals,
)

_NOW = "2026-07-10T01:00:00Z"


def _ref(reference_id: str = "ref-a") -> OperatorCommandEvidenceReference:
    return OperatorCommandEvidenceReference(
        reference_id=reference_id,
        reference_type="approval",
        source_stage="Stage 6.6",
        path="scos/work/control_center/state/control_center.sqlite3",
        exists=True,
        readable=True,
        digest="a" * 64,
    )


def _approval(state: str = "approved") -> OperatorCommandApprovalState:
    return OperatorCommandApprovalState(
        command_id="cmd-1",
        approval_state=state,
        terminal=state in {"denied", "missing_approval", "tampered", "blocked", "executed"},
        human_readable_status=state,
        required_operator_action="inspect evidence",
        evidence_references=(_ref("ref-b"), _ref("ref-a")),
    )


def _execution(state: str = "not_executed") -> ExecutionEvidenceRecord:
    return ExecutionEvidenceRecord(
        evidence_id="evid-1",
        command_id="cmd-1",
        execution_state=state,
        approval_state="approved",
        audit_state="audited",
        event_state="present",
        summary="visible",
        references=(_ref("ref-b"), _ref("ref-a")),
        metadata=(("z", "last"), ("a", "first")),
    )


def test_evidence_reference_to_dict_is_stable_and_immutable() -> None:
    reference = _ref()

    assert list(reference.to_dict()) == [
        "reference_id",
        "reference_type",
        "source_stage",
        "path",
        "exists",
        "readable",
        "digest",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        reference.exists = False  # type: ignore[misc]


def test_nested_models_sort_and_serialize_stably() -> None:
    approval = _approval()
    execution = _execution()
    view = OperatorCommandView(
        view_id="view-1",
        checked_at=_NOW,
        command_id="cmd-1",
        command_type="RUN_SMOKE_CHECK",
        approval=approval,
        execution=execution,
        warnings=("z", "a"),
        blockers=(),
        next_manual_action="inspect",
    )

    assert [ref.reference_id for ref in approval.evidence_references] == ["ref-a", "ref-b"]
    assert execution.metadata == (("a", "first"), ("z", "last"))
    assert view.warnings == ("a", "z")
    assert view.to_dict()["approval"]["approval_state"] == "approved"


def test_snapshot_totals_are_immutable_and_stable() -> None:
    view = OperatorCommandView(
        view_id="view-1",
        checked_at=_NOW,
        command_id="cmd-1",
        command_type="RUN_SMOKE_CHECK",
        approval=_approval(),
        execution=_execution(),
        warnings=(),
        blockers=(),
        next_manual_action="inspect",
    )
    snapshot = OperatorCommandViewSnapshot(
        snapshot_id="snap-1",
        checked_at=_NOW,
        views=(view,),
        totals=OperatorCommandViewTotals(
            pending=0,
            approved=1,
            denied=0,
            missing_approval=0,
            executed=0,
            blocked=0,
            audited=1,
        ),
        warnings=(),
        blockers=(),
        readiness_score=100,
        go_no_go="GO",
        accepted=True,
    )

    assert snapshot.to_dict()["totals"]["approved"] == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.accepted = False  # type: ignore[misc]


def test_invalid_states_are_rejected() -> None:
    with pytest.raises(ValueError):
        _approval("bad")
    with pytest.raises(ValueError):
        _execution("bad")
