"""Stage 8.2 immutable file snapshot refresh transport models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION = 1

FILE_SNAPSHOT_SOURCE_TYPES = (
    "READ_SURFACE",
    "OPERATOR_HEALTH_ACTIVITY",
    "APPROVAL_AWARE_COMMAND_VIEW",
    "TRANSPORT_DECISION",
    "STATIC_FALLBACK",
    "UNKNOWN",
)
FILE_SNAPSHOT_SOURCE_STATUSES = (
    "AVAILABLE",
    "MISSING_OPTIONAL",
    "MISSING_REQUIRED",
    "INVALID",
    "DEGRADED",
)
FILE_SNAPSHOT_TRANSPORT_MODES = ("FILE_SNAPSHOT_REFRESH",)
FILE_SNAPSHOT_GO_NO_GO = ("GO", "NO_GO", "BLOCKED")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


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


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


@dataclass(frozen=True)
class FrozenMap:
    """Tuple-backed immutable mapping with deterministic serialization."""

    items: tuple[tuple[str, Any], ...]

    @staticmethod
    def from_mapping(mapping: dict[str, Any] | None) -> "FrozenMap":
        source = mapping or {}
        return FrozenMap(tuple((str(key), _freeze_value(source[key])) for key in sorted(source)))

    def to_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.items}


@dataclass(frozen=True)
class FileSnapshotTransportSource:
    source_id: str
    source_type: str
    status: str
    path: str
    required: bool
    checksum_sha256: str | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", str(self.source_id))
        object.__setattr__(self, "source_type", str(self.source_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(
            self,
            "checksum_sha256",
            None if self.checksum_sha256 is None else str(self.checksum_sha256),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata or {})))
        _require_allowed("source_type", self.source_type, FILE_SNAPSHOT_SOURCE_TYPES)
        _require_allowed("status", self.status, FILE_SNAPSHOT_SOURCE_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "status": self.status,
            "path": self.path,
            "required": self.required,
            "checksum_sha256": self.checksum_sha256,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FileSnapshotTransportManifest:
    schema_version: int
    snapshot_id: str
    generated_at: str
    transport_mode: str
    repo_root: str
    output_path: str
    source_count: int
    payload_sha256: str
    sources: tuple[FileSnapshotTransportSource, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "generated_at", str(self.generated_at))
        object.__setattr__(self, "transport_mode", str(self.transport_mode))
        object.__setattr__(self, "repo_root", str(self.repo_root))
        object.__setattr__(self, "output_path", str(self.output_path))
        object.__setattr__(self, "source_count", int(self.source_count))
        object.__setattr__(self, "payload_sha256", str(self.payload_sha256))
        object.__setattr__(self, "sources", tuple(sorted(self.sources, key=lambda item: item.source_id)))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata or {})))
        _require_allowed("transport_mode", self.transport_mode, FILE_SNAPSHOT_TRANSPORT_MODES)
        if self.source_count != len(self.sources):
            raise ValueError("source_count must equal len(sources)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at,
            "transport_mode": self.transport_mode,
            "repo_root": self.repo_root,
            "output_path": self.output_path,
            "source_count": self.source_count,
            "payload_sha256": self.payload_sha256,
            "sources": [source.to_dict() for source in self.sources],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FileSnapshotTransportResult:
    accepted: bool
    go_no_go: str
    readiness_score: int
    snapshot_id: str
    output_path: str | None
    manifest: FileSnapshotTransportManifest | None
    payload: dict | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    checked_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "output_path", None if self.output_path is None else str(self.output_path))
        if self.manifest is not None and not isinstance(self.manifest, FileSnapshotTransportManifest):
            raise ValueError("manifest must be FileSnapshotTransportManifest or None")
        object.__setattr__(self, "payload", None if self.payload is None else FrozenMap.from_mapping(self.payload).to_dict())
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        _require_allowed("go_no_go", self.go_no_go, FILE_SNAPSHOT_GO_NO_GO)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "snapshot_id": self.snapshot_id,
            "output_path": self.output_path,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "payload": self.payload,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class FileSnapshotTransportError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "warnings", _strings(self.warnings))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> "FileSnapshotTransportError":
        return FileSnapshotTransportError(
            error_code=error_code,
            message=message,
            checked_at=checked_at,
            blockers=blockers or (message,),
            warnings=warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "checked_at": self.checked_at,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


__all__ = sorted(
    (
        "FILE_SNAPSHOT_GO_NO_GO",
        "FILE_SNAPSHOT_SOURCE_STATUSES",
        "FILE_SNAPSHOT_SOURCE_TYPES",
        "FILE_SNAPSHOT_TRANSPORT_MODES",
        "FILE_SNAPSHOT_TRANSPORT_SCHEMA_VERSION",
        "FileSnapshotTransportError",
        "FileSnapshotTransportManifest",
        "FileSnapshotTransportResult",
        "FileSnapshotTransportSource",
        "FrozenMap",
    )
)
