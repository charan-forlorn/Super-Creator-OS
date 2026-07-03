"""SCOS Stage 4.4 local commercial run orchestrator.

Runs the full commercial delivery flow in one deterministic library call:

    validate inputs -> build commercial report -> build delivery package
    -> write commercial run manifest -> return CommercialRunResult / CommercialRunError

This is an orchestration layer only. It duplicates no Stage 4.1 report logic and
no Stage 4.2 package logic, changes no existing contract, mutates no source
artifact, and performs no network, cloud, SaaS, auth, payment, or LLM behavior.
The Stage 3.9 knowledge access layer is never imported here; ``knowledge_service``
is received as an opaque object and handed straight to the Stage 4.1 builder.

Determinism: ``created_at`` is an explicit injected string (no real clock, no
random/uuid). All JSON is written UTF-8 with LF newlines using
``json.dumps(..., sort_keys=True, indent=2)``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

try:
    from .report_builder import build_commercial_report
    from .report_models import CommercialReport, CommercialReportError, FrozenMap
    from .delivery_package import create_delivery_package
    from .package_models import DeliveryPackageError, DeliveryPackageResult
    from .run_models import (
        COMMERCIAL_RUN_SCHEMA_VERSION,
        CommercialRunError,
        CommercialRunResult,
        CommercialRunStep,
    )
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_builder import build_commercial_report
    from report_models import CommercialReport, CommercialReportError, FrozenMap
    from delivery_package import create_delivery_package
    from package_models import DeliveryPackageError, DeliveryPackageResult
    from run_models import (
        COMMERCIAL_RUN_SCHEMA_VERSION,
        CommercialRunError,
        CommercialRunResult,
        CommercialRunStep,
    )

_URL_PREFIXES = ("http://", "https://")


def _now_fn(created_at: str) -> Callable[[], str]:
    """Return a zero-arg callable yielding the exact provided timestamp string."""

    value = str(created_at)

    def _fn() -> str:
        return value

    return _fn


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _fs_safe(name: str) -> str:
    """Deterministic, Windows-safe folder name for a run/delivery id."""

    return name.replace(":", "_")


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def run_commercial_delivery(
    *,
    knowledge_service: Any,
    run_id: str,
    output_dir: str | Path,
    created_at: str,
    delivery_id: str | None = None,
    video_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    overwrite: bool = False,
    qa_status: str = "unknown",
    risks: tuple[dict[str, Any], ...] | None = None,
) -> CommercialRunResult | CommercialRunError:
    """Execute the full Stage 4 commercial delivery flow for one run.

    Expected failure states return a deterministic CommercialRunError carrying the
    steps recorded so far; never raises for expected conditions.
    """

    steps: list[CommercialRunStep] = []

    # --- Step 1: validate_inputs ------------------------------------------- #
    def _validation_error(error_kind: str, error_detail: str, meta: dict[str, Any]) -> CommercialRunError:
        steps.append(
            CommercialRunStep.of(
                "validate_inputs",
                "failure",
                error_kind=error_kind,
                error_detail=error_detail,
                metadata=meta,
            )
        )
        return CommercialRunError.of(error_kind, error_detail, "validate_inputs", tuple(steps), meta)

    if not isinstance(run_id, str) or not run_id:
        return _validation_error("INVALID_ARGUMENTS", "run_id is required", {})
    if output_dir is None or str(output_dir) == "":
        return _validation_error("INVALID_ARGUMENTS", "output_dir is required", {})
    if not isinstance(created_at, str) or not created_at:
        return _validation_error("INVALID_ARGUMENTS", "created_at is required", {})

    for label, value in (
        ("output_dir", output_dir),
        ("video_path", video_path),
        ("source_manifest_path", source_manifest_path),
    ):
        if _is_url(value):
            return _validation_error(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                {"path": str(value), "argument": label},
            )

    for label, value in (
        ("video_path", video_path),
        ("source_manifest_path", source_manifest_path),
    ):
        if value is None:
            continue
        source = Path(str(value))
        if not source.exists() or not source.is_file():
            return _validation_error(
                "INPUT_NOT_FOUND",
                f"{label} does not exist or is not a file",
                {"path": str(source), "argument": label},
            )

    steps.append(CommercialRunStep.of("validate_inputs", "success"))

    # --- Deterministic run directory (created only after validation) ------- #
    run_folder = _fs_safe(delivery_id if delivery_id else f"local-commercial-run-{run_id}")
    base_dir = Path(output_dir)
    run_dir = base_dir / run_folder
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        resolved_base = base_dir.resolve(strict=True)
        resolved_run = run_dir.resolve()
    except OSError as exc:
        return CommercialRunError.of(
            "VALIDATION_FAILED",
            "output_dir could not be prepared",
            "validate_inputs",
            tuple(steps),
            {"output_dir": str(base_dir), "os_error": type(exc).__name__},
        )
    if resolved_run == resolved_base or resolved_run.parent != resolved_base:
        return CommercialRunError.of(
            "VALIDATION_FAILED",
            "run directory resolves outside the output directory",
            "validate_inputs",
            tuple(steps),
            {"run_folder": run_folder},
        )
    run_dir = resolved_run
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return CommercialRunError.of(
            "OUTPUT_WRITE_FAILED",
            "run directory could not be created",
            "validate_inputs",
            tuple(steps),
            {"run_dir": str(run_dir), "os_error": type(exc).__name__},
        )

    # --- Step 2: build_report ---------------------------------------------- #
    report = build_commercial_report(
        knowledge_service,
        run_id,
        now_fn=_now_fn(created_at),
        report_type="run_summary",
        qa_status=qa_status,
        risks=risks or (),
    )
    if not isinstance(report, CommercialReport):
        detail = "commercial report build failed"
        meta: dict[str, Any] = {}
        if isinstance(report, CommercialReportError):
            err = report.to_dict()
            detail = str(err.get("reason") or detail)
            meta = {"report_error": err}
        steps.append(
            CommercialRunStep.of(
                "build_report", "failure", error_kind="REPORT_BUILD_FAILED", error_detail=detail, metadata=meta
            )
        )
        return CommercialRunError.of("REPORT_BUILD_FAILED", detail, "build_report", tuple(steps), meta)
    steps.append(CommercialRunStep.of("build_report", "success", metadata={"report_id": report.report_id}))

    # --- Step 3: write_report ---------------------------------------------- #
    report_path = run_dir / "report.json"
    try:
        report_path.write_text(_json_text(report.to_dict()), encoding="utf-8", newline="\n")
    except OSError as exc:
        detail = "report.json could not be written"
        meta = {"report_path": str(report_path), "os_error": type(exc).__name__}
        steps.append(
            CommercialRunStep.of(
                "write_report", "failure", error_kind="OUTPUT_WRITE_FAILED", error_detail=detail, metadata=meta
            )
        )
        return CommercialRunError.of("OUTPUT_WRITE_FAILED", detail, "write_report", tuple(steps), meta)
    steps.append(CommercialRunStep.of("write_report", "success", output_path=str(report_path)))

    # --- Step 4: build_package --------------------------------------------- #
    package_result = create_delivery_package(
        commercial_report=report,
        output_dir=run_dir / "delivery_package",
        delivery_id=delivery_id,
        video_path=video_path,
        source_manifest_path=source_manifest_path,
        now_fn=_now_fn(created_at),
        overwrite=overwrite,
    )
    if not isinstance(package_result, DeliveryPackageResult):
        detail = "delivery package build failed"
        meta = {}
        if isinstance(package_result, DeliveryPackageError):
            err = package_result.to_dict()
            detail = str(err.get("error_detail") or detail)
            meta = {"package_error": err}
        steps.append(
            CommercialRunStep.of(
                "build_package", "failure", error_kind="PACKAGE_BUILD_FAILED", error_detail=detail, metadata=meta
            )
        )
        return CommercialRunError.of("PACKAGE_BUILD_FAILED", detail, "build_package", tuple(steps), meta)

    package_path = str(package_result.output_dir)
    package_manifest_path = str(Path(package_path) / "manifest.json")
    resolved_delivery_id = str(package_result.delivery_id)
    steps.append(
        CommercialRunStep.of(
            "build_package",
            "success",
            output_path=package_path,
            metadata={"delivery_id": resolved_delivery_id},
        )
    )

    # --- Step 5: write_manifest -------------------------------------------- #
    manifest_path = run_dir / "commercial_run_manifest.json"
    final_steps = tuple(steps) + (
        CommercialRunStep.of("write_manifest", "success", output_path=str(manifest_path)),
    )
    manifest = {
        "schema_version": COMMERCIAL_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "report_id": report.report_id,
        "delivery_id": resolved_delivery_id,
        "created_at": created_at,
        "report_path": str(report_path),
        "package_path": package_path,
        "package_manifest_path": package_manifest_path,
        "steps": [step.to_dict() for step in final_steps],
        "metadata": {
            "orchestrator": "scos.commercial.run_orchestrator",
            "output_dir": str(run_dir),
        },
    }
    try:
        manifest_path.write_text(_json_text(manifest), encoding="utf-8", newline="\n")
    except OSError as exc:
        detail = "commercial_run_manifest.json could not be written"
        meta = {"manifest_path": str(manifest_path), "os_error": type(exc).__name__}
        steps.append(
            CommercialRunStep.of(
                "write_manifest", "failure", error_kind="OUTPUT_WRITE_FAILED", error_detail=detail, metadata=meta
            )
        )
        return CommercialRunError.of("OUTPUT_WRITE_FAILED", detail, "write_manifest", tuple(steps), meta)

    return CommercialRunResult(
        ok=True,
        schema_version=COMMERCIAL_RUN_SCHEMA_VERSION,
        run_id=run_id,
        report_id=report.report_id,
        delivery_id=resolved_delivery_id,
        output_dir=str(run_dir),
        report_path=str(report_path),
        package_path=package_path,
        manifest_path=str(manifest_path),
        created_at=created_at,
        steps=final_steps,
        metadata=FrozenMap.from_mapping(
            {
                "orchestrator": "scos.commercial.run_orchestrator",
                "package_manifest_path": package_manifest_path,
            }
        ),
    )


__all__ = ("run_commercial_delivery",)
