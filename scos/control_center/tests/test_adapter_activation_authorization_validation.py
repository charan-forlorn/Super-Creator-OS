"""Stage 8.5 explicit adapter activation authorization validation tests."""

from __future__ import annotations

from scos.control_center.adapter_activation_authorization_models import (
    AdapterActivationAuthorizationRequest,
    AdapterActivationScope,
    OperatorIdentity,
)
from scos.control_center.adapter_activation_authorization_validation import (
    validate_activation_scope,
    validate_adapter_activation_authorization_request,
    validate_operator_identity,
)

_NOW = "2026-07-10T08:00:00Z"
_EXPIRES = "2026-07-10T09:00:00Z"


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


def _request(**overrides) -> AdapterActivationAuthorizationRequest:
    payload = {
        "request_id": "auth-request-001",
        "checked_at": _NOW,
        "preflight_result": {
            "result_id": "sspr-ready",
            "checked_at": _NOW,
            "adapter_id": "codex",
            "verdict": "READY_FOR_OPERATOR_DECISION",
            "accepted": True,
            "ready_for_operator_decision": True,
            "can_activate_now": False,
            "activation_authorized": False,
            "real_dispatch_blocked": True,
            "external_calls_blocked": True,
            "credentials_materialized": False,
            "runtime_mutated": False,
            "checks": [],
            "blockers": [],
            "warnings": [],
            "evidence_digest": "digest",
        },
        "operator": _operator(),
        "scope": _scope(),
        "explicit_decision": "APPROVE",
        "decision_reason": "approve exact Stage 8.5 authorization request",
        "approval_evidence": {
            "approval_decision": "APPROVE",
            "request_id": "auth-request-001",
            "adapter_id": "codex",
            "runtime_target": "simulator",
            "operator_id": "operator-charan",
            "authentication_evidence_ref": "auth-evidence-001",
            "approved_operations": ["prepare_activation", "refresh_file_snapshot"],
            "transport_mode": "FILE_SNAPSHOT_REFRESH",
            "credential_reference_ids": ["cred-ref-001"],
            "preflight_result_id": "sspr-ready",
            "preflight_checked_at": _NOW,
            "approved_at": _NOW,
            "expires_at": _EXPIRES,
            "blanket_approval": False,
            "reusable": False,
            "ai_generated_approval": False,
        },
        "audit_readiness": {"append_only_supported": True, "will_write_now": False, "audit_store_mutated": False},
        "rollback_acknowledged": True,
        "fallback_acknowledged": True,
    }
    payload.update(overrides)
    return AdapterActivationAuthorizationRequest(**payload)


def _failed_codes(checks) -> set[str]:
    return {check.code for check in checks if not check.passed}


def test_operator_identity_requires_specific_human_operator() -> None:
    assert not _failed_codes(validate_operator_identity(_operator()))
    assert "operator_identity" in _failed_codes(validate_operator_identity(_operator(operator_id="")))
    assert "operator_identity" in _failed_codes(validate_operator_identity(_operator(human_confirmed=False)))
    assert "operator_identity" in _failed_codes(validate_operator_identity(_operator(role="ai_agent")))


def test_activation_scope_rejects_wildcards_secret_refs_and_empty_operations() -> None:
    assert not _failed_codes(validate_activation_scope(_scope()))
    assert "activation_scope" in _failed_codes(validate_activation_scope(_scope(adapter_id="*")))
    assert "activation_scope" in _failed_codes(validate_activation_scope(_scope(runtime_target="all")))
    assert "activation_scope" in _failed_codes(validate_activation_scope(_scope(allowed_operations=())))
    assert "credential_references" in _failed_codes(
        validate_activation_scope(_scope(credential_reference_ids=("sk-1234567890",)))
    )


def test_request_validation_rejects_blanket_mismatched_stale_and_audit_write_claims() -> None:
    assert not _failed_codes(validate_adapter_activation_authorization_request(_request()))
    assert "approval_binding" in _failed_codes(
        validate_adapter_activation_authorization_request(
            _request(approval_evidence={**_request().approval_evidence.to_dict(), "blanket_approval": True})
        )
    )
    assert "approval_binding" in _failed_codes(
        validate_adapter_activation_authorization_request(
            _request(approval_evidence={**_request().approval_evidence.to_dict(), "adapter_id": "chatgpt"})
        )
    )
    assert "timestamp_binding" in _failed_codes(
        validate_adapter_activation_authorization_request(
            _request(approval_evidence={**_request().approval_evidence.to_dict(), "approved_at": "2026-07-09T08:00:00Z"})
        )
    )
    assert "audit_readiness" in _failed_codes(
        validate_adapter_activation_authorization_request(_request(audit_readiness={"append_only_supported": True, "will_write_now": True}))
    )


def test_request_validation_rejects_secret_material_and_missing_acknowledgements() -> None:
    secret_ref = _scope(credential_reference_ids=("Bearer abcdefghijklmnop",))

    assert "credential_references" in _failed_codes(validate_adapter_activation_authorization_request(_request(scope=secret_ref)))
    assert "approval_evidence_secret_safety" in _failed_codes(
        validate_adapter_activation_authorization_request(
            _request(approval_evidence={**_request().approval_evidence.to_dict(), "token": "abc"})
        )
    )
    assert "rollback_acknowledgement" in _failed_codes(
        validate_adapter_activation_authorization_request(_request(rollback_acknowledged=False))
    )
    assert "fallback_acknowledgement" in _failed_codes(
        validate_adapter_activation_authorization_request(_request(fallback_acknowledged=False))
    )
