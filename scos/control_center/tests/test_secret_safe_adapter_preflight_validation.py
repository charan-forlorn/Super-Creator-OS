"""Stage 8.4 secret-safe adapter preflight validation tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.secret_safe_adapter_preflight_gate import build_stage84_preflight_evidence
from scos.control_center.secret_safe_adapter_preflight_models import SafeCredentialReference
from scos.control_center.secret_safe_adapter_preflight_validation import (
    validate_report_output_path,
    validate_secret_safe_adapter_preflight_request,
)

_NOW = "2026-07-10T08:00:00Z"


def _fake_secret() -> str:
    return "FAKE_" + "SECRET" + "_DO_NOT_USE"


def _evidence() -> dict:
    return {
        "generic_preflight_evidence": {
            "go_no_go": "GO",
            "can_activate_now": False,
            "dispatch_blocked": True,
            "simulator_fallback_status": "pass",
            "manual_fallback_status": "pass",
            "rollback_status": "pass",
            "approval_evidence_status": "pass",
            "audit_evidence_status": "pass",
        },
        "transport_decision_evidence": {
            "accepted": True,
            "can_implement_now": False,
            "transport_implemented": False,
            "dispatch_blocked": True,
            "decision_record": {"decision": "FILE_SNAPSHOT_REFRESH_ALLOWED_LATER"},
        },
        "file_snapshot_boundary_evidence": {
            "manual_refresh_only": True,
            "network": False,
            "polling": False,
            "background_process": False,
            "file_watcher": False,
        },
        "credential_policy_evidence": {
            "accepted": True,
            "metadata": {
                "secret_storage_implemented": False,
                "api_key_flow_implemented": False,
                "external_calls_implemented": False,
                "adapter_activation_implemented": False,
            },
        },
        "operator_approval_evidence": {
            "approval_decision": "approved",
            "approval_scope": "adapter_specific",
            "action": "present_to_operator_decision",
            "adapter_id": "codex",
            "checked_at": _NOW,
        },
        "audit_readiness_evidence": {"append_only_supported": True, "will_write_now": False},
        "rollback_evidence": {"restores_adapter_disabled": True, "network_dependency": False, "steps": ["disable adapter"]},
        "simulator_fallback_evidence": {"available": True, "claims_runtime_activation": False},
        "manual_fallback_evidence": {"available": True, "claims_runtime_activation": False},
    }


def _request(**overrides):
    evidence = _evidence()
    payload = {
        "schema_version": 1,
        "request_id": "req",
        "adapter_id": "codex",
        "adapter_runtime": "simulator",
        "activation_mode": "preflight_only",
        "requested_transport": "FILE_SNAPSHOT_REFRESH",
        "checked_at": _NOW,
        "safe_credential_references": [
            {
                "reference_id": "ref",
                "credential_category": "API_KEY",
                "sensitivity": "SECRET",
                "source_kind": "policy_reference",
                "policy_status": "policy_only",
                "redaction_status": "redacted",
                "material_present": False,
            }
        ],
        "metadata": {"purpose": "stage8.4"},
    }
    payload.update(evidence)
    payload.update(overrides)
    return payload


def test_supported_adapter_request_is_accepted_for_evaluation() -> None:
    result = validate_secret_safe_adapter_preflight_request(_request(), checked_at=_NOW)

    assert result.accepted is True
    assert result.request is not None


def test_unsupported_adapter_malformed_and_missing_timestamp_are_rejected() -> None:
    assert validate_secret_safe_adapter_preflight_request(_request(adapter_id="unknown"), checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request([], checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(_request(checked_at=""), checked_at="").accepted is False


def test_remote_url_and_uncontained_report_path_are_rejected(tmp_path: Path) -> None:
    request = _request(metadata={"path": "https://example.invalid"})
    result = validate_secret_safe_adapter_preflight_request(request, checked_at=_NOW)
    _path, errors = validate_report_output_path(repo_root=tmp_path, output_path=tmp_path.parent / "outside.json")

    assert result.accepted is False
    assert errors


def test_immediate_activation_and_rejected_transport_are_rejected() -> None:
    assert validate_secret_safe_adapter_preflight_request(_request(activation_mode="real_dispatch"), checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(_request(requested_transport="WEBSOCKET"), checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(_request(requested_transport="SSE_EVENTSOURCE"), checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(_request(requested_transport="POLLING"), checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(_request(requested_transport="LOCAL_HTTP"), checked_at=_NOW).accepted is False


def test_credential_material_and_secret_values_are_rejected() -> None:
    material = _request(metadata={"value": "not allowed"})
    leaked = _request(metadata={"safe": _fake_secret()})

    assert validate_secret_safe_adapter_preflight_request(material, checked_at=_NOW).accepted is False
    assert validate_secret_safe_adapter_preflight_request(leaked, checked_at=_NOW).accepted is False


def test_safe_credential_reference_requires_no_material() -> None:
    bad = _request(
        safe_credential_references=[
            {
                "reference_id": "ref",
                "credential_category": "TOKEN",
                "sensitivity": "SECRET",
                "source_kind": "policy_reference",
                "policy_status": "policy_only",
                "redaction_status": "redacted",
                "material_present": True,
            }
        ]
    )

    assert validate_secret_safe_adapter_preflight_request(bad, checked_at=_NOW).accepted is False


def test_missing_evidence_and_bad_approval_block_gate() -> None:
    evidence = _evidence()
    evidence["credential_policy_evidence"] = {}
    missing = build_stage84_preflight_evidence(adapter_id="codex", checked_at=_NOW, **evidence)
    evidence = _evidence()
    evidence["operator_approval_evidence"] = {
        "approval_decision": "denied",
        "approval_scope": "adapter_specific",
        "action": "present_to_operator_decision",
        "adapter_id": "codex",
        "checked_at": _NOW,
    }
    denied = build_stage84_preflight_evidence(adapter_id="codex", checked_at=_NOW, **evidence)

    assert missing.verdict == "BLOCKED"
    assert denied.verdict == "NO_GO"


def test_blanket_default_ambiguous_and_stale_approval_are_rejected() -> None:
    for approval in (
        {"approval_decision": "approved", "approval_scope": "blanket", "action": "present_to_operator_decision", "adapter_id": "codex", "checked_at": _NOW},
        {"approval_decision": "approved", "approval_scope": "default", "action": "present_to_operator_decision", "adapter_id": "codex", "checked_at": _NOW},
        {"approval_decision": "approved", "approval_scope": "adapter_specific", "action": "activate_now", "adapter_id": "codex", "checked_at": _NOW},
        {"approval_decision": "approved", "approval_scope": "adapter_specific", "action": "present_to_operator_decision", "adapter_id": "codex", "checked_at": "2026-07-09T00:00:00Z"},
    ):
        evidence = _evidence()
        evidence["operator_approval_evidence"] = approval
        result = build_stage84_preflight_evidence(adapter_id="codex", checked_at=_NOW, **evidence)
        assert result.accepted is False


def test_missing_audit_rollback_and_fallback_block_gate() -> None:
    for key in ("audit_readiness_evidence", "rollback_evidence", "simulator_fallback_evidence", "manual_fallback_evidence"):
        evidence = _evidence()
        evidence[key] = {}
        result = build_stage84_preflight_evidence(adapter_id="codex", checked_at=_NOW, **evidence)
        assert result.verdict == "BLOCKED"


def test_redacted_evidence_and_safe_reference_are_accepted() -> None:
    evidence = _evidence()
    result = build_stage84_preflight_evidence(
        adapter_id="codex",
        checked_at=_NOW,
        safe_credential_references=(
            SafeCredentialReference("ref", "API_KEY", "SECRET", "policy_reference", "policy_only", "redacted", False),
        ),
        **evidence,
    )

    assert result.verdict == "READY_FOR_OPERATOR_DECISION"
