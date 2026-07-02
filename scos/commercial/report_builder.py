"""SCOS Stage 4.1 commercial report builder.

The builder consumes only the Stage 3.9 KnowledgeService boundary. It creates a
commercial-owned immutable report from public view data and returns deterministic
error objects for expected failure states.
"""

from __future__ import annotations

from typing import Any, Callable

from knowledge_service import KnowledgeService
try:
    from .report_models import (
        COMMERCIAL_REPORT_SCHEMA_VERSION,
        CommercialReport,
        CommercialReportError,
        FrozenMap,
        ReportEvidence,
        ReportRisk,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import (
        COMMERCIAL_REPORT_SCHEMA_VERSION,
        CommercialReport,
        CommercialReportError,
        FrozenMap,
        ReportEvidence,
        ReportRisk,
    )


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _view_dict(view: Any) -> dict[str, Any]:
    to_dict = getattr(view, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        if isinstance(data, dict):
            return data
    return {}


def _evidence_from_run_view(view_data: dict[str, Any]) -> tuple[ReportEvidence, ...]:
    confidence = view_data.get("confidence") or {}
    provenance = view_data.get("provenance") or {}
    run_insight = view_data.get("run_insight") or {}
    references = tuple(view_data.get("references") or ())

    evidence = (
        ReportEvidence(
            evidence_id="run_id",
            evidence_type="identifier",
            source="KnowledgeService.run_view",
            value=_string(view_data.get("run_id")),
        ),
        ReportEvidence(
            evidence_id="style_id",
            evidence_type="identifier",
            source="KnowledgeService.run_view.provenance",
            value=provenance.get("style_id"),
        ),
        ReportEvidence(
            evidence_id="decision",
            evidence_type="status",
            source="KnowledgeService.run_view.provenance",
            value=provenance.get("decision"),
        ),
        ReportEvidence(
            evidence_id="confidence",
            evidence_type="coverage",
            source="KnowledgeService.run_view.confidence",
            value={
                "level": confidence.get("level"),
                "present": confidence.get("present"),
                "expected": confidence.get("expected"),
                "missing": tuple(confidence.get("missing") or ()),
            },
        ),
        ReportEvidence(
            evidence_id="references",
            evidence_type="reference_set",
            source="KnowledgeService.run_view.references",
            value=references,
        ),
        ReportEvidence(
            evidence_id="summary",
            evidence_type="summary",
            source="KnowledgeService.run_view.run_insight",
            value=_string(run_insight.get("summary")),
        ),
    )
    return tuple(sorted(evidence, key=lambda item: item.evidence_id))


def _risks_from_public_state(
    view_data: dict[str, Any],
    explicit_risks: tuple[ReportRisk, ...],
) -> tuple[ReportRisk, ...]:
    risks = list(explicit_risks)
    confidence = view_data.get("confidence") or {}
    missing = tuple(confidence.get("missing") or ())
    if missing:
        risks.append(
            ReportRisk(
                risk_id="missing_evidence",
                risk_type="missing_evidence",
                source="KnowledgeService.run_view.confidence",
                detail="missing: " + ",".join(str(item) for item in missing),
            )
        )
    return tuple(sorted(risks, key=lambda item: (item.risk_id, item.source, item.detail)))


def _explicit_risks(items: tuple[dict[str, Any], ...] | None) -> tuple[ReportRisk, ...]:
    if not items:
        return ()
    risks = []
    for index, item in enumerate(items):
        risks.append(
            ReportRisk(
                risk_id=_string(item.get("risk_id") or f"explicit_{index}"),
                risk_type=_string(item.get("risk_type") or "explicit"),
                source=_string(item.get("source") or "explicit_report_input"),
                detail=_string(item.get("detail")),
            )
        )
    return tuple(sorted(risks, key=lambda item: (item.risk_id, item.source, item.detail)))


def build_commercial_report(
    knowledge_service: KnowledgeService,
    run_id: str,
    *,
    now_fn: Callable[[], str],
    report_type: str = "run_summary",
    qa_status: str = "unknown",
    risks: tuple[dict[str, Any], ...] | None = None,
) -> CommercialReport | CommercialReportError:
    """Build a deterministic commercial report for one run.

    Expected not-found and unavailable states return CommercialReportError. The
    only service call is KnowledgeService.run_view(run_id).
    """

    if not isinstance(run_id, str) or not run_id:
        return CommercialReportError.of(
            "CommercialReportUnavailable",
            "run",
            "run_id is required",
            {"schema_version": COMMERCIAL_REPORT_SCHEMA_VERSION},
        )

    try:
        view = knowledge_service.run_view(run_id)
    except Exception as exc:  # noqa: BLE001 - deterministic boundary, no raw exception leakage
        return CommercialReportError.of(
            "CommercialReportUnavailable",
            run_id,
            "knowledge service call failed",
            {
                "schema_version": COMMERCIAL_REPORT_SCHEMA_VERSION,
                "exception_type": type(exc).__name__,
            },
        )

    view_data = _view_dict(view)
    if "error" in view_data:
        return CommercialReportError.of(
            "CommercialReportUnavailable",
            run_id,
            _string(view_data.get("error")),
            {
                "schema_version": COMMERCIAL_REPORT_SCHEMA_VERSION,
                "source_error": view_data,
            },
        )

    if view_data.get("subject_type") != "run":
        return CommercialReportError.of(
            "CommercialReportUnavailable",
            run_id,
            "KnowledgeService.run_view did not return a run view",
            {"schema_version": COMMERCIAL_REPORT_SCHEMA_VERSION},
        )

    provenance = view_data.get("provenance") or {}
    run_insight = view_data.get("run_insight") or {}
    explicit = _explicit_risks(risks)

    return CommercialReport(
        report_id=f"commercial:{report_type}:{run_id}",
        schema_version=COMMERCIAL_REPORT_SCHEMA_VERSION,
        report_type=str(report_type),
        created_at=str(now_fn()),
        source_run_id=run_id,
        style_id=provenance.get("style_id"),
        qa_status=str(qa_status),
        summary=_string(run_insight.get("summary")),
        evidence=_evidence_from_run_view(view_data),
        recommendations=(),
        risks=_risks_from_public_state(view_data, explicit),
        metadata=FrozenMap.from_mapping(
            {
                "builder": "scos.commercial.report_builder",
                "knowledge_boundary": "KnowledgeService.run_view",
                "source_view_id": view_data.get("view_id"),
                "source_schema_version": view_data.get("schema_version"),
            }
        ),
    )
