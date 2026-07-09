"""Stage 8.3 credential policy validation functions."""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .credential_policy_models import (
        CredentialPolicy,
        CredentialPolicyViolation,
        FrozenPolicyMap,
        PolicyValidationResult,
        create_default_credential_policy,
    )
    from .credential_redaction import classify_secret_field_name, classify_secret_value
except ImportError:  # direct-module execution
    from credential_policy_models import (
        CredentialPolicy,
        CredentialPolicyViolation,
        FrozenPolicyMap,
        PolicyValidationResult,
        create_default_credential_policy,
    )
    from credential_redaction import classify_secret_field_name, classify_secret_value


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _redacted_sample(value: object) -> str:
    text = str(value)
    if len(text) <= 4:
        return "***"
    return text[:2] + "***" + text[-2:]


def _surface_value(surface: str) -> str:
    text = str(surface).strip().upper() or "UNKNOWN"
    return text if text in ("LOG", "EVENT", "SNAPSHOT", "APPROVAL_EVIDENCE", "CERTIFICATION_EVIDENCE") else "UNKNOWN"


def _checked_at_errors(checked_at: str) -> tuple[str, ...]:
    if not str(checked_at).strip():
        return ("checked_at must be caller-supplied and non-empty",)
    return ()


_POLICY_CONTROL_FIELDS = {
    "credential_reference",
    "credential_scope",
    "credential_type",
    "credential_use_requested",
}


def _violation(*, surface: str, path: str, category: str, message: str, evidence: object) -> CredentialPolicyViolation:
    return CredentialPolicyViolation(
        violation_id=_stable_id("cpv-", surface, path, category, message),
        surface=surface,
        path=path,
        category=category,
        severity="SECRET",
        message=message,
        evidence=_redacted_sample(evidence),
    )


def _scan_surface(
    value: Any,
    *,
    path: str,
    surface: str,
    policy: CredentialPolicy,
    violations: list[CredentialPolicyViolation],
) -> None:
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            field_category = (
                None
                if key_text.strip().lower() in _POLICY_CONTROL_FIELDS
                else classify_secret_field_name(key_text, policy=policy)
            )
            child_value = value[key]
            if field_category is not None and child_value != policy.redaction_marker:
                violations.append(
                    _violation(
                        surface=surface,
                        path=child_path,
                        category=field_category,
                        message="secret-like field must contain only the redaction marker",
                        evidence=child_value,
                    )
                )
            _scan_surface(child_value, path=child_path, surface=surface, policy=policy, violations=violations)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_surface(item, path=f"{path}[{index}]", surface=surface, policy=policy, violations=violations)
        return
    value_category = classify_secret_value(value)
    if value_category is not None and value != policy.redaction_marker:
        violations.append(
            _violation(
                surface=surface,
                path=path or "$",
                category=value_category,
                message="secret-like value is not redacted",
                evidence=value,
            )
        )


def _result(
    *,
    accepted: bool,
    checked_at: str,
    policy: CredentialPolicy,
    surface: str,
    approval_boundary_status: str,
    violations: tuple[CredentialPolicyViolation, ...],
    warnings: tuple[str, ...],
    blockers: tuple[str, ...],
    metadata: dict[str, Any] | None = None,
) -> PolicyValidationResult:
    all_blockers = tuple(sorted(set(blockers + tuple(violation.message for violation in violations))))
    return PolicyValidationResult(
        accepted=accepted and not all_blockers,
        go_no_go="GO" if accepted and not all_blockers else "NO_GO",
        readiness_score=100 if accepted and not all_blockers else max(70, 95 - len(all_blockers) * 5),
        checked_at=str(checked_at),
        policy_id=policy.policy_id,
        surface=surface,
        approval_boundary_status=approval_boundary_status,
        violations=violations,
        warnings=warnings,
        blockers=all_blockers,
        metadata=FrozenPolicyMap.from_mapping(metadata or {}),
    )


def validate_no_secret_leak(
    surface,
    *,
    policy: CredentialPolicy | None = None,
    checked_at: str,
    surface_type: str = "UNKNOWN",
) -> PolicyValidationResult:
    active_policy = policy or create_default_credential_policy()
    surface_name = _surface_value(surface_type)
    input_blockers = _checked_at_errors(checked_at)
    violations: list[CredentialPolicyViolation] = []
    if not input_blockers:
        _scan_surface(surface, path="$", surface=surface_name, policy=active_policy, violations=violations)
    return _result(
        accepted=not input_blockers and not violations,
        checked_at=str(checked_at),
        policy=active_policy,
        surface=surface_name,
        approval_boundary_status="NOT_REQUESTED",
        violations=tuple(violations),
        warnings=(),
        blockers=input_blockers,
        metadata={"validation": "no_secret_leak"},
    )


def validate_operator_approval_boundary(
    record,
    *,
    policy: CredentialPolicy | None = None,
    checked_at: str,
) -> PolicyValidationResult:
    active_policy = policy or create_default_credential_policy()
    input_blockers = list(_checked_at_errors(checked_at))
    leak_result = validate_no_secret_leak(
        record,
        policy=active_policy,
        checked_at=checked_at if str(checked_at).strip() else "invalid",
        surface_type="APPROVAL_EVIDENCE",
    )
    record_dict = record if isinstance(record, dict) else {}
    credential_requested = bool(record_dict.get("credential_use_requested", False))
    decision = str(record_dict.get("approval_decision", "")).strip().lower()
    scope = str(record_dict.get("approval_scope", "")).strip().lower()
    later_stage = bool(record_dict.get("later_stage_authorized", False))
    approval_status = "NOT_REQUESTED"
    if credential_requested:
        approval_status = "AMBIGUOUS"
        if decision != "approved":
            approval_status = "DENIED" if decision == "denied" else "PENDING"
            input_blockers.append("credential use requires an explicit later-stage approval decision")
        if scope in ("blanket", "default", "global", "all"):
            approval_status = "BLANKET_APPROVAL_REJECTED"
            input_blockers.append("blanket or default credential approval is forbidden")
        if not later_stage:
            input_blockers.append("credential use is forbidden until a later stage explicitly authorizes it")
        if decision == "approved" and scope == "single_dispatch" and later_stage:
            approval_status = "APPROVED_EXPLICIT_LATER_STAGE"
    warnings = ()
    if not credential_requested and decision:
        warnings = ("approval decision present without credential use request",)
    return _result(
        accepted=not input_blockers and leak_result.accepted,
        checked_at=str(checked_at),
        policy=active_policy,
        surface="APPROVAL_EVIDENCE",
        approval_boundary_status=approval_status,
        violations=tuple(leak_result.violations),
        warnings=warnings,
        blockers=tuple(input_blockers + list(leak_result.blockers)),
        metadata={"validation": "operator_approval_boundary"},
    )


def build_stage83_credential_policy_evidence(
    *,
    checked_at: str,
    metadata=None,
) -> PolicyValidationResult:
    policy = create_default_credential_policy(metadata=dict(metadata or {"stage": "8.3"}))
    input_blockers = _checked_at_errors(checked_at)
    evidence_metadata = {
        "policy_schema_version": policy.schema_version,
        "local_only": True,
        "fake_data_only": True,
        "secret_storage_implemented": False,
        "api_key_flow_implemented": False,
        "external_calls_implemented": False,
        "adapter_activation_implemented": False,
        "redaction_marker": policy.redaction_marker,
        "forbidden_output_surfaces": list(policy.forbidden_output_surfaces),
    }
    if metadata:
        evidence_metadata["metadata"] = dict(metadata)
    return _result(
        accepted=not input_blockers,
        checked_at=str(checked_at),
        policy=policy,
        surface="CERTIFICATION_EVIDENCE",
        approval_boundary_status="NOT_REQUESTED",
        violations=(),
        warnings=(),
        blockers=input_blockers,
        metadata=evidence_metadata,
    )


__all__ = sorted(
    (
        "build_stage83_credential_policy_evidence",
        "validate_no_secret_leak",
        "validate_operator_approval_boundary",
    )
)
