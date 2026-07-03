"""SCOS Stage 4.12 first prospect execution log recorder.

Records a single manual first-prospect outreach attempt as deterministic,
evidence-first output. This module is manual evidence logging only: it does not
send messages, gather or enrich leads, keep a customer database, or call any
external service. It only reads/validates an optional Stage 4.11 launch kit
artifact for reference and never mutates it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .prospect_models import (
        FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION,
        PROSPECT_ACTION_TYPES,
        PROSPECT_RESPONSE_STATUSES,
        FirstProspectExecutionLogError,
        FirstProspectExecutionLogResult,
        ProspectExecutionCheck,
        ProspectOutreachAction,
        ProspectProfile,
        ProspectResponseStatus,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from prospect_models import (
        FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION,
        PROSPECT_ACTION_TYPES,
        PROSPECT_RESPONSE_STATUSES,
        FirstProspectExecutionLogError,
        FirstProspectExecutionLogResult,
        ProspectExecutionCheck,
        ProspectOutreachAction,
        ProspectProfile,
        ProspectResponseStatus,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")
_SENSITIVE_KEY_MARKERS = ("phone", "email", "address", "token", "secret", "password")

_EXECUTION_LOG_FILE = "prospect_execution_log.json"
_STATUS_NEXT_ACTION_OPTIONAL = ("not_contacted",)

_REQUIRED_CHECK_NAMES = (
    "validate_inputs",
    "validate_prospect_profile",
    "validate_outreach_action",
    "validate_response_status",
    "validate_outreach_launch_kit_reference",
    "write_execution_log",
)

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, FrozenMap):
        value = value.to_dict()
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _sanitize(text: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", str(text)).strip("-").lower()
    return cleaned or "prospect"


def _execution_log_id(prospect_id: str, checked_at: str) -> str:
    digest = hashlib.sha256(f"{prospect_id}|{checked_at}".encode("utf-8")).hexdigest()[:12]
    return f"prospect-execution-{_sanitize(prospect_id)}-{_sanitize(checked_at)}-{digest}"


def _check(
    checks: list[ProspectExecutionCheck],
    check_name: str,
    status: str,
    severity: str,
    *,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    checks.append(
        ProspectExecutionCheck.of(
            check_name,
            status,
            severity,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=metadata,
        )
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_check: str,
    checks: list[ProspectExecutionCheck],
    metadata: dict[str, Any] | None = None,
) -> FirstProspectExecutionLogError:
    return FirstProspectExecutionLogError.of(
        error_kind,
        error_detail,
        failed_check,
        tuple(checks),
        metadata,
    )


def _non_empty(value: Any) -> bool:
    return value is not None and str(value) != ""


def record_first_prospect_execution(
    *,
    output_dir: str | Path,
    checked_at: str,
    prospect: ProspectProfile,
    outreach_action: ProspectOutreachAction,
    response_status: ProspectResponseStatus,
    outreach_launch_kit_path: str | Path | None = None,
    overwrite: bool = False,
) -> FirstProspectExecutionLogResult | FirstProspectExecutionLogError:
    checks: list[ProspectExecutionCheck] = []

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(output_dir):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    for label, value in (
        ("output_dir", output_dir),
        ("outreach_launch_kit_path", outreach_launch_kit_path),
    ):
        if _is_url(value):
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="paths must be local filesystem paths",
                   metadata={"argument": label, "path": str(value)})
            return _error("INVALID_ARGUMENTS", "paths must be local filesystem paths",
                          "validate_inputs", checks, {"argument": label, "path": str(value)})
    if not isinstance(prospect, ProspectProfile):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="prospect must be a ProspectProfile")
        return _error("INVALID_ARGUMENTS", "prospect must be a ProspectProfile", "validate_inputs", checks)
    if not isinstance(outreach_action, ProspectOutreachAction):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="outreach_action must be a ProspectOutreachAction")
        return _error("INVALID_ARGUMENTS", "outreach_action must be a ProspectOutreachAction",
                      "validate_inputs", checks)
    if not isinstance(response_status, ProspectResponseStatus):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="response_status must be a ProspectResponseStatus")
        return _error("INVALID_ARGUMENTS", "response_status must be a ProspectResponseStatus",
                      "validate_inputs", checks)
    _check(checks, "validate_inputs", "success", "info", metadata={"output_dir": str(output_dir)})

    # 2. validate_prospect_profile --------------------------------------------
    required_fields = {
        "prospect_id": prospect.prospect_id,
        "display_name": prospect.display_name,
        "business_type": prospect.business_type,
        "channel": prospect.channel,
        "source": prospect.source,
    }
    missing = [name for name, value in required_fields.items() if not _non_empty(value)]
    if missing:
        _check(checks, "validate_prospect_profile", "failure", "error",
               error_kind="INVALID_PROSPECT", error_detail="prospect is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_PROSPECT", "prospect is missing required fields",
                      "validate_prospect_profile", checks, {"missing_fields": missing})
    if _contains_sensitive_key(prospect.metadata):
        _check(checks, "validate_prospect_profile", "failure", "error",
               error_kind="SENSITIVE_DATA_REJECTED",
               error_detail="prospect metadata contains sensitive contact-like keys")
        return _error("SENSITIVE_DATA_REJECTED",
                      "prospect metadata contains sensitive contact-like keys",
                      "validate_prospect_profile", checks)
    _check(checks, "validate_prospect_profile", "success", "info",
           metadata={"prospect_id": prospect.prospect_id})

    # 3. validate_outreach_action ---------------------------------------------
    if outreach_action.action_type not in PROSPECT_ACTION_TYPES:
        _check(checks, "validate_outreach_action", "failure", "error",
               error_kind="INVALID_OUTREACH_ACTION", error_detail="action_type is not allowed",
               metadata={"action_type": outreach_action.action_type})
        return _error("INVALID_OUTREACH_ACTION", "action_type is not allowed",
                      "validate_outreach_action", checks, {"action_type": outreach_action.action_type})
    action_required = {
        "performed_at": outreach_action.performed_at,
        "performed_by": outreach_action.performed_by,
        "message_summary": outreach_action.message_summary,
    }
    action_missing = [name for name, value in action_required.items() if not _non_empty(value)]
    if action_missing:
        _check(checks, "validate_outreach_action", "failure", "error",
               error_kind="INVALID_OUTREACH_ACTION", error_detail="outreach action is missing required fields",
               metadata={"missing_fields": action_missing})
        return _error("INVALID_OUTREACH_ACTION", "outreach action is missing required fields",
                      "validate_outreach_action", checks, {"missing_fields": action_missing})
    if _contains_sensitive_key(outreach_action.metadata):
        _check(checks, "validate_outreach_action", "failure", "error",
               error_kind="SENSITIVE_DATA_REJECTED",
               error_detail="outreach action metadata contains sensitive contact-like keys")
        return _error("SENSITIVE_DATA_REJECTED",
                      "outreach action metadata contains sensitive contact-like keys",
                      "validate_outreach_action", checks)
    _check(checks, "validate_outreach_action", "success", "info",
           metadata={"action_type": outreach_action.action_type})

    # 4. validate_response_status ---------------------------------------------
    if response_status.status not in PROSPECT_RESPONSE_STATUSES:
        _check(checks, "validate_response_status", "failure", "error",
               error_kind="INVALID_RESPONSE_STATUS", error_detail="response status is not allowed",
               metadata={"status": response_status.status})
        return _error("INVALID_RESPONSE_STATUS", "response status is not allowed",
                      "validate_response_status", checks, {"status": response_status.status})
    if response_status.status not in _STATUS_NEXT_ACTION_OPTIONAL and not _non_empty(response_status.next_action):
        _check(checks, "validate_response_status", "failure", "error",
               error_kind="INVALID_RESPONSE_STATUS",
               error_detail="next_action is required unless status is not_contacted",
               metadata={"status": response_status.status})
        return _error("INVALID_RESPONSE_STATUS",
                      "next_action is required unless status is not_contacted",
                      "validate_response_status", checks, {"status": response_status.status})
    if _contains_sensitive_key(response_status.metadata):
        _check(checks, "validate_response_status", "failure", "error",
               error_kind="SENSITIVE_DATA_REJECTED",
               error_detail="response status metadata contains sensitive contact-like keys")
        return _error("SENSITIVE_DATA_REJECTED",
                      "response status metadata contains sensitive contact-like keys",
                      "validate_response_status", checks)
    _check(checks, "validate_response_status", "success", "info",
           metadata={"status": response_status.status})

    # 5. validate_outreach_launch_kit_reference -------------------------------
    kit_path_text: str | None = None
    if outreach_launch_kit_path is None or str(outreach_launch_kit_path) == "":
        _check(checks, "validate_outreach_launch_kit_reference", "skipped", "warning",
               metadata={"provided": False})
    else:
        kit_path = Path(str(outreach_launch_kit_path))
        if not kit_path.exists() or not kit_path.is_file():
            _check(checks, "validate_outreach_launch_kit_reference", "failure", "error",
                   error_kind="INPUT_NOT_FOUND", error_detail="outreach launch kit path does not exist",
                   metadata={"path": str(kit_path)})
            return _error("INPUT_NOT_FOUND", "outreach launch kit path does not exist",
                          "validate_outreach_launch_kit_reference", checks, {"path": str(kit_path)})
        if kit_path.suffix.lower() == ".json":
            try:
                json.loads(kit_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                _check(checks, "validate_outreach_launch_kit_reference", "failure", "error",
                       error_kind="INVALID_OUTREACH_KIT",
                       error_detail="outreach launch kit JSON could not be parsed",
                       metadata={"path": str(kit_path), "reason": type(exc).__name__})
                return _error("INVALID_OUTREACH_KIT",
                              "outreach launch kit JSON could not be parsed",
                              "validate_outreach_launch_kit_reference", checks,
                              {"path": str(kit_path), "reason": type(exc).__name__})
        kit_path_text = str(kit_path)
        _check(checks, "validate_outreach_launch_kit_reference", "success", "info",
               metadata={"provided": True, "path": kit_path_text})

    # 6. write_execution_log ---------------------------------------------------
    execution_log_id = _execution_log_id(prospect.prospect_id, checked_at)
    base_dir = Path(str(output_dir))
    log_path = base_dir / _EXECUTION_LOG_FILE
    if log_path.exists() and not overwrite:
        _check(checks, "write_execution_log", "failure", "error",
               error_kind="OUTPUT_EXISTS",
               error_detail="prospect execution log already exists and overwrite is False",
               metadata={"path": str(log_path)})
        return _error("OUTPUT_EXISTS",
                      "prospect execution log already exists and overwrite is False",
                      "write_execution_log", checks, {"path": str(log_path)})

    result = FirstProspectExecutionLogResult(
        ok=True,
        schema_version=FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION,
        logged=True,
        execution_log_id=execution_log_id,
        checked_at=checked_at,
        prospect=prospect,
        outreach_action=outreach_action,
        response_status=response_status,
        outreach_launch_kit_path=kit_path_text,
        execution_log_path=str(log_path),
        checks=tuple(checks) + (
            ProspectExecutionCheck.of("write_execution_log", "success", "info",
                                      metadata={"path": str(log_path)}),
        ),
        metadata=FrozenMap.from_mapping(
            {
                "recorder": "scos.commercial.first_prospect_execution_log",
                "manual_only": True,
                "launch_kit_referenced": kit_path_text is not None,
            }
        ),
    )
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
    except OSError as exc:
        _check(checks, "write_execution_log", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="prospect execution log could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "prospect execution log could not be written",
                      "write_execution_log", checks, {"os_error": type(exc).__name__})
    return result


__all__ = ("record_first_prospect_execution",)
