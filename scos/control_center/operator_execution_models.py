"""SCOS Stage 5.9 Local Operator Execution Console / Manual Command Runbook models.

Immutable dataclasses that model a deterministic, local-first *operator
runbook*: how an already-approved ``manual_command`` / ``proposed_command``
(Stage 5.8) is turned into ordered, human-readable command steps plus a
safety checklist, how the operator's pasted command output is captured, and
how the outcome is classified.

This module NEVER executes a command. It does not run a subprocess, open a
shell/terminal, read or write the clipboard, touch the network, or call a
git/GitHub API. It only models instructions, safety checks, result-capture
objects, and outcomes so a human can run the real commands manually outside
SCOS and paste the result back.

``FrozenMap`` is reused from ``operator_packet_review_models`` (Stage 5.5)
per the existing project convention: one immutable string-keyed map class
shared across ``scos.control_center`` model modules rather than a new one
per stage. Stage 5.9 additionally rejects the ``access_key`` and
``credential`` secret-key markers on top of the shared FrozenMap guard.

All collection fields are tuples, so no mutable dict/list is ever exposed
from a model instance. ``to_dict()`` uses explicit key order and serializes
tuples as lists, nested dataclasses through their own ``to_dict()``, and
``FrozenMap`` as a plain dict.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no subprocess, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

OPERATOR_EXECUTION_SCHEMA_VERSION = 1

ALLOWED_COMMAND_TYPES = (
    "git_status",
    "git_diff",
    "git_add",
    "git_commit",
    "git_fetch",
    "git_push",
    "test",
    "build",
    "lint",
    "security_scan",
    "verification",
    "informational",
    "unknown",
)

ALLOWED_SHELLS = (
    "powershell",
    "cmd",
    "bash",
    "python",
    "manual",
)

ALLOWED_RISK_LEVELS = (
    "low",
    "medium",
    "high",
    "critical",
)

ALLOWED_SAFETY_CHECK_STATUSES = (
    "pending",
    "passed",
    "failed",
    "skipped",
    "requires_review",
)

ALLOWED_SAFETY_CHECK_SEVERITIES = (
    "info",
    "warning",
    "error",
    "critical",
)

ALLOWED_RUNBOOK_TYPES = (
    "commit_runbook",
    "push_runbook",
    "verification_runbook",
    "release_check_runbook",
    "recovery_runbook",
    "general_manual_command",
)

ALLOWED_RUNBOOK_STATUSES = (
    "drafted",
    "ready_for_operator",
    "blocked",
    "executed_manually",
    "result_captured",
    "verified",
    "failed",
    "archived",
)

ALLOWED_CAPTURE_VERDICTS = (
    "PASS",
    "PASS_WITH_WARNINGS",
    "NEEDS_REVIEW",
    "NEEDS_FIX",
    "BLOCKED",
    "FAIL",
    "UNKNOWN",
)

ALLOWED_OUTCOMES = (
    "command_succeeded",
    "command_succeeded_with_warnings",
    "command_failed",
    "command_blocked",
    "command_needs_review",
    "command_needs_fix",
    "command_unknown",
)

# ``None`` is an allowed recommended_next_agent (no routing suggestion).
ALLOWED_NEXT_AGENTS = (
    "chatgpt",
    "claude_code",
    "codex",
    "hermes",
    "operator",
)

ALLOWED_OPERATOR_EXECUTION_ERROR_KINDS = (
    "validation_error",
    "empty_required_field",
    "invalid_command_type",
    "invalid_shell",
    "invalid_risk_level",
    "invalid_status",
    "invalid_severity",
    "invalid_runbook_type",
    "invalid_verdict",
    "invalid_outcome",
    "invalid_next_agent",
    "invalid_step_order",
    "invalid_path",
    "unsafe_metadata",
    "invalid_collection_type",
    "contract_violation",
)

_FORBIDDEN_URL_MARKERS = ("http://", "https://")
_URL_SCHEME_MARKER = "://"

# Stage 5.9 secret-key markers (superset of the shared FrozenMap markers,
# adding ``access_key`` and ``credential`` per the Stage 5.9 contract).
_SECRET_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
    "access_key",
    "credential",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _require_nonempty(field_name: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_positive_int(field_name: str, value: int) -> None:
    if int(value) <= 0:
        raise ValueError(f"{field_name} must be a positive int, got {value!r}")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _reject_url(field_name: str, value: str | None) -> None:
    if value is None:
        return
    lowered = str(value).lower()
    for marker in _FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{field_name} must be a local path/value, not a URL "
                f"(found {marker!r})"
            )


def _reject_url_like_path(field_name: str, value: str) -> None:
    if _URL_SCHEME_MARKER in str(value).lower():
        raise ValueError(f"{field_name} must not look like a URL: {value!r}")
    _reject_url(field_name, value)


def _reject_secret_keys(field_name: str, metadata: FrozenMap) -> None:
    for key in metadata:
        lowered = key.lower()
        for marker in _SECRET_KEY_MARKERS:
            if marker in lowered:
                raise ValueError(
                    f"{field_name} must not contain secret-bearing keys "
                    f"(found {key!r})"
                )


def _frozen_map(value: Any = None) -> FrozenMap:
    # FrozenMap.of already rejects the shared secret markers + URL values;
    # then apply the Stage 5.9 superset (access_key / credential).
    frozen = FrozenMap.of(value)
    _reject_secret_keys("metadata", frozen)
    return frozen


@dataclass(frozen=True)
class RunbookCommandStep:
    """One ordered, human-run command step in a manual runbook.

    The ``command`` text is instructional only. Nothing in Stage 5.9 ever
    executes it; the operator copies and runs it manually outside SCOS.
    """

    step_id: str
    step_order: int
    title: str
    command: str
    command_type: str
    shell: str
    working_directory: str
    requires_manual_copy: bool
    requires_operator_confirmation: bool
    expected_result_hint: str
    risk_level: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", str(self.step_id))
        object.__setattr__(self, "step_order", int(self.step_order))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "command", str(self.command))
        object.__setattr__(self, "command_type", str(self.command_type))
        object.__setattr__(self, "shell", str(self.shell))
        object.__setattr__(self, "working_directory", str(self.working_directory))
        object.__setattr__(self, "requires_manual_copy", bool(self.requires_manual_copy))
        object.__setattr__(
            self,
            "requires_operator_confirmation",
            bool(self.requires_operator_confirmation),
        )
        object.__setattr__(self, "expected_result_hint", str(self.expected_result_hint))
        object.__setattr__(self, "risk_level", str(self.risk_level))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("step_id", self.step_id)
        _require_positive_int("step_order", self.step_order)
        _require_nonempty("title", self.title)
        _require_nonempty("command", self.command)
        _require_allowed("command_type", self.command_type, ALLOWED_COMMAND_TYPES)
        _require_allowed("shell", self.shell, ALLOWED_SHELLS)
        _require_nonempty("working_directory", self.working_directory)
        _reject_url_like_path("working_directory", self.working_directory)
        _require_allowed("risk_level", self.risk_level, ALLOWED_RISK_LEVELS)

    @staticmethod
    def of(
        step_id: str,
        step_order: int,
        title: str,
        command: str,
        command_type: str,
        *,
        shell: str = "powershell",
        working_directory: str = ".",
        requires_manual_copy: bool = True,
        requires_operator_confirmation: bool = True,
        expected_result_hint: str = "",
        risk_level: str = "low",
        metadata: Any = None,
    ) -> "RunbookCommandStep":
        return RunbookCommandStep(
            step_id=step_id,
            step_order=step_order,
            title=title,
            command=command,
            command_type=command_type,
            shell=shell,
            working_directory=working_directory,
            requires_manual_copy=requires_manual_copy,
            requires_operator_confirmation=requires_operator_confirmation,
            expected_result_hint=expected_result_hint,
            risk_level=risk_level,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_order": self.step_order,
            "title": self.title,
            "command": self.command,
            "command_type": self.command_type,
            "shell": self.shell,
            "working_directory": self.working_directory,
            "requires_manual_copy": self.requires_manual_copy,
            "requires_operator_confirmation": self.requires_operator_confirmation,
            "expected_result_hint": self.expected_result_hint,
            "risk_level": self.risk_level,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ExecutionSafetyCheck:
    """One pre-check the operator must reason about before running a runbook.

    Safety checks are instructions/evidence only. No check ever executes a
    command; ``status`` is set by a human / caller, not by SCOS.
    """

    check_id: str
    title: str
    description: str
    status: str
    severity: str
    required: bool
    operator_instruction: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", str(self.check_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "operator_instruction", str(self.operator_instruction))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("check_id", self.check_id)
        _require_nonempty("title", self.title)
        _require_allowed("status", self.status, ALLOWED_SAFETY_CHECK_STATUSES)
        _require_allowed("severity", self.severity, ALLOWED_SAFETY_CHECK_SEVERITIES)

    @staticmethod
    def of(
        check_id: str,
        title: str,
        description: str,
        *,
        status: str = "pending",
        severity: str = "warning",
        required: bool = True,
        operator_instruction: str = "",
        metadata: Any = None,
    ) -> "ExecutionSafetyCheck":
        return ExecutionSafetyCheck(
            check_id=check_id,
            title=title,
            description=description,
            status=status,
            severity=severity,
            required=required,
            operator_instruction=operator_instruction,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "severity": self.severity,
            "required": self.required,
            "operator_instruction": self.operator_instruction,
            "metadata": self.metadata.to_dict(),
        }


def _command_steps(value: Any) -> tuple[RunbookCommandStep, ...]:
    steps = tuple(value or ())
    for step in steps:
        if not isinstance(step, RunbookCommandStep):
            raise ValueError("command_steps entries must be RunbookCommandStep instances")
    return steps


def _safety_checks(value: Any) -> tuple[ExecutionSafetyCheck, ...]:
    checks = tuple(value or ())
    for check in checks:
        if not isinstance(check, ExecutionSafetyCheck):
            raise ValueError("safety_checks entries must be ExecutionSafetyCheck instances")
    return checks


@dataclass(frozen=True)
class ManualCommandRunbook:
    """A deterministic operator runbook assembled from an approved command."""

    ok: bool
    schema_version: int
    runbook_id: str
    source_approval_id: str | None
    source_commit_proposal_id: str | None
    source_push_proposal_id: str | None
    session_id: str
    task_id: str
    title: str
    objective: str
    command_summary: str
    runbook_type: str
    created_at: str
    status: str
    safety_checks: tuple[ExecutionSafetyCheck, ...]
    command_steps: tuple[RunbookCommandStep, ...]
    expected_outputs: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    operator_notes: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "runbook_id", str(self.runbook_id))
        object.__setattr__(
            self, "source_approval_id", _optional_str(self.source_approval_id)
        )
        object.__setattr__(
            self,
            "source_commit_proposal_id",
            _optional_str(self.source_commit_proposal_id),
        )
        object.__setattr__(
            self,
            "source_push_proposal_id",
            _optional_str(self.source_push_proposal_id),
        )
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "objective", str(self.objective))
        object.__setattr__(self, "command_summary", str(self.command_summary))
        object.__setattr__(self, "runbook_type", str(self.runbook_type))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "safety_checks", _safety_checks(self.safety_checks))
        object.__setattr__(self, "command_steps", _command_steps(self.command_steps))
        object.__setattr__(self, "expected_outputs", _string_tuple(self.expected_outputs))
        object.__setattr__(self, "blocked_reasons", _string_tuple(self.blocked_reasons))
        object.__setattr__(self, "operator_notes", _string_tuple(self.operator_notes))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("runbook_id", self.runbook_id)
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("task_id", self.task_id)
        _require_nonempty("title", self.title)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("runbook_type", self.runbook_type, ALLOWED_RUNBOOK_TYPES)
        _require_allowed("status", self.status, ALLOWED_RUNBOOK_STATUSES)

    @staticmethod
    def of(
        runbook_id: str,
        session_id: str,
        task_id: str,
        title: str,
        objective: str,
        command_summary: str,
        runbook_type: str,
        created_at: str,
        status: str,
        *,
        ok: bool = True,
        schema_version: int = OPERATOR_EXECUTION_SCHEMA_VERSION,
        source_approval_id: str | None = None,
        source_commit_proposal_id: str | None = None,
        source_push_proposal_id: str | None = None,
        safety_checks: Any = None,
        command_steps: Any = None,
        expected_outputs: Any = None,
        blocked_reasons: Any = None,
        operator_notes: Any = None,
        metadata: Any = None,
    ) -> "ManualCommandRunbook":
        return ManualCommandRunbook(
            ok=ok,
            schema_version=schema_version,
            runbook_id=runbook_id,
            source_approval_id=source_approval_id,
            source_commit_proposal_id=source_commit_proposal_id,
            source_push_proposal_id=source_push_proposal_id,
            session_id=session_id,
            task_id=task_id,
            title=title,
            objective=objective,
            command_summary=command_summary,
            runbook_type=runbook_type,
            created_at=created_at,
            status=status,
            safety_checks=_safety_checks(safety_checks),
            command_steps=_command_steps(command_steps),
            expected_outputs=_string_tuple(expected_outputs),
            blocked_reasons=_string_tuple(blocked_reasons),
            operator_notes=_string_tuple(operator_notes),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "runbook_id": self.runbook_id,
            "source_approval_id": self.source_approval_id,
            "source_commit_proposal_id": self.source_commit_proposal_id,
            "source_push_proposal_id": self.source_push_proposal_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "title": self.title,
            "objective": self.objective,
            "command_summary": self.command_summary,
            "runbook_type": self.runbook_type,
            "created_at": self.created_at,
            "status": self.status,
            "safety_checks": [check.to_dict() for check in self.safety_checks],
            "command_steps": [step.to_dict() for step in self.command_steps],
            "expected_outputs": list(self.expected_outputs),
            "blocked_reasons": list(self.blocked_reasons),
            "operator_notes": list(self.operator_notes),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommandExecutionCapture:
    """The operator's pasted-back result after running a runbook manually.

    ``raw_output_excerpt`` is plain text only. No secrets are stored; the
    caller must not paste credentials, and secret-like metadata keys are
    rejected. Nothing here executes a command.
    """

    ok: bool
    schema_version: int
    capture_id: str
    runbook_id: str
    session_id: str
    task_id: str
    operator_reported_command: str
    pasted_output_summary: str
    raw_output_excerpt: str
    exit_status_text: str
    verdict: str
    captured_at: str
    evidence_paths: tuple[str, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "capture_id", str(self.capture_id))
        object.__setattr__(self, "runbook_id", str(self.runbook_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(
            self, "operator_reported_command", str(self.operator_reported_command)
        )
        object.__setattr__(self, "pasted_output_summary", str(self.pasted_output_summary))
        object.__setattr__(self, "raw_output_excerpt", str(self.raw_output_excerpt))
        object.__setattr__(self, "exit_status_text", str(self.exit_status_text))
        object.__setattr__(self, "verdict", str(self.verdict))
        object.__setattr__(self, "captured_at", str(self.captured_at))
        object.__setattr__(self, "evidence_paths", _string_tuple(self.evidence_paths))
        object.__setattr__(self, "warnings", _string_tuple(self.warnings))
        object.__setattr__(self, "blockers", _string_tuple(self.blockers))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("capture_id", self.capture_id)
        _require_nonempty("runbook_id", self.runbook_id)
        _require_nonempty("captured_at", self.captured_at)
        _require_allowed("verdict", self.verdict, ALLOWED_CAPTURE_VERDICTS)
        for path in self.evidence_paths:
            _reject_url_like_path("evidence_paths", path)

    @staticmethod
    def of(
        capture_id: str,
        runbook_id: str,
        session_id: str,
        task_id: str,
        operator_reported_command: str,
        pasted_output_summary: str,
        raw_output_excerpt: str,
        exit_status_text: str,
        verdict: str,
        captured_at: str,
        *,
        ok: bool = True,
        schema_version: int = OPERATOR_EXECUTION_SCHEMA_VERSION,
        evidence_paths: Any = None,
        warnings: Any = None,
        blockers: Any = None,
        metadata: Any = None,
    ) -> "CommandExecutionCapture":
        return CommandExecutionCapture(
            ok=ok,
            schema_version=schema_version,
            capture_id=capture_id,
            runbook_id=runbook_id,
            session_id=session_id,
            task_id=task_id,
            operator_reported_command=operator_reported_command,
            pasted_output_summary=pasted_output_summary,
            raw_output_excerpt=raw_output_excerpt,
            exit_status_text=exit_status_text,
            verdict=verdict,
            captured_at=captured_at,
            evidence_paths=_string_tuple(evidence_paths),
            warnings=_string_tuple(warnings),
            blockers=_string_tuple(blockers),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "capture_id": self.capture_id,
            "runbook_id": self.runbook_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "operator_reported_command": self.operator_reported_command,
            "pasted_output_summary": self.pasted_output_summary,
            "raw_output_excerpt": self.raw_output_excerpt,
            "exit_status_text": self.exit_status_text,
            "verdict": self.verdict,
            "captured_at": self.captured_at,
            "evidence_paths": list(self.evidence_paths),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorExecutionOutcome:
    """The classified outcome derived from a runbook + its capture."""

    ok: bool
    schema_version: int
    outcome_id: str
    runbook_id: str
    capture_id: str
    session_id: str
    task_id: str
    outcome: str
    summary: str
    recommended_next_action: str
    recommended_next_agent: str | None
    operator_review_required: bool
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "outcome_id", str(self.outcome_id))
        object.__setattr__(self, "runbook_id", str(self.runbook_id))
        object.__setattr__(self, "capture_id", str(self.capture_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "outcome", str(self.outcome))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(
            self, "recommended_next_action", str(self.recommended_next_action)
        )
        object.__setattr__(
            self, "recommended_next_agent", _optional_str(self.recommended_next_agent)
        )
        object.__setattr__(
            self, "operator_review_required", bool(self.operator_review_required)
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("outcome_id", self.outcome_id)
        _require_nonempty("runbook_id", self.runbook_id)
        _require_nonempty("capture_id", self.capture_id)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("outcome", self.outcome, ALLOWED_OUTCOMES)
        if self.recommended_next_agent is not None:
            _require_allowed(
                "recommended_next_agent",
                self.recommended_next_agent,
                ALLOWED_NEXT_AGENTS,
            )

    @staticmethod
    def of(
        outcome_id: str,
        runbook_id: str,
        capture_id: str,
        session_id: str,
        task_id: str,
        outcome: str,
        summary: str,
        recommended_next_action: str,
        created_at: str,
        *,
        ok: bool = True,
        schema_version: int = OPERATOR_EXECUTION_SCHEMA_VERSION,
        recommended_next_agent: str | None = None,
        operator_review_required: bool = True,
        metadata: Any = None,
    ) -> "OperatorExecutionOutcome":
        return OperatorExecutionOutcome(
            ok=ok,
            schema_version=schema_version,
            outcome_id=outcome_id,
            runbook_id=runbook_id,
            capture_id=capture_id,
            session_id=session_id,
            task_id=task_id,
            outcome=outcome,
            summary=summary,
            recommended_next_action=recommended_next_action,
            recommended_next_agent=recommended_next_agent,
            operator_review_required=operator_review_required,
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "outcome_id": self.outcome_id,
            "runbook_id": self.runbook_id,
            "capture_id": self.capture_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "outcome": self.outcome,
            "summary": self.summary,
            "recommended_next_action": self.recommended_next_action,
            "recommended_next_agent": self.recommended_next_agent,
            "operator_review_required": self.operator_review_required,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorExecutionError:
    """Structured, deterministic error returned instead of raising."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed(
            "error_kind", self.error_kind, ALLOWED_OPERATOR_EXECUTION_ERROR_KINDS
        )

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        ok: bool = False,
        schema_version: int = OPERATOR_EXECUTION_SCHEMA_VERSION,
        metadata: Any = None,
    ) -> "OperatorExecutionError":
        return OperatorExecutionError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_step=failed_step,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "metadata": self.metadata.to_dict(),
        }
