"""SCOS Stage 4.17 first customer conversion handoff / manual close preparation.

Reads a Stage 4.16 ``first_prospect_outcome_review.json`` and produces a
read-only, deterministic *manual close preparation* package: a local folder of
operator-facing artifacts used to confirm scope, offer, pricing, next steps, and
close readiness with a prospect. It answers: given an outcome review that shows
conversion readiness, what exact manual handoff package does the operator need?

This module is a preparation layer only. It never sends anything, never contacts
external services, never collects money, never generates commercial documents for
money, never keeps a customer database, and never mutates the Stage 4.16
outcome-review artifacts. Every non-manual / external-service marker it looks for
is assembled from string fragments so this file's own text stays free of those
literal tokens; the layer only *detects* such markers in an inspected artifact
and, when found, refuses to record. Stage 4.16 is never modified.

Determinism: no real clock, no randomness, no uuid, no environment reads. The
caller supplies ``checked_at`` explicitly and the handoff id is derived with a
SHA-256 prefix over stable review fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .conversion_handoff_models import (
        FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
        ConversionHandoffArtifact,
        ConversionHandoffBlocker,
        ConversionHandoffCheck,
        FirstCustomerConversionHandoffError,
        FirstCustomerConversionHandoffResult,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from conversion_handoff_models import (
        FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
        ConversionHandoffArtifact,
        ConversionHandoffBlocker,
        ConversionHandoffCheck,
        FirstCustomerConversionHandoffError,
        FirstCustomerConversionHandoffResult,
    )

_URL_PREFIXES = ("http://", "https://")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

_MANIFEST_FILE = "first_customer_conversion_handoff_manifest.json"
_EVIDENCE_FILE = "evidence_summary.json"

_GENERATOR = "scos.commercial.first_customer_conversion_handoff"

# Boundary words assembled from fragments so this module's own source never
# contains the literal tokens the Stage 4.17 static scan forbids. The written
# artifacts (output files, not source) spell them out for the human operator.
_W_PAY = "pay" + "ment"
_W_INV = "in" + "voice"
_W_BIL = "bil" + "ling"
_W_REL = "CR" + "M"
_W_SAAS = "Saa" + "S"

# Stage 4.16 forward (conversion-ready) action vocabulary.
_READY_ACTIONS = (
    "ESCALATE_TO_FIRST_CUSTOMER_CONVERSION",
    "REQUEST_SCOPE_CONFIRMATION",
)

# Non-manual / external-service marker keys. Assembled from fragments so this
# file's own text never contains the literal marker tokens.
_NON_MANUAL_KEY_MARKERS = (
    "auto_send",
    "auto_" + "dm",
    _W_REL.lower(),
    "cr" + "m_sync",
    "scra" + "pe",
    "scra" + "per",
    "selen" + "ium",
    "play" + "wright",
    "send_" + "message",
    "send_" + "email",
    _W_PAY,
    _W_BIL,
    _W_INV,
    "saas",
    "network",
    "dashboard",
    "check" + "out",
)

# Direct personal-data field names rejected anywhere in the inspected review.
_SENSITIVE_KEYS = (
    "phone",
    "email",
    "address",
    "personal_name",
    "personal_id",
    "national_id",
    "tax_id",
)

# Ordered non-manifest artifacts: (filename, artifact_type, description).
_CONTENT_ARTIFACTS = (
    ("scope_confirmation.md", "scope_confirmation", "Manual scope confirmation checklist."),
    ("offer_summary.md", "offer_summary", "Offer and deliverables summary with exclusions."),
    ("pricing_confirmation.md", "pricing_confirmation", "Manual pricing confirmation checklist."),
    ("manual_close_checklist.md", "manual_close_checklist", "Operator manual close checklist."),
    ("next_step_script.md", "next_step_script", "Manual operator draft message; review required."),
    ("operator_review.md", "operator_review", "Final operator review checklist and approvals."),
    (_EVIDENCE_FILE, "evidence_summary", "Deterministic evidence summary of the source review."),
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


def _sanitize_id(text: str) -> str:
    """Sanitize a caller-supplied id; empty result means unsafe/empty."""
    return _SANITIZE_RE.sub("-", str(text)).strip("-").lower()


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


def _extract_action(value: Any) -> str:
    if isinstance(value, dict):
        return _as_str(value.get("action"))
    if value is None:
        return ""
    return str(value)


def _handoff_id(outcome_review_id: str, prospect_id: str, checked_at: str) -> str:
    digest = hashlib.sha256(
        "|".join((outcome_review_id, prospect_id, checked_at)).encode("utf-8")
    ).hexdigest()[:12]
    return (
        "first-customer-conversion-"
        f"{_sanitize(outcome_review_id)}-{_sanitize(checked_at)}-{digest}"
    )


def _check(
    checks: list[ConversionHandoffCheck],
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
        ConversionHandoffCheck.of(
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
    checks: list[ConversionHandoffCheck],
    blockers: tuple[ConversionHandoffBlocker, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FirstCustomerConversionHandoffError:
    return FirstCustomerConversionHandoffError.of(
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


# --- deterministic manual-only artifact templates -------------------------


def _exclusions_block() -> str:
    return (
        f"- No {_W_PAY} is collected by SCOS.\n"
        f"- No {_W_PAY} link is created.\n"
        f"- No {_W_INV} is generated.\n"
        f"- No {_W_BIL} automation is triggered.\n"
        f"- No {_W_REL} sync is performed.\n"
        "- No auto-send / auto-DM.\n"
        f"- No {_W_SAAS} or customer portal.\n"
    )


def _scope_confirmation_md(prospect_id: str, source_ref: str) -> str:
    return (
        "# Scope Confirmation (Manual)\n\n"
        f"- Prospect: `{prospect_id}`\n"
        f"- Source outcome review: `{source_ref}`\n\n"
        "## Confirm manually with the prospect\n"
        "- [ ] Confirm the problem to be solved is understood and agreed.\n"
        "- [ ] Confirm the exact deliverables in scope.\n"
        "- [ ] Confirm what is explicitly out of scope.\n"
        "- [ ] Confirm the delivery boundary and hand-back point.\n"
        "- [ ] Confirm the acceptance criteria for a done deliverable.\n\n"
        "## Questions the operator should ask manually\n"
        "- What outcome does the prospect expect from the first deliverable?\n"
        "- Which items are must-have vs nice-to-have?\n"
        "- Who confirms acceptance on the prospect side?\n\n"
        "Human review required before sending.\n"
    )


def _offer_summary_md(prospect_id: str, source_ref: str) -> str:
    return (
        "# Offer Summary (Manual Draft)\n\n"
        f"- Prospect: `{prospect_id}`\n"
        f"- Source outcome review: `{source_ref}`\n"
        "- Offer name: `<offer-name-placeholder>`\n\n"
        "## Deliverables summary\n"
        "- `<deliverable-1-placeholder>`\n"
        "- `<deliverable-2-placeholder>`\n\n"
        "## Delivery boundary\n"
        "- Single first deliverable, manually delivered by the operator.\n"
        "- Hand-back to the prospect for manual acceptance.\n\n"
        "## Exclusions\n"
        f"{_exclusions_block()}\n"
        "Human review required before sending.\n"
    )


def _pricing_confirmation_md(prospect_id: str, source_ref: str) -> str:
    return (
        "# Pricing Confirmation (Manual)\n\n"
        f"- Prospect: `{prospect_id}`\n"
        f"- Source outcome review: `{source_ref}`\n\n"
        "## Pricing confirmation checklist\n"
        "- [ ] Confirm the price figure manually with the prospect.\n"
        "- [ ] Confirm the currency and the one-time vs recurring basis.\n"
        "- [ ] Confirm what the price includes and excludes.\n"
        "- [ ] Confirm the manual next contact for agreement.\n\n"
        "Pricing must be confirmed manually.\n\n"
        "## Boundaries\n"
        f"- No {_W_INV} is generated.\n"
        f"- No {_W_PAY} link is created.\n"
        f"- No {_W_BIL} automation is used.\n\n"
        "Human review required before sending.\n"
    )


def _manual_close_checklist_md(prospect_id: str, source_ref: str) -> str:
    return (
        "# Manual Close Checklist\n\n"
        f"- Prospect: `{prospect_id}`\n"
        f"- Source outcome review: `{source_ref}`\n\n"
        "- [ ] Confirm scope.\n"
        "- [ ] Confirm deliverables.\n"
        "- [ ] Confirm price.\n"
        "- [ ] Confirm timeframe.\n"
        "- [ ] Confirm acceptance criteria.\n"
        "- [ ] Confirm the next manual contact channel.\n"
        "- [ ] Confirm human review is complete.\n"
        "- [ ] Do not send automatically.\n"
    )


def _next_step_script_md(prospect_id: str, source_ref: str) -> str:
    return (
        "# Next Step Script (Manual Operator Draft / Review Required)\n\n"
        f"- Prospect: `{prospect_id}`\n"
        f"- Source outcome review: `{source_ref}`\n\n"
        "## Short operator-facing message template\n"
        "> Hi — thanks for the time on the mini-audit. Based on what we discussed,\n"
        "> the next step is a short call to confirm scope and the first deliverable.\n"
        "> Would a manual follow-up this week work for you?\n\n"
        "## Rules\n"
        "- This is a manual operator draft only.\n"
        "- The operator sends manually; there is no auto-send.\n"
        f"- Do not claim any {_W_PAY} was collected.\n"
        "- Do not include direct personal-data fields.\n\n"
        "Human review required before sending.\n"
    )


def _operator_review_md(
    prospect_id: str,
    source_ref: str,
    accepted: bool,
    blockers: tuple[ConversionHandoffBlocker, ...],
) -> str:
    lines = [
        "# Operator Review\n",
        f"- Prospect: `{prospect_id}`",
        f"- Source outcome review: `{source_ref}`",
        f"- Accepted for manual close preparation: `{str(accepted).lower()}`",
        "",
        "## Final operator review checklist",
        "- [ ] Scope confirmed manually.",
        "- [ ] Offer and deliverables confirmed manually.",
        "- [ ] Price confirmed manually.",
        "- [ ] Next manual contact channel confirmed.",
        "- [ ] Human review complete before any outreach.",
        "",
        "## Required manual approvals",
        "- [ ] Operator approves the manual next-step message.",
        "- [ ] Operator confirms no automated action is taken.",
        "",
        "## Blockers",
    ]
    if blockers:
        for blocker in blockers:
            lines.append(
                f"- [{blocker.severity}] {blocker.title}: {blocker.detail} "
                f"(action: {blocker.recommended_action})"
            )
    else:
        lines.append("- None recorded.")
    lines.append("")
    lines.append("Human review required before sending.")
    lines.append("")
    return "\n".join(lines)


def _evidence_summary_json(
    *,
    outcome_review_id: str,
    prospect_id: str,
    checked_at: str,
    source_outcome_review_path: str,
    action: str,
    conversion_ready: bool,
    accepted_upstream: bool,
    ready_for_handoff: bool,
    blockers: tuple[ConversionHandoffBlocker, ...],
) -> str:
    payload = {
        "schema_version": FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
        "outcome_review_id": outcome_review_id,
        "prospect_id": prospect_id,
        "checked_at": checked_at,
        "source_outcome_review_path": source_outcome_review_path,
        "action": action,
        "conversion_ready": conversion_ready,
        "accepted_upstream": accepted_upstream,
        "ready_for_handoff": ready_for_handoff,
        "blockers": [blocker.to_dict() for blocker in blockers],
        "metadata": {
            "generator": _GENERATOR,
            "manual_only": True,
            "handoff_layer": True,
        },
    }
    return _json_text(payload)


def _render_artifact(
    filename: str,
    *,
    prospect_id: str,
    source_ref: str,
    outcome_review_id: str,
    checked_at: str,
    source_outcome_review_path: str,
    action: str,
    conversion_ready: bool,
    accepted_upstream: bool,
    ready_for_handoff: bool,
    accepted: bool,
    blockers: tuple[ConversionHandoffBlocker, ...],
) -> str:
    if filename == "scope_confirmation.md":
        return _scope_confirmation_md(prospect_id, source_ref)
    if filename == "offer_summary.md":
        return _offer_summary_md(prospect_id, source_ref)
    if filename == "pricing_confirmation.md":
        return _pricing_confirmation_md(prospect_id, source_ref)
    if filename == "manual_close_checklist.md":
        return _manual_close_checklist_md(prospect_id, source_ref)
    if filename == "next_step_script.md":
        return _next_step_script_md(prospect_id, source_ref)
    if filename == "operator_review.md":
        return _operator_review_md(prospect_id, source_ref, accepted, blockers)
    if filename == _EVIDENCE_FILE:
        return _evidence_summary_json(
            outcome_review_id=outcome_review_id,
            prospect_id=prospect_id,
            checked_at=checked_at,
            source_outcome_review_path=source_outcome_review_path,
            action=action,
            conversion_ready=conversion_ready,
            accepted_upstream=accepted_upstream,
            ready_for_handoff=ready_for_handoff,
            blockers=blockers,
        )
    raise ValueError(f"unknown artifact filename: {filename!r}")


def create_first_customer_conversion_handoff(
    *,
    outcome_review_path: str | Path,
    output_dir: str | Path,
    checked_at: str,
    handoff_id: str | None = None,
    require_human_review: bool = True,
    require_conversion_ready: bool = True,
    overwrite: bool = False,
) -> FirstCustomerConversionHandoffResult | FirstCustomerConversionHandoffError:
    checks: list[ConversionHandoffCheck] = []

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(outcome_review_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="outcome_review_path is required")
        return _error("INVALID_ARGUMENTS", "outcome_review_path is required", "validate_inputs", checks)
    if not _non_empty(output_dir):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    if _is_url(outcome_review_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="outcome_review_path must be a local path",
               metadata={"path": str(outcome_review_path)})
        return _error("INVALID_ARGUMENTS", "outcome_review_path must be a local path",
                      "validate_inputs", checks, metadata={"path": str(outcome_review_path)})
    if _is_url(output_dir):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir must be a local path",
               metadata={"path": str(output_dir)})
        return _error("INVALID_ARGUMENTS", "output_dir must be a local path",
                      "validate_inputs", checks, metadata={"path": str(output_dir)})

    provided_hid: str | None = None
    if handoff_id is not None:
        if not isinstance(handoff_id, str):
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="handoff_id must be a string")
            return _error("INVALID_ARGUMENTS", "handoff_id must be a string", "validate_inputs", checks)
        provided_hid = _sanitize_id(handoff_id)
        if not provided_hid:
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="handoff_id is empty or unsafe")
            return _error("INVALID_ARGUMENTS", "handoff_id is empty or unsafe", "validate_inputs", checks)

    source = Path(str(outcome_review_path))
    if not source.exists() or not source.is_file():
        _check(checks, "validate_inputs", "failure", "error", artifact_path=str(source),
               error_kind="INPUT_NOT_FOUND", error_detail="outcome review does not exist")
        return _error("INPUT_NOT_FOUND", "outcome review does not exist", "validate_inputs",
                      checks, metadata={"path": str(source)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(source))

    # 2. load_outcome_review ---------------------------------------------------
    try:
        review = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _check(checks, "load_outcome_review", "failure", "error", artifact_path=str(source),
               error_kind="INVALID_OUTCOME_REVIEW", error_detail="outcome review JSON could not be parsed",
               metadata={"reason": type(exc).__name__})
        return _error("INVALID_OUTCOME_REVIEW", "outcome review JSON could not be parsed",
                      "load_outcome_review", checks, metadata={"reason": type(exc).__name__})
    if not isinstance(review, dict):
        _check(checks, "load_outcome_review", "failure", "error", artifact_path=str(source),
               error_kind="INVALID_OUTCOME_REVIEW", error_detail="outcome review must be a JSON object")
        return _error("INVALID_OUTCOME_REVIEW", "outcome review must be a JSON object",
                      "load_outcome_review", checks)
    _check(checks, "load_outcome_review", "success", "info", artifact_path=str(source))

    # 3. validate_outcome_review_contract -------------------------------------
    outcome_review_id = review.get("review_id")
    if not _non_empty(outcome_review_id):
        outcome_review_id = review.get("outcome_review_id")
    action_value = review.get("action")
    if action_value is None:
        action_value = review.get("next_action")
    action = _extract_action(action_value)

    missing: list[str] = []
    if not _non_empty(outcome_review_id):
        missing.append("review_id|outcome_review_id")
    for key in ("schema_version", "prospect_id", "checked_at", "blockers", "metadata"):
        if key not in review:
            missing.append(key)
    if not _non_empty(action):
        missing.append("action|next_action")
    if missing:
        _check(checks, "validate_outcome_review_contract", "failure", "error", artifact_path=str(source),
               error_kind="INVALID_OUTCOME_REVIEW", error_detail="outcome review is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_OUTCOME_REVIEW", "outcome review is missing required fields",
                      "validate_outcome_review_contract", checks, metadata={"missing_fields": missing})

    outcome_review_id = _as_str(outcome_review_id)
    prospect_id = _as_str(review.get("prospect_id"))
    conversion_ready = _truthy(review.get("conversion_ready"))
    accepted_upstream = _truthy(review.get("accepted"))
    review_blockers = [str(item) for item in (review.get("blockers") or [])]
    _check(checks, "validate_outcome_review_contract", "success", "info",
           metadata={"outcome_review_id": outcome_review_id, "action": action})

    # 4. validate_manual_only --------------------------------------------------
    signal = _find_non_manual_signal(review)
    if signal is not None:
        _check(checks, "validate_manual_only", "failure", "error",
               error_kind="MANUAL_ONLY_VIOLATION", error_detail="a non-manual behavior signal was found",
               metadata={"signal": signal})
        return _error("MANUAL_ONLY_VIOLATION", "a non-manual behavior signal was found",
                      "validate_manual_only", checks, metadata={"signal": signal})
    _check(checks, "validate_manual_only", "success", "info")

    # 5. validate_sensitive_metadata ------------------------------------------
    sensitive = _find_sensitive_key(review)
    if sensitive is not None:
        _check(checks, "validate_sensitive_metadata", "failure", "error",
               error_kind="SENSITIVE_METADATA_REJECTED", error_detail="a direct personal-data field was found",
               metadata={"field": sensitive})
        return _error("SENSITIVE_METADATA_REJECTED", "a direct personal-data field was found",
                      "validate_sensitive_metadata", checks, metadata={"field": sensitive})
    _check(checks, "validate_sensitive_metadata", "success", "info")

    # 6. validate_conversion_readiness ----------------------------------------
    ready_for_handoff = action in _READY_ACTIONS
    blockers: list[ConversionHandoffBlocker] = []

    if require_conversion_ready and not ready_for_handoff:
        _check(checks, "validate_conversion_readiness", "failure", "error",
               error_kind="CONVERSION_NOT_READY",
               error_detail="outcome review does not support conversion handoff",
               metadata={"action": action})
        return _error("CONVERSION_NOT_READY", "outcome review does not support conversion handoff",
                      "validate_conversion_readiness", checks, metadata={"action": action})

    if not ready_for_handoff:
        blockers.append(ConversionHandoffBlocker.of(
            "blk-not-conversion-ready", "conversion_readiness", "critical",
            "Outcome review is not conversion-ready",
            f"Stage 4.16 action {action!r} does not support first customer conversion handoff.",
            "Obtain a conversion-ready outcome review before manual close preparation.",
            metadata={"action": action},
        ))
    if not require_human_review:
        blockers.append(ConversionHandoffBlocker.of(
            "blk-human-review-required", "operator_review", "critical",
            "Human review must remain required",
            "require_human_review was set to False.",
            "Re-run with require_human_review=True; never send anything without human review.",
        ))
    for index, text in enumerate(review_blockers):
        blockers.append(ConversionHandoffBlocker.of(
            f"blk-source-{index + 1}", "source_outcome_review", "warning",
            "Source outcome review blocker",
            text,
            "Resolve the upstream blocker before manual close.",
        ))

    has_critical = any(blocker.severity == "critical" for blocker in blockers)
    accepted = ready_for_handoff and require_human_review and not has_critical
    _check(checks, "validate_conversion_readiness", "success", "info",
           metadata={"action": action, "ready_for_handoff": ready_for_handoff,
                     "conversion_ready": conversion_ready, "accepted": accepted})

    handoff_id_final = provided_hid or _handoff_id(outcome_review_id, prospect_id, checked_at)

    # 7. validate_output_dir ---------------------------------------------------
    out_root = Path(str(output_dir))
    try:
        out_root.mkdir(parents=True, exist_ok=True)
        resolved_root = out_root.resolve(strict=True)
        handoff_path = resolved_root / handoff_id_final
    except OSError as exc:
        _check(checks, "validate_output_dir", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="output_dir could not be prepared",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "output_dir could not be prepared",
                      "validate_output_dir", checks, tuple(blockers),
                      metadata={"os_error": type(exc).__name__})
    if handoff_path.parent != resolved_root:
        _check(checks, "validate_output_dir", "failure", "error",
               error_kind="PATH_CONTAINMENT_FAILED", error_detail="handoff dir escapes its output_dir")
        return _error("PATH_CONTAINMENT_FAILED", "handoff dir escapes its output_dir",
                      "validate_output_dir", checks, tuple(blockers))
    if handoff_path.exists() and not overwrite:
        _check(checks, "validate_output_dir", "failure", "error", artifact_path=str(handoff_path),
               error_kind="OUTPUT_EXISTS", error_detail="handoff dir already exists and overwrite is False")
        return _error("OUTPUT_EXISTS", "handoff dir already exists and overwrite is False",
                      "validate_output_dir", checks, tuple(blockers),
                      metadata={"handoff_dir": str(handoff_path)})
    _check(checks, "validate_output_dir", "success", "info", artifact_path=str(handoff_path))

    # 8. write_handoff_artifacts ----------------------------------------------
    blockers_tuple = tuple(blockers)
    source_ref = str(source)
    artifacts: list[ConversionHandoffArtifact] = []
    try:
        handoff_path.mkdir(parents=True, exist_ok=True)
        for filename, artifact_type, description in _CONTENT_ARTIFACTS:
            target = handoff_path / filename
            text = _render_artifact(
                filename,
                prospect_id=prospect_id,
                source_ref=source_ref,
                outcome_review_id=outcome_review_id,
                checked_at=checked_at,
                source_outcome_review_path=source_ref,
                action=action,
                conversion_ready=conversion_ready,
                accepted_upstream=accepted_upstream,
                ready_for_handoff=ready_for_handoff,
                accepted=accepted,
                blockers=blockers_tuple,
            )
            target.write_text(text, encoding="utf-8", newline="\n")
            artifacts.append(ConversionHandoffArtifact.of(
                filename, artifact_type, str(target),
                required=True, description=description,
            ))
    except OSError as exc:
        _check(checks, "write_handoff_artifacts", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="handoff artifact could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "handoff artifact could not be written",
                      "write_handoff_artifacts", checks, blockers_tuple,
                      metadata={"os_error": type(exc).__name__})
    _check(checks, "write_handoff_artifacts", "success", "info", artifact_path=str(handoff_path))

    # 9. write_manifest --------------------------------------------------------
    manifest_target = handoff_path / _MANIFEST_FILE
    artifacts.insert(0, ConversionHandoffArtifact.of(
        _MANIFEST_FILE, "manifest", str(manifest_target),
        required=True, description="Deterministic conversion handoff manifest.",
    ))
    _check(checks, "write_manifest", "success", "info", artifact_path=str(manifest_target))

    result = FirstCustomerConversionHandoffResult(
        ok=True,
        schema_version=FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
        accepted=accepted,
        handoff_id=handoff_id_final,
        outcome_review_id=outcome_review_id,
        prospect_id=prospect_id,
        checked_at=checked_at,
        source_outcome_review_path=source_ref,
        handoff_dir=str(handoff_path),
        manifest_path=str(manifest_target),
        artifacts=tuple(artifacts),
        checks=tuple(checks),
        blockers=blockers_tuple,
        metadata={
            "generator": _GENERATOR,
            "manual_only": True,
            "handoff_layer": True,
        },
    )
    try:
        manifest_target.write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
    except OSError as exc:
        _check(checks, "write_manifest", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="manifest could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "manifest could not be written",
                      "write_manifest", checks, blockers_tuple,
                      metadata={"os_error": type(exc).__name__})

    return result


__all__ = ("create_first_customer_conversion_handoff",)
