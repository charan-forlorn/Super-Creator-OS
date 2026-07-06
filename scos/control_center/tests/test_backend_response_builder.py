"""test_backend_response_builder.py - SCOS Stage 6.2 response builder suite.

Run: python -m pytest scos/control_center/tests/test_backend_response_builder.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from backend_models import BackendError, BackendHealthSnapshot, BackendWarning  # noqa: E402
from backend_response_builder import (  # noqa: E402
    build_error_response,
    build_health_response,
    build_rejected_response,
    build_success_response,
    stable_backend_json,
)


def test_build_success_response() -> None:
    response = build_success_response(
        request_id="req-1",
        request_type="health_check",
        response_type="health",
        created_at="2026-07-07T10:00:00Z",
        data={"a": "b"},
    )
    assert response.ok is True
    assert response.status == "success"
    assert response.errors == ()


def test_build_rejected_response() -> None:
    error = BackendError.of("invalid_request_type", "bad type")
    response = build_rejected_response(
        request_id="req-1",
        request_type="NOT_A_TYPE",
        created_at="2026-07-07T10:00:00Z",
        errors=(error,),
    )
    assert response.ok is False
    assert response.status == "rejected"
    assert response.response_type == "rejected"
    assert response.errors == (error,)


def test_build_error_response() -> None:
    error = BackendError.of("backend_unavailable", "unavailable")
    response = build_error_response(
        request_id="req-1",
        request_type="health_check",
        created_at="2026-07-07T10:00:00Z",
        errors=(error,),
    )
    assert response.ok is False
    assert response.status == "failure"
    assert response.response_type == "error"


def test_build_health_response() -> None:
    snapshot = BackendHealthSnapshot.of()
    response = build_health_response(
        request_id="req-1", created_at="2026-07-07T10:00:00Z", snapshot=snapshot
    )
    assert response.ok is True
    assert response.response_type == "health"
    assert response.data.to_dict()["backend_status"] == "ready"


def test_stable_backend_json_is_sorted_and_compact() -> None:
    text = stable_backend_json({"b": 1, "a": 2})
    assert text == '{"a":2,"b":1}'


def test_stable_backend_json_deterministic_across_calls() -> None:
    data = {"z": 1, "y": [1, 2, 3], "x": {"nested": True}}
    assert stable_backend_json(data) == stable_backend_json(data)
