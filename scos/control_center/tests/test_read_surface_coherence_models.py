"""Stage 7.2 read surface coherence model tests."""

from __future__ import annotations

import dataclasses

import pytest

from scos.control_center.read_surface_coherence_models import (
    ReadSurfaceCoherenceError,
    ReadSurfaceCoherenceIssue,
    ReadSurfaceCoherenceReport,
    ReadSurfaceContractCheck,
)

_NOW = "2026-07-09T00:00:00Z"


def test_contract_check_to_dict_is_stable_and_immutable() -> None:
    check = ReadSurfaceContractCheck(
        check_id="check-1",
        check_name="exports",
        status="success",
        severity="info",
        summary="exports present",
        source_stage="Stage 7.1",
        references=("b", "a"),
        metadata=(("z", "last"), ("a", "first")),
    )

    assert check.references == ("a", "b")
    assert check.metadata == (("a", "first"), ("z", "last"))
    assert list(check.to_dict()) == [
        "check_id",
        "check_name",
        "status",
        "severity",
        "summary",
        "source_stage",
        "references",
        "metadata",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        check.status = "failure"  # type: ignore[misc]


def test_issue_and_report_sort_deterministically() -> None:
    issue = ReadSurfaceCoherenceIssue(
        issue_id="issue-2",
        issue_type="missing_optional_stage6_artifact",
        severity="warning",
        message="optional missing",
        source_reference="source",
        read_surface_reference="surface",
        blocker=False,
    )
    check = ReadSurfaceContractCheck(
        check_id="check-1",
        check_name="exports",
        status="success",
        severity="info",
        summary="exports present",
        source_stage="Stage 7.1",
        references=(),
        metadata=(),
    )
    report = ReadSurfaceCoherenceReport(
        report_id="report-1",
        checked_at=_NOW,
        accepted=True,
        go_no_go="GO",
        readiness_score=98,
        contract_checks=(check,),
        coherence_issues=(issue,),
        blockers=(),
        warnings=("z", "a"),
    )

    assert report.warnings == ("a", "z")
    assert report.to_dict()["coherence_issues"][0]["issue_id"] == "issue-2"


def test_error_to_dict_is_stable() -> None:
    error = ReadSurfaceCoherenceError.of(
        "INVALID_COHERENCE_INPUT",
        "bad input",
        checked_at=_NOW,
        blockers=("b2", "b1"),
    )

    assert error.blockers == ("b1", "b2")
    assert list(error.to_dict()) == ["error_code", "message", "checked_at", "blockers"]


def test_invalid_status_and_severity_rejected() -> None:
    with pytest.raises(ValueError):
        ReadSurfaceContractCheck(
            check_id="check-1",
            check_name="bad",
            status="bad",
            severity="info",
            summary="bad",
            source_stage="Stage 7.2",
            references=(),
            metadata=(),
        )
    with pytest.raises(ValueError):
        ReadSurfaceCoherenceIssue(
            issue_id="issue-1",
            issue_type="bad",
            severity="info",
            message="bad",
            source_reference="source",
            read_surface_reference="surface",
            blocker=False,
        )
