"""SCOS Stage 4.2 local delivery package generator.

Turns one Stage 4.1 CommercialReport into a deterministic client-deliverable
folder on the local filesystem. Consumes only commercial-owned models; performs
no network, cloud, SaaS, auth, payment, or LLM behavior. Expected failures
return deterministic DeliveryPackageError objects, never raw exceptions.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

try:
    from .package_models import (
        DELIVERY_PACKAGE_SCHEMA_VERSION,
        DeliveryPackageError,
        DeliveryPackageFile,
        DeliveryPackageManifest,
        DeliveryPackageResult,
    )
    from .report_models import CommercialReport, FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from package_models import (
        DELIVERY_PACKAGE_SCHEMA_VERSION,
        DeliveryPackageError,
        DeliveryPackageFile,
        DeliveryPackageManifest,
        DeliveryPackageResult,
    )
    from report_models import CommercialReport, FrozenMap

_REQUIRED_FILES: tuple[tuple[str, str], ...] = (
    ("report.json", "report_json"),
    ("report.md", "report_markdown"),
    ("qa_summary.md", "qa_summary"),
    ("improvement_plan.md", "improvement_plan"),
)

_NO_RECOMMENDATIONS_LINE = "No evidence-backed recommendations available."
_NO_RISKS_LINE = "No evidence-backed risks available."


def _fs_safe_name(delivery_id: str) -> str:
    """Deterministic folder name for a delivery id.

    Windows forbids ':' in file names, so the on-disk folder replaces ':' with
    '_'. The manifest always keeps the raw delivery_id.
    """

    return delivery_id.replace(":", "_")


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _value_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_report_md(report_data: dict[str, Any]) -> str:
    lines = [
        "# Commercial Report",
        "",
        f"- report_id: {report_data['report_id']}",
        f"- report_type: {report_data['report_type']}",
        f"- schema_version: {report_data['schema_version']}",
        f"- created_at: {report_data['created_at']}",
        f"- source_run_id: {report_data['source_run_id']}",
        f"- style_id: {report_data['style_id']}",
        f"- qa_status: {report_data['qa_status']}",
        "",
        "## Summary",
        "",
        report_data["summary"] or "No summary available.",
        "",
        "## Evidence",
        "",
    ]
    evidence = report_data.get("evidence") or []
    if evidence:
        for item in evidence:
            lines.append(
                f"- {item['evidence_id']} ({item['evidence_type']}, "
                f"{item['source']}): {_value_text(item['value'])}"
            )
    else:
        lines.append("No evidence entries available.")
    lines += ["", "## Risks", ""]
    risks = report_data.get("risks") or []
    if risks:
        for item in risks:
            lines.append(
                f"- {item['risk_id']} ({item['risk_type']}, "
                f"{item['source']}): {item['detail']}"
            )
    else:
        lines.append(_NO_RISKS_LINE)
    lines += ["", "## Recommendations", ""]
    recommendations = report_data.get("recommendations") or []
    if recommendations:
        for item in recommendations:
            lines.append(f"- {_value_text(item)}")
    else:
        lines.append(_NO_RECOMMENDATIONS_LINE)
    lines.append("")
    return "\n".join(lines)


def _render_qa_summary_md(report_data: dict[str, Any]) -> str:
    lines = [
        "# QA Summary",
        "",
        f"- report_id: {report_data['report_id']}",
        f"- source_run_id: {report_data['source_run_id']}",
        f"- qa_status: {report_data['qa_status']}",
        "",
        "## Evidence",
        "",
    ]
    evidence = report_data.get("evidence") or []
    if evidence:
        for item in evidence:
            lines.append(
                f"- {item['evidence_id']} ({item['evidence_type']}, "
                f"{item['source']}): {_value_text(item['value'])}"
            )
    else:
        lines.append("No evidence entries available.")
    lines.append("")
    return "\n".join(lines)


def _render_improvement_plan_md(report_data: dict[str, Any]) -> str:
    lines = [
        "# Improvement Plan",
        "",
        f"- report_id: {report_data['report_id']}",
        f"- source_run_id: {report_data['source_run_id']}",
        "",
        "## Evidence-Backed Recommendations",
        "",
    ]
    recommendations = report_data.get("recommendations") or []
    if recommendations:
        for item in recommendations:
            lines.append(f"- {_value_text(item)}")
    else:
        lines.append(_NO_RECOMMENDATIONS_LINE)
    lines += ["", "## Evidence-Backed Risks", ""]
    risks = report_data.get("risks") or []
    if risks:
        for item in risks:
            lines.append(
                f"- {item['risk_id']} ({item['risk_type']}, "
                f"{item['source']}): {item['detail']}"
            )
    else:
        lines.append(_NO_RISKS_LINE)
    lines.append("")
    return "\n".join(lines)


def _check_optional_source(
    path_value: Any,
    error_kind: str,
    label: str,
) -> Path | DeliveryPackageError | None:
    if path_value is None:
        return None
    source = Path(str(path_value))
    if not source.exists():
        return DeliveryPackageError.of(
            error_kind, f"{label} does not exist", {"path": str(source)}
        )
    if not source.is_file():
        return DeliveryPackageError.of(
            error_kind, f"{label} is not a file", {"path": str(source)}
        )
    return source


def create_delivery_package(
    *,
    commercial_report: CommercialReport,
    output_dir: str | Path,
    delivery_id: str | None = None,
    video_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    now_fn: Callable[[], str],
    overwrite: bool = False,
) -> DeliveryPackageResult | DeliveryPackageError:
    """Create a deterministic local delivery package folder for one report."""

    if not isinstance(commercial_report, CommercialReport):
        return DeliveryPackageError.of(
            "INVALID_REPORT",
            "commercial_report must be a Stage 4.1 CommercialReport",
            {"received_type": type(commercial_report).__name__},
        )

    report_data = commercial_report.to_dict()

    if delivery_id is None:
        delivery_id = (
            f"delivery:{report_data['report_type']}:{report_data['source_run_id']}"
        )
    delivery_id = str(delivery_id)
    if not delivery_id:
        return DeliveryPackageError.of(
            "INVALID_OUTPUT_DIR", "delivery_id must not be empty", {}
        )

    base_dir = Path(output_dir)
    if base_dir.exists() and not base_dir.is_dir():
        return DeliveryPackageError.of(
            "INVALID_OUTPUT_DIR",
            "output_dir exists and is not a directory",
            {"output_dir": str(base_dir)},
        )
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DeliveryPackageError.of(
            "INVALID_OUTPUT_DIR",
            "output_dir could not be created",
            {"output_dir": str(base_dir), "os_error": type(exc).__name__},
        )

    # Path containment guardrail: the package folder must be a direct,
    # non-escaping child of output_dir. A hostile delivery_id must never
    # write outside output_dir.
    folder_name = _fs_safe_name(delivery_id)
    package_dir = base_dir / folder_name
    try:
        resolved_base = base_dir.resolve(strict=True)
        resolved_package = package_dir.resolve()
    except OSError as exc:
        return DeliveryPackageError.of(
            "INVALID_OUTPUT_DIR",
            "package path could not be resolved",
            {"output_dir": str(base_dir), "os_error": type(exc).__name__},
        )
    if (
        resolved_package == resolved_base
        or resolved_package.parent != resolved_base
    ):
        return DeliveryPackageError.of(
            "INVALID_OUTPUT_DIR",
            "delivery_id resolves outside the output directory",
            {"delivery_id": delivery_id},
        )
    package_dir = resolved_package

    if package_dir.exists():
        if not overwrite:
            return DeliveryPackageError.of(
                "PACKAGE_ALREADY_EXISTS",
                "package directory already exists and overwrite is False",
                {"package_dir": str(package_dir)},
            )
        # Overwrite guardrail: delete only the computed package directory,
        # never output_dir itself, parents, or any source path.
        if package_dir == resolved_base or package_dir.parent != resolved_base:
            return DeliveryPackageError.of(
                "INVALID_OUTPUT_DIR",
                "refusing to overwrite outside the package directory",
                {"package_dir": str(package_dir)},
            )
        try:
            shutil.rmtree(package_dir)
        except OSError as exc:
            return DeliveryPackageError.of(
                "WRITE_FAILED",
                "existing package directory could not be replaced",
                {"package_dir": str(package_dir), "os_error": type(exc).__name__},
            )

    video_source = _check_optional_source(
        video_path, "SOURCE_VIDEO_NOT_FOUND", "video_path"
    )
    if isinstance(video_source, DeliveryPackageError):
        return video_source
    manifest_source = _check_optional_source(
        source_manifest_path, "SOURCE_MANIFEST_NOT_FOUND", "source_manifest_path"
    )
    if isinstance(manifest_source, DeliveryPackageError):
        return manifest_source

    created_at = str(now_fn())

    file_entries: list[DeliveryPackageFile] = [
        DeliveryPackageFile(path=path, kind=kind, required=True)
        for path, kind in _REQUIRED_FILES
    ]
    try:
        package_dir.mkdir(parents=True, exist_ok=False)
        (package_dir / "report.json").write_text(
            _json_text(report_data), encoding="utf-8", newline="\n"
        )
        (package_dir / "report.md").write_text(
            _render_report_md(report_data), encoding="utf-8", newline="\n"
        )
        (package_dir / "qa_summary.md").write_text(
            _render_qa_summary_md(report_data), encoding="utf-8", newline="\n"
        )
        (package_dir / "improvement_plan.md").write_text(
            _render_improvement_plan_md(report_data), encoding="utf-8", newline="\n"
        )
        if video_source is not None or manifest_source is not None:
            (package_dir / "assets").mkdir(parents=True, exist_ok=True)
        if video_source is not None:
            shutil.copyfile(video_source, package_dir / "assets" / "video.mp4")
            file_entries.append(
                DeliveryPackageFile(
                    path="assets/video.mp4", kind="video", required=False
                )
            )
        if manifest_source is not None:
            shutil.copyfile(
                manifest_source, package_dir / "assets" / "source_manifest.json"
            )
            file_entries.append(
                DeliveryPackageFile(
                    path="assets/source_manifest.json",
                    kind="source_manifest",
                    required=False,
                )
            )
    except OSError as exc:
        return DeliveryPackageError.of(
            "WRITE_FAILED",
            "package files could not be written",
            {"package_dir": str(package_dir), "os_error": type(exc).__name__},
        )

    file_entries.sort(key=lambda item: item.path)
    checksums: dict[str, str] = {}
    try:
        for entry in file_entries:
            checksums[entry.path] = _sha256_of(package_dir / entry.path)
    except OSError as exc:
        return DeliveryPackageError.of(
            "CHECKSUM_FAILED",
            "package file checksum could not be computed",
            {"package_dir": str(package_dir), "os_error": type(exc).__name__},
        )

    manifest = DeliveryPackageManifest(
        delivery_id=delivery_id,
        schema_version=DELIVERY_PACKAGE_SCHEMA_VERSION,
        created_at=created_at,
        source_run_id=report_data["source_run_id"],
        style_id=report_data["style_id"],
        report_id=report_data["report_id"],
        package_status="complete",
        files=tuple(file_entries),
        checksums=FrozenMap.from_mapping(checksums),
        metadata=FrozenMap.from_mapping(
            {
                "builder": "scos.commercial.delivery_package",
                "package_folder": folder_name,
                "report_schema_version": report_data["schema_version"],
                "report_type": report_data["report_type"],
            }
        ),
    )
    try:
        (package_dir / "manifest.json").write_text(
            _json_text(manifest.to_dict()), encoding="utf-8", newline="\n"
        )
    except OSError as exc:
        return DeliveryPackageError.of(
            "WRITE_FAILED",
            "manifest.json could not be written",
            {"package_dir": str(package_dir), "os_error": type(exc).__name__},
        )

    return DeliveryPackageResult(
        delivery_id=delivery_id,
        output_dir=str(package_dir),
        manifest=manifest,
    )


__all__ = ("create_delivery_package",)
