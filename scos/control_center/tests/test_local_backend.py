"""test_local_backend.py - SCOS Stage 6.2 local backend facade suite.

Run: python -m pytest scos/control_center/tests/test_local_backend.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from backend_models import LocalBackendRequest  # noqa: E402
from local_backend import LocalControlCenterBackend  # noqa: E402


def test_health() -> None:
    backend = LocalControlCenterBackend()
    response = backend.health("req-1", "operator-a", "2026-07-07T10:00:00Z")
    assert response.ok is True
    assert response.response_type == "health"


def test_handle_dispatches_to_health_check() -> None:
    backend = LocalControlCenterBackend()
    request = LocalBackendRequest.of(
        "req-1", "health_check", "operator-a", "2026-07-07T10:00:00Z"
    )
    response = backend.handle(request, "2026-07-07T10:00:00Z")
    assert response.ok is True


def test_preview_command() -> None:
    backend = LocalControlCenterBackend()
    response = backend.preview_command(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_SMOKE_CHECK",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True
    assert response.response_type == "validation_result"


def test_validate_command() -> None:
    backend = LocalControlCenterBackend()
    response = backend.validate_command(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_SMOKE_CHECK",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True


def test_dry_run_enqueue() -> None:
    backend = LocalControlCenterBackend()
    response = backend.dry_run_enqueue(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_SMOKE_CHECK",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True
    assert response.data.to_dict()["would_enqueue"] == "True"


def test_dry_run_enqueue_rejects_unknown_command() -> None:
    backend = LocalControlCenterBackend()
    response = backend.dry_run_enqueue(
        request_id="req-1",
        operator_id="operator-a",
        command_type="NOT_A_TYPE",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is False
    assert response.status == "rejected"


def test_facade_has_no_socket_or_server_attributes() -> None:
    backend = LocalControlCenterBackend()
    forbidden = ("socket", "server", "listen", "bind", "accept")
    for attribute in dir(backend):
        lowered = attribute.lower()
        for marker in forbidden:
            assert marker not in lowered
