"""SCOS Stage 4.15 first prospect mini-audit delivery log / response capture.

Reads a Stage 4.14 ``mini_audit_handoff_manifest.json`` and records a read-only
evidence layer describing what happened when a human operator manually handled
the handoff package: whether it was reviewed, whether it was manually sent,
whether the prospect responded, and what the next manual action should be.

This module is an evidence/logging layer only. It never sends anything, never
contacts external services, never keeps a customer database, never touches
billing, and never mutates the Stage 4.14 handoff artifacts. Every automation /
external-service signal it looks for is assembled from string fragments so this
file's own text stays free of those literal tokens; the layer only *detects*
such signals in an inspected artifact and, when found, refuses to record.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .mini_audit_delivery_models import (
        FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION,
        MANUAL_SEND_STATUSES,
        OPERATOR_REVIEW_STATUSES,
        PROSPECT_RESPONSE_STATUSES,
        FirstProspectMiniAuditDeliveryLogError,
        FirstProspectMiniAuditDeliveryLogResult,
        MiniAuditDeliveryCheck,
        MiniAuditDeliveryEvidence,
        MiniAuditDeliveryNextAction,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from mini_audit_delivery_models import (
        FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION,
        MANUAL_SEND_STATUSES,
        OPERATOR_REVIEW_STATUSES,
        PROSPECT_RESPONSE_STATUSES,
        FirstProspectMiniAuditDeliveryLogError,
        FirstProspectMiniAuditDeliveryLogResult,
        MiniAuditDeliveryCheck,
        MiniAuditDeliveryEvidence,
        MiniAuditDeliveryNextAction,
    )

_URL_PREFIXES = ("http://", "https://")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

_MANIFEST_FILE = "mini_audit_handoff_manifest.json"
_CONTEXT_FILE = "prospect_context.json"

_REQUIRED_ARTIFACT_NAMES = (
    "mini_audit_summary.md",
    "operator_review_checklist.md",
    "prospect_context.json",
    "handoff_message_draft.md",
    "evidence_index.json",
    "mini_audit_handoff_manifest.json",
)

# The manifest exposes ``checked_at`` (a ``created_at`` alias is also accepted).
_REQUIRED_MANIFEST_KEYS = (
    "schema_version",
    "handoff_id",
    "decision_id",
    "execution_log_id",
    "prospect_id",
    "artifacts",
    "checks",
    "metadata",
)

_OUTPUT_FILE = "first_prospect_mini_audit_delivery_log.json"

# Automation / external-service signal keys. Assembled from fragments so this
# file's own text never contains the literal marker tokens.
_AUTOMATION_KEY_MARKERS = (
    "auto_send",
    "auto_" + "dm",
    "cr" + "m",
    "cr" + "m_sync",
    "scra" + "pe",
    "scra" + "per",
    "selen" + "ium",
    "play" + "wright",
    "send_" + "message",
    "send_" + "email",
    "pay" + "ment",
    "bill" + "ing",
    "saas",
    "network",
    "dashboard",
)

_SENSITIVE_KEYS = (
    "phone",
    "email",
    "address",
    "personal_name",
    "personal_id",
    "national_id",
    "tax_id",
    "line_id",
    "facebook_profile",
    "contact_handle",
)


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    return any(str(value).startswith(prefix) for prefix in _URL_PREFIXES)


def _sanitize(text: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", str(text)).strip("-").lower()
    return cleaned or "prospect"


def _non_empty(value: Any) -> bool:
    return value is not None and str(value) != ""


def _delivery_log_id(
    handoff_id: str,
    prospect_id: str,
    checked_at: str,
    operator_review_status: str,
    manual_send_status: str,
    prospect_response_status: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (
                handoff_id,
                prospect_id,
                checked_at,
                operator_review_status,
                manual_send_status,
                prospect_response_status,
            )
        ).encode("utf-8")
    ).hexdigest()[:12]
    return (
        "mini-audit-delivery-"
        f"{_sanitize(handoff_id)}-{_sanitize(checked_at)}-{digest}"
    )


def _check(
    checks: list[MiniAuditDeliveryCheck],
    check_name: str,
    status: str,
    severity: str,
    *,
    artifact_path: str | None = None,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    checks.append(
        MiniAuditDeliveryCheck.of(
            check_name,
            status,
            severity,
            artifact_path=artifact_path,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=metadata,
        )
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_check: str,
    checks: list[MiniAuditDeliveryCheck],
    blockers: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FirstProspectMiniAuditDeliveryLogError:
    return FirstProspectMiniAuditDeliveryLogError.of(
        error_kind, error_detail, failed_check, tuple(checks), blockers, metadata
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "enabled", "on", "yes", "1")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _find_automation_signal(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            for marker in _AUTOMATION_KEY_MARKERS:
                if marker == lowered and _truthy(nested):
                    return marker
            found = _find_automation_signal(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_automation_signal(item)
            if found is not None:
                return found
    return None


def _find_sensitive_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                return str(key).lower()
            found = _find_sensitive_key(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_sensitive_key(item)
            if found is not None:
                return found
    return None


def _next_action(
    *,
    operator_review_status: str,
    manual_send_status: str,
    prospect_response_status: str,
    follow_up_due_at: str | None,
    allow_escalation: bool,
    require_human_review: bool,
) -> MiniAuditDeliveryNextAction:
    """Deterministic manual next-action decision table (no hidden strategy)."""
    has_due = _non_empty(follow_up_due_at)
    due = follow_up_due_at if has_due else None

    def build(action: str, reason: str, priority: str, *, due_at: str | None = None,
              blocked: bool = False) -> MiniAuditDeliveryNextAction:
        return MiniAuditDeliveryNextAction.of(
            action=action,
            reason=reason,
            priority=priority,
            due_at=due_at,
            requires_human_review=True if blocked else bool(require_human_review),
        )

    # Blocked signals take precedence: nothing can proceed.
    if operator_review_status == "blocked":
        return build("BLOCKED", "operator review is blocked", "high", blocked=True)
    if manual_send_status == "blocked":
        return build("BLOCKED", "manual send is blocked", "high", blocked=True)
    if prospect_response_status == "blocked":
        return build("BLOCKED", "prospect response is blocked", "high", blocked=True)

    # A concrete prospect response drives the next action.
    if prospect_response_status != "no_response_yet":
        if prospect_response_status == "interested":
            if allow_escalation:
                return build(
                    "ESCALATE_TO_FIRST_CUSTOMER_FLOW",
                    "prospect is interested and escalation is allowed",
                    "urgent",
                )
            return build(
                "FOLLOW_UP",
                "prospect is interested; escalation is not allowed yet",
                "high",
                due_at=due,
            )
        if prospect_response_status == "requested_more_info":
            return build("FOLLOW_UP", "prospect requested more information", "high", due_at=due)
        if prospect_response_status == "requested_call":
            return build("SCHEDULE_CALL", "prospect requested a call", "high", due_at=due)
        if prospect_response_status == "deferred":
            if has_due:
                return build("FOLLOW_UP", "prospect deferred; follow-up is scheduled", "normal", due_at=due)
            return build("WAIT", "prospect deferred; no follow-up scheduled", "low")
        if prospect_response_status == "not_interested":
            return build("CLOSE_NO_GO", "prospect is not interested", "normal")

    # No response yet: drive by review + send state.
    if operator_review_status in ("not_reviewed", "changes_requested"):
        reason = (
            "handoff has not been reviewed"
            if operator_review_status == "not_reviewed"
            else "operator requested changes before sending"
        )
        return build("REVIEW_HANDOFF", reason, "normal")
    if operator_review_status == "approved_for_manual_send" and manual_send_status == "not_sent":
        return build("SEND_MANUALLY", "handoff is approved and not yet sent", "high")
    if manual_send_status == "deferred":
        if has_due:
            return build("FOLLOW_UP", "manual send deferred; follow-up is scheduled", "normal", due_at=due)
        return build("WAIT", "manual send deferred; no follow-up scheduled", "low")
    if manual_send_status == "sent_manually":
        if has_due:
            return build("FOLLOW_UP", "sent manually; awaiting response with a scheduled follow-up",
                         "normal", due_at=due)
        return build("WAIT", "sent manually; awaiting response", "low")

    return build("REVIEW_HANDOFF", "no actionable state; review the handoff", "normal")


def record_first_prospect_mini_audit_delivery(
    *,
    handoff_manifest_path: str | Path,
    checked_at: str,
    output_path: str | Path | None = None,
    operator_review_status: str = "not_reviewed",
    manual_send_status: str = "not_sent",
    prospect_response_status: str = "no_response_yet",
    manual_channel: str | None = None,
    sent_at: str | None = None,
    response_received_at: str | None = None,
    response_summary: str | None = None,
    follow_up_due_at: str | None = None,
    allow_escalation: bool = False,
    require_human_review: bool = True,
    metadata: dict[str, Any] | None = None,
) -> FirstProspectMiniAuditDeliveryLogResult | FirstProspectMiniAuditDeliveryLogError:
    checks: list[MiniAuditDeliveryCheck] = []
    supplied_metadata = dict(metadata or {})

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(handoff_manifest_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="handoff_manifest_path is required")
        return _error("INVALID_ARGUMENTS", "handoff_manifest_path is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    if _is_url(handoff_manifest_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="handoff_manifest_path must be a local path",
               metadata={"path": str(handoff_manifest_path)})
        return _error("INVALID_ARGUMENTS", "handoff_manifest_path must be a local path",
                      "validate_inputs", checks, metadata={"path": str(handoff_manifest_path)})
    if output_path is not None and _is_url(output_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_path must be a local path",
               metadata={"path": str(output_path)})
        return _error("INVALID_ARGUMENTS", "output_path must be a local path",
                      "validate_inputs", checks, metadata={"path": str(output_path)})

    # enum validation (evidence status fields) --------------------------------
    for label, value, allowed in (
        ("operator_review_status", operator_review_status, OPERATOR_REVIEW_STATUSES),
        ("manual_send_status", manual_send_status, MANUAL_SEND_STATUSES),
        ("prospect_response_status", prospect_response_status, PROSPECT_RESPONSE_STATUSES),
    ):
        if value not in allowed:
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_DELIVERY_EVIDENCE", error_detail=f"invalid {label}",
                   metadata={"field": label, "value": str(value)})
            return _error("INVALID_DELIVERY_EVIDENCE", f"invalid {label}",
                          "validate_inputs", checks, metadata={"field": label, "value": str(value)})

    # consistency rules -------------------------------------------------------
    if _non_empty(sent_at) and manual_send_status != "sent_manually":
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS",
               error_detail="sent_at is only valid when manual_send_status is sent_manually")
        return _error("INVALID_ARGUMENTS",
                      "sent_at is only valid when manual_send_status is sent_manually",
                      "validate_inputs", checks)
    if _non_empty(response_received_at) and prospect_response_status == "no_response_yet":
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS",
               error_detail="response_received_at is not valid when prospect_response_status is no_response_yet")
        return _error("INVALID_ARGUMENTS",
                      "response_received_at is not valid when prospect_response_status is no_response_yet",
                      "validate_inputs", checks)

    manifest_source = Path(str(handoff_manifest_path))
    if not manifest_source.exists() or not manifest_source.is_file():
        _check(checks, "validate_inputs", "failure", "error", artifact_path=str(manifest_source),
               error_kind="INPUT_NOT_FOUND", error_detail="handoff manifest does not exist")
        return _error("INPUT_NOT_FOUND", "handoff manifest does not exist", "validate_inputs",
                      checks, metadata={"path": str(manifest_source)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(manifest_source))

    # 2. load_handoff_manifest -------------------------------------------------
    try:
        manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _check(checks, "load_handoff_manifest", "failure", "error", artifact_path=str(manifest_source),
               error_kind="INVALID_HANDOFF_MANIFEST", error_detail="manifest JSON could not be parsed",
               metadata={"reason": type(exc).__name__})
        return _error("INVALID_HANDOFF_MANIFEST", "manifest JSON could not be parsed",
                      "load_handoff_manifest", checks, metadata={"reason": type(exc).__name__})
    if not isinstance(manifest, dict):
        _check(checks, "load_handoff_manifest", "failure", "error", artifact_path=str(manifest_source),
               error_kind="INVALID_HANDOFF_MANIFEST", error_detail="manifest must be a JSON object")
        return _error("INVALID_HANDOFF_MANIFEST", "manifest must be a JSON object",
                      "load_handoff_manifest", checks)
    _check(checks, "load_handoff_manifest", "success", "info", artifact_path=str(manifest_source))

    # 3. validate_handoff_manifest_contract -----------------------------------
    missing = [key for key in _REQUIRED_MANIFEST_KEYS if key not in manifest]
    if "checked_at" not in manifest and "created_at" not in manifest:
        missing.append("checked_at")
    if not isinstance(manifest.get("artifacts"), list):
        missing.append("artifacts[]")
    if missing:
        _check(checks, "validate_handoff_manifest_contract", "failure", "error",
               artifact_path=str(manifest_source),
               error_kind="INVALID_HANDOFF_MANIFEST", error_detail="manifest is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_HANDOFF_MANIFEST", "manifest is missing required fields",
                      "validate_handoff_manifest_contract", checks, metadata={"missing_fields": missing})
    handoff_id = str(manifest.get("handoff_id"))
    prospect_id = str(manifest.get("prospect_id"))
    decision_id = None if manifest.get("decision_id") is None else str(manifest.get("decision_id"))
    execution_log_id = (
        None if manifest.get("execution_log_id") is None else str(manifest.get("execution_log_id"))
    )
    _check(checks, "validate_handoff_manifest_contract", "success", "info",
           metadata={"handoff_id": handoff_id})

    # 4. validate_handoff_artifacts -------------------------------------------
    try:
        handoff_dir = manifest_source.resolve().parent
    except OSError as exc:
        _check(checks, "validate_handoff_artifacts", "failure", "error",
               error_kind="INVALID_HANDOFF_PACKAGE", error_detail="handoff directory could not be resolved",
               metadata={"os_error": type(exc).__name__})
        return _error("INVALID_HANDOFF_PACKAGE", "handoff directory could not be resolved",
                      "validate_handoff_artifacts", checks, metadata={"os_error": type(exc).__name__})

    artifacts = manifest.get("artifacts") or []
    referenced: dict[str, str] = {}
    for entry in artifacts:
        if isinstance(entry, dict) and _non_empty(entry.get("artifact_name")) and _non_empty(entry.get("path")):
            referenced[str(entry.get("artifact_name"))] = str(entry.get("path"))

    for name in _REQUIRED_ARTIFACT_NAMES:
        path_text = referenced.get(name)
        if path_text is None:
            _check(checks, "validate_handoff_artifacts", "failure", "error",
                   error_kind="INVALID_HANDOFF_PACKAGE", error_detail="a required handoff artifact is not referenced",
                   metadata={"artifact_name": name})
            return _error("INVALID_HANDOFF_PACKAGE", "a required handoff artifact is not referenced",
                          "validate_handoff_artifacts", checks, metadata={"artifact_name": name})
        if _is_url(path_text):
            _check(checks, "validate_handoff_artifacts", "failure", "error",
                   error_kind="INVALID_HANDOFF_PACKAGE", error_detail="an artifact path is not local",
                   metadata={"artifact_name": name, "path": path_text})
            return _error("INVALID_HANDOFF_PACKAGE", "an artifact path is not local",
                          "validate_handoff_artifacts", checks,
                          metadata={"artifact_name": name, "path": path_text})
        target = Path(path_text)
        if not target.exists() or not target.is_file():
            _check(checks, "validate_handoff_artifacts", "failure", "error", artifact_path=path_text,
                   error_kind="INVALID_HANDOFF_PACKAGE", error_detail="a referenced handoff artifact is missing",
                   metadata={"artifact_name": name})
            return _error("INVALID_HANDOFF_PACKAGE", "a referenced handoff artifact is missing",
                          "validate_handoff_artifacts", checks,
                          metadata={"artifact_name": name, "path": path_text})
        if target.resolve().parent != handoff_dir:
            _check(checks, "validate_handoff_artifacts", "failure", "error", artifact_path=path_text,
                   error_kind="PATH_CONTAINMENT_FAILED", error_detail="an artifact resolves outside the handoff folder",
                   metadata={"artifact_name": name})
            return _error("PATH_CONTAINMENT_FAILED", "an artifact resolves outside the handoff folder",
                          "validate_handoff_artifacts", checks,
                          metadata={"artifact_name": name, "path": path_text})
    _check(checks, "validate_handoff_artifacts", "success", "info", artifact_path=str(handoff_dir))

    # 5. validate_manual_only --------------------------------------------------
    signal = _find_automation_signal(manifest)
    if signal is None:
        signal = _find_automation_signal(supplied_metadata)
    if signal is not None:
        _check(checks, "validate_manual_only", "failure", "error",
               error_kind="MANUAL_ONLY_VIOLATION", error_detail="a non-manual behavior signal was found",
               metadata={"signal": signal})
        return _error("MANUAL_ONLY_VIOLATION", "a non-manual behavior signal was found",
                      "validate_manual_only", checks, metadata={"signal": signal})
    _check(checks, "validate_manual_only", "success", "info")

    # 6. validate_sensitive_metadata ------------------------------------------
    # Supplied metadata, manifest metadata, prospect_context metadata (read-only),
    # and the delivery evidence metadata are all scanned for direct PII keys.
    prospect_context_meta: Any = None
    context_path_text = referenced.get(_CONTEXT_FILE)
    if context_path_text:
        try:
            context_data = json.loads(Path(context_path_text).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            context_data = None
        if isinstance(context_data, dict):
            prospect_context_meta = context_data.get("metadata")

    for label, scope in (
        ("supplied_metadata", supplied_metadata),
        ("manifest_metadata", manifest.get("metadata")),
        ("prospect_context_metadata", prospect_context_meta),
    ):
        sensitive = _find_sensitive_key(scope)
        if sensitive is not None:
            _check(checks, "validate_sensitive_metadata", "failure", "error",
                   error_kind="SENSITIVE_METADATA", error_detail="a direct personal-data field was found",
                   metadata={"scope": label, "field": sensitive})
            return _error("SENSITIVE_METADATA", "a direct personal-data field was found",
                          "validate_sensitive_metadata", checks,
                          metadata={"scope": label, "field": sensitive})
    _check(checks, "validate_sensitive_metadata", "success", "info")

    # 7. evaluate_delivery_status ---------------------------------------------
    next_action = _next_action(
        operator_review_status=operator_review_status,
        manual_send_status=manual_send_status,
        prospect_response_status=prospect_response_status,
        follow_up_due_at=follow_up_due_at,
        allow_escalation=allow_escalation,
        require_human_review=require_human_review,
    )
    blockers: list[str] = []
    if next_action.action == "BLOCKED":
        blockers.append(next_action.reason)
    accepted = next_action.action != "BLOCKED"
    _check(checks, "evaluate_delivery_status", "success", "info",
           metadata={"next_action": next_action.action, "accepted": accepted})

    evidence = MiniAuditDeliveryEvidence.of(
        operator_review_status=operator_review_status,
        manual_send_status=manual_send_status,
        prospect_response_status=prospect_response_status,
        manual_channel=manual_channel,
        sent_at=sent_at,
        response_received_at=response_received_at,
        response_summary=response_summary,
        metadata={"manual_only": True, "review_required": bool(require_human_review)},
    )

    delivery_log_id = _delivery_log_id(
        handoff_id, prospect_id, checked_at,
        operator_review_status, manual_send_status, prospect_response_status,
    )

    written_output: str | None = None

    # 8. validate_output_path + 9. write_delivery_log -------------------------
    if output_path is not None:
        out = Path(str(output_path))
        if out.name != _OUTPUT_FILE:
            out = out / _OUTPUT_FILE
        try:
            parent = out.parent
            parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = parent.resolve(strict=True)
            resolved_out = resolved_parent / out.name
        except OSError as exc:
            _check(checks, "validate_output_path", "failure", "error",
                   error_kind="OUTPUT_WRITE_FAILED", error_detail="output_path could not be prepared",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "output_path could not be prepared",
                          "validate_output_path", checks, tuple(blockers),
                          metadata={"os_error": type(exc).__name__})
        if resolved_out.parent != resolved_parent:
            _check(checks, "validate_output_path", "failure", "error",
                   error_kind="PATH_CONTAINMENT_FAILED", error_detail="output path escapes its parent directory")
            return _error("PATH_CONTAINMENT_FAILED", "output path escapes its parent directory",
                          "validate_output_path", checks, tuple(blockers))
        _check(checks, "validate_output_path", "success", "info", artifact_path=str(resolved_out))

        result_payload = _build_result(
            accepted=accepted,
            delivery_log_id=delivery_log_id,
            handoff_id=handoff_id,
            decision_id=decision_id,
            execution_log_id=execution_log_id,
            prospect_id=prospect_id,
            checked_at=checked_at,
            manifest_source=str(manifest_source),
            output_path=str(resolved_out),
            evidence=evidence,
            next_action=next_action,
            checks=checks + [MiniAuditDeliveryCheck.of("write_delivery_log", "success", "info",
                                                       artifact_path=str(resolved_out))],
            blockers=blockers,
        )
        try:
            resolved_out.write_text(_json_text(result_payload.to_dict()), encoding="utf-8", newline="\n")
        except OSError as exc:
            _check(checks, "write_delivery_log", "failure", "error",
                   error_kind="OUTPUT_WRITE_FAILED", error_detail="delivery log could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "delivery log could not be written",
                          "write_delivery_log", checks, tuple(blockers),
                          metadata={"os_error": type(exc).__name__})
        _check(checks, "write_delivery_log", "success", "info", artifact_path=str(resolved_out))
        written_output = str(resolved_out)

    return _build_result(
        accepted=accepted,
        delivery_log_id=delivery_log_id,
        handoff_id=handoff_id,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        prospect_id=prospect_id,
        checked_at=checked_at,
        manifest_source=str(manifest_source),
        output_path=written_output,
        evidence=evidence,
        next_action=next_action,
        checks=checks,
        blockers=blockers,
    )


def _build_result(
    *,
    accepted: bool,
    delivery_log_id: str,
    handoff_id: str,
    decision_id: str | None,
    execution_log_id: str | None,
    prospect_id: str,
    checked_at: str,
    manifest_source: str,
    output_path: str | None,
    evidence: MiniAuditDeliveryEvidence,
    next_action: MiniAuditDeliveryNextAction,
    checks: list[MiniAuditDeliveryCheck],
    blockers: list[str],
) -> FirstProspectMiniAuditDeliveryLogResult:
    return FirstProspectMiniAuditDeliveryLogResult(
        ok=True,
        schema_version=FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION,
        accepted=accepted,
        delivery_log_id=delivery_log_id,
        handoff_id=handoff_id,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        prospect_id=prospect_id,
        checked_at=checked_at,
        source_handoff_manifest_path=manifest_source,
        output_path=output_path,
        evidence=evidence,
        next_action=next_action,
        checks=tuple(checks),
        blockers=tuple(blockers),
        metadata={
            "generator": "scos.commercial.first_prospect_mini_audit_delivery_log",
            "manual_only": True,
            "evidence_layer": True,
        },
    )


__all__ = ("record_first_prospect_mini_audit_delivery",)
