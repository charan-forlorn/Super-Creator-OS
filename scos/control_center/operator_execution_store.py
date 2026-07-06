"""SCOS Stage 5.9 Operator Execution JSONL store.

Append-only, deterministic JSONL persistence for ``ManualCommandRunbook``,
``CommandExecutionCapture``, and ``OperatorExecutionOutcome``. Each public
function takes the target JSONL **file** path directly (str or
``pathlib.Path``) per the Stage 5.9 contract.

No SQLite, no file locks, no background workers, no hidden writes, no writes
outside the provided path, and no database. This module never runs a command,
subprocess, or network call; it only serializes/deserializes the models
produced by ``operator_execution_models`` / ``operator_execution_runbook``.

Deterministic line format: ``json.dumps(sort_keys=True,
separators=(",", ":"))``, UTF-8, LF newline. Append order is preserved.
Malformed JSONL fails fast with a deterministic ``ValueError``.

Default documented work paths (not created automatically by this module):

* scos/work/control_center/manual_command_runbooks.jsonl
* scos/work/control_center/command_execution_captures.jsonl
* scos/work/control_center/operator_execution_outcomes.jsonl
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .operator_execution_models import (
        CommandExecutionCapture,
        ExecutionSafetyCheck,
        ManualCommandRunbook,
        OperatorExecutionOutcome,
        RunbookCommandStep,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_execution_models import (  # type: ignore[no-redef]
        CommandExecutionCapture,
        ExecutionSafetyCheck,
        ManualCommandRunbook,
        OperatorExecutionOutcome,
        RunbookCommandStep,
    )

OPERATOR_EXECUTION_STORE_SCHEMA_VERSION = 1

# Documented default filenames (callers pass a full path; these are the
# conventional basenames under scos/work/control_center/).
MANUAL_COMMAND_RUNBOOKS_FILE = "manual_command_runbooks.jsonl"
COMMAND_EXECUTION_CAPTURES_FILE = "command_execution_captures.jsonl"
OPERATOR_EXECUTION_OUTCOMES_FILE = "operator_execution_outcomes.jsonl"

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _ensure_local_file(path: Any) -> Path:
    if isinstance(path, str):
        text = path.strip()
        if text.lower().startswith(_URL_PREFIXES) or _SCHEME_RE.match(text):
            raise ValueError("URL_PATH_REJECTED: path must be a local file path")
        if not text:
            raise ValueError("INVALID_PATH: path must not be empty")
        return Path(text)
    if isinstance(path, Path):
        return path
    raise ValueError("INVALID_PATH: path must be a str or pathlib.Path")


def _jsonl_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append(path: Any, payload: dict) -> None:
    target = _ensure_local_file(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl_line(payload) + "\n")


def _read(path: Any, error_code: str) -> tuple[dict, ...]:
    target = _ensure_local_file(path)
    if not target.is_file():
        return ()
    objects: list[dict] = []
    text = target.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"{error_code}: line {line_number} is not valid JSON") from None
        if not isinstance(payload, dict):
            raise ValueError(f"{error_code}: line {line_number} is not a JSON object")
        objects.append(payload)
    return tuple(objects)


def _pairs_from_dict(value: Any) -> dict:
    if value is None:
        return {}
    return dict(value)


# --------------------------------------------------------------------------
# Rehydration
# --------------------------------------------------------------------------


def _runbook_from_dict(payload: dict) -> ManualCommandRunbook:
    steps = tuple(
        RunbookCommandStep.of(
            item.get("step_id", ""),
            int(item.get("step_order", 1)),
            item.get("title", ""),
            item.get("command", ""),
            item.get("command_type", "unknown"),
            shell=item.get("shell", "powershell"),
            working_directory=item.get("working_directory", "."),
            requires_manual_copy=bool(item.get("requires_manual_copy", True)),
            requires_operator_confirmation=bool(
                item.get("requires_operator_confirmation", True)
            ),
            expected_result_hint=item.get("expected_result_hint", ""),
            risk_level=item.get("risk_level", "low"),
            metadata=_pairs_from_dict(item.get("metadata")),
        )
        for item in payload.get("command_steps", ())
    )
    checks = tuple(
        ExecutionSafetyCheck.of(
            item.get("check_id", ""),
            item.get("title", ""),
            item.get("description", ""),
            status=item.get("status", "pending"),
            severity=item.get("severity", "warning"),
            required=bool(item.get("required", True)),
            operator_instruction=item.get("operator_instruction", ""),
            metadata=_pairs_from_dict(item.get("metadata")),
        )
        for item in payload.get("safety_checks", ())
    )
    return ManualCommandRunbook.of(
        payload.get("runbook_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("title", ""),
        payload.get("objective", ""),
        payload.get("command_summary", ""),
        payload.get("runbook_type", "general_manual_command"),
        payload.get("created_at", ""),
        payload.get("status", "drafted"),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        source_approval_id=payload.get("source_approval_id"),
        source_commit_proposal_id=payload.get("source_commit_proposal_id"),
        source_push_proposal_id=payload.get("source_push_proposal_id"),
        safety_checks=checks,
        command_steps=steps,
        expected_outputs=tuple(payload.get("expected_outputs", ())),
        blocked_reasons=tuple(payload.get("blocked_reasons", ())),
        operator_notes=tuple(payload.get("operator_notes", ())),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _capture_from_dict(payload: dict) -> CommandExecutionCapture:
    return CommandExecutionCapture.of(
        payload.get("capture_id", ""),
        payload.get("runbook_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("operator_reported_command", ""),
        payload.get("pasted_output_summary", ""),
        payload.get("raw_output_excerpt", ""),
        payload.get("exit_status_text", ""),
        payload.get("verdict", "UNKNOWN"),
        payload.get("captured_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        evidence_paths=tuple(payload.get("evidence_paths", ())),
        warnings=tuple(payload.get("warnings", ())),
        blockers=tuple(payload.get("blockers", ())),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


def _outcome_from_dict(payload: dict) -> OperatorExecutionOutcome:
    return OperatorExecutionOutcome.of(
        payload.get("outcome_id", ""),
        payload.get("runbook_id", ""),
        payload.get("capture_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("outcome", "command_unknown"),
        payload.get("summary", ""),
        payload.get("recommended_next_action", ""),
        payload.get("created_at", ""),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        recommended_next_agent=payload.get("recommended_next_agent"),
        operator_review_required=bool(payload.get("operator_review_required", True)),
        metadata=_pairs_from_dict(payload.get("metadata")),
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------


def append_manual_command_runbook(path: Any, runbook: ManualCommandRunbook) -> None:
    if not isinstance(runbook, ManualCommandRunbook):
        raise ValueError("NOT_A_MANUAL_COMMAND_RUNBOOK: runbook must be a ManualCommandRunbook")
    _append(path, runbook.to_dict())


def append_command_execution_capture(path: Any, capture: CommandExecutionCapture) -> None:
    if not isinstance(capture, CommandExecutionCapture):
        raise ValueError("NOT_A_COMMAND_EXECUTION_CAPTURE: capture must be a CommandExecutionCapture")
    _append(path, capture.to_dict())


def append_operator_execution_outcome(path: Any, outcome: OperatorExecutionOutcome) -> None:
    if not isinstance(outcome, OperatorExecutionOutcome):
        raise ValueError("NOT_AN_OPERATOR_EXECUTION_OUTCOME: outcome must be an OperatorExecutionOutcome")
    _append(path, outcome.to_dict())


def load_manual_command_runbooks(path: Any) -> tuple[ManualCommandRunbook, ...]:
    return tuple(
        _runbook_from_dict(payload)
        for payload in _read(path, "INVALID_MANUAL_COMMAND_RUNBOOK_LINE")
    )


def load_command_execution_captures(path: Any) -> tuple[CommandExecutionCapture, ...]:
    return tuple(
        _capture_from_dict(payload)
        for payload in _read(path, "INVALID_COMMAND_EXECUTION_CAPTURE_LINE")
    )


def load_operator_execution_outcomes(path: Any) -> tuple[OperatorExecutionOutcome, ...]:
    return tuple(
        _outcome_from_dict(payload)
        for payload in _read(path, "INVALID_OPERATOR_EXECUTION_OUTCOME_LINE")
    )
