"""SCOS Stage 6.2 local Control Center backend models.

Immutable dataclasses for the first local backend command boundary: a
deterministic request/response envelope the Control Center frontend will
eventually call into. This stage adds no socket server, no database, no
event stream, and no real AI dispatch -- it only defines the shapes that a
future local server can reuse unchanged.

Reuses the Stage 5.5 ``FrozenMap`` immutable string mapping (which already
rejects secret-bearing metadata keys and URL values at construction time)
rather than redefining one.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

LOCAL_BACKEND_SCHEMA_VERSION = 1

ALLOWED_REQUEST_TYPES = (
    "health_check",
    "command_preview",
    "command_validate",
    "command_enqueue_dry_run",
    "session_snapshot",
    "result_snapshot",
    "approval_snapshot",
    "project_state_snapshot",
)

ALLOWED_RESPONSE_TYPES = (
    "health",
    "validation_result",
    "dry_run_result",
    "snapshot",
    "rejected",
    "error",
)

ALLOWED_RESPONSE_STATUSES = (
    "success",
    "rejected",
    "blocked",
    "failure",
)

ALLOWED_BACKEND_ERROR_KINDS = (
    "invalid_request_type",
    "invalid_payload",
    "forbidden_operation",
    "unsafe_path",
    "url_rejected",
    "secret_metadata_rejected",
    "unsupported_stage",
    "command_not_allowed",
    "backend_unavailable",
    "contract_violation",
)

ALLOWED_BACKEND_WARNING_KINDS = (
    "dry_run_only",
    "snapshot_mocked",
    "persistence_not_enabled",
    "event_stream_not_enabled",
    "adapter_not_active",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _require_nonempty(field_name: str, value: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _frozen_map(value: Any = None) -> FrozenMap:
    if isinstance(value, FrozenMap):
        return value
    return FrozenMap.of(value)


def _errors(value: Any) -> tuple["BackendError", ...]:
    errors = tuple(value or ())
    for error in errors:
        if not isinstance(error, BackendError):
            raise ValueError("errors entries must be BackendError instances")
    return errors


def _warnings(value: Any) -> tuple["BackendWarning", ...]:
    warnings = tuple(value or ())
    for warning in warnings:
        if not isinstance(warning, BackendWarning):
            raise ValueError("warnings entries must be BackendWarning instances")
    return warnings


def _str_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    items = tuple(value or ())
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be strings, got {item!r}")
    return items


@dataclass(frozen=True)
class BackendError:
    """A single deterministic backend rejection/failure reason."""

    error_kind: str
    error_detail: str
    field_name: str | None
    recommended_action: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "field_name", _optional_str(self.field_name))
        object.__setattr__(
            self, "recommended_action", str(self.recommended_action)
        )
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("error_kind", self.error_kind, ALLOWED_BACKEND_ERROR_KINDS)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        *,
        field_name: str | None = None,
        recommended_action: str = "",
        metadata: Any = None,
    ) -> "BackendError":
        return BackendError(
            error_kind=error_kind,
            error_detail=error_detail,
            field_name=field_name,
            recommended_action=recommended_action,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "field_name": self.field_name,
            "recommended_action": self.recommended_action,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BackendError":
        return BackendError(
            error_kind=data["error_kind"],
            error_detail=data["error_detail"],
            field_name=data.get("field_name"),
            recommended_action=data.get("recommended_action", ""),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class BackendWarning:
    """A single non-blocking notice describing reduced/mocked behavior."""

    warning_kind: str
    warning_detail: str
    field_name: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "warning_kind", str(self.warning_kind))
        object.__setattr__(self, "warning_detail", str(self.warning_detail))
        object.__setattr__(self, "field_name", _optional_str(self.field_name))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed(
            "warning_kind", self.warning_kind, ALLOWED_BACKEND_WARNING_KINDS
        )

    @staticmethod
    def of(
        warning_kind: str,
        warning_detail: str,
        *,
        field_name: str | None = None,
        metadata: Any = None,
    ) -> "BackendWarning":
        return BackendWarning(
            warning_kind=warning_kind,
            warning_detail=warning_detail,
            field_name=field_name,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "warning_kind": self.warning_kind,
            "warning_detail": self.warning_detail,
            "field_name": self.field_name,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BackendWarning":
        return BackendWarning(
            warning_kind=data["warning_kind"],
            warning_detail=data["warning_detail"],
            field_name=data.get("field_name"),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class LocalBackendRequest:
    """An operator/UI-authored request into the local backend boundary.

    ``request_type`` is intentionally NOT enforced here: unknown types must
    survive construction so the validation layer can reject them with a
    deterministic ``BackendError`` instead of a constructor-time crash.
    """

    request_id: str
    request_type: str
    operator_id: str
    created_at: str
    payload: FrozenMap
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", str(self.request_id))
        object.__setattr__(self, "request_type", str(self.request_type))
        object.__setattr__(self, "operator_id", str(self.operator_id))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "payload", _frozen_map(self.payload))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("request_id", self.request_id)
        _require_nonempty("operator_id", self.operator_id)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        request_id: str,
        request_type: str,
        operator_id: str,
        created_at: str,
        *,
        payload: Any = None,
        metadata: Any = None,
    ) -> "LocalBackendRequest":
        return LocalBackendRequest(
            request_id=request_id,
            request_type=request_type,
            operator_id=operator_id,
            created_at=created_at,
            payload=_frozen_map(payload),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_type": self.request_type,
            "operator_id": self.operator_id,
            "created_at": self.created_at,
            "payload": self.payload.to_dict(),
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "LocalBackendRequest":
        return LocalBackendRequest(
            request_id=data["request_id"],
            request_type=data["request_type"],
            operator_id=data["operator_id"],
            created_at=data["created_at"],
            payload=_frozen_map(data.get("payload")),
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class LocalBackendResponse:
    """Deterministic outcome of one local backend call for one request."""

    ok: bool
    schema_version: int
    request_id: str
    request_type: str
    response_type: str
    status: str
    data: FrozenMap
    errors: tuple[BackendError, ...]
    warnings: tuple[BackendWarning, ...]
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "request_id", str(self.request_id))
        object.__setattr__(self, "request_type", str(self.request_type))
        object.__setattr__(self, "response_type", str(self.response_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "data", _frozen_map(self.data))
        object.__setattr__(self, "errors", _errors(self.errors))
        object.__setattr__(self, "warnings", _warnings(self.warnings))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("response_type", self.response_type, ALLOWED_RESPONSE_TYPES)
        _require_allowed("status", self.status, ALLOWED_RESPONSE_STATUSES)

    @staticmethod
    def of(
        ok: bool,
        request_id: str,
        request_type: str,
        response_type: str,
        status: str,
        created_at: str,
        *,
        schema_version: int = LOCAL_BACKEND_SCHEMA_VERSION,
        data: Any = None,
        errors: Any = (),
        warnings: Any = (),
        metadata: Any = None,
    ) -> "LocalBackendResponse":
        return LocalBackendResponse(
            ok=ok,
            schema_version=schema_version,
            request_id=request_id,
            request_type=request_type,
            response_type=response_type,
            status=status,
            data=_frozen_map(data),
            errors=tuple(errors or ()),
            warnings=tuple(warnings or ()),
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "request_type": self.request_type,
            "response_type": self.response_type,
            "status": self.status,
            "data": self.data.to_dict(),
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "LocalBackendResponse":
        return LocalBackendResponse(
            ok=data["ok"],
            schema_version=data.get("schema_version", LOCAL_BACKEND_SCHEMA_VERSION),
            request_id=data["request_id"],
            request_type=data["request_type"],
            response_type=data["response_type"],
            status=data["status"],
            data=_frozen_map(data.get("data")),
            errors=tuple(
                BackendError.from_dict(item) for item in data.get("errors", ())
            ),
            warnings=tuple(
                BackendWarning.from_dict(item) for item in data.get("warnings", ())
            ),
            created_at=data["created_at"],
            metadata=_frozen_map(data.get("metadata")),
        )


@dataclass(frozen=True)
class BackendHealthSnapshot:
    """Deterministic description of the Stage 6.2 local backend's capabilities."""

    schema_version: int
    backend_status: str
    stage: str
    capabilities: tuple[str, ...]
    disabled_capabilities: tuple[str, ...]
    active_store: str
    event_stream_status: str
    adapter_dispatch_status: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "backend_status", str(self.backend_status))
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(
            self, "capabilities", _str_tuple("capabilities", self.capabilities)
        )
        object.__setattr__(
            self,
            "disabled_capabilities",
            _str_tuple("disabled_capabilities", self.disabled_capabilities),
        )
        object.__setattr__(self, "active_store", str(self.active_store))
        object.__setattr__(
            self, "event_stream_status", str(self.event_stream_status)
        )
        object.__setattr__(
            self, "adapter_dispatch_status", str(self.adapter_dispatch_status)
        )
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

    @staticmethod
    def of(
        *,
        backend_status: str = "ready",
        stage: str = "Stage 6.2",
        capabilities: Any = (),
        disabled_capabilities: Any = (),
        active_store: str = "in_memory_only",
        event_stream_status: str = "disabled_until_stage_6_4",
        adapter_dispatch_status: str = "disabled_until_later_stage",
        schema_version: int = LOCAL_BACKEND_SCHEMA_VERSION,
        metadata: Any = None,
    ) -> "BackendHealthSnapshot":
        return BackendHealthSnapshot(
            schema_version=schema_version,
            backend_status=backend_status,
            stage=stage,
            capabilities=tuple(capabilities or ()),
            disabled_capabilities=tuple(disabled_capabilities or ()),
            active_store=active_store,
            event_stream_status=event_stream_status,
            adapter_dispatch_status=adapter_dispatch_status,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "backend_status": self.backend_status,
            "stage": self.stage,
            "capabilities": list(self.capabilities),
            "disabled_capabilities": list(self.disabled_capabilities),
            "active_store": self.active_store,
            "event_stream_status": self.event_stream_status,
            "adapter_dispatch_status": self.adapter_dispatch_status,
            "metadata": self.metadata.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "BackendHealthSnapshot":
        return BackendHealthSnapshot(
            schema_version=data.get("schema_version", LOCAL_BACKEND_SCHEMA_VERSION),
            backend_status=data.get("backend_status", "ready"),
            stage=data.get("stage", "Stage 6.2"),
            capabilities=tuple(data.get("capabilities", ())),
            disabled_capabilities=tuple(data.get("disabled_capabilities", ())),
            active_store=data.get("active_store", "in_memory_only"),
            event_stream_status=data.get(
                "event_stream_status", "disabled_until_stage_6_4"
            ),
            adapter_dispatch_status=data.get(
                "adapter_dispatch_status", "disabled_until_later_stage"
            ),
            metadata=_frozen_map(data.get("metadata")),
        )
