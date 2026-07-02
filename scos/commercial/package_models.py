"""SCOS Stage 4.2 delivery package models.

The delivery package contract is an immutable, local-first projection over a
Stage 4.1 CommercialReport. It stores only commercial-owned primitives and
tuple-backed structures, never lower-layer result objects or mutable payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

DELIVERY_PACKAGE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DeliveryPackageFile:
    """One file entry in the delivery package manifest."""

    path: str
    kind: str
    required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "required", bool(self.required))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "required": self.required,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DeliveryPackageFile":
        return DeliveryPackageFile(
            path=str(data.get("path", "")),
            kind=str(data.get("kind", "")),
            required=bool(data.get("required", False)),
        )


@dataclass(frozen=True)
class DeliveryPackageManifest:
    delivery_id: str
    schema_version: int
    created_at: str
    source_run_id: str
    style_id: str | None
    report_id: str
    package_status: str
    files: tuple[DeliveryPackageFile, ...]
    checksums: FrozenMap
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "delivery_id", str(self.delivery_id))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "source_run_id", str(self.source_run_id))
        if self.style_id is not None:
            object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "report_id", str(self.report_id))
        object.__setattr__(self, "package_status", str(self.package_status))
        object.__setattr__(
            self,
            "files",
            tuple(sorted(tuple(self.files), key=lambda item: item.path)),
        )
        object.__setattr__(self, "checksums", _freeze_value(self.checksums))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "source_run_id": self.source_run_id,
            "style_id": self.style_id,
            "report_id": self.report_id,
            "package_status": self.package_status,
            "files": [item.to_dict() for item in self.files],
            "checksums": self.checksums.to_dict(),
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "DeliveryPackageManifest":
        return DeliveryPackageManifest(
            delivery_id=str(data.get("delivery_id", "")),
            schema_version=int(data.get("schema_version", 0)),
            created_at=str(data.get("created_at", "")),
            source_run_id=str(data.get("source_run_id", "")),
            style_id=data.get("style_id"),
            report_id=str(data.get("report_id", "")),
            package_status=str(data.get("package_status", "")),
            files=tuple(
                DeliveryPackageFile.from_dict(item)
                for item in (data.get("files") or ())
            ),
            checksums=FrozenMap.from_mapping(dict(data.get("checksums") or {})),
            metadata=FrozenMap.from_mapping(dict(data.get("metadata") or {})),
        )


@dataclass(frozen=True)
class DeliveryPackageResult:
    delivery_id: str
    output_dir: str
    manifest: DeliveryPackageManifest
    error: None = None
    ok: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "delivery_id", str(self.delivery_id))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "ok", True)
        object.__setattr__(self, "error", None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "delivery_id": self.delivery_id,
            "output_dir": self.output_dir,
            "manifest": self.manifest.to_dict(),
            "error": None,
        }


@dataclass(frozen=True)
class DeliveryPackageError:
    error_kind: str
    error_detail: str
    metadata: FrozenMap
    ok: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))
        object.__setattr__(self, "ok", False)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> "DeliveryPackageError":
        base = {"schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION}
        base.update(metadata or {})
        return DeliveryPackageError(
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            metadata=FrozenMap.from_mapping(base),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "DELIVERY_PACKAGE_SCHEMA_VERSION",
    "DeliveryPackageFile",
    "DeliveryPackageManifest",
    "DeliveryPackageResult",
    "DeliveryPackageError",
)
