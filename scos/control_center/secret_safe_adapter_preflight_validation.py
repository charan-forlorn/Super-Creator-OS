"""Stage 8.4 request and evidence validation for secret-safe adapter preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .credential_policy_models import CredentialPolicy, create_default_credential_policy
    from .credential_policy_validation import validate_no_secret_leak
    from .secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ACTIVATION_MODES,
        SECRET_SAFE_ADAPTER_IDS,
        SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        SECRET_SAFE_ADAPTER_RUNTIMES,
        SECRET_SAFE_REJECTED_ACTIVATION_MODES,
        SECRET_SAFE_REJECTED_TRANSPORTS,
        SECRET_SAFE_TRANSPORTS,
        FrozenEvidenceMap,
        PreflightValidationResult,
        SafeCredentialReference,
        SecretSafeAdapterPreflightRequest,
    )
except ImportError:  # direct-module execution
    from credential_policy_models import CredentialPolicy, create_default_credential_policy
    from credential_policy_validation import validate_no_secret_leak
    from secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ACTIVATION_MODES,
        SECRET_SAFE_ADAPTER_IDS,
        SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        SECRET_SAFE_ADAPTER_RUNTIMES,
        SECRET_SAFE_REJECTED_ACTIVATION_MODES,
        SECRET_SAFE_REJECTED_TRANSPORTS,
        SECRET_SAFE_TRANSPORTS,
        FrozenEvidenceMap,
        PreflightValidationResult,
        SafeCredentialReference,
        SecretSafeAdapterPreflightRequest,
    )

_URL_MARKERS = ("://", "http:", "https:", "ws:", "wss:", "ftp:", "file:")
_FORBIDDEN_INTENT_MARKERS = (
    "activate now",
    "auto activate",
    "auto dispatch",
    "real dispatch",
    "use api key now",
    "connect externally",
    "send request",
    "open network connection",
    "start server",
    "start polling",
    "start watcher",
    "start background worker",
    "bypass operator approval",
    "blanket approval",
    "persist credential material",
    "credentials into snapshots",
    "log credential values",
)
_SAFE_NEGATION_MARKERS = (
    "before any future",
    "blocked",
    "must not",
    "no ",
    "not ",
    "without",
    "forbidden",
    "inactive",
    "disabled",
)
_FORBIDDEN_MATERIAL_FIELDS = {
    "value",
    "secret",
    "token",
    "password",
    "api_key",
    "authorization",
    "cookie",
    "bearer",
    "credential_material",
}
_RUNTIME_BY_ADAPTER = {
    "chatgpt": ("manual", "simulator"),
    "claude_code": ("manual", "simulator"),
    "codex": ("manual", "simulator"),
    "hermes": ("manual", "simulator"),
}


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_secret_safe_preflight_id(prefix: str, *parts: Any) -> str:
    return prefix + hashlib.sha256("|".join(_stable_json(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def _to_plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {str(key): _to_plain(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


def _normalize_for_stage83(value: Any) -> Any:
    if isinstance(value, dict):
        return {f"field_{index}": _normalize_for_stage83(value[key]) for index, key in enumerate(sorted(value, key=lambda item: str(item)))}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_stage83(item) for item in value]
    return value


def _contains_url(value: Any) -> bool:
    text = str(value).lower()
    return any(marker in text for marker in _URL_MARKERS)


def _scan_nested(value: Any, *, path: str = "$") -> tuple[str, ...]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item)):
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            normalized_key = key_text.strip().lower().replace("-", "_")
            if normalized_key in _FORBIDDEN_MATERIAL_FIELDS:
                findings.append(f"{child_path} contains forbidden credential material field")
            findings.extend(_scan_nested(value[key], path=child_path))
        return tuple(findings)
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            findings.extend(_scan_nested(item, path=f"{path}[{index}]"))
        return tuple(findings)
    text = str(value)
    lowered = text.lower()
    if _contains_url(text):
        findings.append(f"{path} contains URL or remote marker")
    for marker in _FORBIDDEN_INTENT_MARKERS:
        if marker in lowered and not any(safe in lowered for safe in _SAFE_NEGATION_MARKERS):
            findings.append(f"{path} contains forbidden intent marker: {marker}")
    return tuple(findings)


def _safe_ref_from(value: Any) -> SafeCredentialReference | None:
    if isinstance(value, SafeCredentialReference):
        return value
    if isinstance(value, dict):
        try:
            return SafeCredentialReference(**value)
        except (TypeError, ValueError):
            return None
    return None


def _request_from_dict(payload: dict[str, Any]) -> SecretSafeAdapterPreflightRequest | None:
    if not isinstance(payload, dict):
        return None
    refs = tuple(
        ref for ref in (_safe_ref_from(item) for item in payload.get("safe_credential_references", ())) if ref is not None
    )
    try:
        return SecretSafeAdapterPreflightRequest(
            schema_version=payload.get("schema_version", SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION),
            request_id=str(payload.get("request_id", "")),
            adapter_id=str(payload.get("adapter_id", "")),
            adapter_runtime=str(payload.get("adapter_runtime", "")),
            activation_mode=str(payload.get("activation_mode", "")),
            requested_transport=str(payload.get("requested_transport", "")),
            checked_at=str(payload.get("checked_at", "")),
            generic_preflight_evidence=FrozenEvidenceMap.from_mapping(payload.get("generic_preflight_evidence", {})),
            transport_decision_evidence=FrozenEvidenceMap.from_mapping(payload.get("transport_decision_evidence", {})),
            file_snapshot_boundary_evidence=FrozenEvidenceMap.from_mapping(payload.get("file_snapshot_boundary_evidence", {})),
            credential_policy_evidence=FrozenEvidenceMap.from_mapping(payload.get("credential_policy_evidence", {})),
            operator_approval_evidence=FrozenEvidenceMap.from_mapping(payload.get("operator_approval_evidence", {})),
            audit_readiness_evidence=FrozenEvidenceMap.from_mapping(payload.get("audit_readiness_evidence", {})),
            rollback_evidence=FrozenEvidenceMap.from_mapping(payload.get("rollback_evidence", {})),
            simulator_fallback_evidence=FrozenEvidenceMap.from_mapping(payload.get("simulator_fallback_evidence", {})),
            manual_fallback_evidence=FrozenEvidenceMap.from_mapping(payload.get("manual_fallback_evidence", {})),
            safe_credential_references=refs,
            metadata=FrozenEvidenceMap.from_mapping(payload.get("metadata", {})),
        )
    except (TypeError, ValueError):
        return None


def validate_report_output_path(*, repo_root, output_path) -> tuple[Path | None, tuple[str, ...]]:
    if output_path is None:
        return None, ()
    errors: list[str] = []
    root = Path(repo_root).resolve()
    path = Path(output_path)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append("output_path must resolve inside repo_root")
    if _contains_url(output_path):
        errors.append("output_path must not contain URL or remote markers")
    return (None if errors else resolved), tuple(sorted(errors))


def validate_secret_safe_adapter_preflight_request(
    request,
    *,
    policy: CredentialPolicy | None = None,
    checked_at: str,
) -> PreflightValidationResult:
    active_policy = policy or create_default_credential_policy()
    request_obj = request if isinstance(request, SecretSafeAdapterPreflightRequest) else _request_from_dict(_to_plain(request))
    blockers: list[str] = []
    warnings: list[str] = []
    if not str(checked_at).strip():
        blockers.append("checked_at must be caller-supplied and non-empty")
    if request_obj is None:
        return PreflightValidationResult(False, str(checked_at), None, (), ("request is malformed",))
    if request_obj.checked_at != str(checked_at):
        blockers.append("request checked_at must match caller checked_at")
    if request_obj.schema_version != SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION:
        blockers.append("unsupported Stage 8.4 request schema_version")
    if request_obj.adapter_id not in SECRET_SAFE_ADAPTER_IDS:
        blockers.append("adapter_id is unsupported")
    if request_obj.adapter_runtime not in SECRET_SAFE_ADAPTER_RUNTIMES:
        blockers.append("adapter_runtime is unsupported")
    elif request_obj.adapter_id in _RUNTIME_BY_ADAPTER and request_obj.adapter_runtime not in _RUNTIME_BY_ADAPTER[request_obj.adapter_id]:
        blockers.append("adapter_runtime does not match adapter contract metadata")
    if request_obj.activation_mode in SECRET_SAFE_REJECTED_ACTIVATION_MODES:
        blockers.append("activation_mode requests forbidden immediate or real activation")
    elif request_obj.activation_mode not in SECRET_SAFE_ACTIVATION_MODES:
        blockers.append("activation_mode is not a safe Stage 8.4 preflight mode")
    if request_obj.requested_transport in SECRET_SAFE_REJECTED_TRANSPORTS:
        blockers.append("requested_transport is not approved for Stage 8.4 readiness")
    elif request_obj.requested_transport not in SECRET_SAFE_TRANSPORTS:
        blockers.append("requested_transport is unsupported")

    plain = request_obj.to_dict()
    blockers.extend(_scan_nested(plain))
    for ref in request_obj.safe_credential_references:
        if ref.material_present:
            blockers.append(f"credential reference {ref.reference_id} has material_present=True")
        if ref.redaction_status not in {"redacted", "not_required"}:
            blockers.append(f"credential reference {ref.reference_id} has unsafe redaction_status")
        if ref.policy_status not in {"policy_only", "reference_only"}:
            warnings.append(f"credential reference {ref.reference_id} has nonstandard policy_status")

    leak_result = validate_no_secret_leak(
        _normalize_for_stage83(plain),
        policy=active_policy,
        checked_at=str(checked_at) if str(checked_at).strip() else "invalid",
        surface_type="APPROVAL_EVIDENCE",
    )
    blockers.extend(leak_result.blockers)
    return PreflightValidationResult(
        accepted=not blockers,
        checked_at=str(checked_at),
        request=request_obj,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
    )


__all__ = sorted(
    (
        "stable_secret_safe_preflight_id",
        "validate_report_output_path",
        "validate_secret_safe_adapter_preflight_request",
    )
)
