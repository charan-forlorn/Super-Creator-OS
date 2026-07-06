"""test_command_api.py - SCOS Stage 6.2 Command API boundary suite.

Run: python -m pytest scos/control_center/tests/test_command_api.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from backend_models import LocalBackendRequest  # noqa: E402
from command_api import (  # noqa: E402
    dry_run_enqueue_command,
    get_backend_health,
    handle_local_backend_request,
    preview_command_request,
    validate_command_request,
)


def test_get_backend_health_reports_stage_6_2() -> None:
    response = get_backend_health(
        request_id="req-1", operator_id="operator-a", checked_at="2026-07-07T10:00:00Z"
    )
    assert response.ok is True
    assert response.response_type == "health"
    data = response.data.to_dict()
    assert data["stage"] == "Stage 6.2"
    assert data["active_store"] == "in_memory_only"
    assert data["event_stream_status"] == "disabled_until_stage_6_4"
    assert data["adapter_dispatch_status"] == "disabled_until_later_stage"


def test_preview_command_request_success() -> None:
    response = preview_command_request(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_SMOKE_CHECK",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True
    assert response.response_type == "validation_result"
    assert any(w.warning_kind == "dry_run_only" for w in response.warnings)


def test_preview_command_request_rejects_unknown_type() -> None:
    response = preview_command_request(
        request_id="req-1",
        operator_id="operator-a",
        command_type="NOT_A_TYPE",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is False
    assert response.status == "rejected"
    assert response.errors[0].error_kind == "command_not_allowed"


def test_validate_command_request_success() -> None:
    response = validate_command_request(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_STAGE4_FINAL_GATE",
        command_payload={"checked_at": "2026-07-07T10:00:00Z"},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True
    assert response.data.to_dict()["valid"] == "True"


def test_validate_command_request_rejects_missing_required_arg() -> None:
    response = validate_command_request(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_STAGE4_FINAL_GATE",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is False
    assert response.status == "rejected"


def test_validate_command_request_rejects_forbidden_text() -> None:
    response = validate_command_request(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_STAGE4_FINAL_GATE",
        command_payload={"checked_at": "git push origin main"},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is False
    assert any(e.error_kind == "forbidden_operation" for e in response.errors)


def test_dry_run_enqueue_command_success_does_not_execute() -> None:
    response = dry_run_enqueue_command(
        request_id="req-1",
        operator_id="operator-a",
        command_type="RUN_SMOKE_CHECK",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is True
    assert response.response_type == "dry_run_result"
    data = response.data.to_dict()
    assert data["would_enqueue"] == "True"
    assert any(w.warning_kind == "persistence_not_enabled" for w in response.warnings)


def test_dry_run_enqueue_command_rejects_unknown_type() -> None:
    response = dry_run_enqueue_command(
        request_id="req-1",
        operator_id="operator-a",
        command_type="DELETE_EVERYTHING",
        command_payload={},
        created_at="2026-07-07T10:00:00Z",
    )
    assert response.ok is False
    assert response.status == "rejected"
    assert response.data.to_dict()["would_enqueue"] == "False"


def test_handle_local_backend_request_health_check() -> None:
    request = LocalBackendRequest.of(
        "req-1", "health_check", "operator-a", "2026-07-07T10:00:00Z"
    )
    response = handle_local_backend_request(request, checked_at="2026-07-07T10:00:00Z")
    assert response.ok is True
    assert response.response_type == "health"


def test_handle_local_backend_request_rejects_invalid_type() -> None:
    request = LocalBackendRequest.of(
        "req-1", "NOT_A_TYPE", "operator-a", "2026-07-07T10:00:00Z"
    )
    response = handle_local_backend_request(request, checked_at="2026-07-07T10:00:00Z")
    assert response.ok is False
    assert response.status == "rejected"


def test_handle_local_backend_request_command_enqueue_dry_run() -> None:
    request = LocalBackendRequest.of(
        "req-1",
        "command_enqueue_dry_run",
        "operator-a",
        "2026-07-07T10:00:00Z",
        payload={"command_type": "RUN_SMOKE_CHECK"},
    )
    response = handle_local_backend_request(request, checked_at="2026-07-07T10:00:00Z")
    assert response.ok is True
    assert response.response_type == "dry_run_result"


def test_handle_local_backend_request_snapshot_is_mocked() -> None:
    request = LocalBackendRequest.of(
        "req-1", "session_snapshot", "operator-a", "2026-07-07T10:00:00Z"
    )
    response = handle_local_backend_request(request, checked_at="2026-07-07T10:00:00Z")
    assert response.ok is True
    assert response.response_type == "snapshot"
    assert any(w.warning_kind == "snapshot_mocked" for w in response.warnings)
