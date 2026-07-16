from __future__ import annotations

import builtins
import socket
import sqlite3
import subprocess
from pathlib import Path

import pytest

from scos.control_center.operator_dry_run import (
    OPERATOR_DRY_RUN_SCHEMA_VERSION,
    plan_operator_dry_run,
    validate_dry_run_request,
)


def _request(operation: str = "inspect-project", **parameters):
    return {
        "request_id": "req-9b-001",
        "operation": operation,
        "dry_run": True,
        "parameters": {"project_id": "project-001"} | parameters,
        "requested_at": "2026-07-16T00:00:00Z",
        "schema_version": OPERATOR_DRY_RUN_SCHEMA_VERSION,
    }


def test_valid_inspect_request_is_ready_and_dry_run_only():
    response = plan_operator_dry_run(_request(), generated_at="t0")

    assert response["mode"] == "DRY_RUN"
    assert response["status"] == "READY"
    assert response["side_effects_performed"] is False
    assert response["authorization"]["status"] == "NOT_APPLICABLE"
    assert response["normalized_parameters"] == {"project_id": "project-001"}
    assert [item["order"] for item in response["proposed_actions"]] == [1, 2]
    assert any(item["action"] == "invoke_hvs" for item in response["prohibited_actions"])


@pytest.mark.parametrize(
    "mutator,reason",
    [
        (lambda req: req.pop("dry_run"), "DRY_RUN_MUST_BE_TRUE"),
        (lambda req: req.update({"dry_run": False}), "DRY_RUN_MUST_BE_TRUE"),
        (lambda req: req.update({"dry_run": 1}), "DRY_RUN_MUST_BE_TRUE"),
        (lambda req: req.update({"operation": "execute-project"}), "UNKNOWN_OPERATION"),
        (lambda req: req.update({"extra": "nope"}), "UNKNOWN_TOP_LEVEL_FIELD"),
        (lambda req: req["parameters"].update({"shell": "rm -rf ."}), "UNKNOWN_PARAMETER_FIELD"),
        (lambda req: req["parameters"].update({"url": "https://example.invalid"}), "UNKNOWN_PARAMETER_FIELD"),
        (lambda req: req["parameters"].update({"env": "SECRET=1"}), "UNKNOWN_PARAMETER_FIELD"),
        (lambda req: req["parameters"].update({"project_id": "bad/project"}), "PROJECT_ID_UNSAFE"),
        (lambda req: req["parameters"].update({"project_id": "x" * 121}), "PROJECT_ID_TOO_LONG"),
    ],
)
def test_request_validation_rejects_invalid_or_executable_shapes(mutator, reason):
    req = _request()
    mutator(req)
    response = plan_operator_dry_run(req)

    assert response["status"] == "INVALID"
    assert reason in response["reason_codes"]
    assert response["mode"] == "DRY_RUN"
    assert response["side_effects_performed"] is False


def test_initialize_project_blocks_without_authorization_and_does_not_fabricate_approval():
    response = plan_operator_dry_run(
        _request("initialize-project", title="Demo", language="en"),
        policy_snapshot={"initialize-project": "NOT_AUTHORIZED"},
    )

    assert response["status"] == "BLOCKED"
    assert response["authorization"]["status"] == "NOT_AUTHORIZED"
    assert "AUTHORIZATION_NOT_GRANTED" in response["reason_codes"]
    assert "write_approval_or_authorization" in {item["action"] for item in response["prohibited_actions"]}


def test_missing_authorization_evaluator_input_is_unavailable_not_fake_empty_success():
    response = plan_operator_dry_run(_request("initialize-project", title="Demo", language="en"))

    assert response["status"] == "UNAVAILABLE"
    assert response["authorization"]["status"] == "AUTHORIZATION_UNAVAILABLE"
    assert response["proposed_actions"]


def test_prepare_render_reports_prerequisite_blocker_and_never_rendered_success():
    response = plan_operator_dry_run(
        _request("prepare-render", render_profile="vertical"),
        policy_snapshot={"prepare-render": "AUTHORIZED_FOR_PREVIEW"},
    )

    assert response["status"] == "BLOCKED"
    assert "RENDER_INPUTS_NOT_VERIFIED_IN_DRY_RUN" in response["reason_codes"]
    assert "start_ffmpeg_or_ffprobe" in {item["action"] for item in response["prohibited_actions"]}


def test_unavailable_dependency_is_distinct_from_empty_ready_plan():
    response = plan_operator_dry_run(
        _request(),
        prerequisite_snapshot={"project-001": "UNAVAILABLE"},
    )

    assert response["status"] == "UNAVAILABLE"
    assert "BACKEND_SNAPSHOT_UNAVAILABLE" in response["reason_codes"]
    assert response["proposed_actions"]


def test_deterministic_and_redacted_response():
    req = _request()
    first = plan_operator_dry_run(req, generated_at="fixed")
    second = plan_operator_dry_run(req, generated_at="fixed")

    assert first == second
    text = str(first).lower()
    for forbidden in ("lease_token", "host_handle", "authorization_token", "secret", "password", "api_key", "c:/users"):
        assert forbidden not in text


def test_zero_side_effect_mutation_traps(monkeypatch, tmp_path):
    counts = {"filesystem": 0, "database": 0, "subprocess": 0, "network": 0}

    def blocked_open(*args, **kwargs):
        counts["filesystem"] += 1
        raise AssertionError("filesystem touched")

    def blocked_connect(*args, **kwargs):
        counts["database"] += 1
        raise AssertionError("database touched")

    def blocked_run(*args, **kwargs):
        counts["subprocess"] += 1
        raise AssertionError("subprocess touched")

    def blocked_socket(*args, **kwargs):
        counts["network"] += 1
        raise AssertionError("network touched")

    monkeypatch.setattr(builtins, "open", blocked_open)
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: (_ for _ in ()).throw(AssertionError("write_text touched")))
    monkeypatch.setattr(sqlite3, "connect", blocked_connect)
    monkeypatch.setattr(subprocess, "run", blocked_run)
    monkeypatch.setattr(socket, "socket", blocked_socket)

    cases = (
        _request(),
        _request("initialize-project", title="Demo", language="en"),
        _request("prepare-render", render_profile="vertical"),
        _request() | {"dry_run": False},
    )
    for case in cases:
        response = plan_operator_dry_run(case, policy_snapshot={"initialize-project": "NOT_AUTHORIZED", "prepare-render": "AUTHORIZED_FOR_PREVIEW"})
        assert response["side_effects_performed"] is False

    assert counts == {"filesystem": 0, "database": 0, "subprocess": 0, "network": 0}


def test_active_runtime_code_has_no_live_execution_imports():
    source = Path("scos/control_center/operator_dry_run.py").read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "Popen",
        "os.system",
        "shell=True",
        "exec(",
        "eval(",
        "ffmpeg",
        "ffprobe",
        "requests",
        "urllib",
        "socket",
        "webhook",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "document.cookie",
    )
    for token in forbidden:
        assert token not in source
