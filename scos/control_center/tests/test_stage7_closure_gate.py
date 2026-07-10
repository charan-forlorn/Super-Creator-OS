"""Stage 7.8 closure gate tests."""

from __future__ import annotations

import json
from pathlib import Path

from scos.control_center import stage7_closure_gate
from scos.control_center.stage7_closure_gate import run_stage7_final_closure_gate
from scos.control_center.stage7_closure_models import Stage7ClosureError, Stage7ClosureResult

_NOW = "2026-07-10T03:00:00Z"


def test_stage7_closure_gate_is_deterministic_for_repo_root() -> None:
    first = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)
    second = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(first, Stage7ClosureResult)
    assert isinstance(second, Stage7ClosureResult)
    assert first.to_dict() == second.to_dict()
    assert first.stage_number == "7.8"
    assert first.latest_commit
    assert first.stage8_handoff_path == "docs/roadmap/STAGE8_HANDOFF.md"


def test_optional_runtime_gaps_do_not_downgrade_clean_closure_score() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    assert result.go_no_go == "GO"
    assert result.readiness_score == 100
    assert result.accepted is True
    assert result.stage_closed is True
    assert result.blockers == ()
    assert any("optional runtime artifact" in warning for warning in result.warnings)


def test_checked_at_is_required() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at="")

    assert isinstance(result, Stage7ClosureError)
    assert result.error_code == "INVALID_STAGE7_CLOSURE_INPUT"
    assert any("checked_at" in blocker for blocker in result.blockers)


def test_url_and_sensitive_inputs_are_rejected(tmp_path: Path) -> None:
    url_result = run_stage7_final_closure_gate(repo_root="https://example.invalid/repo", checked_at=_NOW)
    sensitive_result = run_stage7_final_closure_gate(
        repo_root=tmp_path,
        checked_at=_NOW,
        output_path="reports/API_KEY/value.json",
    )

    assert isinstance(url_result, Stage7ClosureError)
    assert isinstance(sensitive_result, Stage7ClosureError)


def test_missing_required_artifacts_block_but_optional_runtime_warns(tmp_path: Path) -> None:
    (tmp_path / "docs" / "roadmap").mkdir(parents=True)
    result = run_stage7_final_closure_gate(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    assert result.go_no_go == "BLOCKED"
    assert result.blockers
    assert any("required Stage" in blocker for blocker in result.blockers)
    assert any("optional runtime artifact" in warning for warning in result.warnings)


def test_forbidden_behavior_still_blocks(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "docs" / "roadmap").mkdir(parents=True)
    (tmp_path / "docs" / "roadmap" / "STAGE8_HANDOFF.md").write_text("handoff", encoding="utf-8")
    (tmp_path / "bad.py").write_text("fetch('/x')\n", encoding="utf-8")
    monkeypatch.setattr(stage7_closure_gate, "_REQUIRED_ARTIFACTS", ())
    monkeypatch.setattr(stage7_closure_gate, "_OPTIONAL_ARTIFACTS", ())
    monkeypatch.setattr(stage7_closure_gate, "_SAFETY_SCAN_FILES", ("bad.py",))

    result = run_stage7_final_closure_gate(repo_root=tmp_path, checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    assert result.go_no_go == "BLOCKED"
    assert result.readiness_score <= 69
    assert any("forbidden marker" in blocker for blocker in result.blockers)


def test_no_implicit_output_write_and_explicit_output_write() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    assert result.report_path is None
    assert not Path("stage7_final_closure_report.json").exists()

    output_path = Path("scos/work/stage7_closure_tests/closure.json")
    written = run_stage7_final_closure_gate(
        repo_root=Path("."),
        checked_at=_NOW,
        output_path=output_path,
    )

    assert isinstance(written, Stage7ClosureResult)
    assert written.report_path == str(output_path.resolve())
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["gate_id"] == written.gate_id
    assert payload["report_path"] is None


def test_external_checks_do_not_execute_inside_gate() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    all_checks = result.test_results + result.frontend_check_results + result.security_results
    assert all_checks
    for check in all_checks:
        metadata = dict(check.metadata)
        if check.check_name.startswith("run_"):
            assert metadata.get("executed_by_gate") == "false"


def test_stage7_required_artifacts_and_safety_guards_are_represented() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    stages = {artifact.stage for artifact in result.required_artifacts}
    assert {"7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8"}.issubset(stages)
    assert any("real adapter activation" in item for item in result.deferred_items)
    assert any("real AI dispatch" in item for item in result.forbidden_items_rejected)
    assert any(check.check_name == "verify_no_forbidden_stage7_behavior" for check in result.safety_results)


def test_run_flags_false_create_skipped_external_checks() -> None:
    result = run_stage7_final_closure_gate(
        repo_root=Path("."),
        checked_at=_NOW,
        run_control_center_tests=False,
        run_smoke=False,
        run_security_scan=False,
        run_release_script=False,
        run_frontend_checks=False,
    )

    assert isinstance(result, Stage7ClosureResult)
    skipped = [check for check in result.test_results + result.security_results if check.status == "skipped"]
    assert skipped


def test_stage_closed_only_when_go_and_accepted() -> None:
    result = run_stage7_final_closure_gate(repo_root=Path("."), checked_at=_NOW)

    assert isinstance(result, Stage7ClosureResult)
    assert result.stage_closed is (result.go_no_go == "GO" and result.accepted)
