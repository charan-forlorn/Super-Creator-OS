"""Stage 8.5 request validation for explicit adapter activation authorization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .adapter_activation_authorization_models import (
        ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        AdapterActivationAuthorizationRequest,
        AdapterActivationScope,
        AuthorizationCheck,
        OperatorIdentity,
    )
    from .credential_policy_models import CredentialPolicy, create_default_credential_policy
    from .credential_policy_validation import validate_no_secret_leak
    from .secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ADAPTER_IDS,
        SECRET_SAFE_ADAPTER_RUNTIMES,
        SECRET_SAFE_TRANSPORTS,
    )
except ImportError:  # direct-module execution
    from adapter_activation_authorization_models import (
        ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION,
        AdapterActivationAuthorizationRequest,
        AdapterActivationScope,
        AuthorizationCheck,
        OperatorIdentity,
    )
    from credential_policy_models import CredentialPolicy, create_default_credential_policy
    from credential_policy_validation import validate_no_secret_leak
    from secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ADAPTER_IDS,
        SECRET_SAFE_ADAPTER_RUNTIMES,
        SECRET_SAFE_TRANSPORTS,
    )

_URL_MARKERS = ("://", "http:", "https:", "ws:", "wss:", "ftp:", "file:")
_WILDCARDS = {"*", "all", "any", "global", "default", "blanket"}
_AI_OPERATOR_MARKERS = ("ai", "agent", "bot", "automation", "model", "assistant")
_FORBIDDEN_OPERATION_MARKERS = (
    "activate_all",
    "auto_activate",
    "external_call",
    "materialize_credentials",
    "real_dispatch",
)
_FORBIDDEN_MATERIAL_FIELDS = (
    "api_key",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "password",
    "private_key",
    "secret",
    "session_cookie",
    "token",
    "value",
)


def _stable_json(payload: object, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent, separators=None if indent else (",", ":"))


def stable_adapter_activation_authorization_id(prefix: str, *parts: Any) -> str:
    return prefix + hashlib.sha256("|".join(_stable_json(_plain(part)) for part in parts).encode("utf-8")).hexdigest()[:16]


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _normalize_for_leak_scan(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            f"field_{index}": _normalize_for_leak_scan(value[key])
            for index, key in enumerate(sorted(value, key=lambda item: str(item)))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_leak_scan(item) for item in value]
    return value


def _contains_url(value: Any) -> bool:
    text = str(value).lower()
    return any(marker in text for marker in _URL_MARKERS)


def _text(value: Any) -> str:
    return str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _check(code: str, passed: bool, severity: str, message: str, evidence: dict[str, Any] | None = None) -> AuthorizationCheck:
    return AuthorizationCheck(
        check_id=stable_adapter_activation_authorization_id("aac-", code, passed, severity, message, evidence or {}),
        code=code,
        passed=passed,
        severity=severity,
        message=message,
        evidence=evidence or {},
    )


def _material_findings(value: Any, *, path: str = "$") -> tuple[str, ...]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            key_text = str(key)
            normalized = key_text.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized in _FORBIDDEN_MATERIAL_FIELDS or any(field in normalized for field in _FORBIDDEN_MATERIAL_FIELDS):
                findings.append(f"{path}.{key_text} contains forbidden credential material field")
            findings.extend(_material_findings(value[key], path=f"{path}.{key_text}"))
        return tuple(findings)
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(_material_findings(item, path=f"{path}[{index}]"))
        return tuple(findings)
    text = str(value)
    lowered = text.lower()
    if _contains_url(text):
        findings.append(f"{path} contains URL or remote marker")
    if "bearer " in lowered or "sk-" in lowered or "-----begin" in lowered:
        findings.append(f"{path} contains secret-like scalar material")
    return tuple(findings)


def _secret_safety_check(code: str, value: Any, *, checked_at: str, policy: CredentialPolicy | None = None) -> AuthorizationCheck:
    active_policy = policy or create_default_credential_policy()
    material_findings = _material_findings(_plain(value))
    leak = validate_no_secret_leak(
        _normalize_for_leak_scan(_plain(value)),
        policy=active_policy,
        checked_at=str(checked_at) if str(checked_at).strip() else "invalid",
        surface_type="APPROVAL_EVIDENCE",
    )
    blockers = tuple(sorted(material_findings + leak.blockers + tuple(violation.message for violation in leak.violations)))
    return _check(
        code,
        not blockers,
        "critical",
        "authorization evidence contains no credential material" if not blockers else "; ".join(blockers),
        {"blockers": blockers},
    )


def validate_operator_identity(operator: OperatorIdentity) -> tuple[AuthorizationCheck, ...]:
    plain = _plain(operator)
    text = " ".join(str(plain.get(key, "")) for key in ("operator_id", "display_name", "role")).lower()
    blockers: list[str] = []
    if not _text(plain.get("operator_id")) or not _text(plain.get("display_name")):
        blockers.append("operator identity must be specific and named")
    if not _text(plain.get("role")) or not _text(plain.get("authentication_evidence_ref")):
        blockers.append("operator role and authentication evidence reference are required")
    if plain.get("human_confirmed") is not True:
        blockers.append("operator must be human-confirmed")
    if any(marker in text.split() for marker in _AI_OPERATOR_MARKERS) or "ai_agent" in text:
        blockers.append("AI-agent or automated approval attempts are rejected")
    return (
        _check(
            "operator_identity",
            not blockers,
            "critical",
            "operator identity is named, authenticated, and human-confirmed" if not blockers else "; ".join(blockers),
            plain,
        ),
    )


def validate_activation_scope(scope: AdapterActivationScope, *, checked_at: str = "stage8.5-validation") -> tuple[AuthorizationCheck, ...]:
    plain = _plain(scope)
    blockers: list[str] = []
    adapter_id = _lower(plain.get("adapter_id"))
    runtime_target = _lower(plain.get("runtime_target"))
    operations = _strings(plain.get("allowed_operations"))
    transport_mode = _text(plain.get("transport_mode"))
    if adapter_id in _WILDCARDS or adapter_id not in SECRET_SAFE_ADAPTER_IDS:
        blockers.append("adapter_id must identify one supported adapter")
    if runtime_target in _WILDCARDS or runtime_target not in SECRET_SAFE_ADAPTER_RUNTIMES:
        blockers.append("runtime_target must identify one supported runtime")
    if not operations:
        blockers.append("allowed_operations must be explicit and non-empty")
    for operation in operations:
        operation_text = _lower(operation)
        if operation_text in _WILDCARDS or any(marker in operation_text for marker in _FORBIDDEN_OPERATION_MARKERS):
            blockers.append("allowed_operations must not exceed Stage 8.5 authorization scope")
    if transport_mode not in SECRET_SAFE_TRANSPORTS:
        blockers.append("transport_mode must remain within Stage 8.4 allowed transport modes")
    if not _text(plain.get("expires_at")):
        blockers.append("expires_at must be caller-supplied")
    scope_check = _check(
        "activation_scope",
        not blockers,
        "critical",
        "authorization scope is exact, explicit, runtime-bound, and time-bound" if not blockers else "; ".join(blockers),
        plain,
    )
    refs_check = _secret_safety_check("credential_references", plain.get("credential_reference_ids", ()), checked_at=checked_at)
    return (scope_check, refs_check)


def _request_from(value: Any) -> AdapterActivationAuthorizationRequest | None:
    if isinstance(value, AdapterActivationAuthorizationRequest):
        return value
    if not isinstance(value, dict):
        return None
    try:
        return AdapterActivationAuthorizationRequest(**value)
    except (TypeError, ValueError):
        return None


def _approval_binding_checks(request: AdapterActivationAuthorizationRequest) -> tuple[AuthorizationCheck, ...]:
    approval = request.approval_evidence.to_dict()
    scope = request.scope
    operator = request.operator
    blockers: list[str] = []
    expected_values = {
        "approval_decision": request.explicit_decision,
        "request_id": request.request_id,
        "adapter_id": scope.adapter_id,
        "runtime_target": scope.runtime_target,
        "operator_id": operator.operator_id,
        "authentication_evidence_ref": operator.authentication_evidence_ref,
        "transport_mode": scope.transport_mode,
        "expires_at": scope.expires_at,
    }
    for key, expected in expected_values.items():
        if approval.get(key) != expected:
            blockers.append(f"approval_evidence.{key} must match the authorization request")
    if _strings(approval.get("approved_operations")) != scope.allowed_operations:
        blockers.append("approval evidence operations must exactly match scope")
    if _strings(approval.get("credential_reference_ids")) != scope.credential_reference_ids:
        blockers.append("approval evidence credential references must exactly match scope")
    for flag in ("blanket_approval", "reusable", "ai_generated_approval"):
        if approval.get(flag) is not False:
            blockers.append(f"approval_evidence.{flag} must be false")
    return (
        _check(
            "approval_binding",
            not blockers,
            "critical",
            "approval evidence is exact, non-blanket, request-bound, adapter-bound, runtime-bound, and scope-bound"
            if not blockers
            else "; ".join(blockers),
            approval,
        ),
    )


def _timestamp_checks(request: AdapterActivationAuthorizationRequest, *, checked_at: str) -> tuple[AuthorizationCheck, ...]:
    approval = request.approval_evidence.to_dict()
    blockers: list[str] = []
    expired = False
    if request.checked_at != str(checked_at):
        blockers.append("request.checked_at must match caller checked_at")
    if approval.get("approved_at") != request.checked_at:
        expired = True
        blockers.append("approval evidence is stale or not current for checked_at")
    if request.scope.expires_at <= request.checked_at:
        expired = True
        blockers.append("authorization scope expired before or at checked_at")
    if approval.get("preflight_checked_at") != request.preflight_result.to_dict().get("checked_at"):
        expired = True
        blockers.append("preflight timestamp binding is stale or mismatched")
    return (
        _check(
            "timestamp_binding",
            not blockers,
            "critical",
            "authorization timestamps are current, coherent, and not expired" if not blockers else "; ".join(blockers),
            {"expired": expired, "checked_at": checked_at, "expires_at": request.scope.expires_at},
        ),
    )


def _audit_ack_checks(request: AdapterActivationAuthorizationRequest) -> tuple[AuthorizationCheck, ...]:
    audit = request.audit_readiness.to_dict()
    audit_ok = (
        audit.get("append_only_supported") is True
        and audit.get("will_write_now") is False
        and audit.get("audit_store_mutated") is not True
    )
    return (
        _check(
            "audit_readiness",
            audit_ok,
            "critical",
            "audit readiness is append-only capable and claims no write occurred now"
            if audit_ok
            else "audit readiness must be append-only and must not write during Stage 8.5",
            audit,
        ),
        _check(
            "rollback_acknowledgement",
            request.rollback_acknowledged is True,
            "critical",
            "rollback was acknowledged" if request.rollback_acknowledged else "rollback acknowledgement is required",
            {"rollback_acknowledged": request.rollback_acknowledged},
        ),
        _check(
            "fallback_acknowledgement",
            request.fallback_acknowledged is True,
            "critical",
            "fallback was acknowledged" if request.fallback_acknowledged else "fallback acknowledgement is required",
            {"fallback_acknowledged": request.fallback_acknowledged},
        ),
    )


def validate_adapter_activation_authorization_request(
    request,
    *,
    checked_at: str | None = None,
    policy: CredentialPolicy | None = None,
) -> tuple[AuthorizationCheck, ...]:
    request_obj = _request_from(request)
    if request_obj is None:
        return (_check("request_shape", False, "critical", "authorization request is malformed", {}),)
    active_checked_at = str(checked_at) if checked_at is not None else request_obj.checked_at
    checks: list[AuthorizationCheck] = []
    checks.append(
        _check(
            "request_shape",
            request_obj.schema_version == ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION
            and bool(request_obj.request_id.strip())
            and bool(request_obj.checked_at.strip()),
            "critical",
            "authorization request shape is supported"
            if request_obj.schema_version == ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION
            and bool(request_obj.request_id.strip())
            and bool(request_obj.checked_at.strip())
            else "authorization request requires supported schema_version, request_id, and checked_at",
            {"schema_version": request_obj.schema_version, "request_id": request_obj.request_id, "checked_at": request_obj.checked_at},
        )
    )
    checks.extend(validate_operator_identity(request_obj.operator))
    checks.extend(validate_activation_scope(request_obj.scope, checked_at=active_checked_at))
    checks.extend(_approval_binding_checks(request_obj))
    checks.extend(_timestamp_checks(request_obj, checked_at=active_checked_at))
    checks.append(_secret_safety_check("approval_evidence_secret_safety", request_obj.approval_evidence, checked_at=active_checked_at, policy=policy))
    checks.extend(_audit_ack_checks(request_obj))
    return tuple(checks)


def validate_authorization_report_output_path(*, repo_root, output_path) -> tuple[Path | None, tuple[str, ...]]:
    if output_path is None:
        return None, ()
    errors: list[str] = []
    root = Path(repo_root).resolve()
    path_text = str(output_path)
    path = Path(output_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if _contains_url(path_text):
        errors.append("output_path must not contain URL or remote markers")
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append("output_path must resolve inside repo_root")
    return (None if errors else resolved), tuple(sorted(errors))


__all__ = sorted(
    (
        "stable_adapter_activation_authorization_id",
        "validate_activation_scope",
        "validate_adapter_activation_authorization_request",
        "validate_authorization_report_output_path",
        "validate_operator_identity",
    )
)
