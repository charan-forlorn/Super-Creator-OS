"""Stage 7.7 adapter activation preflight gate tests."""

from __future__ import annotations

import json
from pathlib import Path

from scos.control_center.adapter_activation_preflight_gate import run_adapter_activation_preflight
from scos.control_center.adapter_activation_preflight_models import (
    AdapterActivationPreflightError,
    AdapterActivationPreflightResult,
)

_NOW = "2026-07-10T02:00:00Z"


def test_preflight_only_is_deterministic_for_repo_root() -> None:
    first = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW)
    second = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(first, AdapterActivationPreflightResult)
    assert isinstance(second, AdapterActivationPreflightResult)
    assert first.to_dict() == second.to_dict()
    assert first.can_activate_now is False
    assert first.dispatch_blocked is True
    assert first.requested_activation_mode == "preflight_only"
    assert first.target_adapter is None


def test_do_not_activate_is_valid_and_accepted() -> None:
    result = run_adapter_activation_preflight(
        repo_root=Path("."),
        checked_at=_NOW,
        target_adapter="all",
        requested_activation_mode="do_not_activate",
    )

    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.accepted is True
    assert result.can_activate_now is False
    assert any("do_not_activate" in warning for warning in result.warnings)


def test_simulator_and_manual_modes_are_valid() -> None:
    simulator = run_adapter_activation_preflight(
        repo_root=Path("."),
        checked_at=_NOW,
        requested_activation_mode="simulator_only",
    )
    manual = run_adapter_activation_preflight(
        repo_root=Path("."),
        checked_at=_NOW,
        requested_activation_mode="manual_handoff_only",
    )

    assert isinstance(simulator, AdapterActivationPreflightResult)
    assert isinstance(manual, AdapterActivationPreflightResult)
    assert simulator.can_activate_now is False
    assert manual.can_activate_now is False


def test_real_dispatch_flag_returns_blocked_result() -> None:
    result = run_adapter_activation_preflight(
        repo_root=Path("."),
        checked_at=_NOW,
        allow_real_dispatch=True,
    )

    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.go_no_go == "BLOCKED"
    assert result.readiness_score <= 69
    assert result.can_activate_now is False
    assert any("allow_real_dispatch=True" in blocker for blocker in result.blockers)


def test_forbidden_activation_mode_returns_error() -> None:
    result = run_adapter_activation_preflight(
        repo_root=Path("."),
        checked_at=_NOW,
        requested_activation_mode="api_dispatch",
    )

    assert isinstance(result, AdapterActivationPreflightError)
    assert result.error_code == "INVALID_ADAPTER_PREFLIGHT_INPUT"


def test_missing_required_evidence_blocks_and_optional_evidence_warns(tmp_path: Path) -> None:
    (tmp_path / "docs/specification").mkdir(parents=True)
    result = run_adapter_activation_preflight(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.go_no_go == "BLOCKED"
    assert result.blockers
    assert any("required artifact" in blocker for blocker in result.blockers)
    assert any("optional runtime artifact" in warning for warning in result.warnings)


def test_no_implicit_output_write_and_explicit_output_write(tmp_path: Path) -> None:
    result = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW)
    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.report_path is None
    assert not (Path("adapter-preflight-report.json")).exists()

    output_path = tmp_path / "reports" / "preflight.json"
    written = run_adapter_activation_preflight(
        repo_root=tmp_path,
        checked_at=_NOW,
        requested_activation_mode="do_not_activate",
        output_path=output_path,
    )
    assert isinstance(written, AdapterActivationPreflightResult)
    assert written.report_path == str(output_path.resolve())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["gate_id"] == written.gate_id
    assert payload["report_path"] is None


def test_required_status_fields_are_represented() -> None:
    result = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.approval_evidence_status in {"pass", "missing", "blocker"}
    assert result.audit_evidence_status in {"pass", "missing", "blocker"}
    assert result.secret_handling_status == "pass"
    assert result.simulator_fallback_status in {"pass", "missing", "blocker"}
    assert result.manual_fallback_status in {"pass", "missing", "blocker"}
    assert result.rollback_status == "pass"
    assert result.security_review_status in {"pass", "missing", "blocker"}
    assert result.transport_boundary_status in {"pass", "missing", "blocker"}
    assert result.adapter_contract_status in {"pass", "missing", "blocker"}


def test_stage7_7_static_scan_reports_no_forbidden_findings_in_repo() -> None:
    result = run_adapter_activation_preflight(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, AdapterActivationPreflightResult)
    assert result.forbidden_behavior_findings == ()
