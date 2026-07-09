"""Stage 7.8 closure model tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from scos.control_center.stage7_closure_models import (
    Stage7ClosureArtifact,
    Stage7ClosureCheck,
    Stage7ClosureError,
    Stage7ClosureResult,
)


def _artifact(path: str = "docs/example.md") -> Stage7ClosureArtifact:
    return Stage7ClosureArtifact(
        artifact_id="artifact-1",
        stage="7.8",
        artifact_type="contract",
        path=path,
        required=True,
        exists=True,
        readable=True,
        digest="abc",
    )


def _check(name: str = "check") -> Stage7ClosureCheck:
    return Stage7ClosureCheck(
        check_id=f"check-{name}",
        check_name=name,
        category="artifact",
        status="pass",
        summary="ok",
        required=True,
        references=("b", "a"),
        metadata=(("z", "2"), ("a", "1")),
    )


def test_closure_check_is_immutable_and_deterministic() -> None:
    check = _check()

    with pytest.raises(FrozenInstanceError):
        check.status = "warning"  # type: ignore[misc]

    assert check.references == ("a", "b")
    assert check.metadata == (("a", "1"), ("z", "2"))
    assert check.to_dict() == {
        "check_id": "check-check",
        "check_name": "check",
        "category": "artifact",
        "status": "pass",
        "summary": "ok",
        "required": True,
        "references": ["a", "b"],
        "metadata": [["a", "1"], ["z", "2"]],
    }


def test_result_enforces_score_contracts() -> None:
    with pytest.raises(ValueError, match="GO requires readiness_score=100"):
        Stage7ClosureResult(
            gate_id="gate",
            gate_name="Gate",
            checked_at="2026-07-10T00:00:00Z",
            go_no_go="GO",
            readiness_score=99,
            accepted=True,
            stage_closed=True,
            stage_number="7.8",
            latest_commit="abc",
            required_artifacts=(_artifact(),),
            optional_artifacts=(),
            stage_results=(_check(),),
            compatibility_results=(),
            safety_results=(),
            test_results=(),
            frontend_check_results=(),
            security_results=(),
            blockers=(),
            warnings=(),
            inspected_artifacts=(_artifact(),),
            deferred_items=(),
            forbidden_items_rejected=(),
            stage8_handoff_path="docs/roadmap/STAGE8_HANDOFF.md",
            report_path=None,
        )


def test_result_to_dict_is_stable_and_stage_closed_requires_go() -> None:
    artifact = _artifact()
    result = Stage7ClosureResult(
        gate_id="gate",
        gate_name="Gate",
        checked_at="2026-07-10T00:00:00Z",
        go_no_go="NO_GO",
        readiness_score=95,
        accepted=False,
        stage_closed=False,
        stage_number="7.8",
        latest_commit="abc",
        required_artifacts=(artifact,),
        optional_artifacts=(),
        stage_results=(_check("stage"),),
        compatibility_results=(_check("compat"),),
        safety_results=(_check("safe"),),
        test_results=(_check("test"),),
        frontend_check_results=(_check("frontend"),),
        security_results=(_check("security"),),
        blockers=(),
        warnings=("warning",),
        inspected_artifacts=(artifact,),
        deferred_items=("b", "a"),
        forbidden_items_rejected=("z", "a"),
        stage8_handoff_path="docs/roadmap/STAGE8_HANDOFF.md",
        report_path=None,
    )

    payload = result.to_dict()
    assert payload["go_no_go"] == "NO_GO"
    assert payload["stage_closed"] is False
    assert payload["deferred_items"] == ["a", "b"]
    assert payload["forbidden_items_rejected"] == ["a", "z"]


def test_error_to_dict_sorts_blockers() -> None:
    error = Stage7ClosureError.of(
        "INVALID",
        "bad input",
        checked_at="2026-07-10T00:00:00Z",
        blockers=("z", "a"),
    )

    assert error.to_dict() == {
        "error_code": "INVALID",
        "message": "bad input",
        "checked_at": "2026-07-10T00:00:00Z",
        "blockers": ["a", "z"],
    }


def test_invalid_check_status_is_rejected() -> None:
    with pytest.raises(ValueError):
        Stage7ClosureCheck(
            check_id="bad",
            check_name="bad",
            category="artifact",
            status="unknown",
            summary="bad",
            required=True,
            references=(),
            metadata=(),
        )
