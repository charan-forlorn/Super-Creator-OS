"""Stage 7.6 pure execution evidence classifiers."""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .operator_command_view_models import (
        ExecutionEvidenceRecord,
        OperatorCommandEvidenceReference,
    )
except ImportError:  # direct-module execution
    from operator_command_view_models import (
        ExecutionEvidenceRecord,
        OperatorCommandEvidenceReference,
    )


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _pairs(values: Any) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for item in values:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {item!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


def classify_execution_state(
    *,
    approval_state: str,
    has_execution_event: bool = False,
    allowlisted: bool = True,
    validation_ok: bool = True,
    explicit_blocker: str = "",
) -> str:
    if approval_state == "tampered":
        return "blocked_tampered_approval"
    if approval_state == "missing_approval":
        return "blocked_missing_approval"
    if approval_state == "denied":
        return "blocked_denied"
    if not allowlisted:
        return "blocked_not_allowlisted"
    if not validation_ok or str(explicit_blocker).strip():
        return "blocked_validation_failed"
    if has_execution_event or approval_state == "executed":
        return "executed"
    if approval_state in {"pending", "approved"}:
        return "not_executed"
    return "unknown"


def build_execution_evidence_record(
    *,
    command_id: str,
    approval_state: str,
    audit_state: str = "unknown",
    event_state: str = "unknown",
    has_execution_event: bool = False,
    allowlisted: bool = True,
    validation_ok: bool = True,
    explicit_blocker: str = "",
    references: tuple[OperatorCommandEvidenceReference, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
) -> ExecutionEvidenceRecord:
    execution_state = classify_execution_state(
        approval_state=approval_state,
        has_execution_event=has_execution_event,
        allowlisted=allowlisted,
        validation_ok=validation_ok,
        explicit_blocker=explicit_blocker,
    )
    summary_by_state = {
        "not_executed": "Command evidence is visible; Stage 7.6 does not execute it.",
        "executed": "Execution evidence is present for this action instance.",
        "blocked_missing_approval": "Execution is blocked because approval evidence is missing.",
        "blocked_denied": "Execution is blocked because the command was denied.",
        "blocked_tampered_approval": "Execution is blocked because approval evidence is tampered.",
        "blocked_not_allowlisted": "Execution is blocked because the command type is not allowlisted.",
        "blocked_validation_failed": "Execution is blocked because validation evidence failed.",
        "unknown": "Execution evidence is unknown and must not be treated as healthy.",
    }
    evidence_id = _stable_id(
        "evid-",
        command_id,
        approval_state,
        audit_state,
        event_state,
        execution_state,
        tuple(reference.reference_id for reference in references),
        _pairs(metadata),
    )
    return ExecutionEvidenceRecord(
        evidence_id=evidence_id,
        command_id=command_id,
        execution_state=execution_state,
        approval_state=approval_state,
        audit_state=audit_state,
        event_state=event_state,
        summary=summary_by_state[execution_state],
        references=references,
        metadata=_pairs(metadata),
    )


__all__ = sorted(
    (
        "build_execution_evidence_record",
        "classify_execution_state",
    )
)
