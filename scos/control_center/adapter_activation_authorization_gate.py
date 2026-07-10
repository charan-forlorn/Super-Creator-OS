"""Stage 8.5 explicit operator adapter activation authorization gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .adapter_activation_authorization_models import (
        ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        AdapterActivationAuthorizationRequest,
        AdapterActivationAuthorizationResult,
        AuthorizationCheck,
    )
    from .adapter_activation_authorization_validation import (
        stable_adapter_activation_authorization_id,
        validate_adapter_activation_authorization_request,
        validate_authorization_report_output_path,
    )
    from .credential_policy_models import CredentialPolicy, create_default_credential_policy
    from .credential_policy_validation import validate_no_secret_leak
except ImportError:  # direct-module execution
    from adapter_activation_authorization_models import (
        ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        AdapterActivationAuthorizationRequest,
        AdapterActivationAuthorizationResult,
        AuthorizationCheck,
    )
    from adapter_activation_authorization_validation import (
        stable_adapter_activation_authorization_id,
        validate_adapter_activation_authorization_request,
        validate_authorization_report_output_path,
    )
    from credential_policy_models import CredentialPolicy, create_default_credential_policy
    from credential_policy_validation import validate_no_secret_leak

_REQUIRED_STAGE84_CHECK_CATEGORIES = (
    "audit_readiness",
    "credential_policy",
    "file_snapshot_boundary",
    "generic_preflight",
    "manual_fallback",
    "operator_approval",
    "rollback",
    "secret_leak_validation",
    "simulator_fallback",
    "transport_decision",
)


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _stable_json(payload: object, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent, separators=None if indent else (",", ":"))


def _normalize_for_leak_scan(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            f"field_{index}": _normalize_for_leak_scan(value[key])
            for index, key in enumerate(sorted(value, key=lambda item: str(item)))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_leak_scan(item) for item in value]
    return value


def _check(code: str, passed: bool, severity: str, message: str, evidence: dict[str, Any] | None = None) -> AuthorizationCheck:
    return AuthorizationCheck(
        check_id=stable_adapter_activation_authorization_id("aac-", code, passed, severity, message, evidence or {}),
        code=code,
        passed=passed,
        severity=severity,
        message=message,
        evidence=evidence or {},
    )


def _preflight_category_statuses(preflight: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for item in preflight.get("checks", ()):
        if isinstance(item, dict):
            statuses[str(item.get("category", ""))] = str(item.get("status", ""))
    return statuses


def _preflight_checks(request: AdapterActivationAuthorizationRequest, *, policy: CredentialPolicy, checked_at: str) -> tuple[AuthorizationCheck, ...]:
    preflight = request.preflight_result.to_dict()
    checks: list[AuthorizationCheck] = []
    state_ok = (
        preflight.get("adapter_id") == request.scope.adapter_id
        and preflight.get("verdict") == "READY_FOR_OPERATOR_DECISION"
        and preflight.get("accepted") is True
        and preflight.get("ready_for_operator_decision") is True
        and preflight.get("can_activate_now") is False
        and preflight.get("activation_authorized") is False
        and preflight.get("real_dispatch_blocked") is True
        and preflight.get("external_calls_blocked") is True
        and preflight.get("credentials_materialized") is False
        and preflight.get("runtime_mutated") is False
        and not preflight.get("blockers", ())
        and bool(preflight.get("evidence_digest"))
    )
    checks.append(
        _check(
            "stage84_preflight_state",
            state_ok,
            "critical",
            "Stage 8.4 preflight is ready for operator decision and still forbids activation"
            if state_ok
            else "Stage 8.4 preflight is missing, failed, mismatched, or claims runtime authorization",
            {
                "adapter_id": preflight.get("adapter_id"),
                "verdict": preflight.get("verdict"),
                "accepted": preflight.get("accepted"),
                "ready_for_operator_decision": preflight.get("ready_for_operator_decision"),
                "activation_authorized": preflight.get("activation_authorized"),
            },
        )
    )

    statuses = _preflight_category_statuses(preflight)
    missing_or_failed = tuple(
        category for category in _REQUIRED_STAGE84_CHECK_CATEGORIES if statuses.get(category) != "pass"
    )
    checks.append(
        _check(
            "stage84_required_evidence",
            not missing_or_failed,
            "critical",
            "Stage 8.4 required transport, credential, audit, rollback, and fallback checks remain passing"
            if not missing_or_failed
            else "Stage 8.4 required checks are missing or not passing",
            {"missing_or_failed_categories": missing_or_failed},
        )
    )

    approval = request.approval_evidence.to_dict()
    result_binding_ok = approval.get("preflight_result_id") == preflight.get("result_id")
    runtime_binding_ok = (
        approval.get("runtime_target") == request.scope.runtime_target
        and approval.get("preflight_runtime_target") == request.scope.runtime_target
    )
    checks.append(
        _check(
            "preflight_binding",
            result_binding_ok and runtime_binding_ok,
            "critical",
            "authorization is bound to the exact Stage 8.4 result and runtime target"
            if result_binding_ok and runtime_binding_ok
            else "authorization must bind to the exact Stage 8.4 result and runtime target",
            {
                "preflight_result_id": preflight.get("result_id"),
                "approval_preflight_result_id": approval.get("preflight_result_id"),
                "approval_preflight_runtime_target": approval.get("preflight_runtime_target"),
                "runtime_target": request.scope.runtime_target,
            },
        )
    )

    leak = validate_no_secret_leak(
        _normalize_for_leak_scan(preflight),
        policy=policy,
        checked_at=str(checked_at) if str(checked_at).strip() else "invalid",
        surface_type="CERTIFICATION_EVIDENCE",
    )
    checks.append(
        _check(
            "preflight_secret_safety",
            leak.accepted,
            "critical",
            "Stage 8.4 preflight result contains no secret material"
            if leak.accepted
            else "; ".join(tuple(leak.blockers) + tuple(violation.message for violation in leak.violations)),
            {"blockers": leak.blockers},
        )
    )
    return tuple(checks)


def _decision(request: AdapterActivationAuthorizationRequest, checks: tuple[AuthorizationCheck, ...]) -> str:
    if request.explicit_decision == "DENY":
        return "DENIED"
    timestamp_failed = any(check.code == "timestamp_binding" and not check.passed for check in checks)
    if timestamp_failed:
        return "EXPIRED"
    if any(not check.passed and check.severity in {"critical", "error"} for check in checks):
        return "BLOCKED"
    return "AUTHORIZED_IN_PRINCIPLE"


def _result_from_checks(request: AdapterActivationAuthorizationRequest, checks: tuple[AuthorizationCheck, ...], *, checked_at: str) -> AdapterActivationAuthorizationResult:
    decision = _decision(request, checks)
    blockers = tuple(check.message for check in checks if not check.passed and check.severity in {"critical", "error"})
    warnings = tuple(check.message for check in checks if not check.passed and check.severity == "warning")
    evidence = {
        "request_id": request.request_id,
        "operator_id": request.operator.operator_id,
        "adapter_id": request.scope.adapter_id,
        "runtime_target": request.scope.runtime_target,
        "allowed_operations": list(request.scope.allowed_operations),
        "credential_reference_ids": list(request.scope.credential_reference_ids),
        "transport_mode": request.scope.transport_mode,
        "preflight_result_id": request.preflight_result.to_dict().get("result_id"),
        "preflight_checked_at": request.preflight_result.to_dict().get("checked_at"),
        "decision_reason": request.decision_reason,
        "pass_meaning": "AUTHORIZED_IN_PRINCIPLE_ONLY",
    }
    return AdapterActivationAuthorizationResult(
        schema_version=ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        authorization_id=stable_adapter_activation_authorization_id("aar-", checked_at, request.request_id, decision, evidence, [check.to_dict() for check in checks]),
        checked_at=str(checked_at),
        decision=decision,
        authorized_in_principle=decision == "AUTHORIZED_IN_PRINCIPLE",
        can_activate_now=False,
        activation_executed=False,
        credentials_materialized=False,
        external_calls_made=False,
        runtime_mutated=False,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        evidence=evidence,
    )


def evaluate_adapter_activation_authorization(
    request,
    *,
    checked_at: str,
    credential_policy: CredentialPolicy | None = None,
) -> AdapterActivationAuthorizationResult:
    policy = credential_policy or create_default_credential_policy()
    request_obj = request if isinstance(request, AdapterActivationAuthorizationRequest) else AdapterActivationAuthorizationRequest(**request)
    checks = list(validate_adapter_activation_authorization_request(request_obj, checked_at=checked_at, policy=policy))
    checks.extend(_preflight_checks(request_obj, policy=policy, checked_at=checked_at))
    return _result_from_checks(request_obj, tuple(checks), checked_at=str(checked_at))


def build_stage85_authorization_evidence(
    *,
    request,
    checked_at: str,
    credential_policy: CredentialPolicy | None = None,
) -> AdapterActivationAuthorizationResult:
    return evaluate_adapter_activation_authorization(request, checked_at=checked_at, credential_policy=credential_policy)


def write_adapter_activation_authorization_report(result, *, repo_root, output_path):
    resolved, errors = validate_authorization_report_output_path(repo_root=repo_root, output_path=output_path)
    if errors:
        return {"accepted": False, "output_path": None, "blockers": errors, "warnings": ()}
    if resolved is None:
        return {"accepted": True, "output_path": None, "blockers": (), "warnings": ("output_path not supplied; no report written",)}
    document = _plain(result)
    leak = validate_no_secret_leak(
        _normalize_for_leak_scan(document),
        checked_at=str(document.get("checked_at", "")),
        surface_type="CERTIFICATION_EVIDENCE",
    )
    if not leak.accepted:
        return {"accepted": False, "output_path": None, "blockers": leak.blockers, "warnings": ()}
    text = _stable_json(document, indent=2) + "\n"
    if resolved.exists() and resolved.read_text(encoding="utf-8") != text:
        return {"accepted": False, "output_path": None, "blockers": ("output_path already exists with different content",), "warnings": ()}
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8", newline="\n")
    return {"accepted": True, "output_path": str(Path(resolved)), "blockers": (), "warnings": ()}


__all__ = sorted(
    (
        "build_stage85_authorization_evidence",
        "evaluate_adapter_activation_authorization",
        "write_adapter_activation_authorization_report",
    )
)
