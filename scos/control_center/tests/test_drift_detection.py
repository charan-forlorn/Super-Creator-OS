"""Stage 6.9 drift detection tests."""

from __future__ import annotations

from scos.control_center.drift_detection import detect_backend_drift


def _types(findings):
    return {finding.drift_type for finding in findings}


def test_drift_detection_reports_orphan_queued_command() -> None:
    findings = detect_backend_drift(
        queue_commands=({"command_id": "cmd-orphan"},),
        event_log_records=(),
        state_results=(),
    )

    assert "queued_command_missing_result_or_event" in _types(findings)
    assert findings[0].subject_id == "cmd-orphan"


def test_drift_detection_reports_event_referencing_unknown_command() -> None:
    findings = detect_backend_drift(
        state_commands=(),
        queue_commands=(),
        event_log_records=({"command_id": "cmd-missing"},),
    )

    assert "event_references_unknown_command" in _types(findings)


def test_drift_detection_reports_approval_without_command_evidence() -> None:
    findings = detect_backend_drift(
        audit_decisions=({"subject_type": "command", "subject_id": "cmd-approved"},),
    )

    assert "approval_missing_command_evidence" in _types(findings)


def test_drift_detection_reports_audit_chain_failure_as_blocker() -> None:
    findings = detect_backend_drift(audit_chain_ok=False)

    assert "audit_chain_verification_failed" in _types(findings)
    assert findings[0].severity == "blocker"


def test_drift_detection_output_is_deterministic() -> None:
    kwargs = {
        "queue_commands": ({"command_id": "cmd-b"}, {"command_id": "cmd-a"}),
        "event_log_records": ({"command_id": "cmd-z"},),
        "audit_decisions": ({"subject_type": "command", "subject_id": "cmd-y"},),
    }

    first = tuple(finding.to_dict() for finding in detect_backend_drift(**kwargs))
    second = tuple(finding.to_dict() for finding in detect_backend_drift(**kwargs))

    assert first == second


def test_drift_detection_clean_sources_return_no_findings() -> None:
    findings = detect_backend_drift(
        state_commands=({"command_id": "cmd-1"},),
        queue_commands=({"command_id": "cmd-1"},),
        event_log_records=({"command_id": "cmd-1"},),
        audit_decisions=({"subject_type": "command", "subject_id": "cmd-1"},),
        audit_chain_ok=True,
    )

    assert findings == ()
