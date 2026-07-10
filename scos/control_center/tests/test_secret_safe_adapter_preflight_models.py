"""Stage 8.4 secret-safe adapter preflight model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.secret_safe_adapter_preflight_models import (
    SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
    FrozenEvidenceMap,
    PreflightCheck,
    SafeCredentialReference,
    SecretSafeAdapterPreflightRequest,
    SecretSafeAdapterPreflightResult,
)

_NOW = "2026-07-10T08:00:00Z"


def _empty_request() -> SecretSafeAdapterPreflightRequest:
    empty = FrozenEvidenceMap.from_mapping({})
    return SecretSafeAdapterPreflightRequest(
        schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        request_id="req",
        adapter_id="codex",
        adapter_runtime="simulator",
        activation_mode="preflight_only",
        requested_transport="FILE_SNAPSHOT_REFRESH",
        checked_at=_NOW,
        generic_preflight_evidence=empty,
        transport_decision_evidence=empty,
        file_snapshot_boundary_evidence=empty,
        credential_policy_evidence=empty,
        operator_approval_evidence=empty,
        audit_readiness_evidence=empty,
        rollback_evidence=empty,
        simulator_fallback_evidence=empty,
        manual_fallback_evidence=empty,
        safe_credential_references=(
            SafeCredentialReference("ref-b", "TOKEN", "SECRET", "policy_reference", "policy_only", "redacted", False),
            SafeCredentialReference("ref-a", "API_KEY", "SECRET", "policy_reference", "policy_only", "redacted", False),
        ),
        metadata=FrozenEvidenceMap.from_mapping({"nested": {"items": ["b", "a"]}}),
    )


def test_request_model_is_frozen_and_stably_serialized() -> None:
    request = _empty_request()

    assert request.schema_version == SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION
    assert [item["reference_id"] for item in request.to_dict()["safe_credential_references"]] == ["ref-a", "ref-b"]
    assert request.to_dict() == request.to_dict()
    with pytest.raises(FrozenInstanceError):
        request.adapter_id = "chatgpt"  # type: ignore[misc]


def test_nested_mapping_is_frozen_on_input() -> None:
    metadata = {"nested": {"items": ["a"]}}
    frozen = FrozenEvidenceMap.from_mapping(metadata)
    metadata["nested"]["items"].append("b")

    assert frozen.to_dict() == {"nested": {"items": ["a"]}}


def test_result_invariants_prevent_activation_or_dispatch() -> None:
    check = PreflightCheck("c", "semantic", "pass", "info", "ok", (), None, None)
    with pytest.raises(ValueError):
        SecretSafeAdapterPreflightResult(
            schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
            result_id="res",
            checked_at=_NOW,
            adapter_id="codex",
            verdict="READY_FOR_OPERATOR_DECISION",
            readiness_score=100,
            accepted=True,
            ready_for_operator_decision=True,
            can_activate_now=True,
            activation_authorized=False,
            real_dispatch_blocked=True,
            external_calls_blocked=True,
            credentials_materialized=False,
            runtime_mutated=False,
            checks=(check,),
            blockers=(),
            warnings=(),
            required_next_action="present_to_operator",
            evidence_digest="digest",
            report_path=None,
            metadata=FrozenEvidenceMap.from_mapping({}),
        )


def test_result_acceptance_requires_ready_verdict() -> None:
    check = PreflightCheck("c", "semantic", "pass", "info", "ok", (), None, None)
    with pytest.raises(ValueError):
        SecretSafeAdapterPreflightResult(
            schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
            result_id="res",
            checked_at=_NOW,
            adapter_id="codex",
            verdict="NO_GO",
            readiness_score=90,
            accepted=True,
            ready_for_operator_decision=False,
            can_activate_now=False,
            activation_authorized=False,
            real_dispatch_blocked=True,
            external_calls_blocked=True,
            credentials_materialized=False,
            runtime_mutated=False,
            checks=(check,),
            blockers=("x",),
            warnings=(),
            required_next_action="repair",
            evidence_digest="digest",
            report_path=None,
            metadata=FrozenEvidenceMap.from_mapping({}),
        )
