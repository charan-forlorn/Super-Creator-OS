"""Stage 8.4 secret-safe adapter preflight gate tests."""

from __future__ import annotations

import ast
import copy
import json
import shutil
from pathlib import Path

from scos.control_center.adapter_activation_preflight_gate import run_adapter_activation_preflight
from scos.control_center.credential_policy_validation import build_stage83_credential_policy_evidence
from scos.control_center.file_snapshot_refresh_transport import validate_file_snapshot_transport_boundary
from scos.control_center.secret_safe_adapter_preflight_gate import (
    build_stage84_preflight_evidence,
    write_secret_safe_adapter_preflight_report,
)
from scos.control_center.secret_safe_adapter_preflight_models import SafeCredentialReference
from scos.control_center.transport_activation_decision_gate import run_local_transport_activation_decision_gate

_NOW = "2026-07-10T08:00:00Z"


def _generic() -> dict:
    result = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW, target_adapter="codex")
    return result.to_dict()


def _transport() -> dict:
    result = run_local_transport_activation_decision_gate(
        repo_root=Path("."),
        decided_at=_NOW,
        requested_decision="FILE_SNAPSHOT_REFRESH_ALLOWED_LATER",
        allow_future_implementation=True,
    )
    return result.to_dict()


def _evidence() -> dict:
    return {
        "generic_preflight_evidence": _generic(),
        "transport_decision_evidence": _transport(),
        "file_snapshot_boundary_evidence": validate_file_snapshot_transport_boundary(repo_root=Path("."), checked_at=_NOW),
        "credential_policy_evidence": build_stage83_credential_policy_evidence(checked_at=_NOW).to_dict(),
        "operator_approval_evidence": {
            "approval_decision": "approved",
            "approval_scope": "adapter_specific",
            "action": "present_to_operator_decision",
            "adapter_id": "codex",
            "checked_at": _NOW,
        },
        "audit_readiness_evidence": {"append_only_supported": True, "will_write_now": False},
        "rollback_evidence": {"restores_adapter_disabled": True, "network_dependency": False, "steps": ["keep adapter disabled"]},
        "simulator_fallback_evidence": {"available": True, "claims_runtime_activation": False},
        "manual_fallback_evidence": {"available": True, "claims_runtime_activation": False},
    }


def _result(**overrides):
    evidence = _evidence()
    evidence.update(overrides)
    return build_stage84_preflight_evidence(
        adapter_id="codex",
        checked_at=_NOW,
        safe_credential_references=(
            SafeCredentialReference("ref", "API_KEY", "SECRET", "policy_reference", "policy_only", "redacted", False),
        ),
        metadata={"stage": "8.4"},
        **evidence,
    )


def test_complete_synthetic_evidence_is_ready_for_operator_decision() -> None:
    result = _result()

    assert result.verdict == "READY_FOR_OPERATOR_DECISION"
    assert result.accepted is True
    assert result.ready_for_operator_decision is True
    assert result.can_activate_now is False
    assert result.activation_authorized is False
    assert result.real_dispatch_blocked is True
    assert result.external_calls_blocked is True
    assert result.credentials_materialized is False
    assert result.runtime_mutated is False


def test_blocker_overrides_score_and_checks_are_stably_ordered() -> None:
    result = _result(rollback_evidence={})

    assert result.verdict == "BLOCKED"
    assert result.readiness_score <= 69
    assert [check.check_id for check in result.checks] == sorted(check.check_id for check in result.checks)


def test_input_evidence_is_not_mutated() -> None:
    evidence = _evidence()
    before = copy.deepcopy(evidence)

    build_stage84_preflight_evidence(adapter_id="codex", checked_at=_NOW, **evidence)

    assert evidence == before


def test_no_implicit_report_write_and_explicit_report_is_deterministic(tmp_path: Path) -> None:
    result = _result()
    output = tmp_path / "stage8_4_report.json"

    assert result.report_path is None
    first = write_secret_safe_adapter_preflight_report(result, repo_root=tmp_path, output_path=output)
    first_text = output.read_text(encoding="utf-8")
    second = write_secret_safe_adapter_preflight_report(result, repo_root=tmp_path, output_path=output)

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert output.read_text(encoding="utf-8") == first_text
    assert "FAKE_" + "SECRET" + "_DO_NOT_USE" not in first_text
    assert json.loads(first_text)["verdict"] == "READY_FOR_OPERATOR_DECISION"


def test_runtime_stores_are_not_mutated_by_gate() -> None:
    watched = tuple(
        path
        for path in (
            Path("scos/work/control_center/state/control_center.sqlite3"),
            Path("scos/work/control_center/events/command_events.jsonl"),
            Path("scos/work/control_center/queue/approved_commands.jsonl"),
        )
        if path.exists()
    )
    before = {path: path.read_bytes() for path in watched}

    _result()

    assert {path: path.read_bytes() for path in watched} == before


def test_stage_7_7_and_stage_8_1_to_8_3_remain_compatible() -> None:
    result = _result()

    assert result.metadata.to_dict()["pass_meaning"] == "READY_FOR_OPERATOR_DECISION_ONLY"
    assert any(check.category == "generic_preflight" and check.status == "pass" for check in result.checks)
    assert any(check.category == "transport_decision" and check.status == "pass" for check in result.checks)
    assert any(check.category == "file_snapshot_boundary" and check.status == "pass" for check in result.checks)
    assert any(check.category == "credential_policy" and check.status == "pass" for check in result.checks)


def test_static_safety_scan_new_stage84_sources() -> None:
    source_paths = (
        Path("scos/control_center/secret_safe_adapter_preflight_models.py"),
        Path("scos/control_center/secret_safe_adapter_preflight_validation.py"),
        Path("scos/control_center/secret_safe_adapter_preflight_gate.py"),
    )
    forbidden_import_roots = {
        "requests",
        "httpx",
        "socket",
        "websocket",
        "aiohttp",
        "subprocess",
        "dotenv",
        "keyring",
        "boto",
        "vault",
        "time",
        "datetime",
        "uuid",
        "random",
        "threading",
        "multiprocessing",
        "watchdog",
    }
    forbidden_calls = {"Popen", "system"}
    for path in source_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_import_roots
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_import_roots
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    assert func.id not in forbidden_calls
                if isinstance(func, ast.Attribute):
                    assert func.attr not in forbidden_calls


def test_report_path_rejects_escape(tmp_path: Path) -> None:
    result = _result()
    outside = tmp_path.parent / "outside.json"

    write = write_secret_safe_adapter_preflight_report(result, repo_root=tmp_path, output_path=outside)

    assert write["accepted"] is False
    assert not outside.exists()
