"""test_backend_models.py - SCOS Stage 6.2 local backend model suite.

Run: python -m pytest scos/control_center/tests/test_backend_models.py -q
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from backend_models import (  # noqa: E402
    ALLOWED_BACKEND_ERROR_KINDS,
    ALLOWED_BACKEND_WARNING_KINDS,
    ALLOWED_REQUEST_TYPES,
    ALLOWED_RESPONSE_STATUSES,
    ALLOWED_RESPONSE_TYPES,
    LOCAL_BACKEND_SCHEMA_VERSION,
    BackendError,
    BackendHealthSnapshot,
    BackendWarning,
    LocalBackendRequest,
    LocalBackendResponse,
)


def test_schema_version_and_constants() -> None:
    assert LOCAL_BACKEND_SCHEMA_VERSION == 1
    assert len(ALLOWED_REQUEST_TYPES) == 8
    assert "health_check" in ALLOWED_REQUEST_TYPES
    assert "command_enqueue_dry_run" in ALLOWED_REQUEST_TYPES
    assert set(ALLOWED_RESPONSE_TYPES) == {
        "health",
        "validation_result",
        "dry_run_result",
        "snapshot",
        "rejected",
        "error",
    }
    assert set(ALLOWED_RESPONSE_STATUSES) == {
        "success",
        "rejected",
        "blocked",
        "failure",
    }


def test_request_to_dict_key_order() -> None:
    request = LocalBackendRequest.of(
        "req-1",
        "health_check",
        "operator-a",
        "2026-07-07T10:00:00Z",
        payload={"a": "b"},
        metadata={"origin": "control-center"},
    )
    assert list(request.to_dict().keys()) == [
        "request_id",
        "request_type",
        "operator_id",
        "created_at",
        "payload",
        "metadata",
    ]
    assert request.to_dict()["payload"] == {"a": "b"}


def test_request_allows_unknown_type_for_validation_layer() -> None:
    request = LocalBackendRequest.of(
        "req-2", "NOT_A_TYPE", "operator-a", "2026-07-07T10:00:00Z"
    )
    assert request.request_type == "NOT_A_TYPE"


def test_request_rejects_secret_metadata_at_construction() -> None:
    with pytest.raises(ValueError):
        LocalBackendRequest.of(
            "req-3",
            "health_check",
            "operator-a",
            "2026-07-07T10:00:00Z",
            metadata={"api_key": "abc"},
        )


def test_request_rejects_empty_required_fields() -> None:
    with pytest.raises(ValueError):
        LocalBackendRequest.of("", "health_check", "operator-a", "2026-07-07T10:00:00Z")


def test_response_round_trip() -> None:
    response = LocalBackendResponse.of(
        ok=True,
        request_id="req-1",
        request_type="health_check",
        response_type="health",
        status="success",
        created_at="2026-07-07T10:00:00Z",
        data={"backend_status": "ready"},
    )
    data = response.to_dict()
    restored = LocalBackendResponse.from_dict(data)
    assert restored == response
    assert list(data.keys()) == [
        "ok",
        "schema_version",
        "request_id",
        "request_type",
        "response_type",
        "status",
        "data",
        "errors",
        "warnings",
        "created_at",
        "metadata",
    ]


def test_response_enforces_allowed_response_type_and_status() -> None:
    with pytest.raises(ValueError):
        LocalBackendResponse.of(
            ok=True,
            request_id="req-1",
            request_type="health_check",
            response_type="not_a_type",
            status="success",
            created_at="t",
        )
    with pytest.raises(ValueError):
        LocalBackendResponse.of(
            ok=True,
            request_id="req-1",
            request_type="health_check",
            response_type="health",
            status="not_a_status",
            created_at="t",
        )


def test_backend_error_enforces_allowed_kind() -> None:
    with pytest.raises(ValueError):
        BackendError.of("not_a_kind", "detail")
    error = BackendError.of(
        "invalid_request_type", "unknown request_type: x", field_name="request_type"
    )
    assert error.error_kind in ALLOWED_BACKEND_ERROR_KINDS
    assert BackendError.from_dict(error.to_dict()) == error


def test_backend_warning_enforces_allowed_kind() -> None:
    with pytest.raises(ValueError):
        BackendWarning.of("not_a_kind", "detail")
    warning = BackendWarning.of("dry_run_only", "no execution occurred")
    assert warning.warning_kind in ALLOWED_BACKEND_WARNING_KINDS
    assert BackendWarning.from_dict(warning.to_dict()) == warning


def test_health_snapshot_expected_defaults() -> None:
    snapshot = BackendHealthSnapshot.of(
        capabilities=("health_check",), disabled_capabilities=("real_dispatch",)
    )
    assert snapshot.backend_status == "ready"
    assert snapshot.stage == "Stage 6.2"
    assert snapshot.active_store == "in_memory_only"
    assert snapshot.event_stream_status == "disabled_until_stage_6_4"
    assert snapshot.adapter_dispatch_status == "disabled_until_later_stage"
    assert BackendHealthSnapshot.from_dict(snapshot.to_dict()) == snapshot


def test_no_mutable_fields_exposed() -> None:
    request = LocalBackendRequest.of(
        "req-1", "health_check", "operator-a", "2026-07-07T10:00:00Z"
    )
    for field in dataclasses.fields(request):
        value = getattr(request, field.name)
        assert not isinstance(value, (list, dict, set))
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.request_id = "other"  # type: ignore[misc]
