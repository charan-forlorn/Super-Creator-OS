"""SCOS Stage 6.2 local Control Center backend validation helpers.

Deterministic, read-only validation for ``LocalBackendRequest`` instances
before they reach the command API boundary. Rejects unknown request types,
malformed payload shapes, URL-like executable paths, path traversal, and
secret-bearing metadata keys.

Local-first, deterministic, stdlib-only. Read-only: no writes, no network,
no mutation of inputs. Never raises for a normal validation failure --
callers get a deterministic tuple of ``BackendError`` instead.
"""

from __future__ import annotations

import re

try:
    from .backend_models import ALLOWED_REQUEST_TYPES, BackendError, LocalBackendRequest
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from backend_models import ALLOWED_REQUEST_TYPES, BackendError, LocalBackendRequest
    from operator_packet_review_models import FrozenMap

CONTROL_CENTER_BACKEND_VALIDATION_SCHEMA_VERSION = 1

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

_FORBIDDEN_METADATA_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "api_key",
    "private_key",
    "credential",
    "bearer",
)

# request_type -> (allowed payload keys, required payload keys). An empty
# allowed-keys tuple means "no payload keys are expected for this type".
_REQUEST_PAYLOAD_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "health_check": ((), ()),
    "command_preview": (("command_type", "command_payload"), ("command_type",)),
    "command_validate": (("command_type", "command_payload"), ("command_type",)),
    "command_enqueue_dry_run": (
        ("command_type", "command_payload"),
        ("command_type",),
    ),
    "session_snapshot": (("session_id",), ()),
    "result_snapshot": (("result_id",), ()),
    "approval_snapshot": (("approval_id",), ()),
    "project_state_snapshot": ((), ()),
}


def _is_url_like(value: str) -> bool:
    text = str(value).strip()
    return text.lower().startswith(_URL_PREFIXES) or bool(_SCHEME_RE.match(text))


def _is_path_traversal(value: str) -> bool:
    text = str(value).replace("\\", "/")
    return ".." in text.split("/")


def validate_request_type(request_type: str) -> BackendError | None:
    """Return ``None`` for an allowed request type, else a stable error."""
    if request_type in ALLOWED_REQUEST_TYPES:
        return None
    return BackendError.of(
        "invalid_request_type",
        f"unknown request_type: {request_type!r}",
        field_name="request_type",
        recommended_action=(
            f"use one of: {', '.join(ALLOWED_REQUEST_TYPES)}"
        ),
    )


def reject_url_values(value: object) -> tuple[BackendError, ...]:
    """Return errors for any URL-like string found in ``value``.

    Accepts a scalar string, or a mapping/iterable of (key, value) pairs
    (e.g. a ``FrozenMap``). Never raises.
    """
    errors: list[BackendError] = []
    if isinstance(value, (FrozenMap, dict)):
        items = value.items()
    elif isinstance(value, str):
        items = (("value", value),)
    else:
        items = ()
    for key, item_value in items:
        if isinstance(item_value, str) and _is_url_like(item_value):
            errors.append(
                BackendError.of(
                    "url_rejected",
                    f"value must not be a URL: {key}",
                    field_name=str(key),
                    recommended_action="use a local relative path or identifier",
                )
            )
    return tuple(errors)


def reject_secret_metadata(metadata: FrozenMap) -> tuple[BackendError, ...]:
    """Return errors for any secret-bearing metadata key. Never raises."""
    errors: list[BackendError] = []
    for key in metadata:
        lowered = key.lower()
        for marker in _FORBIDDEN_METADATA_KEY_MARKERS:
            if marker in lowered:
                errors.append(
                    BackendError.of(
                        "secret_metadata_rejected",
                        f"metadata key must not carry secret-like data: {key}",
                        field_name=key,
                        recommended_action="remove secret-bearing metadata keys",
                    )
                )
                break
    return tuple(errors)


def validate_safe_relative_path(path: str) -> BackendError | None:
    """Return ``None`` for a safe local relative path, else a stable error."""
    text = str(path)
    if _is_url_like(text):
        return BackendError.of(
            "url_rejected",
            f"path must not be a URL: {text}",
            field_name="path",
            recommended_action="use a local relative path",
        )
    if text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text):
        return BackendError.of(
            "unsafe_path",
            f"path must be relative, not absolute: {text}",
            field_name="path",
            recommended_action="use a repository-relative path",
        )
    if _is_path_traversal(text):
        return BackendError.of(
            "unsafe_path",
            f"path must not contain traversal segments: {text}",
            field_name="path",
            recommended_action="remove '..' segments from the path",
        )
    return None


def validate_payload_shape(
    request_type: str, payload: FrozenMap
) -> tuple[BackendError, ...]:
    """Validate ``payload`` keys against the per-request-type contract."""
    errors: list[BackendError] = []
    spec = _REQUEST_PAYLOAD_SPECS.get(request_type)
    if spec is None:
        return (
            BackendError.of(
                "invalid_payload",
                f"no payload contract for request_type: {request_type!r}",
                field_name="request_type",
                recommended_action="use a supported request_type",
            ),
        )
    allowed_keys, required_keys = spec

    for key in payload:
        if key not in allowed_keys:
            errors.append(
                BackendError.of(
                    "invalid_payload",
                    f"payload key not allowed for {request_type}: {key}",
                    field_name=key,
                    recommended_action=(
                        f"allowed keys: {', '.join(allowed_keys) or '(none)'}"
                    ),
                )
            )

    for key in required_keys:
        if key not in payload or not str(payload[key]).strip():
            errors.append(
                BackendError.of(
                    "invalid_payload",
                    f"missing required payload key: {key}",
                    field_name=key,
                    recommended_action=f"supply a non-empty {key}",
                )
            )

    errors.extend(reject_url_values(payload))

    for key in payload:
        if key.endswith("path") or key.endswith("_path"):
            path_error = validate_safe_relative_path(payload[key])
            if path_error is not None:
                errors.append(path_error)

    return tuple(errors)


def validate_backend_request(
    request: LocalBackendRequest,
) -> tuple[BackendError, ...]:
    """Validate a full request; returns a deterministic error tuple.

    Check sequence is fixed: request type, then payload shape (only when the
    type is known), then secret-bearing metadata keys, then URL values found
    directly in metadata. Never mutates the request.
    """
    errors: list[BackendError] = []

    type_error = validate_request_type(request.request_type)
    if type_error is not None:
        errors.append(type_error)
    else:
        errors.extend(validate_payload_shape(request.request_type, request.payload))

    errors.extend(reject_secret_metadata(request.metadata))
    errors.extend(reject_url_values(request.metadata))

    return tuple(errors)
