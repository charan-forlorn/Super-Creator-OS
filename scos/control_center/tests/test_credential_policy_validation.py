"""Stage 8.3 credential policy validation tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.credential_policy_models import REDACTION_MARKER
from scos.control_center.credential_policy_validation import (
    build_stage83_credential_policy_evidence,
    validate_no_secret_leak,
    validate_operator_approval_boundary,
)
from scos.control_center.credential_redaction import redact_credential_payload
from scos.control_center.file_snapshot_refresh_transport import build_file_snapshot_transport_payload
from scos.control_center.file_snapshot_transport_models import FileSnapshotTransportResult

_NOW = "2026-07-10T07:00:00Z"


def _fake_secret() -> str:
    return "FAKE_" + "SECRET" + "_DO_NOT_USE"


def test_validation_rejects_unredacted_secret_in_log_event_snapshot_and_approval() -> None:
    key = "api" + "_key"
    surfaces = ("LOG", "EVENT", "SNAPSHOT", "APPROVAL_EVIDENCE")

    for surface in surfaces:
        result = validate_no_secret_leak({key: _fake_secret()}, checked_at=_NOW, surface_type=surface)
        assert result.accepted is False
        assert result.go_no_go == "NO_GO"
        assert result.violations
        assert result.checked_at == _NOW


def test_validation_accepts_redacted_payload_and_non_secret_metadata() -> None:
    key = "api" + "_key"
    redacted = redact_credential_payload({key: _fake_secret(), "operator": "local"}).to_dict()["redacted_payload"]

    result = validate_no_secret_leak(redacted, checked_at=_NOW, surface_type="SNAPSHOT")

    assert result.accepted is True
    assert result.go_no_go == "GO"
    assert result.blockers == ()
    assert redacted[key] == REDACTION_MARKER


def test_validation_requires_caller_supplied_timestamp() -> None:
    result = validate_no_secret_leak({"status": "safe"}, checked_at="", surface_type="LOG")

    assert result.accepted is False
    assert any("checked_at" in blocker for blocker in result.blockers)


def test_operator_approval_boundary_rejects_missing_denied_blanket_and_ambiguous_use() -> None:
    missing = validate_operator_approval_boundary(
        {"credential_use_requested": True},
        checked_at=_NOW,
    )
    denied = validate_operator_approval_boundary(
        {
            "credential_use_requested": True,
            "approval_decision": "denied",
            "approval_scope": "single_dispatch",
            "later_stage_authorized": True,
        },
        checked_at=_NOW,
    )
    blanket = validate_operator_approval_boundary(
        {
            "credential_use_requested": True,
            "approval_decision": "approved",
            "approval_scope": "blanket",
            "later_stage_authorized": True,
        },
        checked_at=_NOW,
    )
    ambiguous = validate_operator_approval_boundary(
        {
            "credential_use_requested": True,
            "approval_decision": "approved",
            "approval_scope": "single_dispatch",
            "later_stage_authorized": False,
        },
        checked_at=_NOW,
    )

    for result in (missing, denied, blanket, ambiguous):
        assert result.accepted is False
        assert result.blockers


def test_operator_approval_boundary_accepts_no_credential_request() -> None:
    result = validate_operator_approval_boundary(
        {"credential_use_requested": False, "approval_reference": "stage8.3-policy-only"},
        checked_at=_NOW,
    )

    assert result.accepted is True
    assert result.approval_boundary_status == "NOT_REQUESTED"


def test_operator_approval_boundary_accepts_explicit_later_stage_shape_only_as_policy_evidence() -> None:
    result = validate_operator_approval_boundary(
        {
            "credential_use_requested": True,
            "approval_decision": "approved",
            "approval_scope": "single_dispatch",
            "later_stage_authorized": True,
        },
        checked_at=_NOW,
    )

    assert result.accepted is True
    assert result.approval_boundary_status == "APPROVED_EXPLICIT_LATER_STAGE"


def test_stage83_policy_evidence_is_deterministic_and_policy_only() -> None:
    first = build_stage83_credential_policy_evidence(checked_at=_NOW)
    second = build_stage83_credential_policy_evidence(checked_at=_NOW)

    assert first.to_dict() == second.to_dict()
    assert first.accepted is True
    metadata = first.to_dict()["metadata"]
    assert metadata["secret_storage_implemented"] is False
    assert metadata["api_key_flow_implemented"] is False
    assert metadata["external_calls_implemented"] is False
    assert metadata["adapter_activation_implemented"] is False


def test_stage82_file_snapshot_remains_compatible_and_not_credential_aware() -> None:
    result = build_file_snapshot_transport_payload(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, FileSnapshotTransportResult)
    assert result.accepted is True
    assert result.payload is not None
    assert "credential_policy" not in result.payload
