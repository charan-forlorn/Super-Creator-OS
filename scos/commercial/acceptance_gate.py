"""SCOS Stage 4.5 commercial acceptance gate.

Certifies whether a completed Stage 4.4 commercial run is ready for real
client delivery. This is an evidence-based certification layer only: it
inspects artifacts that already exist on the local filesystem and never
rebuilds reports, never rebuilds packages, never re-runs the commercial flow,
and never touches the Stage 3 knowledge layer. Inspected artifacts are read
but never mutated or deleted.

Determinism: ``created_at`` is an explicit injected string (no real clock, no
random, no UUID). The certification id derives from the run id when not
provided. The single output file is written UTF-8 with LF newlines using
``json.dumps(..., sort_keys=True, indent=2)``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .acceptance_models import (
        COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        AcceptanceCheck,
        CommercialAcceptanceError,
        CommercialAcceptanceReport,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from acceptance_models import (
        COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        AcceptanceCheck,
        CommercialAcceptanceError,
        CommercialAcceptanceReport,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")

_REQUIRED_RUN_FIELDS = ("run_id", "delivery_id", "created_at", "report_path", "package_path")

_REQUIRED_RUN_STEPS = (
    "validate_inputs",
    "build_report",
    "write_report",
    "build_package",
    "write_manifest",
)

_REQUIRED_DELIVERY_FILES = (
    "improvement_plan.md",
    "manifest.json",
    "qa_summary.md",
    "report.json",
    "report.md",
)

_FAIL_PENALTIES = {"CRITICAL": 100, "HIGH": 25, "MEDIUM": 10, "LOW": 3}

_ACCEPTANCE_REPORT_FILENAME = "commercial_acceptance_report.json"


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _fs_safe(name: str) -> str:
    """Deterministic, Windows-safe folder name for a certification id."""

    return name.replace(":", "_")


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _normalize_run_input(
    commercial_run_result: Any,
) -> tuple[dict[str, Any] | None, str | None, CommercialAcceptanceError | None]:
    """Normalize the accepted input forms into a plain run dict.

    Returns ``(run_data, manifest_file, error)``: exactly one of ``run_data``
    or ``error`` is set; ``manifest_file`` is the source file when the input
    was a filesystem path.
    """

    value = commercial_run_result
    if value is None:
        return None, None, CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS", "commercial_run_result is required", "normalize_input"
        )

    if isinstance(value, dict):
        return dict(value), None, None

    if isinstance(value, (str, Path)):
        if _is_url(value):
            return None, None, CommercialAcceptanceError.of(
                "INVALID_ARGUMENTS",
                "commercial_run_result path must be a local filesystem path, not a URL",
                "normalize_input",
                metadata={"path": str(value)},
            )
        source = Path(str(value))
        if not source.exists() or not source.is_file():
            return None, None, CommercialAcceptanceError.of(
                "INPUT_NOT_FOUND",
                "commercial run manifest does not exist or is not a file",
                "normalize_input",
                metadata={"path": str(source)},
            )
        try:
            parsed = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, None, CommercialAcceptanceError.of(
                "INVALID_RUN_RESULT",
                "commercial run manifest is not valid JSON",
                "normalize_input",
                metadata={"path": str(source)},
            )
        if not isinstance(parsed, dict):
            return None, None, CommercialAcceptanceError.of(
                "INVALID_RUN_RESULT",
                "commercial run manifest must be a JSON object",
                "normalize_input",
                metadata={"path": str(source)},
            )
        return parsed, str(source), None

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            data = to_dict()
        except Exception:
            return None, None, CommercialAcceptanceError.of(
                "INVALID_RUN_RESULT", "run result to_dict() failed", "normalize_input"
            )
        if isinstance(data, dict):
            return data, None, None

    return None, None, CommercialAcceptanceError.of(
        "INVALID_RUN_RESULT",
        "commercial_run_result must be a run result object, a dict, or a manifest path",
        "normalize_input",
        metadata={"input_type": type(value).__name__},
    )


def _run_is_successful(run_data: dict[str, Any]) -> bool:
    if "ok" in run_data:
        return run_data.get("ok") is True
    steps = run_data.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    statuses: dict[str, str] = {}
    for step in steps:
        if isinstance(step, dict):
            statuses[str(step.get("step_name"))] = str(step.get("status"))
    return all(statuses.get(name) == "success" for name in _REQUIRED_RUN_STEPS)


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


def run_commercial_acceptance_gate(
    *,
    commercial_run_result: Any,
    output_dir: str | Path,
    created_at: str,
    certification_id: str | None = None,
    min_readiness_score: int = 100,
    require_assets: bool = False,
    require_video: bool = False,
) -> CommercialAcceptanceReport | CommercialAcceptanceError:
    """Evaluate a completed commercial run and write one certification report.

    Expected failure states return a deterministic ``CommercialAcceptanceError``;
    completed evaluations return a ``CommercialAcceptanceReport`` with
    ``overall_status`` PASS / FAIL / BLOCKED and write exactly one file:
    ``<output_dir>/<certification_id>/commercial_acceptance_report.json``.
    """

    # --- argument validation ------------------------------------------------ #
    if not isinstance(created_at, str) or not created_at:
        return CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS", "created_at is required", "validate_arguments"
        )
    if output_dir is None or str(output_dir) == "":
        return CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS", "output_dir is required", "validate_arguments"
        )
    if _is_url(output_dir):
        return CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS",
            "output_dir must be a local filesystem path, not a URL",
            "validate_arguments",
            metadata={"path": str(output_dir)},
        )
    try:
        min_score = int(min_readiness_score)
    except (TypeError, ValueError):
        return CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS", "min_readiness_score must be an integer", "validate_arguments"
        )
    if min_score < 0 or min_score > 100:
        return CommercialAcceptanceError.of(
            "INVALID_ARGUMENTS",
            "min_readiness_score must be between 0 and 100",
            "validate_arguments",
            metadata={"min_readiness_score": min_score},
        )

    run_data, manifest_file, input_error = _normalize_run_input(commercial_run_result)
    if input_error is not None:
        return input_error
    assert run_data is not None  # narrowed by input_error check

    missing_fields = tuple(
        field
        for field in _REQUIRED_RUN_FIELDS
        if not isinstance(run_data.get(field), str) or not run_data.get(field)
    )
    if missing_fields:
        return CommercialAcceptanceError.of(
            "INVALID_RUN_RESULT",
            "run result is missing required fields",
            "validate_run_result",
            metadata={"missing_fields": list(missing_fields)},
        )

    run_id = str(run_data["run_id"])
    delivery_id = str(run_data["delivery_id"])
    report_path = str(run_data["report_path"])
    package_path = str(run_data["package_path"])
    run_created_at = str(run_data["created_at"])

    metadata_block = run_data.get("metadata")
    metadata_block = metadata_block if isinstance(metadata_block, dict) else {}

    # Resolve the run manifest path from the richest available source.
    if manifest_file is not None:
        manifest_path = manifest_file
    elif isinstance(run_data.get("manifest_path"), str) and run_data.get("manifest_path"):
        manifest_path = str(run_data["manifest_path"])
    elif isinstance(run_data.get("output_dir"), str) and run_data.get("output_dir"):
        manifest_path = str(Path(str(run_data["output_dir"])) / "commercial_run_manifest.json")
    elif isinstance(metadata_block.get("output_dir"), str) and metadata_block.get("output_dir"):
        manifest_path = str(Path(str(metadata_block["output_dir"])) / "commercial_run_manifest.json")
    else:
        manifest_path = None

    if isinstance(run_data.get("package_manifest_path"), str) and run_data.get("package_manifest_path"):
        package_manifest_path = str(run_data["package_manifest_path"])
    elif isinstance(metadata_block.get("package_manifest_path"), str) and metadata_block.get(
        "package_manifest_path"
    ):
        package_manifest_path = str(metadata_block["package_manifest_path"])
    else:
        package_manifest_path = str(Path(package_path) / "manifest.json")

    cert_id = str(certification_id) if certification_id else f"commercial-acceptance-{run_id}"

    # --- checks --------------------------------------------------------------- #
    checks: list[AcceptanceCheck] = []
    evidence_paths: set[str] = set()

    run_successful = _run_is_successful(run_data)
    if run_successful:
        checks.append(
            AcceptanceCheck.of(
                "run_result_is_successful", "PASS", "CRITICAL",
                evidence=manifest_path,
            )
        )
    else:
        checks.append(
            AcceptanceCheck.of(
                "run_result_is_successful", "BLOCKED", "CRITICAL",
                evidence=manifest_path,
                error_kind="VALIDATION_FAILED",
                error_detail="commercial run did not complete successfully",
            )
        )

    def _skip(check_name: str, severity: str) -> None:
        checks.append(
            AcceptanceCheck.of(
                check_name, "SKIPPED", severity,
                error_detail="skipped: commercial run did not complete successfully",
            )
        )

    def _evidence_check(check_name: str, severity: str, target: str | None, is_dir: bool, detail: str) -> bool:
        exists = _existing_dir(target) if is_dir else _existing_file(target)
        if target is not None:
            evidence_paths.add(str(target))
        checks.append(
            AcceptanceCheck.of(
                check_name,
                "PASS" if exists else "FAIL",
                severity,
                evidence=None if target is None else str(target),
                error_kind=None if exists else "INPUT_NOT_FOUND",
                error_detail=None if exists else detail,
            )
        )
        return exists

    missing_delivery_files: list[str] = []
    if run_successful:
        _evidence_check(
            "report_json_exists", "CRITICAL", report_path, False,
            "commercial report file does not exist",
        )
        package_exists = _evidence_check(
            "delivery_package_exists", "CRITICAL", package_path, True,
            "delivery package directory does not exist",
        )
        _evidence_check(
            "commercial_run_manifest_exists", "HIGH", manifest_path, False,
            "commercial run manifest file does not exist",
        )
        _evidence_check(
            "package_manifest_exists", "HIGH", package_manifest_path, False,
            "package manifest file does not exist",
        )

        for filename in _REQUIRED_DELIVERY_FILES:
            candidate = Path(package_path) / filename
            evidence_paths.add(str(candidate))
            if not package_exists or not candidate.is_file():
                missing_delivery_files.append(filename)
        checks.append(
            AcceptanceCheck.of(
                "required_delivery_files_exist",
                "PASS" if not missing_delivery_files else "FAIL",
                "CRITICAL",
                evidence=package_path,
                error_kind=None if not missing_delivery_files else "INPUT_NOT_FOUND",
                error_detail=None
                if not missing_delivery_files
                else "missing required delivery files: " + ", ".join(sorted(missing_delivery_files)),
                metadata={"missing_files": sorted(missing_delivery_files)},
            )
        )
    else:
        _skip("report_json_exists", "CRITICAL")
        _skip("delivery_package_exists", "CRITICAL")
        _skip("commercial_run_manifest_exists", "HIGH")
        _skip("package_manifest_exists", "HIGH")
        _skip("required_delivery_files_exist", "CRITICAL")

    timestamps_ok = bool(run_created_at) and bool(created_at)
    checks.append(
        AcceptanceCheck.of(
            "deterministic_timestamps",
            "PASS" if timestamps_ok else "FAIL",
            "MEDIUM",
            error_kind=None if timestamps_ok else "VALIDATION_FAILED",
            error_detail=None if timestamps_ok else "created_at timestamps are not explicit strings",
            metadata={"run_created_at": run_created_at, "acceptance_created_at": created_at},
        )
    )

    url_evidence = sorted(p for p in evidence_paths if _is_url(p))
    for candidate in (report_path, package_path, manifest_path, package_manifest_path):
        if _is_url(candidate):
            url_evidence.append(str(candidate))
    url_evidence = sorted(set(url_evidence))
    checks.append(
        AcceptanceCheck.of(
            "local_only_paths",
            "PASS" if not url_evidence else "FAIL",
            "CRITICAL",
            error_kind=None if not url_evidence else "VALIDATION_FAILED",
            error_detail=None if not url_evidence else "evidence paths must be local, not URLs",
            metadata={"url_paths": url_evidence},
        )
    )

    if run_successful:
        critical_evidence = [report_path, package_path] + [
            str(Path(package_path) / filename) for filename in _REQUIRED_DELIVERY_FILES
        ]
        missing_evidence = sorted(
            p for p in critical_evidence
            if not (Path(p).is_dir() if p == package_path else Path(p).is_file())
        )
        checks.append(
            AcceptanceCheck.of(
                "no_missing_blocking_evidence",
                "PASS" if not missing_evidence else "FAIL",
                "CRITICAL",
                error_kind=None if not missing_evidence else "INPUT_NOT_FOUND",
                error_detail=None
                if not missing_evidence
                else "critical evidence paths are missing",
                metadata={"missing_evidence": missing_evidence},
            )
        )
    else:
        _skip("no_missing_blocking_evidence", "CRITICAL")

    # Optional asset checks.
    assets_dir = Path(package_path) / "assets"
    video_path = assets_dir / "video.mp4"
    if require_video:
        exists = run_successful and video_path.is_file()
        evidence_paths.add(str(video_path))
        checks.append(
            AcceptanceCheck.of(
                "video_asset_exists",
                "PASS" if exists else "FAIL",
                "HIGH",
                evidence=str(video_path),
                error_kind=None if exists else "INPUT_NOT_FOUND",
                error_detail=None if exists else "required video asset does not exist",
            )
        )
    else:
        checks.append(
            AcceptanceCheck.of(
                "video_asset_exists", "SKIPPED", "INFO",
                error_detail="skipped: require_video is False",
            )
        )
    if require_assets:
        exists = run_successful and assets_dir.is_dir()
        evidence_paths.add(str(assets_dir))
        checks.append(
            AcceptanceCheck.of(
                "asset_folder_exists",
                "PASS" if exists else "FAIL",
                "HIGH",
                evidence=str(assets_dir),
                error_kind=None if exists else "INPUT_NOT_FOUND",
                error_detail=None if exists else "required assets folder does not exist",
            )
        )
    else:
        checks.append(
            AcceptanceCheck.of(
                "asset_folder_exists", "SKIPPED", "INFO",
                error_detail="skipped: require_assets is False",
            )
        )

    # --- readiness score (from all checks so far) --------------------------- #
    score = 100
    for chk in checks:
        if chk.status == "FAIL":
            score -= _FAIL_PENALTIES.get(chk.severity, 0)
    score = max(0, score)

    threshold_ok = score >= min_score
    checks.append(
        AcceptanceCheck.of(
            "readiness_score_threshold",
            "PASS" if threshold_ok else "FAIL",
            "HIGH",
            error_kind=None if threshold_ok else "ACCEPTANCE_FAILED",
            error_detail=None
            if threshold_ok
            else f"readiness score {score} is below required minimum {min_score}",
            metadata={"readiness_score": score, "min_readiness_score": min_score},
        )
    )

    # --- overall status ------------------------------------------------------ #
    has_blocked = any(chk.status == "BLOCKED" for chk in checks)
    failed = [chk for chk in checks if chk.status == "FAIL"]
    has_critical_fail = any(chk.severity == "CRITICAL" for chk in failed)
    has_blocking_fail = any(chk.severity in ("CRITICAL", "HIGH", "MEDIUM") for chk in failed)

    if has_blocked:
        overall_status = "BLOCKED"
    elif has_critical_fail:
        overall_status = "FAIL"
    elif not has_blocking_fail and threshold_ok:
        overall_status = "PASS"
    else:
        overall_status = "FAIL"

    blocking_reasons = tuple(
        f"{chk.check_name}: {chk.error_detail or chk.status}"
        for chk in checks
        if chk.status == "BLOCKED" or (chk.status == "FAIL" and chk.severity == "CRITICAL")
    )

    report = CommercialAcceptanceReport(
        ok=overall_status == "PASS",
        schema_version=COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        certification_id=cert_id,
        run_id=run_id,
        delivery_id=delivery_id,
        created_at=created_at,
        overall_status=overall_status,
        readiness_score=score,
        checks=tuple(checks),
        evidence_paths=tuple(sorted(evidence_paths)),
        blocking_reasons=blocking_reasons,
        metadata=FrozenMap.from_mapping(
            {
                "gate": "scos.commercial.acceptance_gate",
                "min_readiness_score": min_score,
                "require_assets": bool(require_assets),
                "require_video": bool(require_video),
                "run_created_at": run_created_at,
            }
        ),
    )

    # --- write exactly one certification file -------------------------------- #
    cert_dir = Path(output_dir) / _fs_safe(cert_id)
    report_file = cert_dir / _ACCEPTANCE_REPORT_FILENAME
    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
        report_file.write_text(_json_text(report.to_dict()), encoding="utf-8", newline="\n")
    except OSError as exc:
        return CommercialAcceptanceError.of(
            "OUTPUT_WRITE_FAILED",
            "commercial acceptance report could not be written",
            "write_acceptance_report",
            tuple(checks),
            {"output_path": str(report_file), "os_error": type(exc).__name__},
        )

    return report


__all__ = ("run_commercial_acceptance_gate",)
