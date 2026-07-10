"""Stage 8.5 explicit adapter activation authorization gate tests."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from scos.control_center.adapter_activation_authorization_gate import (
    build_stage85_authorization_evidence,
    evaluate_adapter_activation_authorization,
    write_adapter_activation_authorization_report,
)
from scos.control_center.adapter_activation_authorization_models import (
    AdapterActivationAuthorizationRequest,
    AdapterActivationScope,
    OperatorIdentity,
)
from scos.control_center.secret_safe_adapter_preflight_gate import build_stage84_preflight_evidence
from scos.control_center.secret_safe_adapter_preflight_models import SafeCredentialReference

_NOW = "2026-07-10T08:00:00Z"
_EXPIRES = "2026-07-10T09:00:00Z"


def _stage84_evidence() -> dict:
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
        "rollback_evidence": {"restores_adapter_disabled": True, "network_dependency": False, "steps": ["keep adapter disabled"]},
        "simulator_fallback_evidence": {"available": True, "claims_runtime_activation": False},
        "manual_fallback_evidence": {"available": True, "claims_runtime_activation": False},
    }


def _ready_preflight(**overrides):
    evidence = _stage84_evidence()
    evidence.update(overrides)
    return build_stage84_preflight_evidence(
        adapter_id="codex",
        checked_at=_NOW,
        safe_credential_references=(
            SafeCredentialReference("cred-ref-001", "API_KEY", "SECRET", "policy_reference", "policy_only", "redacted", False),
        ),
        metadata={"stage": "8.4"},
        **evidence,
    )


def _operator(**overrides) -> OperatorIdentity:
    payload = {
        "operator_id": "operator-charan",
        "display_name": "Charan",
        "role": "owner",
        "authentication_evidence_ref": "auth-evidence-001",
        "human_confirmed": True,
    }
    payload.update(overrides)
    return OperatorIdentity(**payload)


def _scope(**overrides) -> AdapterActivationScope:
    payload = {
        "adapter_id": "codex",
        "adapter_kind": "ai_agent_adapter",
        "runtime_target": "simulator",
        "allowed_operations": ("prepare_activation", "refresh_file_snapshot"),
        "transport_mode": "FILE_SNAPSHOT_REFRESH",
        "credential_reference_ids": ("cred-ref-001",),
        "expires_at": _EXPIRES,
    }
    payload.update(overrides)
    return AdapterActivationScope(**payload)


def _approval(**overrides) -> dict:
    payload = {
        "approval_decision": "APPROVE",
        "request_id": "auth-request-001",
        "adapter_id": "codex",
        "runtime_target": "simulator",
        "operator_id": "operator-charan",
        "authentication_evidence_ref": "auth-evidence-001",
        "approved_operations": ["prepare_activation", "refresh_file_snapshot"],
        "transport_mode": "FILE_SNAPSHOT_REFRESH",
        "credential_reference_ids": ["cred-ref-001"],
        "preflight_result_id": _ready_preflight().result_id,
        "preflight_runtime_target": "simulator",
        "preflight_checked_at": _NOW,
        "approved_at": _NOW,
        "expires_at": _EXPIRES,
        "blanket_approval": False,
        "reusable": False,
        "ai_generated_approval": False,
    }
    payload.update(overrides)
    return payload


def _request(**overrides) -> AdapterActivationAuthorizationRequest:
    preflight = overrides.pop("preflight_result", _ready_preflight())
    payload = {
        "request_id": "auth-request-001",
        "checked_at": _NOW,
        "preflight_result": preflight,
        "operator": _operator(),
        "scope": _scope(),
        "explicit_decision": "APPROVE",
        "decision_reason": "approve exact Stage 8.5 authorization request",
        "approval_evidence": _approval(preflight_result_id=preflight.result_id),
        "audit_readiness": {"append_only_supported": True, "will_write_now": False, "audit_store_mutated": False},
        "rollback_acknowledged": True,
        "fallback_acknowledged": True,
    }
    payload.update(overrides)
    return AdapterActivationAuthorizationRequest(**payload)


def test_valid_exact_human_approval_authorizes_in_principle_only() -> None:
    result = evaluate_adapter_activation_authorization(_request(), checked_at=_NOW)

    assert result.decision == "AUTHORIZED_IN_PRINCIPLE"
    assert result.authorized_in_principle is True
    assert result.can_activate_now is False
    assert result.activation_executed is False
    assert result.credentials_materialized is False
    assert result.external_calls_made is False
    assert result.runtime_mutated is False


def test_explicit_denial_returns_denied_without_authorization() -> None:
    result = evaluate_adapter_activation_authorization(
        _request(explicit_decision="DENY", decision_reason="operator rejected exact request", approval_evidence=_approval(approval_decision="DENY")),
        checked_at=_NOW,
    )

    assert result.decision == "DENIED"
    assert result.authorized_in_principle is False
    assert "operator rejected exact request" in result.evidence.to_dict()["decision_reason"]


def test_security_matrix_blocked_cases() -> None:
    cases = (
        _request(operator=_operator(operator_id="")),
        _request(operator=_operator(role="ai_agent")),
        _request(approval_evidence=_approval(blanket_approval=True)),
        _request(scope=_scope(adapter_id="*"), approval_evidence=_approval(adapter_id="*")),
        _request(scope=_scope(adapter_id="chatgpt")),
        _request(scope=_scope(runtime_target="manual"), approval_evidence=_approval(runtime_target="manual")),
        _request(approval_evidence=_approval(request_id="other-request")),
        _request(preflight_result=_ready_preflight(rollback_evidence={})),
        _request(scope=_scope(credential_reference_ids=("sk-1234567890",)), approval_evidence=_approval(credential_reference_ids=["sk-1234567890"])),
        _request(scope=_scope(transport_mode="WEBSOCKET"), approval_evidence=_approval(transport_mode="WEBSOCKET")),
        _request(rollback_acknowledged=False),
        _request(fallback_acknowledged=False),
        _request(audit_readiness={"append_only_supported": True, "will_write_now": True}),
        _request(scope=_scope(allowed_operations=("prepare_activation", "real_dispatch")), approval_evidence=_approval(approved_operations=["prepare_activation", "real_dispatch"])),
    )

    for request in cases:
        result = evaluate_adapter_activation_authorization(request, checked_at=_NOW)
        assert result.decision == "BLOCKED"
        assert result.authorized_in_principle is False
        assert result.can_activate_now is False


def test_expired_authorization_and_stale_preflight_return_expired() -> None:
    expired_scope = _scope(expires_at="2026-07-10T07:59:59Z")
    expired = evaluate_adapter_activation_authorization(
        _request(scope=expired_scope, approval_evidence=_approval(expires_at="2026-07-10T07:59:59Z")),
        checked_at=_NOW,
    )
    stale = evaluate_adapter_activation_authorization(
        _request(approval_evidence=_approval(approved_at="2026-07-09T08:00:00Z")),
        checked_at=_NOW,
    )
    stale_preflight = evaluate_adapter_activation_authorization(
        _request(approval_evidence=_approval(preflight_checked_at="2026-07-09T08:00:00Z")),
        checked_at=_NOW,
    )

    assert expired.decision == "EXPIRED"
    assert stale.decision == "EXPIRED"
    assert stale_preflight.decision == "EXPIRED"


def test_input_is_not_mutated_and_evaluation_is_deterministic() -> None:
    request = _request()
    before = copy.deepcopy(request.to_dict())

    first = evaluate_adapter_activation_authorization(request, checked_at=_NOW)
    second = evaluate_adapter_activation_authorization(request, checked_at=_NOW)

    assert request.to_dict() == before
    assert first.to_dict() == second.to_dict()
    assert first.authorization_id == second.authorization_id


def test_build_evidence_and_report_writer_are_deterministic_and_redacted(tmp_path: Path) -> None:
    result = build_stage85_authorization_evidence(request=_request(), checked_at=_NOW)
    output = tmp_path / "reports" / "stage8_5.json"

    none_write = write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path=None)
    first = write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path=output)
    first_text = output.read_text(encoding="utf-8")
    second = write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path=output)

    assert none_write["accepted"] is True
    assert none_write["output_path"] is None
    assert first["accepted"] is True
    assert second["accepted"] is True
    assert output.read_text(encoding="utf-8") == first_text
    assert json.loads(first_text)["decision"] == "AUTHORIZED_IN_PRINCIPLE"
    assert "sk-" not in first_text
    assert "Bearer" not in first_text


def test_report_writer_rejects_url_escape_and_unrelated_overwrite(tmp_path: Path) -> None:
    result = evaluate_adapter_activation_authorization(_request(), checked_at=_NOW)
    outside = tmp_path.parent / "outside-stage8-5.json"
    existing = tmp_path / "existing.json"
    existing.write_text('{"unrelated": true}\n', encoding="utf-8")

    assert write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path="https://example.invalid/report.json")["accepted"] is False
    assert write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path=outside)["accepted"] is False
    assert write_adapter_activation_authorization_report(result, repo_root=tmp_path, output_path=existing)["accepted"] is False
    assert json.loads(existing.read_text(encoding="utf-8")) == {"unrelated": True}


def test_static_safety_scan_new_stage85_sources() -> None:
    source_paths = (
        Path("scos/control_center/adapter_activation_authorization_models.py"),
        Path("scos/control_center/adapter_activation_authorization_validation.py"),
        Path("scos/control_center/adapter_activation_authorization_gate.py"),
    )
    forbidden_import_roots = {
        "asyncio",
        "dotenv",
        "http",
        "keyring",
        "multiprocessing",
        "os",
        "requests",
        "socket",
        "subprocess",
        "threading",
        "urllib",
        "webbrowser",
        "websocket",
    }
    forbidden_call_names = {
        "Popen",
        "EventSource",
        "run",
        "system",
        "start",
        "open_new",
        "open_new_tab",
        "copy",
        "paste",
    }
    forbidden_attribute_roots = {"environ", "getenv"}
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_import_roots
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_import_roots
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    assert func.id not in forbidden_call_names
                if isinstance(func, ast.Attribute):
                    assert func.attr not in forbidden_call_names | forbidden_attribute_roots
