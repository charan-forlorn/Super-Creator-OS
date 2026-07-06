"""SCOS Stage 6.2 local Control Center backend facade.

``LocalControlCenterBackend`` is a pure local callable facade over the
Command API boundary (:mod:`scos.control_center.command_api`). It opens no
socket, starts no HTTP server, uses no web framework, persists nothing, and
never dispatches real AI work.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

from typing import Any

try:
    from .backend_models import LocalBackendRequest, LocalBackendResponse
    from .command_api import (
        dry_run_enqueue_command,
        get_backend_health,
        handle_local_backend_request,
        preview_command_request,
        validate_command_request,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from backend_models import LocalBackendRequest, LocalBackendResponse
    from command_api import (
        dry_run_enqueue_command,
        get_backend_health,
        handle_local_backend_request,
        preview_command_request,
        validate_command_request,
    )

LOCAL_CONTROL_CENTER_BACKEND_SCHEMA_VERSION = 1


class LocalControlCenterBackend:
    """Pure local facade the Control Center frontend can eventually call.

    No socket server, no HTTP server, no persistence, no event stream, no
    real adapter dispatch, no external processes, no network.
    """

    def health(
        self, request_id: str, operator_id: str, checked_at: str
    ) -> LocalBackendResponse:
        return get_backend_health(
            request_id=request_id, operator_id=operator_id, checked_at=checked_at
        )

    def handle(
        self, request: LocalBackendRequest, checked_at: str
    ) -> LocalBackendResponse:
        return handle_local_backend_request(request, checked_at=checked_at)

    def preview_command(
        self,
        *,
        request_id: str,
        operator_id: str,
        command_type: str,
        command_payload: dict[str, Any],
        created_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> LocalBackendResponse:
        return preview_command_request(
            request_id=request_id,
            operator_id=operator_id,
            command_type=command_type,
            command_payload=command_payload,
            created_at=created_at,
            metadata=metadata,
        )

    def validate_command(
        self,
        *,
        request_id: str,
        operator_id: str,
        command_type: str,
        command_payload: dict[str, Any],
        created_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> LocalBackendResponse:
        return validate_command_request(
            request_id=request_id,
            operator_id=operator_id,
            command_type=command_type,
            command_payload=command_payload,
            created_at=created_at,
            metadata=metadata,
        )

    def dry_run_enqueue(
        self,
        *,
        request_id: str,
        operator_id: str,
        command_type: str,
        command_payload: dict[str, Any],
        created_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> LocalBackendResponse:
        return dry_run_enqueue_command(
            request_id=request_id,
            operator_id=operator_id,
            command_type=command_type,
            command_payload=command_payload,
            created_at=created_at,
            metadata=metadata,
        )
