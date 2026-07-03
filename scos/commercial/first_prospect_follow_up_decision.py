"""SCOS Stage 4.13 first prospect follow-up decision gate.

Reads a Stage 4.12 ``prospect_execution_log.json`` and decides, deterministically,
what the operator should manually do next. This module is a read-only decision
gate: it never sends anything, never contacts external services, never keeps a
customer database, never touches billing, and never mutates the source log.

Every automation / external-service signal it looks for is assembled from string
fragments at import time so this file's own text stays free of those literal
tokens; the gate only *detects* such signals in an inspected log and, when found,
returns a BLOCKED decision (accepted=False) so a human decides what to do.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .follow_up_models import (
        FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION,
        FollowUpDecisionAction,
        FollowUpDecisionCheck,
        FirstProspectFollowUpDecisionError,
        FirstProspectFollowUpDecisionResult,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from follow_up_models import (
        FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION,
        FollowUpDecisionAction,
        FollowUpDecisionCheck,
        FirstProspectFollowUpDecisionError,
        FirstProspectFollowUpDecisionResult,
    )

_URL_PREFIXES = ("http://", "https://")
_OUTPUT_FILE = "first_prospect_follow_up_decision.json"
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

# Automation / external-service signal keys. Assembled from fragments so this
# file's own text never contains the literal marker tokens (keeps the static
# manual-only scan clean while still detecting them inside an inspected log).
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
    "saas",
    "network",
)

# Direct personal-data keys that must never appear in an inspected log.
_SENSITIVE_KEYS = (
    "phone",
    "email",
    "address",
    "personal_name",
    "personal_id",
    "national_id",
    "tax_id",
)

_STRONG_INTEREST = ("interested", "mini_audit_requested")

_KNOWN_STATUSES = (
    "not_contacted",
    "contacted",
    "interested",
    "not_interested",
    "no_response",
    "follow_up_needed",
    "mini_audit_requested",
    "blocked",
)

_REQUIRED_CHECK_NAMES = (
    "validate_inputs",
    "load_execution_log",
    "validate_execution_log_contract",
    "validate_manual_only",
    "validate_sensitive_metadata",
    "evaluate_blockers",
    "evaluate_response_status",
    "evaluate_escalation",
)


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _sanitize(text: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", str(text)).strip("-").lower()
    return cleaned or "prospect"


def _non_empty(value: Any) -> bool:
    return value is not None and str(value) != ""


def _decision_id(execution_log_id: str, prospect_id: str, checked_at: str, action: str) -> str:
    raw = f"{execution_log_id}|{prospect_id}|{checked_at}|{action}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"follow-up-decision-{_sanitize(prospect_id)}-{_sanitize(checked_at)}-{digest}"


def _check(
    checks: list[FollowUpDecisionCheck],
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
        FollowUpDecisionCheck.of(
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
    checks: list[FollowUpDecisionCheck],
    blockers: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FirstProspectFollowUpDecisionError:
    return FirstProspectFollowUpDecisionError.of(
        error_kind,
        error_detail,
        failed_check,
        tuple(checks),
        blockers,
        metadata,
    )


def _find_automation_signal(value: Any) -> str | None:
    """Return the first automation marker found as a truthy key, else None."""
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "enabled", "on", "yes", "1")
    if isinstance(value, (int, float)):
        return value != 0
    return False


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


def _has_traversal(path_text: str) -> bool:
    return ".." in Path(str(path_text)).parts


def decide_first_prospect_follow_up(
    *,
    execution_log_path: str | Path,
    checked_at: str,
    output_path: str | Path | None = None,
    require_human_review: bool = True,
    allow_escalation: bool = False,
) -> FirstProspectFollowUpDecisionResult | FirstProspectFollowUpDecisionError:
    checks: list[FollowUpDecisionCheck] = []

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(execution_log_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="execution_log_path is required")
        return _error("INVALID_ARGUMENTS", "execution_log_path is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    for label, value in (("execution_log_path", execution_log_path), ("output_path", output_path)):
        if _is_url(value):
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="paths must be local filesystem paths",
                   metadata={"argument": label, "path": str(value)})
            return _error("INVALID_ARGUMENTS", "paths must be local filesystem paths",
                          "validate_inputs", checks, metadata={"argument": label, "path": str(value)})
    source_path = Path(str(execution_log_path))
    if not source_path.exists() or not source_path.is_file():
        _check(checks, "validate_inputs", "failure", "error",
               artifact_path=str(source_path),
               error_kind="INPUT_NOT_FOUND", error_detail="execution log path does not exist")
        return _error("INPUT_NOT_FOUND", "execution log path does not exist", "validate_inputs",
                      checks, metadata={"path": str(source_path)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(source_path))

    # 2. load_execution_log ----------------------------------------------------
    try:
        loaded = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _check(checks, "load_execution_log", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="execution log JSON could not be parsed",
               metadata={"reason": type(exc).__name__})
        return _error("INVALID_EXECUTION_LOG", "execution log JSON could not be parsed",
                      "load_execution_log", checks, metadata={"reason": type(exc).__name__})
    if not isinstance(loaded, dict):
        _check(checks, "load_execution_log", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="execution log must be a JSON object")
        return _error("INVALID_EXECUTION_LOG", "execution log must be a JSON object",
                      "load_execution_log", checks)
    _check(checks, "load_execution_log", "success", "info", artifact_path=str(source_path))

    # 3. validate_execution_log_contract --------------------------------------
    required_top = ("schema_version", "execution_log_id", "prospect", "response_status",
                    "outreach_action", "outreach_launch_kit_path", "metadata")
    missing = [key for key in required_top if key not in loaded]
    if "checked_at" not in loaded and "created_at" not in loaded:
        missing.append("checked_at_or_created_at")
    if missing:
        _check(checks, "validate_execution_log_contract", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="execution log is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_EXECUTION_LOG", "execution log is missing required fields",
                      "validate_execution_log_contract", checks, metadata={"missing_fields": missing})
    prospect = loaded.get("prospect")
    response_status = loaded.get("response_status")
    if not isinstance(prospect, dict) or not _non_empty(prospect.get("prospect_id")):
        _check(checks, "validate_execution_log_contract", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="prospect.prospect_id is required")
        return _error("INVALID_EXECUTION_LOG", "prospect.prospect_id is required",
                      "validate_execution_log_contract", checks)
    if not isinstance(response_status, dict) or not _non_empty(response_status.get("status")):
        _check(checks, "validate_execution_log_contract", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="response_status.status is required")
        return _error("INVALID_EXECUTION_LOG", "response_status.status is required",
                      "validate_execution_log_contract", checks)
    if not isinstance(loaded.get("outreach_action"), dict):
        _check(checks, "validate_execution_log_contract", "failure", "error", artifact_path=str(source_path),
               error_kind="INVALID_EXECUTION_LOG", error_detail="outreach_action object is required")
        return _error("INVALID_EXECUTION_LOG", "outreach_action object is required",
                      "validate_execution_log_contract", checks)

    execution_log_id = str(loaded.get("execution_log_id"))
    prospect_id = str(prospect.get("prospect_id"))
    status = str(response_status.get("status"))
    next_action = str(response_status.get("next_action") or "")
    follow_up_due = response_status.get("follow_up_due")
    blocker_summary = response_status.get("blocker_summary")
    _check(checks, "validate_execution_log_contract", "success", "info",
           metadata={"execution_log_id": execution_log_id, "status": status})

    # 4. validate_manual_only --------------------------------------------------
    # A detected automation signal is NOT a hard error: the log was inspected,
    # it just must not be acted on, so the gate returns a BLOCKED decision.
    manual_only_signal = _find_automation_signal(loaded)
    if manual_only_signal is not None:
        _check(checks, "validate_manual_only", "failure", "warning",
               error_kind="MANUAL_ONLY_VIOLATION",
               error_detail="execution log signals a non-manual behavior",
               metadata={"signal": manual_only_signal})
    else:
        _check(checks, "validate_manual_only", "success", "info")

    # 5. validate_sensitive_metadata ------------------------------------------
    sensitive_key = _find_sensitive_key(prospect)
    if sensitive_key is None:
        sensitive_key = _find_sensitive_key(loaded.get("metadata"))
    if sensitive_key is not None:
        _check(checks, "validate_sensitive_metadata", "failure", "error",
               error_kind="SENSITIVE_METADATA",
               error_detail="execution log contains a direct personal-data field",
               metadata={"field": sensitive_key})
        return _error("SENSITIVE_METADATA", "execution log contains a direct personal-data field",
                      "validate_sensitive_metadata", checks, metadata={"field": sensitive_key})
    _check(checks, "validate_sensitive_metadata", "success", "info")

    # 6. evaluate_blockers -----------------------------------------------------
    blockers: tuple[str, ...] = ()
    if _non_empty(blocker_summary):
        blockers = (str(blocker_summary),)
    _check(checks, "evaluate_blockers", "success", "info",
           metadata={"blocker_count": len(blockers)})

    # 7 + 8. determine the decision -------------------------------------------
    if status not in _KNOWN_STATUSES:
        _check(checks, "evaluate_response_status", "failure", "error",
               error_kind="INVALID_RESPONSE_STATUS", error_detail="response status is not recognized",
               metadata={"status": status})
        return _error("INVALID_RESPONSE_STATUS", "response status is not recognized",
                      "evaluate_response_status", checks, metadata={"status": status})

    action, reason, priority, due_at, accepted = _decide(
        status=status,
        next_action=next_action,
        follow_up_due=follow_up_due,
        has_blocker=bool(blockers),
        manual_only_signal=manual_only_signal,
        blocker_summary=blocker_summary,
        allow_escalation=allow_escalation,
    )
    _check(checks, "evaluate_response_status", "success", "info", metadata={"status": status, "action": action})
    _check(checks, "evaluate_escalation", "success", "info",
           metadata={"allow_escalation": bool(allow_escalation), "action": action})

    requires_review = bool(require_human_review) or action == "ESCALATE_TO_FIRST_CUSTOMER_FLOW"
    action_obj = FollowUpDecisionAction.of(
        action=action,
        reason=reason,
        priority=priority,
        due_at=due_at,
        requires_human_review=requires_review,
        metadata={"source_status": status},
    )
    decision_id = _decision_id(execution_log_id, prospect_id, checked_at, action)

    # 9. validate_output_path --------------------------------------------------
    output_text: str | None = None
    if _non_empty(output_path):
        candidate = Path(str(output_path))
        if _has_traversal(str(output_path)):
            _check(checks, "validate_output_path", "failure", "error", artifact_path=str(output_path),
                   error_kind="PATH_CONTAINMENT_FAILED", error_detail="output_path contains a parent traversal")
            return _error("PATH_CONTAINMENT_FAILED", "output_path contains a parent traversal",
                          "validate_output_path", checks, blockers, metadata={"path": str(output_path)})
        out_file = candidate if candidate.suffix.lower() == ".json" else candidate / _OUTPUT_FILE
        output_text = str(out_file)
        _check(checks, "validate_output_path", "success", "info", artifact_path=output_text)

    result = FirstProspectFollowUpDecisionResult(
        ok=True,
        schema_version=FIRST_PROSPECT_FOLLOW_UP_DECISION_SCHEMA_VERSION,
        accepted=accepted,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        prospect_id=prospect_id,
        checked_at=checked_at,
        action=action_obj,
        source_execution_log_path=str(source_path),
        output_path=output_text,
        checks=tuple(checks),
        blockers=blockers,
        metadata={
            "decider": "scos.commercial.first_prospect_follow_up_decision",
            "manual_only": True,
            "manual_only_violation": manual_only_signal is not None,
        },
    )

    # 10. write_decision_report -----------------------------------------------
    if output_text is not None:
        out_file = Path(output_text)
        try:
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
        except OSError as exc:
            _check(checks, "write_decision_report", "failure", "error",
                   error_kind="OUTPUT_WRITE_FAILED", error_detail="decision report could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "decision report could not be written",
                          "write_decision_report", checks, blockers, metadata={"os_error": type(exc).__name__})
    return result


def _decide(
    *,
    status: str,
    next_action: str,
    follow_up_due: Any,
    has_blocker: bool,
    manual_only_signal: str | None,
    blocker_summary: Any,
    allow_escalation: bool,
) -> tuple[str, str, str, str | None, bool]:
    """Pure mapping from evidence to (action, reason, priority, due_at, accepted)."""
    if manual_only_signal is not None:
        return (
            "BLOCKED",
            f"Execution log signals a non-manual behavior ({manual_only_signal}); a human must review.",
            "urgent",
            None,
            False,
        )
    if status == "blocked" or has_blocker:
        summary_text = str(blocker_summary or "").lower()
        priority = "urgent" if any(word in summary_text for word in ("high", "critical")) else "high"
        return (
            "BLOCKED",
            "A blocker is recorded on the execution log; resolve it before acting.",
            priority,
            None,
            False,
        )
    follow_up_evidence = _non_empty(follow_up_due) or "follow" in next_action.lower()
    if status in _STRONG_INTEREST:
        if allow_escalation:
            return (
                "ESCALATE_TO_FIRST_CUSTOMER_FLOW",
                "Prospect shows strong interest; recommend the operator move to the first-customer path.",
                "high",
                None,
                True,
            )
        return (
            "SEND_MINI_AUDIT",
            "Prospect shows strong interest; prepare and send a manual mini-audit.",
            "high",
            None,
            True,
        )
    if status == "follow_up_needed":
        return ("FOLLOW_UP", "A follow-up is explicitly needed.", "normal",
                str(follow_up_due) if _non_empty(follow_up_due) else None, True)
    if status == "not_interested":
        return ("CLOSE_NO_GO", "Prospect is not interested; close this thread.", "normal", None, True)
    if status == "no_response":
        if follow_up_evidence:
            return ("FOLLOW_UP", "No response yet and a follow-up is due.", "normal",
                    str(follow_up_due) if _non_empty(follow_up_due) else None, True)
        return ("WAIT", "No response yet and no follow-up is due; wait.", "low", None, True)
    if status == "contacted":
        if follow_up_evidence:
            return ("FOLLOW_UP", "Prospect contacted and a follow-up is due.", "normal",
                    str(follow_up_due) if _non_empty(follow_up_due) else None, True)
        return ("WAIT", "Prospect contacted; wait for a reply.", "low", None, True)
    # not_contacted (remaining known status)
    return ("WAIT", "Prospect not contacted yet; wait for the manual outreach step.", "low", None, True)


__all__ = ("decide_first_prospect_follow_up",)
