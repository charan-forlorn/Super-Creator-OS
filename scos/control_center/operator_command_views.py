"""Stage 7.6 read-only operator command view builders."""

from __future__ import annotations

import hashlib
import json
from typing import Any

try:
    from .execution_evidence_surface import build_execution_evidence_record
    from .operator_command_view_models import (
        OperatorCommandApprovalState,
        OperatorCommandEvidenceReference,
        OperatorCommandView,
        OperatorCommandViewSnapshot,
        OperatorCommandViewTotals,
    )
except ImportError:  # direct-module execution
    from execution_evidence_surface import build_execution_evidence_record
    from operator_command_view_models import (
        OperatorCommandApprovalState,
        OperatorCommandEvidenceReference,
        OperatorCommandView,
        OperatorCommandViewSnapshot,
        OperatorCommandViewTotals,
    )


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def validate_operator_command_view_inputs(*, checked_at: str, commands: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    errors: list[str] = []
    if not str(checked_at).strip():
        errors.append("checked_at must be caller-supplied and non-empty")
    seen: set[str] = set()
    for index, command in enumerate(commands):
        command_id = str(command.get("command_id", "")).strip()
        command_type = str(command.get("command_type", "")).strip()
        if not command_id:
            errors.append(f"commands[{index}].command_id must be non-empty")
        if not command_type:
            errors.append(f"commands[{index}].command_type must be non-empty")
        if command_id in seen:
            errors.append(f"duplicate command_id: {command_id}")
        seen.add(command_id)
        if "output_path" in command:
            errors.append(f"commands[{index}] must not request output_path or writes")
    return tuple(sorted(errors))


def _reference_from_dict(payload: dict[str, Any]) -> OperatorCommandEvidenceReference:
    return OperatorCommandEvidenceReference(
        reference_id=str(payload.get("reference_id", "")),
        reference_type=str(payload.get("reference_type", "unknown")),
        source_stage=str(payload.get("source_stage", "Stage 7.6")),
        path=str(payload.get("path", "")),
        exists=bool(payload.get("exists", False)),
        readable=bool(payload.get("readable", False)),
        digest=None if payload.get("digest") is None else str(payload.get("digest")),
    )


def _references(values: Any) -> tuple[OperatorCommandEvidenceReference, ...]:
    refs: list[OperatorCommandEvidenceReference] = []
    for item in tuple(values or ()):
        if isinstance(item, OperatorCommandEvidenceReference):
            refs.append(item)
        else:
            refs.append(_reference_from_dict(dict(item)))
    return tuple(refs)


def classify_approval_state(
    *,
    command_id: str,
    approval_decision: str | None = None,
    approval_required: bool = True,
    approval_tampered: bool = False,
    has_execution_event: bool = False,
    explicit_blocker: str = "",
) -> OperatorCommandApprovalState:
    decision = None if approval_decision is None else str(approval_decision)
    if approval_tampered:
        state = "tampered"
    elif has_execution_event:
        state = "executed"
    elif explicit_blocker:
        state = "blocked"
    elif decision == "approved":
        state = "approved"
    elif decision == "denied":
        state = "denied"
    elif decision == "pending":
        state = "pending"
    elif approval_required:
        state = "missing_approval"
    else:
        state = "unknown"

    terminal = state in {"denied", "missing_approval", "tampered", "blocked", "executed"}
    action_by_state = {
        "pending": "Review approval evidence manually.",
        "approved": "Inspect execution evidence; Stage 7.6 does not run commands.",
        "denied": "Create a new command draft manually if needed.",
        "missing_approval": "Create a fresh approved command instance before execution.",
        "tampered": "Stop and investigate approval evidence.",
        "executed": "Inspect audit and event evidence for the completed action instance.",
        "blocked": "Resolve the displayed blocker without bypassing approval.",
        "unknown": "Inspect source evidence before trusting this command.",
    }
    return OperatorCommandApprovalState(
        command_id=command_id,
        approval_state=state,
        terminal=terminal,
        human_readable_status=state.replace("_", " "),
        required_operator_action=action_by_state[state],
        evidence_references=(),
    )


def build_operator_command_view(
    *,
    checked_at: str,
    command: dict[str, Any],
) -> OperatorCommandView:
    command_id = str(command.get("command_id", ""))
    command_type = str(command.get("command_type", ""))
    references = _references(command.get("references", ()))
    has_execution_event = bool(command.get("has_execution_event", False))
    explicit_blocker = str(command.get("blocker_reason", ""))
    approval = classify_approval_state(
        command_id=command_id,
        approval_decision=command.get("approval_decision"),
        approval_required=bool(command.get("approval_required", True)),
        approval_tampered=bool(command.get("approval_tampered", False)),
        has_execution_event=has_execution_event,
        explicit_blocker=explicit_blocker,
    )
    approval = OperatorCommandApprovalState(
        command_id=approval.command_id,
        approval_state=approval.approval_state,
        terminal=approval.terminal,
        human_readable_status=approval.human_readable_status,
        required_operator_action=approval.required_operator_action,
        evidence_references=references,
    )
    audit_state = str(command.get("audit_state", "unknown"))
    event_state = str(command.get("event_state", "unknown"))
    execution = build_execution_evidence_record(
        command_id=command_id,
        approval_state=approval.approval_state,
        audit_state=audit_state,
        event_state=event_state,
        has_execution_event=has_execution_event,
        allowlisted=bool(command.get("allowlisted", True)),
        validation_ok=bool(command.get("validation_ok", True)),
        explicit_blocker=explicit_blocker,
        references=references,
        metadata=tuple(command.get("metadata", ())),
    )
    blockers = list(command.get("blockers", ()))
    warnings = list(command.get("warnings", ()))
    if approval.approval_state in {"missing_approval", "tampered", "denied", "blocked"}:
        blockers.append(approval.required_operator_action)
    if execution.execution_state == "unknown":
        warnings.append("Execution evidence is unknown and not healthy.")
    if audit_state in {"missing", "tampered"}:
        blockers.append(f"audit evidence is {audit_state}")
    elif audit_state == "unknown":
        warnings.append("Audit evidence is unknown.")
    missing_optional = tuple(ref.path for ref in references if not ref.exists and ref.reference_type != "approval")
    if missing_optional:
        warnings.append("Optional evidence is missing: " + ", ".join(sorted(missing_optional)))
    view_id = _stable_id(
        "ocv-",
        checked_at,
        command_id,
        command_type,
        approval.approval_state,
        execution.execution_state,
        tuple(ref.reference_id for ref in references),
    )
    return OperatorCommandView(
        view_id=view_id,
        checked_at=checked_at,
        command_id=command_id,
        command_type=command_type,
        approval=approval,
        execution=execution,
        warnings=tuple(warnings),
        blockers=tuple(blockers),
        next_manual_action=approval.required_operator_action,
    )


def _totals(views: tuple[OperatorCommandView, ...]) -> OperatorCommandViewTotals:
    return OperatorCommandViewTotals(
        pending=sum(1 for view in views if view.approval.approval_state == "pending"),
        approved=sum(1 for view in views if view.approval.approval_state == "approved"),
        denied=sum(1 for view in views if view.approval.approval_state == "denied"),
        missing_approval=sum(1 for view in views if view.approval.approval_state == "missing_approval"),
        executed=sum(1 for view in views if view.execution.execution_state == "executed"),
        blocked=sum(1 for view in views if view.blockers or view.execution.execution_state.startswith("blocked_")),
        audited=sum(1 for view in views if view.execution.audit_state == "audited"),
    )


def build_operator_command_view_snapshot(
    *,
    checked_at: str,
    commands: tuple[dict[str, Any], ...],
) -> OperatorCommandViewSnapshot:
    input_errors = validate_operator_command_view_inputs(checked_at=checked_at, commands=commands)
    views = tuple(
        build_operator_command_view(checked_at=checked_at, command=command)
        for command in sorted(commands, key=lambda item: str(item.get("command_id", "")))
    )
    blockers = tuple(sorted(set(input_errors) | {blocker for view in views for blocker in view.blockers}))
    warnings = tuple(sorted({warning for view in views for warning in view.warnings}))
    accepted = not blockers
    readiness_score = 100 if accepted and not warnings else max(0, 90 - (len(blockers) * 10) - (len(warnings) * 2))
    snapshot_id = _stable_id(
        "ocvs-",
        checked_at,
        _stable_json([view.to_dict() for view in views]),
        blockers,
        warnings,
    )
    return OperatorCommandViewSnapshot(
        snapshot_id=snapshot_id,
        checked_at=checked_at,
        views=views,
        totals=_totals(views),
        warnings=warnings,
        blockers=blockers,
        readiness_score=readiness_score,
        go_no_go="GO" if accepted else "NO_GO",
        accepted=accepted,
    )


def render_operator_command_view_markdown(*, snapshot: OperatorCommandViewSnapshot) -> str:
    lines = [
        "# Stage 7.6 Operator Command Views",
        "",
        f"- Snapshot ID: `{snapshot.snapshot_id}`",
        f"- Checked at: `{snapshot.checked_at}`",
        f"- Go/No-Go: `{snapshot.go_no_go}`",
        f"- Readiness score: `{snapshot.readiness_score}`",
        "",
        "## Totals",
    ]
    for key, value in snapshot.totals.to_dict().items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Commands")
    for view in snapshot.views:
        lines.append(f"- `{view.command_id}` {view.command_type}: {view.approval.approval_state} / {view.execution.execution_state}")
    return "\n".join(lines) + "\n"


__all__ = sorted(
    (
        "build_operator_command_view",
        "build_operator_command_view_snapshot",
        "classify_approval_state",
        "render_operator_command_view_markdown",
        "validate_operator_command_view_inputs",
    )
)
