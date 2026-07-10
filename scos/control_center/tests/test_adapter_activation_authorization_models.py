"""Stage 8.5 explicit adapter activation authorization model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.adapter_activation_authorization_models import (
    ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
    AdapterActivationAuthorizationRequest,
    AdapterActivationAuthorizationResult,
    AdapterActivationScope,
    AuthorizationCheck,
    OperatorIdentity,
)

_NOW = "2026-07-10T08:00:00Z"
_EXPIRES = "2026-07-10T09:00:00Z"


def _operator() -> OperatorIdentity:
    return OperatorIdentity(
        operator_id="operator-charan",
        display_name="Charan",
        role="owner",
        authentication_evidence_ref="auth-evidence-001",
        human_confirmed=True,
    )


def _scope() -> AdapterActivationScope:
    return AdapterActivationScope(
        adapter_id="codex",
        adapter_kind="ai_agent_adapter",
        runtime_target="simulator",
        allowed_operations=("prepare_activation", "refresh_file_snapshot"),
        transport_mode="FILE_SNAPSHOT_REFRESH",
        credential_reference_ids=("cred-ref-b", "cred-ref-a"),
        expires_at=_EXPIRES,
    )


def _request() -> AdapterActivationAuthorizationRequest:
    return AdapterActivationAuthorizationRequest(
        request_id="auth-request-001",
        checked_at=_NOW,
        preflight_result={"result_id": "preflight-001", "adapter_id": "codex"},
        operator=_operator(),
        scope=_scope(),
        explicit_decision="APPROVE",
        decision_reason="approve exact Stage 8.5 authorization request",
        approval_evidence={
            "approval_decision": "APPROVE",
            "request_id": "auth-request-001",
            "adapter_id": "codex",
            "runtime_target": "simulator",
        },
        audit_readiness={"append_only_supported": True, "will_write_now": False},
        rollback_acknowledged=True,
        fallback_acknowledged=True,
    )


def test_models_are_frozen_and_serialized_deterministically() -> None:
    request = _request()

    assert request.schema_version == ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION
    assert request.scope.credential_reference_ids == ("cred-ref-a", "cred-ref-b")
    assert request.scope.allowed_operations == ("prepare_activation", "refresh_file_snapshot")
    assert request.to_dict() == request.to_dict()
    with pytest.raises(FrozenInstanceError):
        request.explicit_decision = "DENY"  # type: ignore[misc]


def test_nested_inputs_are_frozen_on_model_creation() -> None:
    evidence = {"binding": {"operations": ["prepare_activation"]}}
    request = AdapterActivationAuthorizationRequest(
        request_id="auth-request-001",
        checked_at=_NOW,
        preflight_result={"result_id": "preflight-001", "adapter_id": "codex"},
        operator=_operator(),
        scope=_scope(),
        explicit_decision="APPROVE",
        decision_reason="approve exact request",
        approval_evidence=evidence,
        audit_readiness={"append_only_supported": True, "will_write_now": False},
        rollback_acknowledged=True,
        fallback_acknowledged=True,
    )
    evidence["binding"]["operations"].append("mutated")

    assert request.approval_evidence.to_dict() == {"binding": {"operations": ["prepare_activation"]}}


def test_authorized_result_never_allows_runtime_activation() -> None:
    check = AuthorizationCheck("check-001", "operator_identity", True, "info", "ok", {"operator_id": "operator-charan"})
    result = AdapterActivationAuthorizationResult(
        schema_version=ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        authorization_id="authz-001",
        checked_at=_NOW,
        decision="AUTHORIZED_IN_PRINCIPLE",
        authorized_in_principle=True,
        can_activate_now=False,
        activation_executed=False,
        credentials_materialized=False,
        external_calls_made=False,
        runtime_mutated=False,
        checks=(check,),
        blockers=(),
        warnings=(),
        evidence={"request_id": "auth-request-001"},
    )

    assert result.to_dict()["decision"] == "AUTHORIZED_IN_PRINCIPLE"
    assert result.to_dict()["can_activate_now"] is False
    assert result.to_dict()["activation_executed"] is False
    assert result.to_dict()["credentials_materialized"] is False
    assert result.to_dict()["external_calls_made"] is False
    assert result.to_dict()["runtime_mutated"] is False


def test_result_invariants_reject_any_runtime_or_secret_materialization_claim() -> None:
    check = AuthorizationCheck("check-001", "operator_identity", True, "info", "ok", {})

    with pytest.raises(ValueError):
        AdapterActivationAuthorizationResult(
            schema_version=ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
            authorization_id="authz-001",
            checked_at=_NOW,
            decision="AUTHORIZED_IN_PRINCIPLE",
            authorized_in_principle=True,
            can_activate_now=True,
            activation_executed=False,
            credentials_materialized=False,
            external_calls_made=False,
            runtime_mutated=False,
            checks=(check,),
            blockers=(),
            warnings=(),
            evidence={},
        )
