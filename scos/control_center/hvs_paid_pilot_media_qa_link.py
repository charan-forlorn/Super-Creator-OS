"""SCOS Cohort 10H — media-QA linkage (reuse Cohort 10G QA engine).

This module is a NARROW bridge. It does not implement a second QA engine. It
imports and invokes the certified ``hvs_golden_render_service.run_media_qa``
and maps its result into the paid-pilot delivery gate vocabulary.

Single source of truth for QA:
  * ``scos.control_center.hvs_golden_render_service.run_media_qa``
  * ``scos.control_center.hvs_golden_render_models`` (state vocabulary)

Stdlib-only. Deterministic. No clock/random/uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from scos.control_center.hvs_golden_render_models import (  # noqa: E402
    QA_NOT_RUN,
    QA_PASSED,
    QA_FAILED_CONFIRMED,
)
from scos.control_center.hvs_paid_pilot_delivery_models import (  # noqa: E402
    DELIVERY_BLOCKED_QA_FAILED,
    DELIVERY_BLOCKED_QA_REQUIRED,
    QA_NOT_RUN as PP_QA_NOT_RUN,
)

# QA states reused from Cohort 10G vocabulary (aliased here for clarity).
QA_PASSED_STATE = QA_PASSED
QA_FAILED_STATE = QA_FAILED_CONFIRMED
QA_NOT_RUN_STATE = QA_NOT_RUN


@dataclass(frozen=True)
class QaLinkResult:
    ok: bool
    qa_report_id: Optional[str]
    qa_state: str
    artifact_id: Optional[str]
    artifact_sha256: Optional[str]
    failure_codes: tuple[str, ...]
    delivery_gate_state: str
    error_code: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "qa_report_id": self.qa_report_id,
            "qa_state": self.qa_state,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "failure_codes": list(self.failure_codes),
            "delivery_gate_state": self.delivery_gate_state,
            "error_code": self.error_code,
            "detail": self.detail,
        }


def link_qa_state(*, qa_state: str) -> str:
    """Map a QA state to the delivery gate state (fail closed)."""
    if qa_state == QA_PASSED_STATE:
        # QA passed alone is not enough; rights must also be approved upstream.
        return "QA_PASSED_GATE_OPEN"
    if qa_state == QA_FAILED_STATE:
        return DELIVERY_BLOCKED_QA_FAILED
    if qa_state in (QA_NOT_RUN_STATE, "", None):
        return DELIVERY_BLOCKED_QA_REQUIRED
    # Unknown QA state: never coerce to success.
    return DELIVERY_BLOCKED_QA_REQUIRED


def run_qa_link(
    *,
    project_id: str,
    hvs_project_id: str,
    attempt_id: str,
    profile_id: str,
    artifact_path: str,
    recorded_at: str,
    tool_versions: dict[str, str],
    ffprobe_bin: Optional[str] = None,
    ffmpeg_bin: Optional[str] = None,
) -> QaLinkResult:
    """Run the Cohort 10G QA engine and return a paid-pilot delivery gate link.

    Reuses ``run_media_qa`` exclusively; no second QA implementation.
    """
    from scos.control_center.hvs_golden_render_service import run_media_qa

    try:
        report = run_media_qa(
            project_id=project_id,
            hvs_project_id=hvs_project_id,
            attempt_id=attempt_id,
            profile_id=profile_id,
            artifact_path=artifact_path,
            recorded_at=recorded_at,
            tool_versions=tool_versions,
            ffprobe_bin=ffprobe_bin,
            ffmpeg_bin=ffmpeg_bin,
        )
    except Exception as exc:  # defensive: never mask as success
        return QaLinkResult(
            ok=False, qa_report_id=None, qa_state=QA_NOT_RUN_STATE,
            artifact_id=None, artifact_sha256=None, failure_codes=(),
            delivery_gate_state=DELIVERY_BLOCKED_QA_REQUIRED,
            error_code="QA_ENGINE_ERROR", detail=str(exc),
        )

    passed = report.overall_state == QA_PASSED_STATE
    return QaLinkResult(
        ok=passed,
        qa_report_id=report.qa_report_id,
        qa_state=report.overall_state,
        artifact_id=report.artifact_id,
        artifact_sha256=report.artifact_checksum,
        failure_codes=tuple(report.failure_codes),
        delivery_gate_state=link_qa_state(qa_state=report.overall_state),
    )
