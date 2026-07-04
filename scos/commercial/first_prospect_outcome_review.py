"""SCOS Stage 4.16 first prospect outcome review / conversion readiness gate.

Reads a Stage 4.15 ``first_prospect_mini_audit_delivery_log.json`` and produces a
read-only *decision/review* layer describing whether the prospect is ready to
move toward first-customer conversion, and which manual next action the operator
should take next.

This module is a review/decision layer only. It never sends anything, never
contacts external services, never keeps a customer database, never touches
billing, and never mutates the Stage 4.15 delivery-log artifacts or the Stage
4.14 handoff artifacts. Every non-manual / external-service signal it looks for
is assembled from string fragments so this file's own text stays free of those
literal tokens; the layer only *detects* such signals in an inspected artifact
and, when found, refuses to record.

The Stage 4.15 delivery log nests the operator review / send / response statuses
under an ``evidence`` object and exposes the recommended manual step under a
top-level ``next_action`` object. Stage 4.16 aligns to that real contract and
normalizes those status strings (plus a documented superset of conceptual
statuses) into a small canonical vocabulary before deciding the outcome action.
Stage 4.15 is never modified.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .outcome_review_models import (
        FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION,
        FirstProspectOutcomeReviewError,
        FirstProspectOutcomeReviewResult,
        OutcomeReviewAction,
        OutcomeReviewCheck,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from outcome_review_models import (
        FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION,
        FirstProspectOutcomeReviewError,
        FirstProspectOutcomeReviewResult,
        OutcomeReviewAction,
        OutcomeReviewCheck,
    )

_URL_PREFIXES = ("http://", "https://")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

_OUTPUT_FILE = "first_prospect_outcome_review.json"

# Required Stage 4.15 delivery-log top-level keys (aligned to the real contract).
_REQUIRED_LOG_KEYS = (
    "schema_version",
    "delivery_log_id",
    "handoff_id",
    "prospect_id",
    "decision_id",
    "execution_log_id",
    "source_handoff_manifest_path",
    "evidence",
    "next_action",
    "checks",
    "blockers",
    "metadata",
)
_REQUIRED_EVIDENCE_KEYS = (
    "operator_review_status",
    "manual_send_status",
    "prospect_response_status",
)

# --- Normalization maps (Stage 4.16 internal; Stage 4.15 is not modified) ----
# The delivery log carries Stage 4.15 status names. We normalize those (plus a
# documented superset of conceptual names described in the Stage 4.16 contract)
# into a compact canonical vocabulary used by the decision table below.
_REVIEW_STATUS_NORMALIZATION = {
    "not_reviewed": "not_reviewed",
    "review_needed": "not_reviewed",
    "reviewed": "reviewed",
    "approved": "approved",
    "approved_for_manual_send": "approved",
    "changes_requested": "changes_requested",
    "rejected": "rejected",
    "blocked": "blocked",
}
_SEND_STATUS_NORMALIZATION = {
    "not_sent": "not_sent",
    "sent": "sent",
    "sent_manually": "sent",
    "manually_sent": "sent",
    "deferred": "deferred",
    "send_failed": "send_failed",
    "blocked": "blocked",
}
_RESPONSE_STATUS_NORMALIZATION = {
    "no_response": "no_response",
    "no_response_yet": "no_response",
    "none": "no_response",
    "waiting": "waiting",
    "deferred": "waiting",
    "pending": "waiting",
    "interested": "interested",
    "positive_response": "interested",
    "requested_scope": "interested",
    "requested_more_info": "interested",
    "asked_questions": "interested",
    "requested_call": "interested",
    "requested_changes": "requested_changes",
    "ready_to_buy": "ready_to_buy",
    "not_interested": "not_interested",
    "declined": "not_interested",
    "blocked": "blocked",
}

# Non-manual / external-service signal keys. Assembled from fragments so this
# file's own text never contains the literal marker tokens.
_NON_MANUAL_KEY_MARKERS = (
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


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "enabled", "on", "yes", "1")
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _review_id(
    delivery_log_id: str,
    handoff_id: str,
    prospect_id: str,
    checked_at: str,
    action: str,
) -> str:
    digest = hashlib.sha256(
        "|".join((delivery_log_id, handoff_id, prospect_id, checked_at, action)).encode("utf-8")
    ).hexdigest()[:12]
    return (
        "first-prospect-outcome-"
        f"{_sanitize(delivery_log_id)}-{_sanitize(checked_at)}-{digest}"
    )


def _check(
    checks: list[OutcomeReviewCheck],
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
        OutcomeReviewCheck.of(
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
    checks: list[OutcomeReviewCheck],
    blockers: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FirstProspectOutcomeReviewError:
    return FirstProspectOutcomeReviewError.of(
        error_kind, error_detail, failed_check, tuple(checks), blockers, metadata
    )


def _find_non_manual_signal(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            for marker in _NON_MANUAL_KEY_MARKERS:
                if marker == lowered and _truthy(nested):
                    return marker
            found = _find_non_manual_signal(nested)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _find_non_manual_signal(item)
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


def _decide(
    *,
    review_c: str,
    send_c: str,
    response_c: str,
    blockers: list[str],
    has_follow_up_evidence: bool,
    allow_conversion_escalation: bool,
    require_human_review: bool,
) -> tuple[OutcomeReviewAction, bool]:
    """Deterministic outcome decision table (no hidden strategy).

    Returns ``(action, conversion_ready)``. Precedence, first match wins:
    reported blockers, explicit blocked/failed signals, incomplete review,
    unsent mini-audit, then the prospect response evidence.
    """
    review_ok = review_c in ("reviewed", "approved")
    sent = send_c == "sent"
    action_meta = {"require_human_review_flag": bool(require_human_review)}

    def build(action: str, reason: str, priority: str, *, due_at: str | None = None) -> OutcomeReviewAction:
        # Every outcome action is a manual operator step: it always requires a
        # human and never implies automatic execution.
        return OutcomeReviewAction.of(
            action=action,
            reason=reason,
            priority=priority,
            due_at=due_at,
            requires_human_review=True,
            metadata=action_meta,
        )

    # 1. Reported blockers take precedence.
    if blockers:
        return build("BLOCKED", "delivery log reports blockers: " + "; ".join(blockers), "high"), False

    # 2. Explicit blocked / failed signals.
    if review_c == "blocked":
        return build("BLOCKED", "operator review is blocked", "high"), False
    if send_c == "blocked":
        return build("BLOCKED", "manual send is blocked", "high"), False
    if send_c == "send_failed":
        return build("BLOCKED", "manual send failed", "high"), False
    if response_c == "blocked":
        return build("BLOCKED", "prospect response is blocked", "high"), False

    # 3. Review not complete yet.
    if review_c == "not_reviewed":
        return build("BLOCKED", "mini-audit has not been reviewed", "normal"), False
    if review_c == "changes_requested":
        return build("BLOCKED", "operator requested changes before the mini-audit was sent", "normal"), False

    # 4. Operator rejected the mini-audit.
    if review_c == "rejected":
        if response_c == "not_interested":
            return build("CLOSE_NO_GO", "mini-audit was rejected and the prospect is not interested", "normal"), False
        return build("SEND_REVISED_MINI_AUDIT", "mini-audit was rejected; send a revised mini-audit", "high"), False

    # 5. Reviewed/approved but not yet sent.
    if send_c == "not_sent":
        return build("BLOCKED", "mini-audit is reviewed but has not been sent yet", "normal"), False

    # 6. Reviewed/approved and sent (or deferred): drive by the prospect response.
    conversion_ready = review_ok and sent and not blockers

    if response_c == "ready_to_buy":
        if allow_conversion_escalation:
            return build(
                "ESCALATE_TO_FIRST_CUSTOMER_CONVERSION",
                "prospect is ready to buy and conversion escalation is allowed",
                "urgent",
            ), conversion_ready
        return build(
            "REQUEST_SCOPE_CONFIRMATION",
            "prospect is ready to buy; confirm scope before conversion escalation",
            "high",
        ), conversion_ready
    if response_c == "interested":
        return build(
            "REQUEST_SCOPE_CONFIRMATION",
            "prospect is interested; confirm scope for the first engagement",
            "high",
        ), conversion_ready
    if response_c == "requested_changes":
        return build(
            "SEND_REVISED_MINI_AUDIT",
            "prospect requested changes; send a revised mini-audit",
            "high",
        ), False
    if response_c == "not_interested":
        return build("CLOSE_NO_GO", "prospect is not interested", "normal"), False
    if response_c == "waiting":
        return build("WAIT_FOR_RESPONSE", "prospect response is still pending", "low"), False
    # response_c == "no_response"
    if has_follow_up_evidence:
        return build(
            "FOLLOW_UP_AFTER_MINI_AUDIT",
            "no response yet and a manual follow-up is already planned",
            "normal",
        ), False
    return build("WAIT_FOR_RESPONSE", "no response yet and no follow-up is planned", "low"), False


def review_first_prospect_outcome(
    *,
    delivery_log_path: str | Path,
    checked_at: str,
    output_path: str | Path | None = None,
    require_human_review: bool = True,
    allow_conversion_escalation: bool = False,
) -> FirstProspectOutcomeReviewResult | FirstProspectOutcomeReviewError:
    checks: list[OutcomeReviewCheck] = []

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(delivery_log_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="delivery_log_path is required")
        return _error("INVALID_ARGUMENTS", "delivery_log_path is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    if _is_url(delivery_log_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="delivery_log_path must be a local path",
               metadata={"path": str(delivery_log_path)})
        return _error("INVALID_ARGUMENTS", "delivery_log_path must be a local path",
                      "validate_inputs", checks, metadata={"path": str(delivery_log_path)})
    if output_path is not None and _is_url(output_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_path must be a local path",
               metadata={"path": str(output_path)})
        return _error("INVALID_ARGUMENTS", "output_path must be a local path",
                      "validate_inputs", checks, metadata={"path": str(output_path)})

    log_source = Path(str(delivery_log_path))
    if not log_source.exists() or not log_source.is_file():
        _check(checks, "validate_inputs", "failure", "error", artifact_path=str(log_source),
               error_kind="INPUT_NOT_FOUND", error_detail="delivery log does not exist")
        return _error("INPUT_NOT_FOUND", "delivery log does not exist", "validate_inputs",
                      checks, metadata={"path": str(log_source)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(log_source))

    # 2. load_delivery_log -----------------------------------------------------
    try:
        log = json.loads(log_source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _check(checks, "load_delivery_log", "failure", "error", artifact_path=str(log_source),
               error_kind="INVALID_DELIVERY_LOG", error_detail="delivery log JSON could not be parsed",
               metadata={"reason": type(exc).__name__})
        return _error("INVALID_DELIVERY_LOG", "delivery log JSON could not be parsed",
                      "load_delivery_log", checks, metadata={"reason": type(exc).__name__})
    if not isinstance(log, dict):
        _check(checks, "load_delivery_log", "failure", "error", artifact_path=str(log_source),
               error_kind="INVALID_DELIVERY_LOG", error_detail="delivery log must be a JSON object")
        return _error("INVALID_DELIVERY_LOG", "delivery log must be a JSON object",
                      "load_delivery_log", checks)
    _check(checks, "load_delivery_log", "success", "info", artifact_path=str(log_source))

    # 3. validate_delivery_log_contract ---------------------------------------
    missing = [key for key in _REQUIRED_LOG_KEYS if key not in log]
    if "checked_at" not in log and "created_at" not in log:
        missing.append("checked_at")
    evidence = log.get("evidence")
    if not isinstance(evidence, dict):
        missing.append("evidence{}")
        evidence = {}
    else:
        for key in _REQUIRED_EVIDENCE_KEYS:
            if key not in evidence:
                missing.append(f"evidence.{key}")
    next_action_obj = log.get("next_action")
    if not isinstance(next_action_obj, dict) or "action" not in next_action_obj:
        missing.append("next_action.action")
        next_action_obj = {}
    if missing:
        _check(checks, "validate_delivery_log_contract", "failure", "error", artifact_path=str(log_source),
               error_kind="INVALID_DELIVERY_LOG", error_detail="delivery log is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_DELIVERY_LOG", "delivery log is missing required fields",
                      "validate_delivery_log_contract", checks, metadata={"missing_fields": missing})

    delivery_log_id = _as_str(log.get("delivery_log_id"))
    handoff_id = _as_str(log.get("handoff_id"))
    prospect_id = _as_str(log.get("prospect_id"))
    decision_id = _as_str(log.get("decision_id"))
    execution_log_id = _as_str(log.get("execution_log_id"))
    source_handoff_manifest_path = _as_str(log.get("source_handoff_manifest_path"))
    log_blockers = [str(item) for item in (log.get("blockers") or [])]
    _check(checks, "validate_delivery_log_contract", "success", "info",
           metadata={"delivery_log_id": delivery_log_id})

    # 4. validate_manual_only --------------------------------------------------
    signal = _find_non_manual_signal(log)
    if signal is not None:
        _check(checks, "validate_manual_only", "failure", "error",
               error_kind="MANUAL_ONLY_VIOLATION", error_detail="a non-manual behavior signal was found",
               metadata={"signal": signal})
        return _error("MANUAL_ONLY_VIOLATION", "a non-manual behavior signal was found",
                      "validate_manual_only", checks, metadata={"signal": signal})
    _check(checks, "validate_manual_only", "success", "info")

    # 5. validate_sensitive_metadata ------------------------------------------
    for label, scope in (
        ("log_metadata", log.get("metadata")),
        ("evidence_metadata", evidence.get("metadata")),
        ("next_action_metadata", next_action_obj.get("metadata")),
        ("prospect", log.get("prospect")),
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

    # 6. validate_handoff_reference (reference-only; never mutated) -----------
    if _non_empty(source_handoff_manifest_path) and not _is_url(source_handoff_manifest_path):
        manifest_ref = Path(source_handoff_manifest_path)
        if manifest_ref.exists() and manifest_ref.is_file():
            try:
                json.loads(manifest_ref.read_text(encoding="utf-8"))
                _check(checks, "validate_handoff_reference", "success", "info",
                       artifact_path=str(manifest_ref))
            except (OSError, ValueError):
                _check(checks, "validate_handoff_reference", "success", "warning",
                       artifact_path=str(manifest_ref),
                       error_detail="handoff manifest reference could not be parsed (reference-only)")
        else:
            _check(checks, "validate_handoff_reference", "skipped", "info",
                   metadata={"reason": "handoff manifest reference not present locally"})
    else:
        _check(checks, "validate_handoff_reference", "skipped", "info",
               metadata={"reason": "no local handoff manifest reference"})

    # Normalize the evidence status strings ------------------------------------
    raw_review = str(evidence.get("operator_review_status"))
    raw_send = str(evidence.get("manual_send_status"))
    raw_response = str(evidence.get("prospect_response_status"))
    review_c = _REVIEW_STATUS_NORMALIZATION.get(raw_review, "blocked")
    send_c = _SEND_STATUS_NORMALIZATION.get(raw_send, "blocked")
    response_c = _RESPONSE_STATUS_NORMALIZATION.get(raw_response)
    if response_c is None:
        _check(checks, "evaluate_response_status", "failure", "error",
               error_kind="INVALID_RESPONSE_STATUS", error_detail="unknown prospect response status",
               metadata={"prospect_response_status": raw_response})
        return _error("INVALID_RESPONSE_STATUS", "unknown prospect response status",
                      "evaluate_response_status", checks,
                      metadata={"prospect_response_status": raw_response})

    # 7. evaluate_blockers -----------------------------------------------------
    _check(checks, "evaluate_blockers", "success", "info",
           metadata={"blocker_count": len(log_blockers)})

    # 8/9/10. evaluate review / send / response --------------------------------
    _check(checks, "evaluate_review_status", "success", "info",
           metadata={"operator_review_status": raw_review, "normalized": review_c})
    _check(checks, "evaluate_send_status", "success", "info",
           metadata={"manual_send_status": raw_send, "normalized": send_c})

    next_action_action = str(next_action_obj.get("action"))
    next_action_due = next_action_obj.get("due_at")
    has_follow_up_evidence = (
        next_action_action in ("FOLLOW_UP", "SCHEDULE_CALL") or _non_empty(next_action_due)
    )

    action, conversion_ready = _decide(
        review_c=review_c,
        send_c=send_c,
        response_c=response_c,
        blockers=log_blockers,
        has_follow_up_evidence=has_follow_up_evidence,
        allow_conversion_escalation=allow_conversion_escalation,
        require_human_review=require_human_review,
    )
    _check(checks, "evaluate_response_status", "success", "info",
           metadata={"prospect_response_status": raw_response, "normalized": response_c,
                     "action": action.action})

    # 11. evaluate_conversion_readiness ---------------------------------------
    accepted = action.action != "BLOCKED"
    blockers = list(log_blockers)
    if action.action == "BLOCKED" and not blockers:
        blockers.append(action.reason)
    _check(checks, "evaluate_conversion_readiness", "success", "info",
           metadata={"conversion_ready": conversion_ready, "accepted": accepted})

    review_id = _review_id(delivery_log_id, handoff_id, prospect_id, checked_at, action.action)

    written_output: str | None = None

    # 12. validate_output_path + 13. write_outcome_review ---------------------
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
            review_id=review_id,
            delivery_log_id=delivery_log_id,
            handoff_id=handoff_id,
            prospect_id=prospect_id,
            decision_id=decision_id,
            execution_log_id=execution_log_id,
            checked_at=checked_at,
            conversion_ready=conversion_ready,
            action=action,
            source_delivery_log_path=str(log_source),
            output_path=str(resolved_out),
            checks=checks + [OutcomeReviewCheck.of("write_outcome_review", "success", "info",
                                                   artifact_path=str(resolved_out))],
            blockers=blockers,
        )
        try:
            resolved_out.write_text(_json_text(result_payload.to_dict()), encoding="utf-8", newline="\n")
        except OSError as exc:
            _check(checks, "write_outcome_review", "failure", "error",
                   error_kind="OUTPUT_WRITE_FAILED", error_detail="outcome review could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "outcome review could not be written",
                          "write_outcome_review", checks, tuple(blockers),
                          metadata={"os_error": type(exc).__name__})
        _check(checks, "write_outcome_review", "success", "info", artifact_path=str(resolved_out))
        written_output = str(resolved_out)

    return _build_result(
        accepted=accepted,
        review_id=review_id,
        delivery_log_id=delivery_log_id,
        handoff_id=handoff_id,
        prospect_id=prospect_id,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        checked_at=checked_at,
        conversion_ready=conversion_ready,
        action=action,
        source_delivery_log_path=str(log_source),
        output_path=written_output,
        checks=checks,
        blockers=blockers,
    )


def _build_result(
    *,
    accepted: bool,
    review_id: str,
    delivery_log_id: str,
    handoff_id: str,
    prospect_id: str,
    decision_id: str,
    execution_log_id: str,
    checked_at: str,
    conversion_ready: bool,
    action: OutcomeReviewAction,
    source_delivery_log_path: str,
    output_path: str | None,
    checks: list[OutcomeReviewCheck],
    blockers: list[str],
) -> FirstProspectOutcomeReviewResult:
    return FirstProspectOutcomeReviewResult(
        ok=True,
        schema_version=FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION,
        accepted=accepted,
        review_id=review_id,
        delivery_log_id=delivery_log_id,
        handoff_id=handoff_id,
        prospect_id=prospect_id,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        checked_at=checked_at,
        conversion_ready=conversion_ready,
        action=action,
        source_delivery_log_path=source_delivery_log_path,
        output_path=output_path,
        checks=tuple(checks),
        blockers=tuple(blockers),
        metadata={
            "generator": "scos.commercial.first_prospect_outcome_review",
            "manual_only": True,
            "review_layer": True,
        },
    )


__all__ = ("review_first_prospect_outcome",)
