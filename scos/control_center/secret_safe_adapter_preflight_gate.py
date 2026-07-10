"""Stage 8.4 secret-safe adapter activation preflight gate."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    from .credential_policy_models import CredentialPolicy, create_default_credential_policy
    from .credential_policy_validation import validate_no_secret_leak
    from .secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        FrozenEvidenceMap,
        PreflightCheck,
        SafeCredentialReference,
        SecretSafeAdapterPreflightRequest,
        SecretSafeAdapterPreflightResult,
    )
    from .secret_safe_adapter_preflight_validation import (
        stable_secret_safe_preflight_id,
        validate_report_output_path,
        validate_secret_safe_adapter_preflight_request,
    )
except ImportError:  # direct-module execution
    from credential_policy_models import CredentialPolicy, create_default_credential_policy
    from credential_policy_validation import validate_no_secret_leak
    from secret_safe_adapter_preflight_models import (
        SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        FrozenEvidenceMap,
        PreflightCheck,
        SafeCredentialReference,
        SecretSafeAdapterPreflightRequest,
        SecretSafeAdapterPreflightResult,
    )
    from secret_safe_adapter_preflight_validation import (
        stable_secret_safe_preflight_id,
        validate_report_output_path,
        validate_secret_safe_adapter_preflight_request,
    )

_REQUIRED_EVIDENCE_KEYS = (
    "generic_preflight_evidence",
    "transport_decision_evidence",
    "file_snapshot_boundary_evidence",
    "credential_policy_evidence",
    "operator_approval_evidence",
    "audit_readiness_evidence",
    "rollback_evidence",
    "simulator_fallback_evidence",
    "manual_fallback_evidence",
)


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


def _stable_json(payload: object, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=indent, separators=None if indent else (",", ":"))


def _check(category: str, status: str, severity: str, summary: str, refs: tuple[str, ...] = ()) -> PreflightCheck:
    blocker_code = category.upper() if status in {"blocker", "missing"} else None
    warning_code = category.upper() if status == "warning" else None
    return PreflightCheck(
        check_id=stable_secret_safe_preflight_id("sspc-", category, status, summary, refs),
        category=category,
        status=status,
        severity=severity,
        summary=summary,
        evidence_refs=refs,
        blocker_code=blocker_code,
        warning_code=warning_code,
    )


def _mapping(evidence: FrozenEvidenceMap) -> dict[str, Any]:
    return evidence.to_dict()


def _is_truthy(mapping: dict[str, Any], *keys: str) -> bool:
    return all(bool(mapping.get(key)) for key in keys)


def _evidence_checks(request: SecretSafeAdapterPreflightRequest, *, checked_at: str, policy: CredentialPolicy) -> tuple[PreflightCheck, ...]:
    checks: list[PreflightCheck] = []
    for key in _REQUIRED_EVIDENCE_KEYS:
        if not _mapping(getattr(request, key)):
            checks.append(_check(key, "missing", "critical", f"{key} is missing", (key,)))

    generic = _mapping(request.generic_preflight_evidence)
    if generic:
        ok = (
            generic.get("can_activate_now") is False
            and generic.get("dispatch_blocked") is True
            and generic.get("go_no_go") in {"GO", "NO_GO"}
        )
        checks.append(_check("generic_preflight", "pass" if ok else "blocker", "critical", "Stage 7.7 preflight keeps activation and dispatch blocked"))

    transport = _mapping(request.transport_decision_evidence)
    if transport:
        record = transport.get("decision_record", {}) if isinstance(transport.get("decision_record", {}), dict) else {}
        ok = (
            transport.get("accepted") is True
            and transport.get("can_implement_now") is False
            and transport.get("transport_implemented") is False
            and transport.get("dispatch_blocked") is True
            and record.get("decision") == "FILE_SNAPSHOT_REFRESH_ALLOWED_LATER"
        )
        checks.append(_check("transport_decision", "pass" if ok else "blocker", "critical", "Stage 8.1 transport evidence permits only later file snapshot implementation"))

    boundary = _mapping(request.file_snapshot_boundary_evidence)
    if boundary:
        ok = (
            boundary.get("manual_refresh_only") is True
            and boundary.get("network") is False
            and boundary.get("polling") is False
            and boundary.get("background_process") is False
            and boundary.get("file_watcher") is False
        )
        checks.append(_check("file_snapshot_boundary", "pass" if ok else "blocker", "critical", "Stage 8.2 snapshot boundary remains manual, local, and non-live"))

    credential = _mapping(request.credential_policy_evidence)
    if credential:
        metadata = credential.get("metadata", {}) if isinstance(credential.get("metadata", {}), dict) else {}
        ok = (
            credential.get("accepted") is True
            and metadata.get("secret_storage_implemented") is False
            and metadata.get("api_key_flow_implemented") is False
            and metadata.get("external_calls_implemented") is False
            and metadata.get("adapter_activation_implemented") is False
        )
        checks.append(_check("credential_policy", "pass" if ok else "blocker", "critical", "Stage 8.3 policy evidence is policy-only and not credential-use authorization"))

    approval = _mapping(request.operator_approval_evidence)
    if approval:
        decision = str(approval.get("approval_decision", "")).lower()
        scope = str(approval.get("approval_scope", "")).lower()
        action = str(approval.get("action", "")).lower()
        status = "pass"
        if decision == "denied":
            status = "blocker"
        if scope in {"blanket", "default", "global", "all"}:
            status = "blocker"
        ok = decision == "approved" and scope == "adapter_specific" and action == "present_to_operator_decision"
        if approval.get("adapter_id") != request.adapter_id or approval.get("checked_at") != checked_at:
            ok = False
        checks.append(_check("operator_approval", "pass" if ok and status == "pass" else "blocker", "critical", "operator approval is explicit, adapter-specific, and presentation-only"))

    audit = _mapping(request.audit_readiness_evidence)
    if audit:
        ok = _is_truthy(audit, "append_only_supported") and audit.get("will_write_now") is False
        checks.append(_check("audit_readiness", "pass" if ok else "blocker", "critical", "append-only audit readiness is represented without writing records"))

    rollback = _mapping(request.rollback_evidence)
    if rollback:
        steps = rollback.get("steps", ())
        ok = rollback.get("restores_adapter_disabled") is True and rollback.get("network_dependency") is False and bool(steps)
        checks.append(_check("rollback", "pass" if ok else "blocker", "critical", "rollback restores adapter-disabled state without network dependency"))

    simulator = _mapping(request.simulator_fallback_evidence)
    if simulator:
        ok = simulator.get("available") is True and simulator.get("claims_runtime_activation") is not True
        checks.append(_check("simulator_fallback", "pass" if ok else "blocker", "error", "simulator fallback remains available and inactive"))

    manual = _mapping(request.manual_fallback_evidence)
    if manual:
        ok = manual.get("available") is True and manual.get("claims_runtime_activation") is not True
        checks.append(_check("manual_fallback", "pass" if ok else "blocker", "error", "manual fallback remains available and inactive"))

    leak_payload = {"evidence_values": [_normalize_for_leak_scan(_plain(getattr(request, key).to_dict())) for key in _REQUIRED_EVIDENCE_KEYS]}
    leak = validate_no_secret_leak(leak_payload, policy=policy, checked_at=checked_at, surface_type="CERTIFICATION_EVIDENCE")
    checks.append(_check("secret_leak_validation", "pass" if leak.accepted else "blocker", "critical", "Stage 8.3 no-secret-leak validation applied to evidence values"))
    return tuple(checks)


def _result_from_checks(
    request: SecretSafeAdapterPreflightRequest,
    checks: tuple[PreflightCheck, ...],
    *,
    checked_at: str,
    report_path: str | None = None,
) -> SecretSafeAdapterPreflightResult:
    blockers = tuple(check.summary for check in checks if check.status in {"blocker", "missing"})
    warnings = tuple(check.summary for check in checks if check.status == "warning")
    if any(check.status == "missing" for check in checks):
        verdict = "BLOCKED"
        score = max(0, min(69, 69 - len(blockers) * 3))
    elif blockers:
        verdict = "NO_GO"
        score = max(70, 99 - len(blockers) * 3)
    else:
        verdict = "READY_FOR_OPERATOR_DECISION"
        score = 100
    digest_payload = {"request": request.to_dict(), "checks": [check.to_dict() for check in checks]}
    digest = stable_secret_safe_preflight_id("sspd-", digest_payload)
    return SecretSafeAdapterPreflightResult(
        schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        result_id=stable_secret_safe_preflight_id("sspr-", checked_at, request.request_id, digest, verdict),
        checked_at=checked_at,
        adapter_id=request.adapter_id,
        verdict=verdict,
        readiness_score=score,
        accepted=verdict == "READY_FOR_OPERATOR_DECISION",
        ready_for_operator_decision=verdict == "READY_FOR_OPERATOR_DECISION",
        can_activate_now=False,
        activation_authorized=False,
        real_dispatch_blocked=True,
        external_calls_blocked=True,
        credentials_materialized=False,
        runtime_mutated=False,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        required_next_action="present_to_operator_for_later_explicit_activation_decision" if verdict == "READY_FOR_OPERATOR_DECISION" else "repair_preflight_evidence_before_operator_decision",
        evidence_digest=digest,
        report_path=report_path,
        metadata=FrozenEvidenceMap.from_mapping({"pass_meaning": "READY_FOR_OPERATOR_DECISION_ONLY"}),
    )


def evaluate_secret_safe_adapter_preflight(
    request,
    *,
    credential_policy: CredentialPolicy | None = None,
    checked_at: str,
) -> SecretSafeAdapterPreflightResult:
    policy = credential_policy or create_default_credential_policy()
    validation = validate_secret_safe_adapter_preflight_request(request, policy=policy, checked_at=checked_at)
    request_obj = validation.request
    if request_obj is None:
        synthetic_request = SecretSafeAdapterPreflightRequest(
            schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
            request_id="invalid",
            adapter_id="unknown",
            adapter_runtime="manual",
            activation_mode="preflight_only",
            requested_transport="NO_TRANSPORT",
            checked_at=str(checked_at),
            generic_preflight_evidence=FrozenEvidenceMap.from_mapping({}),
            transport_decision_evidence=FrozenEvidenceMap.from_mapping({}),
            file_snapshot_boundary_evidence=FrozenEvidenceMap.from_mapping({}),
            credential_policy_evidence=FrozenEvidenceMap.from_mapping({}),
            operator_approval_evidence=FrozenEvidenceMap.from_mapping({}),
            audit_readiness_evidence=FrozenEvidenceMap.from_mapping({}),
            rollback_evidence=FrozenEvidenceMap.from_mapping({}),
            simulator_fallback_evidence=FrozenEvidenceMap.from_mapping({}),
            manual_fallback_evidence=FrozenEvidenceMap.from_mapping({}),
            safe_credential_references=(),
            metadata=FrozenEvidenceMap.from_mapping({}),
        )
        checks = (_check("request_validation", "missing", "critical", "; ".join(validation.blockers)),)
        return _result_from_checks(synthetic_request, checks, checked_at=str(checked_at))
    checks = list(_evidence_checks(request_obj, checked_at=str(checked_at), policy=policy))
    if validation.blockers:
        checks.append(_check("request_validation", "blocker", "critical", "; ".join(validation.blockers)))
    if validation.warnings:
        checks.append(_check("request_validation_warning", "warning", "warning", "; ".join(validation.warnings)))
    return _result_from_checks(request_obj, tuple(checks), checked_at=str(checked_at))


def build_stage84_preflight_evidence(
    *,
    adapter_id: str,
    checked_at: str,
    generic_preflight_evidence,
    transport_decision_evidence,
    file_snapshot_boundary_evidence,
    credential_policy_evidence,
    operator_approval_evidence,
    audit_readiness_evidence,
    rollback_evidence,
    simulator_fallback_evidence,
    manual_fallback_evidence,
    metadata=None,
    adapter_runtime: str = "simulator",
    activation_mode: str = "preflight_only",
    requested_transport: str = "FILE_SNAPSHOT_REFRESH",
    safe_credential_references: tuple[SafeCredentialReference, ...] = (),
) -> SecretSafeAdapterPreflightResult:
    request_id = stable_secret_safe_preflight_id(
        "ssrq-",
        adapter_id,
        checked_at,
        adapter_runtime,
        activation_mode,
        requested_transport,
        _plain(metadata or {}),
    )
    request = SecretSafeAdapterPreflightRequest(
        schema_version=SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION,
        request_id=request_id,
        adapter_id=adapter_id,
        adapter_runtime=adapter_runtime,
        activation_mode=activation_mode,
        requested_transport=requested_transport,
        checked_at=checked_at,
        generic_preflight_evidence=FrozenEvidenceMap.from_mapping(_plain(generic_preflight_evidence)),
        transport_decision_evidence=FrozenEvidenceMap.from_mapping(_plain(transport_decision_evidence)),
        file_snapshot_boundary_evidence=FrozenEvidenceMap.from_mapping(_plain(file_snapshot_boundary_evidence)),
        credential_policy_evidence=FrozenEvidenceMap.from_mapping(_plain(credential_policy_evidence)),
        operator_approval_evidence=FrozenEvidenceMap.from_mapping(_plain(operator_approval_evidence)),
        audit_readiness_evidence=FrozenEvidenceMap.from_mapping(_plain(audit_readiness_evidence)),
        rollback_evidence=FrozenEvidenceMap.from_mapping(_plain(rollback_evidence)),
        simulator_fallback_evidence=FrozenEvidenceMap.from_mapping(_plain(simulator_fallback_evidence)),
        manual_fallback_evidence=FrozenEvidenceMap.from_mapping(_plain(manual_fallback_evidence)),
        safe_credential_references=safe_credential_references,
        metadata=FrozenEvidenceMap.from_mapping(_plain(metadata or {})),
    )
    return evaluate_secret_safe_adapter_preflight(request, checked_at=checked_at)


def write_secret_safe_adapter_preflight_report(result, *, repo_root, output_path):
    resolved, errors = validate_report_output_path(repo_root=repo_root, output_path=output_path)
    if errors:
        return {"accepted": False, "output_path": None, "blockers": errors, "warnings": ()}
    assert resolved is not None
    document = _plain(result)
    leak = validate_no_secret_leak(
        _normalize_for_leak_scan(document),
        checked_at=str(document.get("checked_at", "")),
        surface_type="CERTIFICATION_EVIDENCE",
    )
    if not leak.accepted:
        return {"accepted": False, "output_path": None, "blockers": leak.blockers, "warnings": ()}
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_stable_json(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"accepted": True, "output_path": str(resolved), "blockers": (), "warnings": ()}


__all__ = sorted(
    (
        "build_stage84_preflight_evidence",
        "evaluate_secret_safe_adapter_preflight",
        "write_secret_safe_adapter_preflight_report",
    )
)
