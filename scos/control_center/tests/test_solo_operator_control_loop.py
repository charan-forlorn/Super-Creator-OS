from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scos.control_center.solo_operator_control_loop import (
    STATUS_APPROVAL_REQUIRED,
    STATUS_APPROVED,
    STATUS_DRY_RUN_SUCCEEDED,
    STATUS_REJECTED,
    SoloOperatorControlLoop,
    validate_video_request,
)


def _payload(idempotency_key: str = "idem-1") -> dict[str, str]:
    return {
        "workflow": "video-production",
        "project_id": "demo-project",
        "title": "Demo Project",
        "language": "en",
        "render_profile": "vertical",
        "idempotency_key": idempotency_key,
    }


@pytest.fixture()
def loop(tmp_path: Path) -> SoloOperatorControlLoop:
    service = SoloOperatorControlLoop(repo_root=tmp_path, db_path=Path("state/control.sqlite3"))
    assert service.initialize(applied_at="t0") is None
    return service


def test_valid_request_creates_durable_command_and_stable_identity(loop: SoloOperatorControlLoop) -> None:
    first = loop.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    second = loop.submit_request(payload=_payload(), operator_id="operator", created_at="t2")

    assert first["ok"] is True
    assert first["status"] == STATUS_APPROVAL_REQUIRED
    assert first["command_id"] == second["command_id"]
    assert second["status"] == STATUS_APPROVAL_REQUIRED
    assert second["event_count"] == 1


def test_invalid_request_fails_before_durable_command(loop: SoloOperatorControlLoop) -> None:
    response = loop.submit_request(
        payload={**_payload(), "project_id": "../bad", "shell": "no"},
        operator_id="operator",
        created_at="t1",
    )

    assert response["ok"] is False
    assert response["side_effects_performed"] is False
    assert {error["error_kind"] for error in response["errors"]} >= {"invalid_payload", "forbidden_payload"}
    assert loop.store.list_commands() == ()


def test_approval_rejection_and_duplicate_decisions_are_idempotent(loop: SoloOperatorControlLoop) -> None:
    created = loop.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    approved = loop.approve(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="reviewed")
    duplicate = loop.approve(command_id=created["command_id"], operator_id="operator", decided_at="t3", reason="reviewed")
    rejected_after_approval = loop.reject(command_id=created["command_id"], operator_id="operator", decided_at="t4", reason="changed")

    assert approved["status"] == STATUS_APPROVED
    assert duplicate["status"] == STATUS_APPROVED
    assert rejected_after_approval["status"] == STATUS_APPROVED
    assert approved["approval_count"] == 1
    assert len(loop.store.list_approvals()) == 1


def test_rejection_is_terminal_and_dispatch_is_blocked(loop: SoloOperatorControlLoop) -> None:
    created = loop.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    rejected = loop.reject(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="not now")
    dispatched = loop.dispatch_dry_run(command_id=created["command_id"], operator_id="operator", dispatched_at="t3")

    assert rejected["status"] == STATUS_REJECTED
    assert dispatched["ok"] is False
    assert dispatched["status"] == "blocked"
    assert dispatched["error_kind"] == "dispatch_requires_approval"
    assert loop.store.list_results() == ()


def test_approved_dispatch_is_fake_dry_run_and_at_most_once(loop: SoloOperatorControlLoop) -> None:
    created = loop.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    loop.approve(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="reviewed")

    first = loop.dispatch_dry_run(command_id=created["command_id"], operator_id="operator", dispatched_at="t3")
    second = loop.dispatch_dry_run(command_id=created["command_id"], operator_id="operator", dispatched_at="t4")

    assert first["status"] == STATUS_DRY_RUN_SUCCEEDED
    assert first["side_effects_performed"] is False
    assert first["safe_result_summary"] == "Fake HVS dry-run succeeded; no live render executed."
    assert second["status"] == STATUS_DRY_RUN_SUCCEEDED
    assert len(loop.store.list_results()) == 1


def test_restart_reconstructs_authoritative_status(tmp_path: Path) -> None:
    db_path = Path("state/control.sqlite3")
    first = SoloOperatorControlLoop(repo_root=tmp_path, db_path=db_path)
    assert first.initialize(applied_at="t0") is None
    created = first.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    first.approve(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="reviewed")
    first.dispatch_dry_run(command_id=created["command_id"], operator_id="operator", dispatched_at="t3")

    restarted = SoloOperatorControlLoop(repo_root=tmp_path, db_path=db_path)
    assert restarted.initialize(applied_at="t4") is None
    status = restarted.status(command_id=created["command_id"], checked_at="t5")

    assert status["status"] == STATUS_DRY_RUN_SUCCEEDED
    assert status["result_count"] == 1
    assert status["approval_count"] == 1


def test_unknown_outcome_dispatching_state_does_not_auto_retry(tmp_path: Path) -> None:
    db_path = Path("state/control.sqlite3")
    first = SoloOperatorControlLoop(repo_root=tmp_path, db_path=db_path)
    assert first.initialize(applied_at="t0") is None
    created = first.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    first.approve(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="reviewed")

    restarted = SoloOperatorControlLoop(repo_root=tmp_path, db_path=db_path)
    assert restarted.initialize(applied_at="t3") is None
    status = restarted.status(command_id=created["command_id"], checked_at="t4")

    assert status["status"] == STATUS_APPROVED
    assert status["result_count"] == 0


def test_validation_rejects_mutation_escape_fields() -> None:
    intent, errors = validate_video_request({**_payload(), "output_path": "C:/tmp/live.mp4"})

    assert intent is None
    assert any(error.error_kind == "forbidden_payload" for error in errors)


def test_operator_memory_database_is_not_touched(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    memory = root / "memory"
    memory.mkdir()
    database = memory / "database.json"
    database.write_text('{"operator":"owned"}\n', encoding="utf-8")
    before = database.read_bytes()

    service = SoloOperatorControlLoop(repo_root=root, db_path=Path("state/control.sqlite3"))
    assert service.initialize(applied_at="t0") is None
    created = service.submit_request(payload=_payload(), operator_id="operator", created_at="t1")
    service.approve(command_id=created["command_id"], operator_id="operator", decided_at="t2", reason="reviewed")
    service.dispatch_dry_run(command_id=created["command_id"], operator_id="operator", dispatched_at="t3")

    assert database.read_bytes() == before
    shutil.rmtree(root / "state", ignore_errors=True)
