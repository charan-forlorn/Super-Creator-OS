"""Stage 7.6 execution evidence surface tests."""

from __future__ import annotations

from scos.control_center.execution_evidence_surface import (
    build_execution_evidence_record,
    classify_execution_state,
)
from scos.control_center.operator_command_view_models import OperatorCommandEvidenceReference


def _ref() -> OperatorCommandEvidenceReference:
    return OperatorCommandEvidenceReference(
        reference_id="event-ref",
        reference_type="event",
        source_stage="Stage 6.4",
        path="scos/work/control_center/events/command_events.jsonl",
        exists=True,
        readable=True,
        digest="b" * 64,
    )


def test_execution_state_classification_blocks_unsafe_states() -> None:
    assert classify_execution_state(approval_state="missing_approval") == "blocked_missing_approval"
    assert classify_execution_state(approval_state="denied") == "blocked_denied"
    assert classify_execution_state(approval_state="tampered") == "blocked_tampered_approval"
    assert classify_execution_state(approval_state="approved", allowlisted=False) == "blocked_not_allowlisted"
    assert classify_execution_state(approval_state="approved", validation_ok=False) == "blocked_validation_failed"


def test_execution_state_visible_for_approved_and_executed() -> None:
    assert classify_execution_state(approval_state="approved") == "not_executed"
    assert classify_execution_state(approval_state="approved", has_execution_event=True) == "executed"


def test_execution_evidence_record_is_deterministic() -> None:
    first = build_execution_evidence_record(
        command_id="cmd-1",
        approval_state="approved",
        audit_state="audited",
        event_state="present",
        references=(_ref(),),
        metadata=(("source", "test"),),
    )
    second = build_execution_evidence_record(
        command_id="cmd-1",
        approval_state="approved",
        audit_state="audited",
        event_state="present",
        references=(_ref(),),
        metadata=(("source", "test"),),
    )

    assert first.evidence_id == second.evidence_id
    assert first.to_dict() == second.to_dict()
    assert first.execution_state == "not_executed"
