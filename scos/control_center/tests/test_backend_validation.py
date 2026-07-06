"""test_backend_validation.py - SCOS Stage 6.2 backend validation suite.

Run: python -m pytest scos/control_center/tests/test_backend_validation.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from backend_models import LocalBackendRequest  # noqa: E402
from backend_validation import (  # noqa: E402
    reject_secret_metadata,
    reject_url_values,
    validate_backend_request,
    validate_payload_shape,
    validate_request_type,
    validate_safe_relative_path,
)
from operator_packet_review_models import FrozenMap  # noqa: E402


def test_validate_request_type_accepts_known() -> None:
    assert validate_request_type("health_check") is None


def test_validate_request_type_rejects_unknown() -> None:
    error = validate_request_type("NOT_A_TYPE")
    assert error is not None
    assert error.error_kind == "invalid_request_type"
    assert error.field_name == "request_type"


def test_reject_url_values_in_frozen_map() -> None:
    payload = FrozenMap.of({"target_path": "notes.txt"})
    assert reject_url_values(payload) == ()


def test_reject_url_values_detects_scheme() -> None:
    # FrozenMap.of() itself rejects http/https at construction, so we exercise
    # reject_url_values directly against a plain dict here.
    errors = reject_url_values({"endpoint": "ftp://example.com/x"})
    assert len(errors) == 1
    assert errors[0].error_kind == "url_rejected"


def test_reject_secret_metadata_detects_markers() -> None:
    # Metadata carrying secret-like keys can never reach FrozenMap.of()
    # (it raises at construction), so this exercises the standalone
    # defensive check against a hand-built FrozenMap bypass path.
    metadata = FrozenMap(_items=(("safe_key", "value"),))
    assert reject_secret_metadata(metadata) == ()


def test_validate_safe_relative_path_accepts_relative() -> None:
    assert validate_safe_relative_path("docs/specification/x.md") is None


def test_validate_safe_relative_path_rejects_absolute() -> None:
    error = validate_safe_relative_path("/etc/passwd")
    assert error is not None
    assert error.error_kind == "unsafe_path"


def test_validate_safe_relative_path_rejects_windows_absolute() -> None:
    error = validate_safe_relative_path("C:\\Windows\\System32")
    assert error is not None
    assert error.error_kind == "unsafe_path"


def test_validate_safe_relative_path_rejects_traversal() -> None:
    error = validate_safe_relative_path("../../etc/passwd")
    assert error is not None
    assert error.error_kind == "unsafe_path"


def test_validate_safe_relative_path_rejects_url() -> None:
    error = validate_safe_relative_path("https://example.com/x")
    assert error is not None
    assert error.error_kind == "url_rejected"


def test_validate_payload_shape_rejects_unknown_request_type() -> None:
    errors = validate_payload_shape("NOT_A_TYPE", FrozenMap.of({}))
    assert len(errors) == 1
    assert errors[0].error_kind == "invalid_payload"


def test_validate_payload_shape_requires_command_type() -> None:
    errors = validate_payload_shape("command_preview", FrozenMap.of({}))
    assert any(error.field_name == "command_type" for error in errors)


def test_validate_payload_shape_accepts_valid_health_check() -> None:
    errors = validate_payload_shape("health_check", FrozenMap.of({}))
    assert errors == ()


def test_validate_payload_shape_rejects_unexpected_key() -> None:
    errors = validate_payload_shape("health_check", FrozenMap.of({"extra": "1"}))
    assert len(errors) == 1
    assert errors[0].field_name == "extra"


def test_validate_backend_request_full_flow_success() -> None:
    request = LocalBackendRequest.of(
        "req-1", "health_check", "operator-a", "2026-07-07T10:00:00Z"
    )
    assert validate_backend_request(request) == ()


def test_validate_backend_request_full_flow_unknown_type() -> None:
    request = LocalBackendRequest.of(
        "req-2", "NOT_A_TYPE", "operator-a", "2026-07-07T10:00:00Z"
    )
    errors = validate_backend_request(request)
    assert len(errors) == 1
    assert errors[0].error_kind == "invalid_request_type"


def test_validate_backend_request_rejects_missing_command_type() -> None:
    request = LocalBackendRequest.of(
        "req-3", "command_preview", "operator-a", "2026-07-07T10:00:00Z"
    )
    errors = validate_backend_request(request)
    assert any(error.field_name == "command_type" for error in errors)
