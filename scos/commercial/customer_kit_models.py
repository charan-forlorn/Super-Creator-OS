"""SCOS Stage 4.6 first customer operating kit models.

Immutable, local-first models for the Stage 4.6 operating kit generator. They
store only commercial-owned primitives and tuple-backed structures, reuse the
Stage 4.1 ``FrozenMap`` (never a duplicate implementation), and serialize
deterministically: tuples render as lists, ``FrozenMap`` renders as a plain
dict, explicit key order is fixed, and callers apply
``json.dumps(..., sort_keys=True, indent=2)``. No real clock, no random, no
UUID is ever consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

CUSTOMER_KIT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CustomerKitFile:
    """One generated operating-kit file recorded in the kit manifest."""

    file_name: str
    file_path: str
    file_type: str
    required: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_name", str(self.file_name))
        object.__setattr__(self, "file_path", str(self.file_path))
        object.__setattr__(self, "file_type", str(self.file_type))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        file_name: str,
        file_path: str,
        file_type: str,
        required: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "CustomerKitFile":
        return CustomerKitFile(
            file_name=str(file_name),
            file_path=str(file_path),
            file_type=str(file_type),
            required=bool(required),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "required": self.required,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CustomerKitResult:
    """Deterministic result for one generated first customer operating kit."""

    ok: bool
    schema_version: int
    customer_id: str
    kit_id: str
    acceptance_id: str
    run_id: str
    delivery_id: str
    output_dir: str
    manifest_path: str
    created_at: str
    files: tuple[CustomerKitFile, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "customer_id", str(self.customer_id))
        object.__setattr__(self, "kit_id", str(self.kit_id))
        object.__setattr__(self, "acceptance_id", str(self.acceptance_id))
        object.__setattr__(self, "run_id", str(self.run_id))
        object.__setattr__(self, "delivery_id", str(self.delivery_id))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "files", tuple(self.files))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "customer_id": self.customer_id,
            "kit_id": self.kit_id,
            "acceptance_id": self.acceptance_id,
            "run_id": self.run_id,
            "delivery_id": self.delivery_id,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "created_at": self.created_at,
            "files": [f.to_dict() for f in self.files],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CustomerKitError:
    """Deterministic failure object for an aborted kit generation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        metadata: dict[str, Any] | None = None,
    ) -> "CustomerKitError":
        base = {"schema_version": CUSTOMER_KIT_SCHEMA_VERSION}
        base.update(metadata or {})
        return CustomerKitError(
            ok=False,
            schema_version=CUSTOMER_KIT_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_step=str(failed_step),
            metadata=FrozenMap.from_mapping(base),
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


__all__ = (
    "CUSTOMER_KIT_SCHEMA_VERSION",
    "CustomerKitFile",
    "CustomerKitResult",
    "CustomerKitError",
)
