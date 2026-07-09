"""Stage 7.1 immutable models for the local Control Center read surface.

The read surface is a deterministic, read-only query layer over existing
Stage 6 artifacts. Models are frozen and serialize with stable key order.
Caller-supplied timestamps are echoed; no clock-derived values, network,
transport, or adapter behavior exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

READ_SURFACE_SCHEMA_VERSION = 1

ALLOWED_READ_SURFACE_QUERY_TYPES = (
    "CONTROL_CENTER_OVERVIEW",
    "STATE_SUMMARY",
    "EVENT_SUMMARY",
    "APPROVAL_SUMMARY",
    "AUDIT_SUMMARY",
    "HEALTH_SUMMARY",
    "DRIFT_SUMMARY",
    "FULL_LOCAL_READ_SURFACE",
)

GO_NO_GO_VALUES = ("GO", "NO_GO")


def _freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenMap):
        return value
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return FrozenMap.from_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class FrozenMap:
    """Tuple-backed immutable mapping with deterministic serialization."""

    items: tuple[tuple[str, Any], ...]

    @staticmethod
    def from_mapping(mapping: dict[str, Any] | None) -> "FrozenMap":
        source = mapping or {}
        return FrozenMap(
            tuple((str(key), _freeze_value(source[key])) for key in sorted(source))
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.items}


@dataclass(frozen=True)
class ReadSurfaceReference:
    reference_id: str
    reference_type: str
    path: str
    exists: bool
    readable: bool
    source_stage: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", str(self.reference_id))
        object.__setattr__(self, "reference_type", str(self.reference_type))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "exists", bool(self.exists))
        object.__setattr__(self, "readable", bool(self.readable))
        object.__setattr__(self, "source_stage", str(self.source_stage))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "path": self.path,
            "exists": self.exists,
            "readable": self.readable,
            "source_stage": self.source_stage,
        }


@dataclass(frozen=True)
class ReadSurfaceQuery:
    query_id: str
    query_type: str
    requested_at: str
    include_state: bool
    include_events: bool
    include_approvals: bool
    include_audit: bool
    include_health: bool
    include_drift: bool
    limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "query_id", str(self.query_id))
        object.__setattr__(self, "query_type", str(self.query_type))
        object.__setattr__(self, "requested_at", str(self.requested_at))
        object.__setattr__(self, "include_state", bool(self.include_state))
        object.__setattr__(self, "include_events", bool(self.include_events))
        object.__setattr__(self, "include_approvals", bool(self.include_approvals))
        object.__setattr__(self, "include_audit", bool(self.include_audit))
        object.__setattr__(self, "include_health", bool(self.include_health))
        object.__setattr__(self, "include_drift", bool(self.include_drift))
        object.__setattr__(self, "limit", int(self.limit))

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_type": self.query_type,
            "requested_at": self.requested_at,
            "include_state": self.include_state,
            "include_events": self.include_events,
            "include_approvals": self.include_approvals,
            "include_audit": self.include_audit,
            "include_health": self.include_health,
            "include_drift": self.include_drift,
            "limit": self.limit,
        }


@dataclass(frozen=True)
class ReadSurfaceRecord:
    record_id: str
    record_type: str
    source_stage: str
    summary: str
    status: str
    references: tuple[ReadSurfaceReference, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", str(self.record_id))
        object.__setattr__(self, "record_type", str(self.record_type))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "status", str(self.status))
        refs = tuple(self.references or ())
        for reference in refs:
            if not isinstance(reference, ReadSurfaceReference):
                raise ValueError("references must contain ReadSurfaceReference values")
        object.__setattr__(
            self,
            "references",
            tuple(sorted(refs, key=lambda item: item.reference_id)),
        )
        object.__setattr__(
            self,
            "metadata",
            tuple(sorted((str(k), str(v)) for k, v in (self.metadata or ()))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "source_stage": self.source_stage,
            "summary": self.summary,
            "status": self.status,
            "references": [reference.to_dict() for reference in self.references],
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class ReadSurfaceSnapshot:
    snapshot_id: str
    checked_at: str
    query_id: str
    records: tuple[ReadSurfaceRecord, ...]
    readiness: FrozenMap
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "query_id", str(self.query_id))
        records = tuple(self.records or ())
        for record in records:
            if not isinstance(record, ReadSurfaceRecord):
                raise ValueError("records must contain ReadSurfaceRecord values")
        object.__setattr__(
            self,
            "records",
            tuple(sorted(records, key=lambda item: item.record_id)),
        )
        if not isinstance(self.readiness, FrozenMap):
            object.__setattr__(
                self, "readiness", FrozenMap.from_mapping(dict(self.readiness or {}))
            )
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "checked_at": self.checked_at,
            "query_id": self.query_id,
            "records": [record.to_dict() for record in self.records],
            "readiness": self.readiness.to_dict(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ReadSurfaceResult:
    accepted: bool
    go_no_go: str
    readiness_score: int
    snapshot: ReadSurfaceSnapshot | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    checked_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        if self.go_no_go not in GO_NO_GO_VALUES:
            raise ValueError(f"go_no_go must be one of {list(GO_NO_GO_VALUES)}")
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        if self.snapshot is not None and not isinstance(self.snapshot, ReadSurfaceSnapshot):
            raise ValueError("snapshot must be ReadSurfaceSnapshot or None")
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))
        object.__setattr__(self, "checked_at", str(self.checked_at))

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
class ReadSurfaceError:
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
    ) -> "ReadSurfaceError":
        return ReadSurfaceError(
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
        "ALLOWED_READ_SURFACE_QUERY_TYPES",
        "GO_NO_GO_VALUES",
        "FrozenMap",
        "READ_SURFACE_SCHEMA_VERSION",
        "ReadSurfaceError",
        "ReadSurfaceQuery",
        "ReadSurfaceRecord",
        "ReadSurfaceReference",
        "ReadSurfaceResult",
        "ReadSurfaceSnapshot",
    )
)
