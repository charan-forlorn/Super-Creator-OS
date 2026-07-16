"""Cohort 10A solo-operator durable control loop.

This module owns one narrow operator workflow:

operator request -> validation -> durable command -> explicit approval or
rejection -> fake HVS dry-run dispatch -> durable result -> status projection.

It reuses the certified SQLite Control Center store. It never imports HVS,
starts a subprocess, opens a socket, reads the real clock, generates random IDs,
or writes operator-owned runtime memory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .sqlite_state_schema import stable_json_dumps
    from .sqlite_state_store import SQLiteStateStore
    from .state_models import (
        DurableApprovalRecord,
        DurableCommandRecord,
        DurableEventRecord,
        DurableResultRecord,
        DurableStateError,
    )
except ImportError:  # direct-module execution
    from sqlite_state_schema import stable_json_dumps
    from sqlite_state_store import SQLiteStateStore
    from state_models import (
        DurableApprovalRecord,
        DurableCommandRecord,
        DurableEventRecord,
        DurableResultRecord,
        DurableStateError,
    )

SOLO_OPERATOR_SCHEMA_VERSION = "scos.solo-operator-control-loop.v1"
SUPPORTED_WORKFLOW = "video-production"
SUPPORTED_RENDER_PROFILES = ("vertical", "standard")
SUPPORTED_LANGUAGES = ("en", "th")

STATUS_APPROVAL_REQUIRED = "approval_required"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_DRY_RUN_SUCCEEDED = "dry_run_succeeded"
STATUS_BLOCKED = "blocked"

_SUBJECT_TYPE = "cohort10a_command"
_SOURCE = "solo_operator_control_loop"
_MAX_TEXT = 120
_MAX_ID = 80
_FORBIDDEN_KEYS = frozenset(
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
        "webhook",
        "environment",
        "env",
        "working_directory",
        "output_path",
    }
)


@dataclass(frozen=True)
class WorkflowError:
    error_kind: str
    error_detail: str
    field_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "field_name": self.field_name,
        }


def _hash_id(prefix: str, *parts: Any) -> str:
    payload = stable_json_dumps({"parts": [str(part) for part in parts]})
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _safe_text(value: Any, field: str, *, max_len: int = _MAX_TEXT) -> tuple[str | None, tuple[WorkflowError, ...]]:
    if not isinstance(value, str):
        return None, (WorkflowError("invalid_payload", f"{field} must be a string", field),)
    text = value.strip()
    if not text:
        return None, (WorkflowError("invalid_payload", f"{field} is required", field),)
    if len(text) > max_len:
        return None, (WorkflowError("invalid_payload", f"{field} is too long", field),)
    if any(ch in text for ch in "\r\n\t"):
        return None, (WorkflowError("invalid_payload", f"{field} contains a control character", field),)
    return text, ()


def _safe_identifier(text: str) -> bool:
    return all(ch.isalnum() or ch in {"-", "_", "."} for ch in text)


def _intent_hash(intent: dict[str, str]) -> str:
    return hashlib.sha256(
        stable_json_dumps(intent).encode("utf-8")
    ).hexdigest()


def validate_video_request(payload: dict[str, Any]) -> tuple[dict[str, str] | None, tuple[WorkflowError, ...]]:
    """Validate and normalize the one supported Cohort 10A request."""
    if not isinstance(payload, dict):
        return None, (WorkflowError("invalid_payload", "request payload must be an object"),)

    errors: list[WorkflowError] = []
    unknown = sorted(set(payload) - {"workflow", "project_id", "title", "language", "render_profile", "idempotency_key"})
    if unknown:
        errors.append(WorkflowError("invalid_payload", "unknown request fields are not allowed", ",".join(unknown)))
    forbidden = sorted(set(payload) & _FORBIDDEN_KEYS)
    if forbidden:
        errors.append(WorkflowError("forbidden_payload", "forbidden request fields are not allowed", ",".join(forbidden)))

    workflow, field_errors = _safe_text(payload.get("workflow"), "workflow")
    errors.extend(field_errors)
    project_id, field_errors = _safe_text(payload.get("project_id"), "project_id", max_len=_MAX_ID)
    errors.extend(field_errors)
    title, field_errors = _safe_text(payload.get("title"), "title")
    errors.extend(field_errors)
    language, field_errors = _safe_text(payload.get("language"), "language", max_len=10)
    errors.extend(field_errors)
    render_profile, field_errors = _safe_text(payload.get("render_profile"), "render_profile", max_len=20)
    errors.extend(field_errors)
    idem, field_errors = _safe_text(payload.get("idempotency_key"), "idempotency_key", max_len=_MAX_ID)
    errors.extend(field_errors)

    if workflow and workflow != SUPPORTED_WORKFLOW:
        errors.append(WorkflowError("unsupported_workflow", "only video-production is supported", "workflow"))
    if project_id and not _safe_identifier(project_id):
        errors.append(WorkflowError("invalid_payload", "project_id must be a safe local identifier", "project_id"))
    if language and language not in SUPPORTED_LANGUAGES:
        errors.append(WorkflowError("invalid_payload", "language must be en or th", "language"))
    if render_profile and render_profile not in SUPPORTED_RENDER_PROFILES:
        errors.append(WorkflowError("invalid_payload", "render_profile must be vertical or standard", "render_profile"))

    if errors:
        return None, tuple(errors)
    assert workflow and project_id and title and language and render_profile and idem
    return {
        "workflow": workflow,
        "project_id": project_id,
        "title": title,
        "language": language,
        "render_profile": render_profile,
        "idempotency_key": idem,
    }, ()


class SoloOperatorControlLoop:
    """Authoritative local owner for the Cohort 10A command lifecycle."""

    def __init__(self, *, repo_root: Path, db_path: Path | None = None) -> None:
        self._store = SQLiteStateStore(repo_root=Path(repo_root), db_path=db_path)

    @property
    def store(self) -> SQLiteStateStore:
        return self._store

    def initialize(self, *, applied_at: str) -> DurableStateError | None:
        return self._store.initialize(applied_at=applied_at, metadata={"cohort": "10A"})

    def submit_request(self, *, payload: dict[str, Any], operator_id: str, created_at: str) -> dict[str, Any]:
        intent, errors = validate_video_request(payload)
        if errors:
            return {
                "ok": False,
                "status": "rejected",
                "errors": [error.to_dict() for error in errors],
                "side_effects_performed": False,
            }

        assert intent is not None
        intent_hash = _intent_hash({key: intent[key] for key in sorted(intent) if key != "idempotency_key"})
        command_id = _hash_id("soc-", intent["idempotency_key"], intent_hash)
        existing = self._store.get_command(command_id)
        if isinstance(existing, DurableCommandRecord):
            return self.status(command_id=command_id, checked_at=created_at)

        payload_json = stable_json_dumps(
            {
                "schema_version": SOLO_OPERATOR_SCHEMA_VERSION,
                "intent": intent,
                "intent_hash": intent_hash,
                "dry_run_only": True,
            }
        )
        record = DurableCommandRecord.of(
            command_id,
            SUPPORTED_WORKFLOW,
            STATUS_APPROVAL_REQUIRED,
            created_at,
            request_id=intent["idempotency_key"],
            payload_json=payload_json,
            metadata={"operator_id": operator_id, "intent_hash": intent_hash},
        )
        inserted = self._store.insert_command(record)
        if isinstance(inserted, DurableStateError):
            return inserted.to_dict()
        self._append_event(command_id, "REQUEST_ACCEPTED", created_at, 1, {"status": STATUS_APPROVAL_REQUIRED})
        return self.status(command_id=command_id, checked_at=created_at)

    def approve(self, *, command_id: str, operator_id: str, decided_at: str, reason: str) -> dict[str, Any]:
        return self._decide(command_id=command_id, operator_id=operator_id, decided_at=decided_at, reason=reason, decision="approved")

    def reject(self, *, command_id: str, operator_id: str, decided_at: str, reason: str) -> dict[str, Any]:
        return self._decide(command_id=command_id, operator_id=operator_id, decided_at=decided_at, reason=reason, decision="rejected")

    def dispatch_dry_run(self, *, command_id: str, operator_id: str, dispatched_at: str) -> dict[str, Any]:
        command = self._store.get_command(command_id)
        if isinstance(command, DurableStateError):
            return command.to_dict()
        current = self.status(command_id=command_id, checked_at=dispatched_at)
        if current["status"] == STATUS_DRY_RUN_SUCCEEDED:
            return current
        if current["status"] != STATUS_APPROVED:
            return self._blocked(command_id, dispatched_at, "dispatch_requires_approval", "dispatch requires an approved command")

        result_id = _hash_id("soc-result-", command_id, "fake-hvs-dry-run")
        prior = [result for result in self._store.list_results(subject_type=_SUBJECT_TYPE, subject_id=command_id) if result.result_id == result_id]
        if prior:
            return self.status(command_id=command_id, checked_at=dispatched_at)

        payload = json.loads(command.payload_json)
        result_payload = stable_json_dumps(
            {
                "mode": "HVS_FAKE_DRY_RUN",
                "workflow": SUPPORTED_WORKFLOW,
                "intent_hash": payload["intent_hash"],
                "operator_id": operator_id,
                "summary": "Fake HVS dry-run dispatch accepted; no live render executed.",
                "side_effects_performed": False,
            }
        )
        inserted = self._store.insert_result(
            DurableResultRecord.of(
                result_id,
                "hvs_fake_dry_run",
                _SUBJECT_TYPE,
                command_id,
                "pass",
                dispatched_at,
                payload_json=result_payload,
                metadata={"dry_run": "true", "live_render": "false"},
            )
        )
        if isinstance(inserted, DurableStateError):
            return inserted.to_dict()
        self._append_event(command_id, "DRY_RUN_DISPATCH_SUCCEEDED", dispatched_at, 3, {"status": STATUS_DRY_RUN_SUCCEEDED})
        return self.status(command_id=command_id, checked_at=dispatched_at)

    def status(self, *, command_id: str, checked_at: str) -> dict[str, Any]:
        command = self._store.get_command(command_id)
        if isinstance(command, DurableStateError):
            return command.to_dict()
        approvals = self._store.list_approvals(subject_type=_SUBJECT_TYPE, subject_id=command_id)
        results = self._store.list_results(subject_type=_SUBJECT_TYPE, subject_id=command_id)
        events = self._store.list_events(subject_type=_SUBJECT_TYPE, subject_id=command_id)
        status = command.status
        if any(result.result_type == "hvs_fake_dry_run" and result.verdict == "pass" for result in results):
            status = STATUS_DRY_RUN_SUCCEEDED
        elif any(approval.decision == "rejected" for approval in approvals):
            status = STATUS_REJECTED
        elif any(approval.decision == "approved" for approval in approvals):
            status = STATUS_APPROVED
        return {
            "ok": True,
            "schema_version": SOLO_OPERATOR_SCHEMA_VERSION,
            "command_id": command.command_id,
            "status": status,
            "workflow": command.command_type,
            "checked_at": checked_at,
            "created_at": command.created_at,
            "updated_at": self._last_observed_at(command, approvals, results, events),
            "approval_required": status == STATUS_APPROVAL_REQUIRED,
            "dry_run_only": True,
            "side_effects_performed": False,
            "approval_count": len(approvals),
            "result_count": len(results),
            "event_count": len(events),
            "safe_result_summary": self._safe_result_summary(results),
            "next_operator_action": self._next_action(status),
        }

    def _decide(self, *, command_id: str, operator_id: str, decided_at: str, reason: str, decision: str) -> dict[str, Any]:
        command = self._store.get_command(command_id)
        if isinstance(command, DurableStateError):
            return command.to_dict()
        current = self.status(command_id=command_id, checked_at=decided_at)
        if current["status"] in {STATUS_DRY_RUN_SUCCEEDED, STATUS_REJECTED}:
            return current
        approvals = self._store.list_approvals(subject_type=_SUBJECT_TYPE, subject_id=command_id)
        if approvals:
            return self.status(command_id=command_id, checked_at=decided_at)
        approval_id = _hash_id("soc-approval-", command_id, decision)
        inserted = self._store.insert_approval(
            DurableApprovalRecord.of(
                approval_id,
                "operator_workflow_approval",
                _SUBJECT_TYPE,
                command_id,
                decision,
                operator_id,
                decided_at,
                reason=reason,
                metadata={"approval_bound_to": command_id},
            )
        )
        if isinstance(inserted, DurableStateError):
            return inserted.to_dict()
        event = "REQUEST_APPROVED" if decision == "approved" else "REQUEST_REJECTED"
        projected = STATUS_APPROVED if decision == "approved" else STATUS_REJECTED
        self._append_event(command_id, event, decided_at, 2, {"status": projected})
        return self.status(command_id=command_id, checked_at=decided_at)

    def _blocked(self, command_id: str, created_at: str, kind: str, detail: str) -> dict[str, Any]:
        self._append_event(command_id, "DISPATCH_BLOCKED", created_at, 3, {"error_kind": kind})
        return {
            "ok": False,
            "command_id": command_id,
            "status": STATUS_BLOCKED,
            "error_kind": kind,
            "error_detail": detail,
            "side_effects_performed": False,
        }

    def _append_event(self, command_id: str, event_type: str, created_at: str, sequence: int, payload: dict[str, str]) -> None:
        event = DurableEventRecord.of(
            _hash_id("soc-event-", command_id, event_type, sequence),
            event_type,
            _SOURCE,
            _SUBJECT_TYPE,
            command_id,
            created_at,
            sequence,
            payload_json=stable_json_dumps(payload),
        )
        self._store.append_event(event)

    @staticmethod
    def _last_observed_at(command: DurableCommandRecord, approvals: tuple[DurableApprovalRecord, ...], results: tuple[DurableResultRecord, ...], events: tuple[DurableEventRecord, ...]) -> str:
        values = [command.updated_at or command.created_at]
        values.extend(approval.decided_at for approval in approvals)
        values.extend(result.created_at for result in results)
        values.extend(event.created_at for event in events)
        return sorted(values)[-1]

    @staticmethod
    def _safe_result_summary(results: tuple[DurableResultRecord, ...]) -> str | None:
        dry_runs = [result for result in results if result.result_type == "hvs_fake_dry_run"]
        if not dry_runs:
            return None
        return "Fake HVS dry-run succeeded; no live render executed."

    @staticmethod
    def _next_action(status: str) -> str:
        return {
            STATUS_APPROVAL_REQUIRED: "Approve or reject the request.",
            STATUS_APPROVED: "Dispatch the fake HVS dry-run.",
            STATUS_REJECTED: "Submit a new request if work is still needed.",
            STATUS_DRY_RUN_SUCCEEDED: "Inspect the dry-run result summary.",
            STATUS_BLOCKED: "Resolve the blocker before retrying.",
        }.get(status, "Inspect durable state before acting.")


__all__ = [
    "SOLO_OPERATOR_SCHEMA_VERSION",
    "SUPPORTED_WORKFLOW",
    "SoloOperatorControlLoop",
    "WorkflowError",
    "validate_video_request",
]
