"""SCOS Stage 6.2 local Control Center backend response builder.

Small deterministic helpers that assemble ``LocalBackendResponse`` envelopes
and serialize them to stable JSON. Callers always supply ``created_at`` /
``checked_at`` -- this module never reads a clock.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from .backend_models import (
        BackendError,
        BackendHealthSnapshot,
        BackendWarning,
        LOCAL_BACKEND_SCHEMA_VERSION,
        LocalBackendResponse,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from backend_models import (
        BackendError,
        BackendHealthSnapshot,
        BackendWarning,
        LOCAL_BACKEND_SCHEMA_VERSION,
        LocalBackendResponse,
    )

BACKEND_RESPONSE_BUILDER_SCHEMA_VERSION = 1


def build_success_response(
    *,
    request_id: str,
    request_type: str,
    response_type: str,
    created_at: str,
    data: Any = None,
    warnings: tuple[BackendWarning, ...] = (),
    metadata: Any = None,
) -> LocalBackendResponse:
    return LocalBackendResponse.of(
        ok=True,
        request_id=request_id,
        request_type=request_type,
        response_type=response_type,
        status="success",
        created_at=created_at,
        data=data,
        errors=(),
        warnings=warnings,
        metadata=metadata,
    )


def build_rejected_response(
    *,
    request_id: str,
    request_type: str,
    created_at: str,
    errors: tuple[BackendError, ...],
    response_type: str = "rejected",
    status: str = "rejected",
    data: Any = None,
    warnings: tuple[BackendWarning, ...] = (),
    metadata: Any = None,
) -> LocalBackendResponse:
    return LocalBackendResponse.of(
        ok=False,
        request_id=request_id,
        request_type=request_type,
        response_type=response_type,
        status=status,
        created_at=created_at,
        data=data,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


def build_error_response(
    *,
    request_id: str,
    request_type: str,
    created_at: str,
    errors: tuple[BackendError, ...],
    data: Any = None,
    warnings: tuple[BackendWarning, ...] = (),
    metadata: Any = None,
) -> LocalBackendResponse:
    return LocalBackendResponse.of(
        ok=False,
        request_id=request_id,
        request_type=request_type,
        response_type="error",
        status="failure",
        created_at=created_at,
        data=data,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )


def build_health_response(
    *,
    request_id: str,
    created_at: str,
    snapshot: BackendHealthSnapshot,
    metadata: Any = None,
) -> LocalBackendResponse:
    return LocalBackendResponse.of(
        ok=True,
        request_id=request_id,
        request_type="health_check",
        response_type="health",
        status="success",
        created_at=created_at,
        data=snapshot.to_dict(),
        errors=(),
        warnings=(),
        metadata=metadata,
    )


def stable_backend_json(data: dict[str, Any]) -> str:
    """Serialize ``data`` deterministically: sorted keys, compact separators."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))
