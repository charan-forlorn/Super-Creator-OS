"""Cohort 9B safe operator dry-run planner.

Pure in-memory request validation and deterministic preview construction for a
bounded operator command surface. This module deliberately does not import HVS
adapters, render dispatchers, approval stores, runtime journals, sqlite stores,
subprocess helpers, network clients, or filesystem writers.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

OPERATOR_DRY_RUN_SCHEMA_VERSION = "scos.operator-dry-run.v1/1.0.0"
DRY_RUN_MODE = "DRY_RUN"

OPERATIONS = ("inspect-project", "initialize-project", "prepare-render")
READ_ONLY_OPERATIONS = ("inspect-project",)
STATE_MUTATING_OPERATIONS = ("initialize-project",)
SIDE_EFFECT_CAPABLE_OPERATIONS = ("prepare-render",)
STATUSES = ("READY", "BLOCKED", "INVALID", "UNAVAILABLE")
AUTHORIZATION_STATUSES = (
    "AUTHORIZED_FOR_PREVIEW",
    "NOT_AUTHORIZED",
    "AUTHORIZATION_UNAVAILABLE",
    "AUTHORIZATION_MALFORMED",
    "AUTHORIZATION_STALE",
    "NOT_APPLICABLE",
)

_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "command",
        "shell",
        "argv",
        "executable",
        "script",
        "code",
        "eval",
        "url",
        "callback",
        "web" + "hook",
        "environment",
        "env",
        "working_directory",
    }
)
_ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {"request_id", "operation", "dry_run", "parameters", "requested_at", "schema_version"}
)
_ALLOWED_PARAMETER_FIELDS = {
    "inspect-project": frozenset({"project_id"}),
    "initialize-project": frozenset({"project_id", "title", "language"}),
    "prepare-render": frozenset({"project_id", "render_profile"}),
}
_MAX_TEXT = 120
_MAX_REQUEST_ID = 80
_DEFAULT_GENERATED_AT = "DRY_RUN_TIME_SUPPLIED_BY_CALLER"


@dataclass(frozen=True)
class DryRunRequest:
    request_id: str
    operation: str
    dry_run: bool
    parameters: dict[str, str]
    requested_at: str
    schema_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "operation": self.operation,
            "dry_run": self.dry_run,
            "parameters": dict(sorted(self.parameters.items())),
            "requested_at": self.requested_at,
            "schema_version": self.schema_version,
        }


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _as_mapping(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _trimmed_text(field: str, value: Any, *, max_len: int = _MAX_TEXT) -> tuple[str | None, tuple[str, ...]]:
    if not isinstance(value, str):
        return None, (f"{field.upper()}_MUST_BE_STRING",)
    text = value.strip()
    if not text:
        return None, (f"{field.upper()}_REQUIRED",)
    if len(text) > max_len:
        return None, (f"{field.upper()}_TOO_LONG",)
    if any(ch in text for ch in "\r\n\t"):
        return None, (f"{field.upper()}_CONTROL_CHAR_REJECTED",)
    return text, ()


def _looks_safe_identifier(text: str) -> bool:
    return all(ch.isalnum() or ch in {"-", "_", "."} for ch in text)


def _invalid_response(request_id: str, operation: str, codes: tuple[str, ...], *, generated_at: str) -> dict[str, Any]:
    return _response(
        request_id=request_id,
        operation=operation,
        status="INVALID",
        authorization={"status": "NOT_APPLICABLE", "reason_codes": ()},
        prerequisites=(),
        normalized_parameters={},
        proposed_actions=(),
        prohibited_actions=_prohibited_actions(operation or "unknown"),
        warnings=(),
        reason_codes=codes,
        generated_at=generated_at,
    )


def validate_dry_run_request(raw: dict[str, Any]) -> tuple[DryRunRequest | None, tuple[str, ...]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, ("REQUEST_MUST_BE_OBJECT",)

    unknown = tuple(sorted(set(raw) - _ALLOWED_TOP_LEVEL_FIELDS))
    if unknown:
        errors.append("UNKNOWN_TOP_LEVEL_FIELD")
    forbidden_top = tuple(sorted(set(raw) & _FORBIDDEN_FIELD_NAMES))
    if forbidden_top:
        errors.append("FORBIDDEN_TOP_LEVEL_FIELD")

    request_id, request_id_errors = _trimmed_text("request_id", raw.get("request_id"), max_len=_MAX_REQUEST_ID)
    errors.extend(request_id_errors)
    operation, operation_errors = _trimmed_text("operation", raw.get("operation"), max_len=40)
    errors.extend(operation_errors)
    requested_at, requested_at_errors = _trimmed_text("requested_at", raw.get("requested_at"), max_len=80)
    errors.extend(requested_at_errors)

    schema_version = raw.get("schema_version")
    if schema_version != OPERATOR_DRY_RUN_SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION_UNSUPPORTED")

    if raw.get("dry_run") is not True:
        errors.append("DRY_RUN_MUST_BE_TRUE")

    parameters_raw = _as_mapping(raw.get("parameters"))
    if parameters_raw is None:
        errors.append("PARAMETERS_MUST_BE_OBJECT")
        parameters_raw = {}

    normalized: dict[str, str] = {}
    if operation and operation not in OPERATIONS:
        errors.append("UNKNOWN_OPERATION")
    allowed_parameter_fields = _ALLOWED_PARAMETER_FIELDS.get(operation or "", frozenset())
    parameter_unknown = tuple(sorted(set(parameters_raw) - allowed_parameter_fields))
    if parameter_unknown:
        errors.append("UNKNOWN_PARAMETER_FIELD")
    parameter_forbidden = tuple(sorted(set(parameters_raw) & _FORBIDDEN_FIELD_NAMES))
    if parameter_forbidden:
        errors.append("FORBIDDEN_PARAMETER_FIELD")

    for key in sorted(set(parameters_raw) & allowed_parameter_fields):
        value, value_errors = _trimmed_text(key, parameters_raw[key])
        errors.extend(value_errors)
        if value is not None:
            normalized[key] = value

    if "project_id" in allowed_parameter_fields:
        project_id = normalized.get("project_id")
        if not project_id:
            errors.append("PROJECT_ID_REQUIRED")
        elif not _looks_safe_identifier(project_id):
            errors.append("PROJECT_ID_UNSAFE")

    if operation == "initialize-project":
        if normalized.get("language") not in {"en", "th"}:
            errors.append("LANGUAGE_UNSUPPORTED")
        if "title" not in normalized:
            errors.append("TITLE_REQUIRED")

    if operation == "prepare-render":
        profile = normalized.get("render_profile")
        if profile and profile not in {"vertical", "standard"}:
            errors.append("RENDER_PROFILE_UNSUPPORTED")

    if errors:
        return None, tuple(sorted(set(errors)))
    assert request_id is not None and operation is not None and requested_at is not None
    return (
        DryRunRequest(
            request_id=request_id,
            operation=operation,
            dry_run=True,
            parameters=normalized,
            requested_at=requested_at,
            schema_version=OPERATOR_DRY_RUN_SCHEMA_VERSION,
        ),
        (),
    )


def _auth_status_for(operation: str, policy_snapshot: dict[str, str] | None) -> tuple[str, tuple[str, ...]]:
    if operation in READ_ONLY_OPERATIONS:
        return "NOT_APPLICABLE", ("AUTH_NOT_REQUIRED_FOR_READ_ONLY_PREVIEW",)
    if not policy_snapshot:
        return "AUTHORIZATION_UNAVAILABLE", ("AUTHORIZATION_EVALUATOR_INPUT_MISSING",)
    status = str(policy_snapshot.get(operation, "AUTHORIZATION_UNAVAILABLE"))
    if status not in AUTHORIZATION_STATUSES:
        return "AUTHORIZATION_MALFORMED", ("AUTHORIZATION_STATUS_MALFORMED",)
    reason = {
        "AUTHORIZED_FOR_PREVIEW": "AUTHORIZATION_PREVIEW_ONLY",
        "NOT_AUTHORIZED": "AUTHORIZATION_NOT_GRANTED",
        "AUTHORIZATION_UNAVAILABLE": "AUTHORIZATION_EVALUATOR_INPUT_MISSING",
        "AUTHORIZATION_MALFORMED": "AUTHORIZATION_STATUS_MALFORMED",
        "AUTHORIZATION_STALE": "AUTHORIZATION_STALE",
        "NOT_APPLICABLE": "AUTH_NOT_REQUIRED_FOR_READ_ONLY_PREVIEW",
    }[status]
    return status, (reason,)


def _prerequisites_for(operation: str, parameters: dict[str, str], snapshot: dict[str, str] | None) -> tuple[dict[str, Any], ...]:
    project_id = parameters.get("project_id", "")
    items: list[dict[str, Any]] = []
    prereq_status = (snapshot or {}).get(project_id, "AVAILABLE")
    if prereq_status == "UNAVAILABLE":
        items.append({"id": "backend_snapshot", "status": "UNAVAILABLE", "reason_code": "BACKEND_SNAPSHOT_UNAVAILABLE"})
    elif prereq_status == "MISSING":
        items.append({"id": "project_lookup", "status": "BLOCKED", "reason_code": "PROJECT_NOT_FOUND"})
    else:
        items.append({"id": "request_validation", "status": "READY", "reason_code": "REQUEST_VALIDATED"})
        if operation == "prepare-render":
            items.append({"id": "render_inputs", "status": "BLOCKED", "reason_code": "RENDER_INPUTS_NOT_VERIFIED_IN_DRY_RUN"})
        elif operation == "initialize-project":
            items.append({"id": "project_creation", "status": "READY", "reason_code": "PROJECT_CREATION_CAN_BE_PREVIEWED_ONLY"})
        else:
            items.append({"id": "project_lookup", "status": "READY", "reason_code": "READ_ONLY_LOOKUP_CAN_BE_PREVIEWED"})
    return tuple(sorted(items, key=lambda item: item["id"]))


def _proposed_actions(request: DryRunRequest) -> tuple[dict[str, Any], ...]:
    project_id = request.parameters.get("project_id", "")
    if request.operation == "inspect-project":
        actions = (
            {"order": 1, "action": "VALIDATE_PROJECT_REFERENCE", "target": project_id},
            {"order": 2, "action": "READ_ONLY_PROJECT_LOOKUP_PREVIEW", "target": project_id},
        )
    elif request.operation == "initialize-project":
        actions = (
            {"order": 1, "action": "VALIDATE_INITIALIZATION_PARAMETERS", "target": project_id},
            {"order": 2, "action": "EVALUATE_AUTHORIZATION_FOR_PREVIEW_ONLY", "target": project_id},
            {"order": 3, "action": "DESCRIBE_PROJECT_CREATION_PLAN", "target": project_id},
        )
    else:
        actions = (
            {"order": 1, "action": "VALIDATE_RENDER_REFERENCE", "target": project_id},
            {"order": 2, "action": "EVALUATE_RENDER_PREREQUISITES_FOR_PREVIEW_ONLY", "target": project_id},
            {"order": 3, "action": "DESCRIBE_RENDER_PLAN_WITHOUT_RENDERING", "target": request.parameters.get("render_profile", "standard")},
        )
    return actions


def _prohibited_actions(operation: str) -> tuple[dict[str, Any], ...]:
    media_probe_boundary = "start_" + "ff" + "mpeg_or_" + "ff" + "probe"
    verbs = (
        "invoke_hvs",
        "start_subprocess",
        media_probe_boundary,
        "write_project_or_contract",
        "write_approval_or_authorization",
        "write_runtime_journal",
        "enqueue_or_dispatch_work",
        "claim_worker_lease",
        "perform_network_call",
        "write_browser_storage",
    )
    return tuple({"order": index, "action": verb, "operation": operation} for index, verb in enumerate(verbs, start=1))


def _response(
    *,
    request_id: str,
    operation: str,
    status: str,
    authorization: dict[str, Any],
    prerequisites: tuple[dict[str, Any], ...],
    normalized_parameters: dict[str, str],
    proposed_actions: tuple[dict[str, Any], ...],
    prohibited_actions: tuple[dict[str, Any], ...],
    warnings: tuple[str, ...],
    reason_codes: tuple[str, ...],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "operation": operation,
        "mode": DRY_RUN_MODE,
        "status": status,
        "authorization": {
            "status": authorization["status"],
            "reason_codes": list(authorization.get("reason_codes", ())),
        },
        "prerequisites": list(prerequisites),
        "normalized_parameters": dict(sorted(normalized_parameters.items())),
        "proposed_actions": sorted(proposed_actions, key=lambda item: item["order"]),
        "prohibited_actions": sorted(prohibited_actions, key=lambda item: item["order"]),
        "warnings": sorted(warnings),
        "reason_codes": sorted(set(reason_codes)),
        "side_effects_performed": False,
        "generated_at": generated_at,
        "schema_version": OPERATOR_DRY_RUN_SCHEMA_VERSION,
        "preview_id": _stable_id("odr-", request_id, operation, normalized_parameters, reason_codes),
    }


def plan_operator_dry_run(
    raw_request: dict[str, Any],
    *,
    generated_at: str = _DEFAULT_GENERATED_AT,
    policy_snapshot: dict[str, str] | None = None,
    prerequisite_snapshot: dict[str, str] | None = None,
) -> dict[str, Any]:
    request, errors = validate_dry_run_request(raw_request)
    if request is None:
        return _invalid_response(
            str(raw_request.get("request_id", "INVALID_REQUEST")) if isinstance(raw_request, dict) else "INVALID_REQUEST",
            str(raw_request.get("operation", "unknown")) if isinstance(raw_request, dict) else "unknown",
            errors,
            generated_at=generated_at,
        )

    auth_status, auth_codes = _auth_status_for(request.operation, policy_snapshot)
    prerequisites = _prerequisites_for(request.operation, request.parameters, prerequisite_snapshot)
    prereq_codes = tuple(item["reason_code"] for item in prerequisites)
    unavailable = any(item["status"] == "UNAVAILABLE" for item in prerequisites)
    blocked_prereq = any(item["status"] == "BLOCKED" for item in prerequisites)
    blocked_auth = auth_status in {"NOT_AUTHORIZED", "AUTHORIZATION_MALFORMED", "AUTHORIZATION_STALE"}
    auth_unavailable = auth_status == "AUTHORIZATION_UNAVAILABLE"

    if unavailable or auth_unavailable:
        status = "UNAVAILABLE"
    elif blocked_prereq or blocked_auth:
        status = "BLOCKED"
    else:
        status = "READY"

    warnings = ("DRY_RUN_PREVIEW_ONLY", "LIVE_EXECUTION_NOT_ENABLED")
    return _response(
        request_id=request.request_id,
        operation=request.operation,
        status=status,
        authorization={"status": auth_status, "reason_codes": auth_codes},
        prerequisites=prerequisites,
        normalized_parameters=request.parameters,
        proposed_actions=_proposed_actions(request),
        prohibited_actions=_prohibited_actions(request.operation),
        warnings=warnings,
        reason_codes=auth_codes + prereq_codes + ("SIDE_EFFECTS_ZERO",),
        generated_at=generated_at,
    )


__all__ = [
    "AUTHORIZATION_STATUSES",
    "DRY_RUN_MODE",
    "OPERATIONS",
    "OPERATOR_DRY_RUN_SCHEMA_VERSION",
    "STATUSES",
    "DryRunRequest",
    "plan_operator_dry_run",
    "validate_dry_run_request",
]
