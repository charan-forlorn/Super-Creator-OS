"""Stage 7.3 immutable operator health/activity read models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OPERATOR_READ_MODELS_SCHEMA_VERSION = 1

FRESHNESS_LEVELS = ("FRESH", "STALE", "MISSING", "UNKNOWN")
HEALTH_SIGNAL_TYPES = (
    "BACKEND_HEALTH",
    "STATE_STORE_HEALTH",
    "EVENT_STREAM_HEALTH",
    "APPROVAL_HEALTH",
    "AUDIT_HEALTH",
    "SECURITY_BASELINE",
    "DRIFT_STATUS",
    "HOST_METRICS",
)
HEALTH_STATUSES = ("HEALTHY", "DEGRADED", "STALE", "MISSING", "BLOCKED", "UNKNOWN")
HEALTH_SEVERITIES = ("info", "warning", "error", "critical")
ACTIVITY_TYPES = (
    "COMMAND_ACTIVITY",
    "APPROVAL_ACTIVITY",
    "AUDIT_ACTIVITY",
    "EVENT_ACTIVITY",
    "STATE_ACTIVITY",
    "SECURITY_ACTIVITY",
    "DRIFT_ACTIVITY",
)
GO_NO_GO_VALUES = ("GO", "NO_GO")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _pairs(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for item in value:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {item!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


@dataclass(frozen=True)
class OperatorFreshnessStatus:
    checked_at: str
    source_id: str
    source_type: str
    is_present: bool
    is_readable: bool
    is_stale: bool
    freshness_level: str
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "source_id", str(self.source_id))
        object.__setattr__(self, "source_type", str(self.source_type))
        object.__setattr__(self, "is_present", bool(self.is_present))
        object.__setattr__(self, "is_readable", bool(self.is_readable))
        object.__setattr__(self, "is_stale", bool(self.is_stale))
        object.__setattr__(self, "freshness_level", str(self.freshness_level))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))
        _require_allowed("freshness_level", self.freshness_level, FRESHNESS_LEVELS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "is_present": self.is_present,
            "is_readable": self.is_readable,
            "is_stale": self.is_stale,
            "freshness_level": self.freshness_level,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class OperatorHealthSignal:
    signal_id: str
    signal_type: str
    status: str
    severity: str
    summary: str
    source_stage: str
    freshness: OperatorFreshnessStatus
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "signal_id", str(self.signal_id))
        object.__setattr__(self, "signal_type", str(self.signal_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        if not isinstance(self.freshness, OperatorFreshnessStatus):
            raise ValueError("freshness must be OperatorFreshnessStatus")
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("signal_type", self.signal_type, HEALTH_SIGNAL_TYPES)
        _require_allowed("status", self.status, HEALTH_STATUSES)
        _require_allowed("severity", self.severity, HEALTH_SEVERITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "source_stage": self.source_stage,
            "freshness": self.freshness.to_dict(),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class OperatorActivityRecord:
    activity_id: str
    activity_type: str
    status: str
    summary: str
    source_stage: str
    occurred_at: str
    references: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "activity_id", str(self.activity_id))
        object.__setattr__(self, "activity_type", str(self.activity_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "occurred_at", str(self.occurred_at))
        object.__setattr__(self, "references", tuple(sorted(str(item) for item in self.references)))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("activity_type", self.activity_type, ACTIVITY_TYPES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "activity_type": self.activity_type,
            "status": self.status,
            "summary": self.summary,
            "source_stage": self.source_stage,
            "occurred_at": self.occurred_at,
            "references": list(self.references),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class OperatorReadModelSnapshot:
    snapshot_id: str
    checked_at: str
    health_signals: tuple[OperatorHealthSignal, ...]
    recent_activity: tuple[OperatorActivityRecord, ...]
    readiness_score: int
    go_no_go: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        for signal in self.health_signals:
            if not isinstance(signal, OperatorHealthSignal):
                raise ValueError("health_signals must contain OperatorHealthSignal values")
        for activity in self.recent_activity:
            if not isinstance(activity, OperatorActivityRecord):
                raise ValueError("recent_activity must contain OperatorActivityRecord values")
        object.__setattr__(
            self,
            "health_signals",
            tuple(sorted(self.health_signals, key=lambda item: item.signal_id)),
        )
        object.__setattr__(
            self,
            "recent_activity",
            tuple(sorted(self.recent_activity, key=lambda item: (item.occurred_at, item.activity_id), reverse=True)),
        )
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "checked_at": self.checked_at,
            "health_signals": [signal.to_dict() for signal in self.health_signals],
            "recent_activity": [activity.to_dict() for activity in self.recent_activity],
            "readiness_score": self.readiness_score,
            "go_no_go": self.go_no_go,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class OperatorReadModelResult:
    accepted: bool
    go_no_go: str
    readiness_score: int
    snapshot: OperatorReadModelSnapshot | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        if self.snapshot is not None and not isinstance(self.snapshot, OperatorReadModelSnapshot):
            raise ValueError("snapshot must be OperatorReadModelSnapshot or None")
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class OperatorReadModelError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "OperatorReadModelError":
        return OperatorReadModelError(
            error_code=error_code,
            message=message,
            checked_at=checked_at,
            blockers=blockers or (message,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "checked_at": self.checked_at,
            "blockers": list(self.blockers),
        }


__all__ = sorted(
    (
        "ACTIVITY_TYPES",
        "FRESHNESS_LEVELS",
        "GO_NO_GO_VALUES",
        "HEALTH_SEVERITIES",
        "HEALTH_SIGNAL_TYPES",
        "HEALTH_STATUSES",
        "OPERATOR_READ_MODELS_SCHEMA_VERSION",
        "OperatorActivityRecord",
        "OperatorFreshnessStatus",
        "OperatorHealthSignal",
        "OperatorReadModelError",
        "OperatorReadModelResult",
        "OperatorReadModelSnapshot",
    )
)
