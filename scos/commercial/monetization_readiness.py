"""SCOS Stage 4.7 monetization readiness review.

Determines whether SCOS is ready to start selling / accepting a real first
customer. This is a *review* layer only: it inspects artifacts that already
exist on the local filesystem — an accepted Stage 4.5 acceptance report and a
Stage 4.6 first customer operating kit — scores seven readiness categories,
lists concrete gaps, and emits a deterministic GO / CONDITIONAL_GO / NO_GO
decision. It never rebuilds reports, never rebuilds packages, never re-runs any
Stage 4 flow, never calls the Stage 3 knowledge layer, and never mutates or
deletes any inspected artifact.

Determinism: ``checked_at`` is an explicit injected string (no real clock, no
random, no UUID). ``readiness_id`` derives from the acceptance report id. The
single optional output file is written UTF-8 with LF newlines using
``json.dumps(..., sort_keys=True, indent=2)``.

Scoring is explainable: each of the seven readiness categories owns exactly one
scoring check worth 10 points (total ``max_score`` 70). Every awarded point is
traceable to a named check and, where relevant, to a gap. Points are never
assigned silently — a category that is not satisfied scores below its maximum
and records why in the check metadata and/or a gap. A default Stage 4.6 kit
without a risk checklist legitimately produces ``ready=False`` / ``NO_GO`` via a
blocking risk gap; that is expected behavior, not an error.

Acceptance-report shape adaptation: the real Stage 4.5 report records ``ok`` /
``overall_status`` / ``created_at`` / ``checks``. This review requires ``ok`` and
``checks`` and derives ``accepted`` = explicit ``accepted`` when present else
(``ok`` is True and ``overall_status`` == "PASS"); it derives the acceptance
timestamp from ``checked_at`` when present else ``created_at``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .monetization_models import (
        MONETIZATION_READINESS_SCHEMA_VERSION,
        MonetizationGap,
        MonetizationReadinessCheck,
        MonetizationReadinessError,
        MonetizationReadinessResult,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from monetization_models import (
        MONETIZATION_READINESS_SCHEMA_VERSION,
        MonetizationGap,
        MonetizationReadinessCheck,
        MonetizationReadinessError,
        MonetizationReadinessResult,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")

_KIT_MANIFEST_FILENAME = "customer_kit_manifest.json"
_READINESS_REPORT_FILENAME = "monetization_readiness_report.json"

_CATEGORY_MAX = 10
_TOTAL_MAX = 70  # 7 categories x 10

# Kit-relative artifact file names (Stage 4.6 operating kit).
_OFFER_PRICING_FILE = "pricing_offer_checklist.md"
_SOP_FILE = "operator_sop.md"
_INTAKE_FILE = "customer_intake_checklist.md"
_HANDOFF_FILE = "delivery_handoff.md"
_FILES_TO_SEND_FILE = "files_to_send.md"
_RISK_FILE_CANDIDATES = ("risk_checklist.md", "risks.md")

# GO thresholds.
_GO_MIN_SCORE = 60
_CONDITIONAL_MIN_SCORE = 50


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _existing_file(value: Any) -> bool:
    if value is None or _is_url(value):
        return False
    path = Path(str(value))
    return path.exists() and path.is_file()


def _existing_dir(value: Any) -> bool:
    if value is None or _is_url(value):
        return False
    path = Path(str(value))
    return path.exists() and path.is_dir()


def review_monetization_readiness(
    *,
    acceptance_report_path: str | Path,
    operating_kit_path: str | Path,
    checked_at: str,
    output_path: str | Path | None = None,
    require_pricing: bool = True,
    require_offer: bool = True,
    require_delivery_artifacts: bool = True,
    require_handoff_script: bool = True,
    require_risk_checklist: bool = True,
) -> MonetizationReadinessResult | MonetizationReadinessError:
    """Review monetization readiness from an accepted acceptance report + kit.

    Returns a deterministic ``MonetizationReadinessResult`` on a completed
    review (which may still be ``ready=False`` / ``NO_GO``), or a
    ``MonetizationReadinessError`` when the review cannot run. Writes exactly one
    ``monetization_readiness_report.json`` only when ``output_path`` is provided
    and validation completes.
    """

    checks: list[MonetizationReadinessCheck] = []
    gaps: list[MonetizationGap] = []

    # --- check 1: validate_inputs (non-scoring) ----------------------------- #
    if not isinstance(checked_at, str) or not checked_at:
        return MonetizationReadinessError.of(
            "INVALID_ARGUMENTS", "checked_at is required", "validate_inputs"
        )
    if acceptance_report_path is None or str(acceptance_report_path) == "":
        return MonetizationReadinessError.of(
            "INVALID_ARGUMENTS", "acceptance_report_path is required", "validate_inputs"
        )
    if operating_kit_path is None or str(operating_kit_path) == "":
        return MonetizationReadinessError.of(
            "INVALID_ARGUMENTS", "operating_kit_path is required", "validate_inputs"
        )
    for label, value in (
        ("acceptance_report_path", acceptance_report_path),
        ("operating_kit_path", operating_kit_path),
        ("output_path", output_path),
    ):
        if value is not None and _is_url(value):
            return MonetizationReadinessError.of(
                "PATH_CONTAINMENT_FAILED",
                "paths must be local filesystem paths, not URLs",
                "validate_inputs",
                metadata={"argument": label, "path": str(value)},
            )

    report_source = Path(str(acceptance_report_path))
    if not report_source.exists() or not report_source.is_file():
        return MonetizationReadinessError.of(
            "INPUT_NOT_FOUND",
            "acceptance_report_path does not exist or is not a file",
            "validate_inputs",
            metadata={"path": str(report_source)},
        )
    kit_source = Path(str(operating_kit_path))
    if not kit_source.exists():
        return MonetizationReadinessError.of(
            "INPUT_NOT_FOUND",
            "operating_kit_path does not exist",
            "validate_inputs",
            metadata={"path": str(kit_source)},
        )
    checks.append(
        MonetizationReadinessCheck.of(
            "validate_inputs", "inputs", "success", "info", 0, 0,
            metadata={
                "acceptance_report_path": str(report_source),
                "operating_kit_path": str(kit_source),
            },
        )
    )

    # --- check 2: load_acceptance_report (non-scoring) ---------------------- #
    try:
        acceptance = json.loads(report_source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MonetizationReadinessError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report is not valid JSON",
            "load_acceptance_report",
            tuple(checks),
            metadata={"path": str(report_source)},
        )
    if not isinstance(acceptance, dict):
        return MonetizationReadinessError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report must be a JSON object",
            "load_acceptance_report",
            tuple(checks),
            metadata={"path": str(report_source)},
        )
    if "accepted" not in acceptance and "ok" not in acceptance:
        return MonetizationReadinessError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report is missing required acceptance status (accepted or ok)",
            "load_acceptance_report",
            tuple(checks),
            metadata={"path": str(report_source)},
        )
    if "checks" not in acceptance:
        return MonetizationReadinessError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report is missing required checks",
            "load_acceptance_report",
            tuple(checks),
            metadata={"path": str(report_source)},
        )
    acc_checks = acceptance.get("checks")
    if not isinstance(acc_checks, list):
        return MonetizationReadinessError.of(
            "INVALID_ACCEPTANCE_REPORT",
            "acceptance report checks must be a list",
            "load_acceptance_report",
            tuple(checks),
            metadata={"path": str(report_source)},
        )

    overall_status = str(acceptance.get("overall_status", ""))
    if "accepted" in acceptance:
        accepted = acceptance.get("accepted") is True
    else:
        accepted = acceptance.get("ok") is True and overall_status == "PASS"
    acceptance_checked_at = str(acceptance.get("checked_at") or acceptance.get("created_at") or "")
    acceptance_id = str(acceptance.get("certification_id") or acceptance.get("acceptance_id") or "unknown")
    failed_acc_checks = sorted(
        str(c.get("check_name"))
        for c in acc_checks
        if isinstance(c, dict) and str(c.get("status")) in ("FAIL", "BLOCKED")
    )
    checks.append(
        MonetizationReadinessCheck.of(
            "load_acceptance_report", "inputs", "success", "info", 0, 0,
            artifact_path=str(report_source),
            metadata={
                "accepted": bool(accepted),
                "acceptance_checked_at": acceptance_checked_at,
                "overall_status": overall_status,
                "failed_acceptance_checks": failed_acc_checks,
            },
        )
    )

    # --- check 3: inspect_operating_kit (non-scoring) ----------------------- #
    manifest_data: dict[str, Any] = {}
    if kit_source.is_dir():
        kit_dir = kit_source
        manifest_path = kit_dir / _KIT_MANIFEST_FILENAME
        if manifest_path.is_file():
            try:
                loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return MonetizationReadinessError.of(
                    "INVALID_OPERATING_KIT",
                    "kit manifest is not valid JSON",
                    "inspect_operating_kit",
                    tuple(checks),
                    metadata={"path": str(manifest_path)},
                )
            if isinstance(loaded, dict):
                manifest_data = loaded
    else:
        # A manifest (JSON) file was supplied directly.
        try:
            loaded = json.loads(kit_source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return MonetizationReadinessError.of(
                "INVALID_OPERATING_KIT",
                "operating kit manifest is not valid JSON",
                "inspect_operating_kit",
                tuple(checks),
                metadata={"path": str(kit_source)},
            )
        if not isinstance(loaded, dict):
            return MonetizationReadinessError.of(
                "INVALID_OPERATING_KIT",
                "operating kit manifest must be a JSON object",
                "inspect_operating_kit",
                tuple(checks),
                metadata={"path": str(kit_source)},
            )
        manifest_data = loaded
        manifest_output_dir = manifest_data.get("output_dir")
        if isinstance(manifest_output_dir, str) and _existing_dir(manifest_output_dir):
            kit_dir = Path(manifest_output_dir)
        else:
            kit_dir = kit_source.parent

    generated_files = manifest_data.get("generated_files")
    generated_files = [str(f) for f in generated_files] if isinstance(generated_files, list) else []
    manifest_files = manifest_data.get("files")
    manifest_files = manifest_files if isinstance(manifest_files, list) else []

    def _manifest_referenced_paths(name: str) -> list[Path]:
        paths: list[Path] = []
        for entry in generated_files:
            entry_path = Path(entry)
            if entry == name or entry_path.name == name:
                paths.append(entry_path if entry_path.is_absolute() else kit_dir / entry_path)
        for entry in manifest_files:
            if isinstance(entry, dict):
                file_name = str(entry.get("file_name") or "")
                file_path = str(entry.get("file_path") or "")
                if file_name == name or (file_path and Path(file_path).name == name):
                    path = Path(file_path) if file_path else Path(file_name)
                    paths.append(path if path.is_absolute() else kit_dir / path)
            elif isinstance(entry, str):
                entry_path = Path(entry)
                if entry == name or entry_path.name == name:
                    paths.append(entry_path if entry_path.is_absolute() else kit_dir / entry_path)
        return paths

    def _kit_has(name: str) -> bool:
        """Artifact present if it exists in the kit dir or via manifest reference."""

        if (kit_dir / name).is_file():
            return True
        for path in _manifest_referenced_paths(name):
            if path.is_file():
                return True
        return False

    checks.append(
        MonetizationReadinessCheck.of(
            "inspect_operating_kit", "inputs", "success", "info", 0, 0,
            artifact_path=str(kit_dir),
            metadata={
                "has_manifest": bool(manifest_data),
                "generated_files": sorted(generated_files),
                "manifest_file_count": len(manifest_files),
            },
        )
    )

    # ---------------------------------------------------------------------- #
    # Scoring helpers
    # ---------------------------------------------------------------------- #
    def _scoring_check(
        name: str,
        category: str,
        satisfied: bool,
        required: bool,
        *,
        score: int,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if satisfied:
            status, severity = "success", "info"
        elif not required:
            status, severity = "skipped", "info"
        else:
            status, severity = "failure", ("critical" if category == "acceptance_readiness" else "error")
        checks.append(
            MonetizationReadinessCheck.of(
                name, category, status, severity, score, _CATEGORY_MAX,
                artifact_path=artifact_path,
                error_kind=None if satisfied or not required else error_kind,
                error_detail=None if satisfied else (error_detail if required else "not required"),
                metadata=metadata,
            )
        )

    def _gap(
        gap_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        action: str,
        blocking: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        gaps.append(
            MonetizationGap.of(
                gap_id, category, severity, title, detail, action, blocking,
                metadata=metadata,
            )
        )

    # --- check 4: offer_readiness ------------------------------------------ #
    offer_present = _kit_has(_OFFER_PRICING_FILE)
    _scoring_check(
        "check_offer_readiness", "offer_readiness", offer_present, require_offer,
        score=_CATEGORY_MAX if offer_present else 0,
        artifact_path=str(kit_dir / _OFFER_PRICING_FILE),
        error_kind="MISSING_OFFER",
        error_detail=f"offer artifact '{_OFFER_PRICING_FILE}' not found in operating kit",
        metadata={"artifact": _OFFER_PRICING_FILE, "required": bool(require_offer)},
    )
    if not offer_present and require_offer:
        _gap(
            "GAP_MISSING_OFFER", "offer_readiness", "error",
            "Offer artifact missing",
            f"No explicit offer artifact ('{_OFFER_PRICING_FILE}') found in the operating kit.",
            "Add an explicit offer definition to the operating kit before selling.",
            True,
            {"artifact": _OFFER_PRICING_FILE},
        )

    # --- check 5: pricing_readiness ---------------------------------------- #
    pricing_present = _kit_has(_OFFER_PRICING_FILE)
    _scoring_check(
        "check_pricing_readiness", "pricing_readiness", pricing_present, require_pricing,
        score=_CATEGORY_MAX if pricing_present else 0,
        artifact_path=str(kit_dir / _OFFER_PRICING_FILE),
        error_kind="MISSING_PRICING",
        error_detail=f"pricing artifact '{_OFFER_PRICING_FILE}' not found in operating kit",
        metadata={"artifact": _OFFER_PRICING_FILE, "required": bool(require_pricing)},
    )
    if not pricing_present and require_pricing:
        _gap(
            "GAP_MISSING_PRICING", "pricing_readiness", "error",
            "Pricing artifact missing",
            f"No explicit pricing artifact ('{_OFFER_PRICING_FILE}') found in the operating kit.",
            "Add explicit pricing terms to the operating kit before selling.",
            True,
            {"artifact": _OFFER_PRICING_FILE},
        )

    # --- check 6: workflow_readiness (always required) --------------------- #
    sop_present = _kit_has(_SOP_FILE)
    intake_present = _kit_has(_INTAKE_FILE)
    workflow_present = sop_present and intake_present
    workflow_score = 0
    if sop_present:
        workflow_score += 5
    if intake_present:
        workflow_score += 5
    _scoring_check(
        "check_workflow_readiness", "workflow_readiness", workflow_present, True,
        score=workflow_score,
        artifact_path=str(kit_dir),
        error_kind="MISSING_WORKFLOW",
        error_detail="first-customer workflow artifacts are incomplete",
        metadata={
            "operator_sop": bool(sop_present),
            "customer_intake_checklist": bool(intake_present),
            "sop_file": _SOP_FILE,
            "intake_file": _INTAKE_FILE,
        },
    )
    if not workflow_present:
        missing = sorted(
            n for n, present in ((_SOP_FILE, sop_present), (_INTAKE_FILE, intake_present)) if not present
        )
        _gap(
            "GAP_MISSING_WORKFLOW", "workflow_readiness", "error",
            "First-customer workflow incomplete",
            "Missing operator/intake workflow artifacts: " + ", ".join(missing),
            "Ensure the operating kit includes the operator SOP and customer intake checklist.",
            True,
            {"missing": missing},
        )

    # --- check 7: delivery_readiness --------------------------------------- #
    source_report_path = str(manifest_data.get("source_report_path") or "")
    source_package_path = str(manifest_data.get("source_package_path") or "")
    delivery_items = {
        "commercial_report": (3, _existing_file(source_report_path)),
        "delivery_package": (3, _existing_dir(source_package_path)),
        "acceptance_report": (2, _existing_file(report_source)),
        "handoff_material": (2, _kit_has(_HANDOFF_FILE) or _kit_has(_FILES_TO_SEND_FILE)),
    }
    delivery_score = sum(weight for weight, present in delivery_items.values() if present)
    delivery_present = all(present for _, present in delivery_items.values())
    missing_delivery = sorted(name for name, (_, present) in delivery_items.items() if not present)
    _scoring_check(
        "check_delivery_readiness", "delivery_readiness", delivery_present, require_delivery_artifacts,
        score=delivery_score if (delivery_present or not require_delivery_artifacts) else delivery_score,
        artifact_path=str(kit_dir),
        error_kind="MISSING_DELIVERY_ARTIFACT",
        error_detail="delivery artifacts are incomplete: " + ", ".join(missing_delivery),
        metadata={
            "source_report_path": source_report_path,
            "source_package_path": source_package_path,
            "item_weights": {name: weight for name, (weight, _) in delivery_items.items()},
            "present": sorted(name for name, (_, present) in delivery_items.items() if present),
            "missing": missing_delivery,
            "required": bool(require_delivery_artifacts),
        },
    )
    if missing_delivery and require_delivery_artifacts:
        _gap(
            "GAP_MISSING_DELIVERY_ARTIFACT", "delivery_readiness", "error",
            "Delivery artifacts incomplete",
            "Missing referenced delivery artifacts: " + ", ".join(missing_delivery),
            "Ensure the commercial report, delivery package, acceptance report, and handoff material all exist.",
            True,
            {"missing": missing_delivery},
        )

    # --- check 8: acceptance_readiness (always required) ------------------- #
    acceptance_ok = accepted and not failed_acc_checks
    if accepted:
        acceptance_score = max(0, _CATEGORY_MAX - 2 * len(failed_acc_checks))
    else:
        acceptance_score = 0
    _scoring_check(
        "check_acceptance_readiness", "acceptance_readiness", acceptance_ok, True,
        score=acceptance_score,
        artifact_path=str(report_source),
        error_kind="ACCEPTANCE_NOT_READY",
        error_detail="acceptance report is not accepted or has failing checks",
        metadata={
            "accepted": bool(accepted),
            "overall_status": overall_status,
            "failed_acceptance_checks": failed_acc_checks,
        },
    )
    if not accepted:
        _gap(
            "GAP_ACCEPTANCE_NOT_READY", "acceptance_readiness", "critical",
            "Acceptance not passed",
            f"Acceptance report is not an accepted result (overall_status={overall_status!r}).",
            "Re-run the Stage 4.5 acceptance gate until it certifies PASS.",
            True,
            {"overall_status": overall_status},
        )
    elif failed_acc_checks:
        _gap(
            "GAP_ACCEPTANCE_FAILED_CHECKS", "acceptance_readiness", "error",
            "Accepted report has failing checks",
            "Acceptance report is accepted but records failing checks: " + ", ".join(failed_acc_checks),
            "Resolve the failing acceptance checks and re-certify.",
            False,
            {"failed_acceptance_checks": failed_acc_checks},
        )

    # --- check 9: risk_readiness ------------------------------------------- #
    risk_file = next((n for n in _RISK_FILE_CANDIDATES if _kit_has(n)), None)
    risk_present = risk_file is not None
    _scoring_check(
        "check_risk_readiness", "risk_readiness", risk_present, require_risk_checklist,
        score=_CATEGORY_MAX if risk_present else 0,
        artifact_path=str(kit_dir / risk_file) if risk_file else str(kit_dir),
        error_kind="MISSING_RISK_CHECKLIST",
        error_detail="no risk checklist found in operating kit",
        metadata={"candidates": list(_RISK_FILE_CANDIDATES), "required": bool(require_risk_checklist)},
    )
    if not risk_present and require_risk_checklist:
        _gap(
            "GAP_MISSING_RISK_CHECKLIST", "risk_readiness", "error",
            "Risk checklist missing",
            "No explicit risk checklist ("
            + " / ".join(_RISK_FILE_CANDIDATES)
            + ") found in the operating kit.",
            "Add an explicit risk checklist to the operating kit before selling.",
            True,
            {"candidates": list(_RISK_FILE_CANDIDATES)},
        )

    # --- check 10: handoff_readiness --------------------------------------- #
    handoff_present = _kit_has(_HANDOFF_FILE)
    _scoring_check(
        "check_handoff_readiness", "handoff_readiness", handoff_present, require_handoff_script,
        score=_CATEGORY_MAX if handoff_present else 0,
        artifact_path=str(kit_dir / _HANDOFF_FILE),
        error_kind="MISSING_HANDOFF_SCRIPT",
        error_detail=f"handoff artifact '{_HANDOFF_FILE}' not found in operating kit",
        metadata={"artifact": _HANDOFF_FILE, "required": bool(require_handoff_script)},
    )
    if not handoff_present and require_handoff_script:
        _gap(
            "GAP_MISSING_HANDOFF_SCRIPT", "handoff_readiness", "warning",
            "Handoff script missing",
            f"No explicit customer handoff artifact ('{_HANDOFF_FILE}') found in the operating kit.",
            "Add explicit customer handoff instructions to the operating kit.",
            True,
            {"artifact": _HANDOFF_FILE},
        )

    # --- check 11: compute_readiness_score --------------------------------- #
    score = sum(chk.score for chk in checks)
    max_score = sum(chk.max_score for chk in checks)
    checks.append(
        MonetizationReadinessCheck.of(
            "compute_readiness_score", "scoring", "success", "info", 0, 0,
            metadata={"score": score, "max_score": max_score, "category_max": _CATEGORY_MAX},
        )
    )

    # --- check 12: determine_go_no_go -------------------------------------- #
    blocking_gaps = [g for g in gaps if g.blocking]
    acceptance_blocking = any(
        g.blocking and g.category == "acceptance_readiness" for g in gaps
    )
    # A single blocking gap (e.g. a missing required risk checklist) forces
    # NO_GO regardless of score: a default Stage 4.6 kit without a risk
    # checklist legitimately lands here. CONDITIONAL_GO is reserved for a run
    # with no blocking gaps that merely falls short of the GO score (50-59) or
    # carries non-blocking gaps.
    if not blocking_gaps and score >= _GO_MIN_SCORE and accepted:
        go_no_go = "GO"
        readiness_level = "ready"
        ready = True
    elif not blocking_gaps and not acceptance_blocking and accepted and score >= _CONDITIONAL_MIN_SCORE:
        go_no_go = "CONDITIONAL_GO"
        readiness_level = "conditional"
        ready = False
    else:
        go_no_go = "NO_GO"
        readiness_level = "not_ready"
        ready = False
    checks.append(
        MonetizationReadinessCheck.of(
            "determine_go_no_go", "decision", "success", "info", 0, 0,
            metadata={
                "go_no_go": go_no_go,
                "readiness_level": readiness_level,
                "blocking_gap_ids": sorted(g.gap_id for g in blocking_gaps),
                "acceptance_blocking": bool(acceptance_blocking),
            },
        )
    )

    readiness_id = f"monetization-readiness-{acceptance_id}"
    result = MonetizationReadinessResult(
        ok=True,
        schema_version=MONETIZATION_READINESS_SCHEMA_VERSION,
        ready=ready,
        readiness_id=readiness_id,
        checked_at=checked_at,
        score=score,
        max_score=max_score,
        readiness_level=readiness_level,
        go_no_go=go_no_go,
        acceptance_report_path=str(report_source),
        operating_kit_path=str(kit_source),
        checks=tuple(checks),
        gaps=tuple(gaps),
        metadata=FrozenMap.from_mapping(
            {
                "reviewer": "scos.commercial.monetization_readiness",
                "acceptance_id": acceptance_id,
            "accepted": bool(accepted),
            "acceptance_checked_at": acceptance_checked_at,
            "require_offer": bool(require_offer),
                "require_pricing": bool(require_pricing),
                "require_delivery_artifacts": bool(require_delivery_artifacts),
                "require_handoff_script": bool(require_handoff_script),
                "require_risk_checklist": bool(require_risk_checklist),
                "blocking_gap_count": len(blocking_gaps),
                "gap_count": len(gaps),
            }
        ),
    )

    # --- optional output ---------------------------------------------------- #
    if output_path is not None and str(output_path) != "":
        target = Path(str(output_path))
        try:
            if target.parent and not target.parent.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
        except OSError as exc:
            return MonetizationReadinessError.of(
                "OUTPUT_WRITE_FAILED",
                "monetization readiness report could not be written",
                "write_output",
                tuple(checks),
                tuple(gaps),
                {"output_path": str(target), "os_error": type(exc).__name__},
            )

    return result


__all__ = ("review_monetization_readiness",)
