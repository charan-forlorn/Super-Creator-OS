"""SCOS Stage 6.2 Control Center Command API boundary.

Local callable functions that represent the future backend API without
opening sockets, starting a server, or adding web routes. Reuses the Stage
5.1 command validation contracts (``ALLOWED_COMMAND_TYPES``,
``validate_command_args``, ``validate_no_forbidden_command_text``) so a
command that would be rejected by the Stage 5.1 approval gate is rejected
here too, before it ever reaches that gate.

This module never executes a command, never calls ``subprocess``, never
opens a socket, never mutates repository files, and never reads a real
clock/random/uuid -- ``created_at`` / ``checked_at`` are always caller
supplied.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

from typing import Any

try:
    from .backend_models import (
        ALLOWED_REQUEST_TYPES,
        BackendError,
        BackendHealthSnapshot,
        BackendWarning,
        LocalBackendRequest,
        LocalBackendResponse,
    )
    from .backend_response_builder import (
        build_error_response,
        build_health_response,
        build_rejected_response,
        build_success_response,
    )
    from .backend_validation import validate_backend_request
    from .command_models import ALLOWED_COMMAND_TYPES
    from .command_validation import (
        validate_command_args,
        validate_no_forbidden_command_text,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from backend_models import (
        ALLOWED_REQUEST_TYPES,
        BackendError,
        BackendHealthSnapshot,
        BackendWarning,
        LocalBackendRequest,
        LocalBackendResponse,
    )
    from backend_response_builder import (
        build_error_response,
        build_health_response,
        build_rejected_response,
        build_success_response,
    )
    from backend_validation import validate_backend_request
    from command_models import ALLOWED_COMMAND_TYPES
    from command_validation import (
        validate_command_args,
        validate_no_forbidden_command_text,
    )

COMMAND_API_SCHEMA_VERSION = 1

_HEALTH_CAPABILITIES = (
    "health_check",
    "command_preview",
    "command_validate",
    "command_enqueue_dry_run",
)

_HEALTH_DISABLED_CAPABILITIES = (
    "sqlite_wal_persistence",
    "websocket_stream",
    "server_sent_events",
    "polling",
    "real_adapter_dispatch",
    "arbitrary_command_execution",
)


def _command_payload_to_args(
    command_payload: dict[str, Any] | None,
) -> tuple[tuple[str, str], ...]:
    if not command_payload:
        return ()
    return tuple((str(key), str(value)) for key, value in command_payload.items())


def _validate_command_type_and_args(
    command_type: str, command_payload: dict[str, Any] | None
) -> tuple[BackendError, ...]:
    """Reuse the Stage 5.1 command contract to validate type + args.

    Returns a deterministic tuple of ``BackendError``; never raises.
    """
    errors: list[BackendError] = []
    args = _command_payload_to_args(command_payload)

    if command_type not in ALLOWED_COMMAND_TYPES:
        errors.append(
            BackendError.of(
                "command_not_allowed",
                f"unknown command_type: {command_type!r}",
                field_name="command_type",
                recommended_action=(
                    f"use one of: {', '.join(ALLOWED_COMMAND_TYPES)}"
                ),
            )
        )
        return tuple(errors)

    args_ok, arg_errors = validate_command_args(command_type, args)
    if not args_ok:
        for detail in arg_errors:
            errors.append(
                BackendError.of(
                    "invalid_payload",
                    detail,
                    field_name="command_payload",
                    recommended_action="fix the command_payload arg per the contract",
                )
            )

    for key, value in args:
        text_ok, found = validate_no_forbidden_command_text(f"{key} {value}")
        if not text_ok:
            for marker in found:
                errors.append(
                    BackendError.of(
                        "forbidden_operation",
                        f"forbidden command text in command_payload.{key}: {marker}",
                        field_name=key,
                        recommended_action="remove the forbidden command text",
                    )
                )

    return tuple(errors)


def _dry_run_data(
    command_type: str, command_payload: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "would_enqueue": True,
        "command_type": command_type,
        "command_payload": {
            str(key): str(value) for key, value in (command_payload or {}).items()
        },
    }


def get_backend_health(
    *,
    request_id: str,
    operator_id: str,
    checked_at: str,
) -> LocalBackendResponse:
    """Return the Stage 6.2 backend health snapshot. Never fails."""
    del operator_id  # not part of the deterministic snapshot; kept for symmetry
    snapshot = BackendHealthSnapshot.of(
        backend_status="ready",
        stage="Stage 6.2",
        capabilities=_HEALTH_CAPABILITIES,
        disabled_capabilities=_HEALTH_DISABLED_CAPABILITIES,
        active_store="in_memory_only",
        event_stream_status="disabled_until_stage_6_4",
        adapter_dispatch_status="disabled_until_later_stage",
    )
    return build_health_response(
        request_id=request_id, created_at=checked_at, snapshot=snapshot
    )


def preview_command_request(
    *,
    request_id: str,
    operator_id: str,
    command_type: str,
    command_payload: dict[str, Any],
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> LocalBackendResponse:
    """Preview what a command would look like, without validating fully or
    executing it. Always returns a response; rejects unknown command types.
    """
    del operator_id
    errors = _validate_command_type_and_args(command_type, command_payload)
    if errors:
        return build_rejected_response(
            request_id=request_id,
            request_type="command_preview",
            created_at=created_at,
            errors=errors,
            metadata=metadata,
        )
    return build_success_response(
        request_id=request_id,
        request_type="command_preview",
        response_type="validation_result",
        created_at=created_at,
        data={
            "command_type": command_type,
            "command_payload": {
                str(key): str(value) for key, value in command_payload.items()
            },
            "would_be_valid": True,
        },
        warnings=(
            BackendWarning.of(
                "dry_run_only",
                "preview does not execute or enqueue the command",
            ),
        ),
        metadata=metadata,
    )


def validate_command_request(
    *,
    request_id: str,
    operator_id: str,
    command_type: str,
    command_payload: dict[str, Any],
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> LocalBackendResponse:
    """Fully validate a command against the Stage 5.1 command contract."""
    del operator_id
    errors = _validate_command_type_and_args(command_type, command_payload)
    if errors:
        return build_rejected_response(
            request_id=request_id,
            request_type="command_validate",
            created_at=created_at,
            errors=errors,
            response_type="validation_result",
            metadata=metadata,
        )
    return build_success_response(
        request_id=request_id,
        request_type="command_validate",
        response_type="validation_result",
        created_at=created_at,
        data={
            "command_type": command_type,
            "command_payload": {
                str(key): str(value) for key, value in command_payload.items()
            },
            "valid": True,
        },
        metadata=metadata,
    )


def dry_run_enqueue_command(
    *,
    request_id: str,
    operator_id: str,
    command_type: str,
    command_payload: dict[str, Any],
    created_at: str,
    metadata: dict[str, Any] | None = None,
) -> LocalBackendResponse:
    """Return what would be enqueued, without writing to the real queue.

    Status is ``success`` only when validation passes; otherwise the
    command is rejected deterministically and nothing is described as
    enqueued.
    """
    del operator_id
    errors = _validate_command_type_and_args(command_type, command_payload)
    if errors:
        return build_rejected_response(
            request_id=request_id,
            request_type="command_enqueue_dry_run",
            created_at=created_at,
            errors=errors,
            response_type="dry_run_result",
            data={"would_enqueue": False},
            metadata=metadata,
        )
    return build_success_response(
        request_id=request_id,
        request_type="command_enqueue_dry_run",
        response_type="dry_run_result",
        created_at=created_at,
        data=_dry_run_data(command_type, command_payload),
        warnings=(
            BackendWarning.of(
                "dry_run_only",
                "no real command queue write occurred",
            ),
            BackendWarning.of(
                "persistence_not_enabled",
                "Stage 6.2 has no SQLite/database-backed persistence",
            ),
        ),
        metadata=metadata,
    )


def _snapshot_response(request: LocalBackendRequest, checked_at: str) -> LocalBackendResponse:
    return build_success_response(
        request_id=request.request_id,
        request_type=request.request_type,
        response_type="snapshot",
        created_at=checked_at,
        data=request.payload.to_dict(),
        warnings=(
            BackendWarning.of(
                "snapshot_mocked",
                f"{request.request_type} is a mocked snapshot in Stage 6.2",
            ),
        ),
    )


def handle_local_backend_request(
    request: LocalBackendRequest,
    *,
    checked_at: str,
) -> LocalBackendResponse:
    """Dispatch a validated/unvalidated request to the right handler.

    Runs ``validate_backend_request`` first; a request that fails
    validation is rejected before any handler-specific logic runs.
    """
    errors = validate_backend_request(request)
    if errors:
        return build_rejected_response(
            request_id=request.request_id,
            request_type=request.request_type,
            created_at=checked_at,
            errors=errors,
        )

    if request.request_type == "health_check":
        return get_backend_health(
            request_id=request.request_id,
            operator_id=request.operator_id,
            checked_at=checked_at,
        )

    if request.request_type == "command_preview":
        payload = request.payload.to_dict()
        return preview_command_request(
            request_id=request.request_id,
            operator_id=request.operator_id,
            command_type=payload.get("command_type", ""),
            command_payload={
                key: value
                for key, value in payload.items()
                if key not in ("command_type",)
            },
            created_at=checked_at,
        )

    if request.request_type == "command_validate":
        payload = request.payload.to_dict()
        return validate_command_request(
            request_id=request.request_id,
            operator_id=request.operator_id,
            command_type=payload.get("command_type", ""),
            command_payload={
                key: value
                for key, value in payload.items()
                if key not in ("command_type",)
            },
            created_at=checked_at,
        )

    if request.request_type == "command_enqueue_dry_run":
        payload = request.payload.to_dict()
        return dry_run_enqueue_command(
            request_id=request.request_id,
            operator_id=request.operator_id,
            command_type=payload.get("command_type", ""),
            command_payload={
                key: value
                for key, value in payload.items()
                if key not in ("command_type",)
            },
            created_at=checked_at,
        )

    if request.request_type in (
        "session_snapshot",
        "result_snapshot",
        "approval_snapshot",
        "project_state_snapshot",
    ):
        return _snapshot_response(request, checked_at)

    # Unreachable when validate_backend_request has already run, but kept as
    # a deterministic fallback in case ALLOWED_REQUEST_TYPES grows without a
    # matching branch here.
    return build_error_response(
        request_id=request.request_id,
        request_type=request.request_type,
        created_at=checked_at,
        errors=(
            BackendError.of(
                "unsupported_stage",
                f"no handler implemented for request_type: {request.request_type!r}",
                field_name="request_type",
                recommended_action=(
                    f"supported handlers: {', '.join(ALLOWED_REQUEST_TYPES)}"
                ),
            ),
        ),
    )
