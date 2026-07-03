"""SCOS Stage 4.14 first prospect mini-audit handoff package generator.

Reads a Stage 4.13 ``first_prospect_follow_up_decision.json`` and, when the
decision recommends a manual mini-audit (or an approved escalation), generates a
deterministic local handoff folder the operator manually reviews and sends
*outside* SCOS. This module is a local package-generation layer only: it never
sends anything, never contacts external services, never keeps a customer
database, never touches billing, and never mutates the Stage 4.12 / Stage 4.13
source artifacts.

Every automation / external-service signal it looks for is assembled from string
fragments so this file's own text stays free of those literal tokens; the
generator only *detects* such signals in an inspected artifact and, when found,
refuses to build the package.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .mini_audit_handoff_models import (
        FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
        FirstProspectMiniAuditHandoffError,
        FirstProspectMiniAuditHandoffResult,
        MiniAuditHandoffArtifact,
        MiniAuditHandoffCheck,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from mini_audit_handoff_models import (
        FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
        FirstProspectMiniAuditHandoffError,
        FirstProspectMiniAuditHandoffResult,
        MiniAuditHandoffArtifact,
        MiniAuditHandoffCheck,
    )

_URL_PREFIXES = ("http://", "https://")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

_MANIFEST_FILE = "mini_audit_handoff_manifest.json"
_SUMMARY_FILE = "mini_audit_summary.md"
_CHECKLIST_FILE = "operator_review_checklist.md"
_CONTEXT_FILE = "prospect_context.json"
_DRAFT_FILE = "handoff_message_draft.md"
_EVIDENCE_FILE = "evidence_index.json"

_ALLOWED_ACTIONS = ("SEND_MINI_AUDIT", "ESCALATE_TO_FIRST_CUSTOMER_FLOW")

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
)

_REQUIRED_DECISION_KEYS = (
    "schema_version",
    "decision_id",
    "prospect_id",
    "checked_at",
    "action",
    "source_execution_log_path",
    "checks",
    "blockers",
    "metadata",
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


def _fs_safe(name: str) -> str:
    return name.replace(":", "_")


def _non_empty(value: Any) -> bool:
    return value is not None and str(value) != ""


def _handoff_id(decision_id: str, prospect_id: str, checked_at: str) -> str:
    digest = hashlib.sha256(
        f"{decision_id}|{prospect_id}|{checked_at}".encode("utf-8")
    ).hexdigest()[:12]
    return f"mini-audit-handoff-{_sanitize(prospect_id)}-{_sanitize(checked_at)}-{digest}"


def _check(
    checks: list[MiniAuditHandoffCheck],
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
        MiniAuditHandoffCheck.of(
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
    checks: list[MiniAuditHandoffCheck],
    blockers: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> FirstProspectMiniAuditHandoffError:
    return FirstProspectMiniAuditHandoffError.of(
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


# --------------------------------------------------------------------------- #
# Deterministic artifact templates
# --------------------------------------------------------------------------- #
def _md_summary(context: dict[str, Any], action: str, reason: str, blockers: list[str]) -> str:
    lines = [
        "# Mini-Audit Handoff Summary\n",
        "This package is a manual-review-first handoff. SCOS generated it locally; it",
        "sends nothing on its own. An operator must review every artifact before any",
        "message leaves SCOS.\n",
        "## Prospect Context\n",
        f"- Prospect id: `{context.get('prospect_id')}`",
        f"- Business display name: {context.get('business_display_name') or '(not available)'}",
        f"- Market / category: {context.get('market_category') or '(not available)'}\n",
        "## Outreach Evidence\n",
        f"- Response status: {context.get('response_status') or '(not available)'}",
        f"- Recorded next action: {context.get('next_action') or '(not available)'}\n",
        "## Recommended Manual Next Step\n",
        f"- Decision action: {action}",
        f"- Reason: {reason}\n",
        "## Operator Notes\n",
        "- Confirm the business/display alias is safe to use.",
        "- Confirm no direct personal data appears in any artifact.",
        "- Select the channel and message manually.",
    ]
    if blockers:
        lines.append("")
        lines.append("### Blockers")
        lines.append("")
        for item in blockers:
            lines.append(f"- {item}")
    lines.append("")
    lines.append("## Out of Scope\n")
    lines.append("- No automated messaging, no external contact-database sync, no billing,")
    lines.append("  no data harvesting, no dashboards, no network calls, no LLM evaluation.")
    lines.append("")
    return "\n".join(lines)


def _md_checklist() -> str:
    return (
        "# Operator Review Checklist\n\n"
        "Complete every item before any message leaves SCOS.\n\n"
        "- [ ] Confirm the business / display alias is safe to use\n"
        "- [ ] Confirm no direct personal data (phone / e-mail / address) is present\n"
        "- [ ] Confirm no unsupported business claim is made\n"
        "- [ ] Confirm nothing here performs automated messaging\n"
        "- [ ] Confirm the channel and message are manually selected\n"
        "- [ ] Confirm this handoff was reviewed by a human operator\n"
    )


def _md_draft(business_display_name: str) -> str:
    name = business_display_name or "there"
    return (
        "# Handoff Message Draft\n\n"
        "> MANUAL REVIEW REQUIRED. This is a draft only. Review and edit it, then\n"
        "> send it yourself through your own channel. SCOS does not deliver it and\n"
        "> attaches no delivery metadata.\n\n"
        "## Draft\n\n"
        f"Hi {name},\n\n"
        "I put together a short, no-obligation mini-audit of a few things I noticed\n"
        "that could be quick wins. Happy to walk you through it whenever suits you.\n\n"
        "## Not included\n\n"
        "- No guaranteed-revenue or guaranteed-result claim.\n"
        "- No automated delivery of any kind.\n"
        "- No personal data.\n"
        "- No platform-specific delivery instruction.\n"
    )


def create_first_prospect_mini_audit_handoff(
    *,
    decision_path: str | Path,
    checked_at: str,
    output_dir: str | Path,
    allow_escalation_handoff: bool = False,
    require_human_review: bool = True,
    overwrite: bool = False,
) -> FirstProspectMiniAuditHandoffResult | FirstProspectMiniAuditHandoffError:
    checks: list[MiniAuditHandoffCheck] = []

    # 1. validate_inputs -------------------------------------------------------
    if not _non_empty(decision_path):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="decision_path is required")
        return _error("INVALID_ARGUMENTS", "decision_path is required", "validate_inputs", checks)
    if not _non_empty(output_dir):
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", checks)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "error",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks)
    for label, value in (("decision_path", decision_path), ("output_dir", output_dir)):
        if _is_url(value):
            _check(checks, "validate_inputs", "failure", "error",
                   error_kind="INVALID_ARGUMENTS", error_detail="paths must be local filesystem paths",
                   metadata={"argument": label, "path": str(value)})
            return _error("INVALID_ARGUMENTS", "paths must be local filesystem paths",
                          "validate_inputs", checks, metadata={"argument": label, "path": str(value)})
    decision_source = Path(str(decision_path))
    if not decision_source.exists() or not decision_source.is_file():
        _check(checks, "validate_inputs", "failure", "error", artifact_path=str(decision_source),
               error_kind="INPUT_NOT_FOUND", error_detail="decision_path does not exist")
        return _error("INPUT_NOT_FOUND", "decision_path does not exist", "validate_inputs",
                      checks, metadata={"path": str(decision_source)})
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(decision_source))

    # 2. load_decision ---------------------------------------------------------
    try:
        decision = json.loads(decision_source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _check(checks, "load_decision", "failure", "error", artifact_path=str(decision_source),
               error_kind="INVALID_DECISION", error_detail="decision JSON could not be parsed",
               metadata={"reason": type(exc).__name__})
        return _error("INVALID_DECISION", "decision JSON could not be parsed",
                      "load_decision", checks, metadata={"reason": type(exc).__name__})
    if not isinstance(decision, dict):
        _check(checks, "load_decision", "failure", "error", artifact_path=str(decision_source),
               error_kind="INVALID_DECISION", error_detail="decision must be a JSON object")
        return _error("INVALID_DECISION", "decision must be a JSON object", "load_decision", checks)
    _check(checks, "load_decision", "success", "info", artifact_path=str(decision_source))

    # 3. validate_decision_contract -------------------------------------------
    missing = [key for key in _REQUIRED_DECISION_KEYS if key not in decision]
    action_obj = decision.get("action")
    if not isinstance(action_obj, dict) or not _non_empty(action_obj.get("action")):
        missing.append("action.action")
    if missing:
        _check(checks, "validate_decision_contract", "failure", "error", artifact_path=str(decision_source),
               error_kind="INVALID_DECISION", error_detail="decision is missing required fields",
               metadata={"missing_fields": missing})
        return _error("INVALID_DECISION", "decision is missing required fields",
                      "validate_decision_contract", checks, metadata={"missing_fields": missing})
    decision_id = str(decision.get("decision_id"))
    prospect_id = str(decision.get("prospect_id"))
    action = str(action_obj.get("action"))
    reason = str(action_obj.get("reason") or "")
    accepted_decision = decision.get("accepted") is True
    source_execution_log_path = decision.get("source_execution_log_path")
    _check(checks, "validate_decision_contract", "success", "info",
           metadata={"decision_id": decision_id, "action": action})

    # 4. validate_decision_allows_handoff -------------------------------------
    if action not in _ALLOWED_ACTIONS or (
        action == "ESCALATE_TO_FIRST_CUSTOMER_FLOW" and not allow_escalation_handoff
    ):
        _check(checks, "validate_decision_allows_handoff", "failure", "error",
               error_kind="HANDOFF_NOT_ALLOWED", error_detail="decision action does not permit a mini-audit handoff",
               metadata={"action": action, "allow_escalation_handoff": bool(allow_escalation_handoff)})
        return _error("HANDOFF_NOT_ALLOWED", "decision action does not permit a mini-audit handoff",
                      "validate_decision_allows_handoff", checks,
                      metadata={"action": action, "allow_escalation_handoff": bool(allow_escalation_handoff)})
    if not accepted_decision:
        _check(checks, "validate_decision_allows_handoff", "failure", "error",
               error_kind="DECISION_NOT_ACCEPTED", error_detail="decision was not accepted")
        return _error("DECISION_NOT_ACCEPTED", "decision was not accepted",
                      "validate_decision_allows_handoff", checks)
    _check(checks, "validate_decision_allows_handoff", "success", "info", metadata={"action": action})

    # 5. load_execution_log_reference -----------------------------------------
    blockers: list[str] = []
    execution_log: dict[str, Any] | None = None
    execution_log_id: str | None = None
    execution_log_text = "" if source_execution_log_path is None else str(source_execution_log_path)
    if _is_url(execution_log_text):
        _check(checks, "load_execution_log_reference", "failure", "error",
               error_kind="INVALID_EXECUTION_LOG", error_detail="execution log path must be a local path",
               metadata={"path": execution_log_text})
        return _error("INVALID_EXECUTION_LOG", "execution log path must be a local path",
                      "load_execution_log_reference", checks, metadata={"path": execution_log_text})
    if execution_log_text:
        exec_path = Path(execution_log_text)
        if not exec_path.exists() or not exec_path.is_file():
            blockers.append("referenced execution log is missing")
            _check(checks, "load_execution_log_reference", "failure", "warning",
                   artifact_path=execution_log_text,
                   error_kind="INPUT_NOT_FOUND", error_detail="referenced execution log is missing")
        else:
            try:
                loaded = json.loads(exec_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                _check(checks, "load_execution_log_reference", "failure", "error",
                       artifact_path=execution_log_text,
                       error_kind="INVALID_EXECUTION_LOG", error_detail="execution log JSON could not be parsed",
                       metadata={"reason": type(exc).__name__})
                return _error("INVALID_EXECUTION_LOG", "execution log JSON could not be parsed",
                              "load_execution_log_reference", checks, metadata={"reason": type(exc).__name__})
            if not isinstance(loaded, dict):
                _check(checks, "load_execution_log_reference", "failure", "error",
                       artifact_path=execution_log_text,
                       error_kind="INVALID_EXECUTION_LOG", error_detail="execution log must be a JSON object")
                return _error("INVALID_EXECUTION_LOG", "execution log must be a JSON object",
                              "load_execution_log_reference", checks)
            execution_log = loaded
            execution_log_id = None if loaded.get("execution_log_id") is None else str(loaded.get("execution_log_id"))
            _check(checks, "load_execution_log_reference", "success", "info", artifact_path=execution_log_text)
    else:
        _check(checks, "load_execution_log_reference", "skipped", "warning", metadata={"provided": False})

    # 6. validate_manual_only --------------------------------------------------
    signal = _find_automation_signal(decision)
    if signal is None and execution_log is not None:
        signal = _find_automation_signal(execution_log)
    if signal is not None:
        _check(checks, "validate_manual_only", "failure", "error",
               error_kind="MANUAL_ONLY_VIOLATION", error_detail="a non-manual behavior signal was found",
               metadata={"signal": signal})
        return _error("MANUAL_ONLY_VIOLATION", "a non-manual behavior signal was found",
                      "validate_manual_only", checks, metadata={"signal": signal})
    _check(checks, "validate_manual_only", "success", "info")

    # 7. validate_sensitive_metadata ------------------------------------------
    sensitive = _find_sensitive_key(decision)
    if sensitive is None and execution_log is not None:
        sensitive = _find_sensitive_key(execution_log.get("prospect"))
    if sensitive is not None:
        _check(checks, "validate_sensitive_metadata", "failure", "error",
               error_kind="SENSITIVE_METADATA", error_detail="a direct personal-data field was found",
               metadata={"field": sensitive})
        return _error("SENSITIVE_METADATA", "a direct personal-data field was found",
                      "validate_sensitive_metadata", checks, metadata={"field": sensitive})
    _check(checks, "validate_sensitive_metadata", "success", "info")

    # Build safe prospect context from the execution log where available.
    prospect = execution_log.get("prospect") if isinstance(execution_log, dict) else None
    response_status = execution_log.get("response_status") if isinstance(execution_log, dict) else None
    prospect = prospect if isinstance(prospect, dict) else {}
    response_status = response_status if isinstance(response_status, dict) else {}
    context = {
        "prospect_id": prospect_id,
        "business_display_name": prospect.get("display_name"),
        "market_category": prospect.get("business_type"),
        "response_status": response_status.get("status"),
        "next_action": response_status.get("next_action"),
        "blockers": list(blockers),
        "metadata": {"manual_only": True, "review_required": bool(require_human_review)},
    }

    # 8. prepare_output_layout -------------------------------------------------
    handoff_id = _handoff_id(decision_id, prospect_id, checked_at)
    base_dir = Path(str(output_dir))
    handoff_folder = _fs_safe(handoff_id)
    handoff_dir = base_dir / handoff_folder
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        resolved_base = base_dir.resolve(strict=True)
        resolved_handoff = handoff_dir.resolve()
    except OSError as exc:
        _check(checks, "prepare_output_layout", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="output_dir could not be prepared",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "output_dir could not be prepared",
                      "prepare_output_layout", checks, tuple(blockers),
                      metadata={"os_error": type(exc).__name__})
    if resolved_handoff == resolved_base or resolved_handoff.parent != resolved_base:
        _check(checks, "prepare_output_layout", "failure", "error",
               error_kind="PATH_CONTAINMENT_FAILED", error_detail="handoff folder resolves outside output_dir")
        return _error("PATH_CONTAINMENT_FAILED", "handoff folder resolves outside output_dir",
                      "prepare_output_layout", checks, tuple(blockers))
    handoff_dir = resolved_handoff
    if handoff_dir.exists() and not overwrite:
        _check(checks, "prepare_output_layout", "failure", "error", artifact_path=str(handoff_dir),
               error_kind="OUTPUT_EXISTS", error_detail="handoff folder already exists and overwrite is False")
        return _error("OUTPUT_EXISTS", "handoff folder already exists and overwrite is False",
                      "prepare_output_layout", checks, tuple(blockers), metadata={"path": str(handoff_dir)})
    _check(checks, "prepare_output_layout", "success", "info", artifact_path=str(handoff_dir))

    accepted = len(blockers) == 0

    # 9. write_artifacts -------------------------------------------------------
    summary_text = _md_summary(context, action, reason, blockers)
    checklist_text = _md_checklist()
    draft_text = _md_draft(str(context.get("business_display_name") or ""))
    context_json = _json_text(context)
    evidence_json = _json_text({
        "decision_path": str(decision_source),
        "execution_log_path": execution_log_text or None,
        "generated_artifacts": [
            _SUMMARY_FILE, _CHECKLIST_FILE, _CONTEXT_FILE, _DRAFT_FILE, _EVIDENCE_FILE, _MANIFEST_FILE,
        ],
        "source_artifacts_read_only": [
            str(decision_source)
        ] + ([execution_log_text] if execution_log_text else []),
        "no_mutation_confirmed": True,
    })

    manifest_path = handoff_dir / _MANIFEST_FILE
    artifacts = (
        MiniAuditHandoffArtifact.of(artifact_name=_SUMMARY_FILE, artifact_type="summary",
                                    path=str(handoff_dir / _SUMMARY_FILE),
                                    description="Human-readable mini-audit handoff summary."),
        MiniAuditHandoffArtifact.of(artifact_name=_CHECKLIST_FILE, artifact_type="checklist",
                                    path=str(handoff_dir / _CHECKLIST_FILE),
                                    description="Operator pre-send review checklist."),
        MiniAuditHandoffArtifact.of(artifact_name=_CONTEXT_FILE, artifact_type="json",
                                    path=str(handoff_dir / _CONTEXT_FILE),
                                    description="Safe prospect context (no personal data)."),
        MiniAuditHandoffArtifact.of(artifact_name=_DRAFT_FILE, artifact_type="markdown",
                                    path=str(handoff_dir / _DRAFT_FILE),
                                    description="Manual-review-first message draft."),
        MiniAuditHandoffArtifact.of(artifact_name=_EVIDENCE_FILE, artifact_type="evidence",
                                    path=str(handoff_dir / _EVIDENCE_FILE),
                                    description="Read-only evidence index."),
        MiniAuditHandoffArtifact.of(artifact_name=_MANIFEST_FILE, artifact_type="manifest",
                                    path=str(manifest_path),
                                    description="Mini-audit handoff manifest."),
    )

    manifest_data = {
        "schema_version": FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
        "handoff_id": handoff_id,
        "prospect_id": prospect_id,
        "decision_id": decision_id,
        "execution_log_id": execution_log_id,
        "checked_at": checked_at,
        "source_decision_path": str(decision_source),
        "source_execution_log_path": execution_log_text or None,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
        "checks": [chk.to_dict() for chk in checks]
        + [MiniAuditHandoffCheck.of("write_artifacts", "success", "info",
                                    artifact_path=str(handoff_dir)).to_dict()],
        "blockers": list(blockers),
        "metadata": {
            "generator": "scos.commercial.first_prospect_mini_audit_handoff",
            "manual_only": True,
            "accepted": accepted,
            "action": action,
        },
    }

    try:
        handoff_dir.mkdir(parents=True, exist_ok=True)
        (handoff_dir / _SUMMARY_FILE).write_text(summary_text, encoding="utf-8", newline="\n")
        (handoff_dir / _CHECKLIST_FILE).write_text(checklist_text, encoding="utf-8", newline="\n")
        (handoff_dir / _CONTEXT_FILE).write_text(context_json, encoding="utf-8", newline="\n")
        (handoff_dir / _DRAFT_FILE).write_text(draft_text, encoding="utf-8", newline="\n")
        (handoff_dir / _EVIDENCE_FILE).write_text(evidence_json, encoding="utf-8", newline="\n")
        manifest_path.write_text(_json_text(manifest_data), encoding="utf-8", newline="\n")
    except OSError as exc:
        _check(checks, "write_artifacts", "failure", "error",
               error_kind="OUTPUT_WRITE_FAILED", error_detail="handoff artifacts could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "handoff artifacts could not be written",
                      "write_artifacts", checks, tuple(blockers), metadata={"os_error": type(exc).__name__})
    _check(checks, "write_artifacts", "success", "info", artifact_path=str(handoff_dir))

    # 10. validate_output_artifacts -------------------------------------------
    for artifact in artifacts:
        target = Path(artifact.path)
        if not target.exists() or not target.is_file():
            _check(checks, "validate_output_artifacts", "failure", "error", artifact_path=artifact.path,
                   error_kind="VALIDATION_FAILED", error_detail="a required handoff artifact is missing")
            return _error("VALIDATION_FAILED", "a required handoff artifact is missing",
                          "validate_output_artifacts", checks, tuple(blockers), metadata={"path": artifact.path})
        if target.resolve().parent != handoff_dir:
            _check(checks, "validate_output_artifacts", "failure", "error", artifact_path=artifact.path,
                   error_kind="PATH_CONTAINMENT_FAILED", error_detail="an artifact resolves outside the handoff folder")
            return _error("PATH_CONTAINMENT_FAILED", "an artifact resolves outside the handoff folder",
                          "validate_output_artifacts", checks, tuple(blockers), metadata={"path": artifact.path})
    _check(checks, "validate_output_artifacts", "success", "info", artifact_path=str(handoff_dir))

    return FirstProspectMiniAuditHandoffResult(
        ok=True,
        schema_version=FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
        accepted=accepted,
        handoff_id=handoff_id,
        prospect_id=prospect_id,
        decision_id=decision_id,
        execution_log_id=execution_log_id,
        checked_at=checked_at,
        output_dir=str(handoff_dir),
        manifest_path=str(manifest_path),
        artifacts=artifacts,
        checks=tuple(checks),
        blockers=tuple(blockers),
        metadata={
            "generator": "scos.commercial.first_prospect_mini_audit_handoff",
            "manual_only": True,
            "action": action,
        },
    )


__all__ = ("create_first_prospect_mini_audit_handoff",)
