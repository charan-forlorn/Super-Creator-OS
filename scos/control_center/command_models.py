"""SCOS Stage 5.1 Control Center command bridge models.

Immutable dataclasses for the local command lifecycle: an operator drafts a
command, validates it, approves it, queues it, runs it through the allowlisted
local runner, and records deterministic command/result events.

All collection fields are tuples (``args`` / ``metadata`` are tuples of
``(key, value)`` string pairs), so no mutable dict/list is ever exposed from a
model instance. ``to_dict()`` uses explicit key order and serializes tuples as
lists.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CONTROL_CENTER_COMMAND_SCHEMA_VERSION = 1

ALLOWED_COMMAND_TYPES = (
    "RUN_SMOKE_CHECK",
    "RUN_RELEASE_CHECK",
    "RUN_SECURITY_SCAN",
    "RUN_STAGE4_FINAL_GATE",
    "OPEN_STAGE5_HANDOFF",
    "GENERATE_STATUS_SNAPSHOT",
)

ALLOWED_EVENT_TYPES = (
    "COMMAND_DRAFTED",
    "COMMAND_VALIDATED",
    "COMMAND_REJECTED",
    "COMMAND_APPROVED",
    "COMMAND_QUEUED",
    "COMMAND_STARTED",
    "COMMAND_COMPLETED",
    "COMMAND_FAILED",
    "COMMAND_BLOCKED",
)

ALLOWED_EVENT_STATUSES = (
    "success",
    "failure",
    "skipped",
    "blocked",
    "pending",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_pairs(field_name: str, value: Any) -> tuple[tuple[str, str], ...]:
    """Normalize ``value`` into an immutable tuple of (str, str) pairs.

    Accepts a mapping or an iterable of two-item pairs; the resulting order is
    the input order (deterministic for tuples/lists; mappings preserve their
    own insertion order).
    """
    if value is None:
        return ()
    if isinstance(value, dict):
        items = value.items()
    else:
        items = value
    pairs: list[tuple[str, str]] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(
                f"{field_name} entries must be (key, value) pairs, got {item!r}"
            )
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(pairs)


def _pairs_to_lists(pairs: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in pairs]


@dataclass(frozen=True)
class CommandDraft:
    """An operator-authored command request; not yet validated or approved.

    ``command_type`` is intentionally NOT enforced here: drafts are operator
    input and unknown types must survive construction so the validation layer
    can reject them with a deterministic error message.
    """

    command_id: str
    command_type: str
    requested_by: str
    created_at: str
    summary: str
    args: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "command_type", str(self.command_type))
        object.__setattr__(self, "requested_by", str(self.requested_by))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "args", _string_pairs("args", self.args))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

    @staticmethod
    def of(
        command_id: str,
        command_type: str,
        requested_by: str,
        created_at: str,
        summary: str,
        *,
        args: Any = (),
        metadata: Any = (),
    ) -> "CommandDraft":
        return CommandDraft(
            command_id=command_id,
            command_type=command_type,
            requested_by=requested_by,
            created_at=created_at,
            summary=summary,
            args=_string_pairs("args", args),
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "summary": self.summary,
            "args": _pairs_to_lists(self.args),
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class OperatorApproval:
    """A single explicit operator decision (approve or reject) for one draft."""

    approval_id: str
    command_id: str
    approved: bool
    approved_by: str
    approved_at: str
    reason: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", str(self.approval_id))
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "approved", bool(self.approved))
        object.__setattr__(self, "approved_by", str(self.approved_by))
        object.__setattr__(self, "approved_at", str(self.approved_at))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

    @staticmethod
    def of(
        approval_id: str,
        command_id: str,
        approved: bool,
        approved_by: str,
        approved_at: str,
        reason: str,
        *,
        metadata: Any = (),
    ) -> "OperatorApproval":
        return OperatorApproval(
            approval_id=approval_id,
            command_id=command_id,
            approved=approved,
            approved_by=approved_by,
            approved_at=approved_at,
            reason=reason,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "command_id": self.command_id,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "reason": self.reason,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class ApprovedCommand:
    """A validated draft that carries an explicit operator approval.

    ``command_type`` is intentionally NOT enforced here: queue lines are
    re-read from disk, and the runner (the last gate) must turn an unknown
    type into a deterministic blocked result instead of a read-time crash.
    The approval gate only ever creates instances from validated drafts.
    """

    command_id: str
    command_type: str
    approved_by: str
    approved_at: str
    args: tuple[tuple[str, str], ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "command_type", str(self.command_type))
        object.__setattr__(self, "approved_by", str(self.approved_by))
        object.__setattr__(self, "approved_at", str(self.approved_at))
        object.__setattr__(self, "args", _string_pairs("args", self.args))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

    @staticmethod
    def of(
        command_id: str,
        command_type: str,
        approved_by: str,
        approved_at: str,
        *,
        args: Any = (),
        metadata: Any = (),
    ) -> "ApprovedCommand":
        return ApprovedCommand(
            command_id=command_id,
            command_type=command_type,
            approved_by=approved_by,
            approved_at=approved_at,
            args=_string_pairs("args", args),
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "args": _pairs_to_lists(self.args),
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class CommandResult:
    """Deterministic outcome of one runner invocation for one approved command."""

    command_id: str
    command_type: str
    ok: bool
    exit_code: int
    started_at: str
    finished_at: str
    stdout_excerpt: str
    stderr_excerpt: str
    output_path: str | None
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "command_type", str(self.command_type))
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "exit_code", int(self.exit_code))
        object.__setattr__(self, "started_at", str(self.started_at))
        object.__setattr__(self, "finished_at", str(self.finished_at))
        object.__setattr__(self, "stdout_excerpt", str(self.stdout_excerpt))
        object.__setattr__(self, "stderr_excerpt", str(self.stderr_excerpt))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

    @staticmethod
    def of(
        command_id: str,
        command_type: str,
        ok: bool,
        exit_code: int,
        started_at: str,
        finished_at: str,
        *,
        stdout_excerpt: str = "",
        stderr_excerpt: str = "",
        output_path: str | None = None,
        metadata: Any = (),
    ) -> "CommandResult":
        return CommandResult(
            command_id=command_id,
            command_type=command_type,
            ok=ok,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=finished_at,
            stdout_excerpt=stdout_excerpt,
            stderr_excerpt=stderr_excerpt,
            output_path=output_path,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "ok": self.ok,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stdout_excerpt": self.stdout_excerpt,
            "stderr_excerpt": self.stderr_excerpt,
            "output_path": self.output_path,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class CommandEvent:
    """One append-only lifecycle event for a command.

    Events are engine-generated, so ``event_type`` and ``status`` are enforced
    at construction time (unlike operator-authored drafts).
    """

    event_id: str
    command_id: str
    event_type: str
    created_at: str
    status: str
    message: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", str(self.event_id))
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "event_type", str(self.event_type))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("event_type", self.event_type, ALLOWED_EVENT_TYPES)
        _require_allowed("status", self.status, ALLOWED_EVENT_STATUSES)

    @staticmethod
    def of(
        event_id: str,
        command_id: str,
        event_type: str,
        created_at: str,
        status: str,
        message: str,
        *,
        metadata: Any = (),
    ) -> "CommandEvent":
        return CommandEvent(
            event_id=event_id,
            command_id=command_id,
            event_type=event_type,
            created_at=created_at,
            status=status,
            message=message,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "command_id": self.command_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "status": self.status,
            "message": self.message,
            "metadata": _pairs_to_lists(self.metadata),
        }
