"""Stage 7.6 operator command view builder tests."""

from __future__ import annotations

from pathlib import Path

from scos.control_center.operator_command_views import (
    build_operator_command_view,
    build_operator_command_view_snapshot,
    classify_approval_state,
    render_operator_command_view_markdown,
    validate_operator_command_view_inputs,
)
from scos.control_center.operator_command_view_models import OperatorCommandViewSnapshot

_NOW = "2026-07-10T01:00:00Z"


def _command(command_id: str, **overrides):
    payload = {
        "command_id": command_id,
        "command_type": "RUN_SMOKE_CHECK",
        "approval_decision": "approved",
        "audit_state": "audited",
        "event_state": "present",
        "has_execution_event": False,
        "allowlisted": True,
        "validation_ok": True,
        "references": (
            {
                "reference_id": f"{command_id}-approval",
                "reference_type": "approval",
                "source_stage": "Stage 6.6",
                "path": "scos/work/control_center/state/control_center.sqlite3",
                "exists": True,
                "readable": True,
                "digest": "c" * 64,
            },
            {
                "reference_id": f"{command_id}-event",
                "reference_type": "event",
                "source_stage": "Stage 6.4",
                "path": "scos/work/control_center/events/command_events.jsonl",
                "exists": True,
                "readable": True,
                "digest": "d" * 64,
            },
        ),
    }
    payload.update(overrides)
    return payload


def test_pending_approval_is_visible_and_non_terminal() -> None:
    approval = classify_approval_state(command_id="cmd-pending", approval_decision="pending")

    assert approval.approval_state == "pending"
    assert approval.terminal is False
    assert "Review approval evidence" in approval.required_operator_action


def test_approved_command_is_visible_but_not_executed() -> None:
    view = build_operator_command_view(checked_at=_NOW, command=_command("cmd-approved"))

    assert view.approval.approval_state == "approved"
    assert view.approval.terminal is False
    assert view.execution.execution_state == "not_executed"
    assert "does not run commands" in view.next_manual_action


def test_denied_missing_tampered_and_blocked_are_terminal() -> None:
    denied = build_operator_command_view(
        checked_at=_NOW,
        command=_command("cmd-denied", approval_decision="denied"),
    )
    missing = build_operator_command_view(
        checked_at=_NOW,
        command=_command("cmd-missing", approval_decision=None),
    )
    tampered = build_operator_command_view(
        checked_at=_NOW,
        command=_command("cmd-tampered", approval_tampered=True),
    )
    blocked = build_operator_command_view(
        checked_at=_NOW,
        command=_command("cmd-blocked", blocker_reason="validation denied command type"),
    )

    assert denied.approval.terminal is True
    assert denied.execution.execution_state == "blocked_denied"
    assert missing.approval.terminal is True
    assert missing.execution.execution_state == "blocked_missing_approval"
    assert tampered.approval.terminal is True
    assert tampered.execution.execution_state == "blocked_tampered_approval"
    assert blocked.approval.terminal is True
    assert blocked.blockers


def test_executed_command_shows_audit_and_event_evidence() -> None:
    view = build_operator_command_view(
        checked_at=_NOW,
        command=_command("cmd-executed", has_execution_event=True),
    )

    assert view.approval.approval_state == "executed"
    assert view.approval.terminal is True
    assert view.execution.execution_state == "executed"
    assert view.execution.audit_state == "audited"
    assert view.execution.event_state == "present"


def test_unknown_and_missing_optional_evidence_are_not_healthy() -> None:
    view = build_operator_command_view(
        checked_at=_NOW,
        command=_command(
            "cmd-unknown",
            approval_decision="approved",
            audit_state="unknown",
            event_state="unknown",
            references=(
                {
                    "reference_id": "optional-result",
                    "reference_type": "result",
                    "source_stage": "Stage 6.4",
                    "path": "scos/work/control_center/results/command_result.json",
                    "exists": False,
                    "readable": False,
                    "digest": None,
                },
            ),
        ),
    )

    assert "Audit evidence is unknown." in view.warnings
    assert any("Optional evidence is missing" in warning for warning in view.warnings)


def test_snapshot_totals_and_ids_are_deterministic() -> None:
    commands = (
        _command("cmd-approved"),
        _command("cmd-denied", approval_decision="denied"),
        _command("cmd-missing", approval_decision=None),
        _command("cmd-executed", has_execution_event=True),
        _command("cmd-blocked", allowlisted=False),
        _command("cmd-pending", approval_decision="pending"),
    )
    first = build_operator_command_view_snapshot(checked_at=_NOW, commands=commands)
    second = build_operator_command_view_snapshot(checked_at=_NOW, commands=commands)

    assert isinstance(first, OperatorCommandViewSnapshot)
    assert first.snapshot_id == second.snapshot_id
    assert first.to_dict() == second.to_dict()
    assert first.totals.pending == 1
    assert first.totals.approved == 2
    assert first.totals.denied == 1
    assert first.totals.missing_approval == 1
    assert first.totals.executed == 1
    assert first.totals.blocked >= 3
    assert first.totals.audited == 6


def test_input_validation_rejects_output_path_and_bad_inputs() -> None:
    errors = validate_operator_command_view_inputs(
        checked_at="",
        commands=(
            {"command_id": "cmd-1", "command_type": "RUN_SMOKE_CHECK", "output_path": "out.json"},
            {"command_id": "cmd-1", "command_type": ""},
        ),
    )

    assert "checked_at must be caller-supplied and non-empty" in errors
    assert any("output_path" in error for error in errors)
    assert any("duplicate command_id" in error for error in errors)


def test_render_markdown_is_deterministic() -> None:
    snapshot = build_operator_command_view_snapshot(
        checked_at=_NOW,
        commands=(_command("cmd-approved"),),
    )

    first = render_operator_command_view_markdown(snapshot=snapshot)
    second = render_operator_command_view_markdown(snapshot=snapshot)

    assert first == second
    assert snapshot.snapshot_id in first


def test_stage7_6_production_files_do_not_import_execution_or_write_paths() -> None:
    source_paths = (
        Path("scos/control_center/operator_command_view_models.py"),
        Path("scos/control_center/operator_command_views.py"),
        Path("scos/control_center/execution_evidence_surface.py"),
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)
    forbidden = (
        "sub" + "process",
        "shell=True",
        "append_",
        "sqlite3.connect",
        "open(",
        "write_text",
        "write_bytes",
        "time." + "time",
        "datetime." + "now",
        "uuid",
        "random",
        "Web" + "Socket",
        "Event" + "Source",
        "set" + "Interval",
        "set" + "Timeout",
        "fetch(",
        "XML" + "HttpRequest",
        "axios",
    )
    for token in forbidden:
        assert token not in combined
