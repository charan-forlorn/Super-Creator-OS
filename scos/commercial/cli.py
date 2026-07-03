"""SCOS Stage 4.3 — Local Commercial CLI.

A local-only, stdlib ``argparse`` command line over the Stage 4.1 commercial
report builder and the Stage 4.2 delivery package generator. It performs no
network, cloud, SaaS, auth, payment, or LLM behavior, mutates no source
artifacts, and emits deterministic JSON only.

Entrypoint::

    python -m scos.commercial.cli <command> [options]

Commands: report, package, validate, version.

Boundary: the Stage 3.9 knowledge access layer and the Stage 4.1 report builder
are imported lazily inside ``_cmd_report`` only. The version / package / validate
commands never import the knowledge layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

try:  # package context (python -m scos.commercial.cli)
    from .report_models import CommercialReport, FrozenMap, ReportEvidence, ReportRisk
    from .package_models import DeliveryPackageError
    from .delivery_package import create_delivery_package
except ImportError:  # pragma: no cover - plain-script / sys.path fallback
    from report_models import CommercialReport, FrozenMap, ReportEvidence, ReportRisk
    from package_models import DeliveryPackageError
    from delivery_package import create_delivery_package

COMMERCIAL_CLI_SCHEMA_VERSION = 1

_SUPPORTED_COMMANDS = ("package", "report", "validate", "version")
_SUPPORTED_REPORT_TYPES = ("run_summary",)
_UNSUPPORTED_REPORT_TYPES = ("style_summary", "portfolio", "system")
_UNSUPPORTED_REPORT_TYPE_DETAIL = "report-type not supported by Stage 4.1 builder"

_DELIVERY_FILES = (
    "report.json",
    "report.md",
    "qa_summary.md",
    "improvement_plan.md",
    "manifest.json",
)


class _CliError(Exception):
    """Expected, deterministic failure. Rendered as failure JSON with exit 1."""

    def __init__(self, error_kind: str, error_detail: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(error_detail)
        self.error_kind = error_kind
        self.error_detail = error_detail
        self.metadata = dict(metadata or {})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_fn(created_at: str) -> Callable[[], str]:
    """Return a zero-arg callable yielding the exact provided timestamp string."""

    value = str(created_at)

    def _fn() -> str:
        return value

    return _fn


def _reject_urls(*paths: Any) -> None:
    for path in paths:
        if path is None:
            continue
        text = str(path)
        if text.startswith("http://") or text.startswith("https://"):
            raise _CliError(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                {"path": text},
            )


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2))


def _success(
    command: str,
    *,
    output_path: str | None = None,
    delivery_id: str | None = None,
    report_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "command": command,
        "schema_version": COMMERCIAL_CLI_SCHEMA_VERSION,
        "output_path": output_path,
        "delivery_id": delivery_id,
        "report_id": report_id,
        "metadata": metadata or {},
    }


def _failure(command: str, error_kind: str, error_detail: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "command": command,
        "schema_version": COMMERCIAL_CLI_SCHEMA_VERSION,
        "error_kind": error_kind,
        "error_detail": error_detail,
        "metadata": metadata or {},
    }


def _reconstruct_report(data: dict[str, Any]) -> CommercialReport:
    """Rebuild a CommercialReport from report.json using public constructors only.

    CommercialReport has no from_dict, so evidence, risks, and metadata are
    reconstructed via ReportEvidence, ReportRisk, and FrozenMap.from_mapping.
    """

    evidence = tuple(
        ReportEvidence(
            item["evidence_id"],
            item["evidence_type"],
            item["source"],
            item.get("value"),
        )
        for item in (data.get("evidence") or ())
    )
    risks = tuple(
        ReportRisk(item["risk_id"], item["risk_type"], item["source"], item["detail"])
        for item in (data.get("risks") or ())
    )
    return CommercialReport(
        report_id=data["report_id"],
        schema_version=data["schema_version"],
        report_type=data["report_type"],
        created_at=data["created_at"],
        source_run_id=data["source_run_id"],
        style_id=data.get("style_id"),
        qa_status=data["qa_status"],
        summary=data["summary"],
        evidence=evidence,
        recommendations=tuple(data.get("recommendations") or ()),
        risks=risks,
        metadata=FrozenMap.from_mapping(dict(data.get("metadata") or {})),
    )


def _load_json_object(path: Path, error_kind: str, missing_kind: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise _CliError(missing_kind, "report-json does not exist or is not a file", {"report_json": str(path)})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _CliError(error_kind, "report-json could not be read or parsed", {"report_json": str(path), "reason": type(exc).__name__})
    if not isinstance(data, dict):
        raise _CliError(error_kind, "report-json must be a JSON object", {"report_json": str(path)})
    return data


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _cmd_version(args: argparse.Namespace) -> int:
    _emit(
        {
            "ok": True,
            "cli_schema_version": COMMERCIAL_CLI_SCHEMA_VERSION,
            "supported_commands": ["package", "report", "validate", "version"],
        }
    )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    command = "report"
    _reject_urls(args.index_path, args.output)

    report_type = args.report_type
    if report_type in _UNSUPPORTED_REPORT_TYPES or report_type not in _SUPPORTED_REPORT_TYPES:
        raise _CliError("INVALID_ARGUMENTS", _UNSUPPORTED_REPORT_TYPE_DETAIL, {"report_type": report_type})
    if not args.run_id:
        raise _CliError("INVALID_ARGUMENTS", "--run-id is required for report-type run_summary", {"report_type": report_type})

    index_path = Path(args.index_path)
    if not index_path.exists() or not index_path.is_file():
        raise _CliError("INVALID_INDEX_PATH", "index path does not exist or is not a file", {"index_path": str(index_path)})

    # Boundary: knowledge access layer + report builder are imported here only.
    knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge"
    if str(knowledge_dir) not in sys.path:
        sys.path.insert(0, str(knowledge_dir))
    try:
        from index_store import IndexStore
        from knowledge_service import KnowledgeService
    except ImportError as exc:
        raise _CliError("INVALID_INDEX_PATH", "knowledge access layer is unavailable", {"reason": type(exc).__name__})

    try:
        index = IndexStore(index_path).load()
    except Exception as exc:  # noqa: BLE001 - deterministic boundary, no raw leakage
        raise _CliError("INVALID_INDEX_PATH", "index could not be loaded", {"index_path": str(index_path), "reason": type(exc).__name__})

    service = KnowledgeService(index)

    try:
        from .report_builder import build_commercial_report
    except ImportError:  # pragma: no cover - plain-script / sys.path fallback
        from report_builder import build_commercial_report

    result = build_commercial_report(
        service,
        args.run_id,
        now_fn=_now_fn(args.created_at),
        report_type=report_type,
        qa_status=args.qa_status,
        risks=None,
    )
    if not isinstance(result, CommercialReport):
        err = result.to_dict()
        raise _CliError(
            "REPORT_BUILD_FAILED",
            str(err.get("reason") or "report build failed"),
            {"error": err.get("error"), "target": err.get("target"), "reason": err.get("reason")},
        )

    output_path = Path(args.output)
    try:
        if output_path.parent and not output_path.parent.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.to_dict(), sort_keys=True, indent=2),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise _CliError("OUTPUT_WRITE_FAILED", "report output could not be written", {"output_path": str(output_path), "os_error": type(exc).__name__})

    _emit(_success(command, output_path=str(output_path), report_id=result.report_id))
    return 0


def _cmd_package(args: argparse.Namespace) -> int:
    command = "package"
    _reject_urls(args.report_json, args.output_dir, args.video_path, args.source_manifest_path)

    report_path = Path(args.report_json)
    data = _load_json_object(report_path, "INVALID_REPORT_JSON", "INPUT_NOT_FOUND")
    try:
        report = _reconstruct_report(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise _CliError("INVALID_REPORT_JSON", "report-json is missing required fields", {"report_json": str(report_path), "reason": type(exc).__name__})

    result = create_delivery_package(
        commercial_report=report,
        output_dir=args.output_dir,
        delivery_id=args.delivery_id,
        video_path=args.video_path,
        source_manifest_path=args.source_manifest_path,
        now_fn=_now_fn(args.created_at),
        overwrite=bool(args.overwrite),
    )
    if isinstance(result, DeliveryPackageError):
        err = result.to_dict()
        raise _CliError(
            "PACKAGE_BUILD_FAILED",
            str(err.get("error_detail") or "package build failed"),
            {"error_kind": err.get("error_kind"), "error_detail": err.get("error_detail")},
        )

    _emit(
        _success(
            command,
            output_path=result.output_dir,
            delivery_id=result.delivery_id,
            report_id=result.manifest.report_id,
        )
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    command = "validate"
    _reject_urls(args.report_json, args.output_dir, args.video_path, args.source_manifest_path)

    report_path = Path(args.report_json)
    data = _load_json_object(report_path, "VALIDATION_FAILED", "VALIDATION_FAILED")
    try:
        _reconstruct_report(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise _CliError("VALIDATION_FAILED", "report-json is missing required fields", {"report_json": str(report_path), "reason": type(exc).__name__})

    # output-dir must be usable or creatable, but validate must NOT create it.
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        if not output_dir.is_dir():
            raise _CliError("VALIDATION_FAILED", "output-dir exists and is not a directory", {"output_dir": str(output_dir)})
    else:
        ancestor = output_dir.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if not ancestor.exists() or not ancestor.is_dir():
            raise _CliError("VALIDATION_FAILED", "output-dir is not creatable", {"output_dir": str(output_dir)})

    # Optional asset paths must exist and be files.
    for label, value in (("video_path", args.video_path), ("source_manifest_path", args.source_manifest_path)):
        if value is None:
            continue
        asset = Path(value)
        if not asset.exists() or not asset.is_file():
            raise _CliError("VALIDATION_FAILED", f"{label} does not exist or is not a file", {label: str(asset)})

    # Compute the would-write plan without touching disk.
    delivery_id = f"delivery:{data.get('report_type')}:{data.get('source_run_id')}"
    folder_name = delivery_id.replace(":", "_")
    planned_files = list(_DELIVERY_FILES)
    if args.video_path is not None:
        planned_files.append("assets/video.mp4")
    if args.source_manifest_path is not None:
        planned_files.append("assets/source_manifest.json")
    would_write = {
        "delivery_id": delivery_id,
        "package_dir": str(output_dir / folder_name),
        "files": sorted(planned_files),
        "created_at": str(args.created_at),
    }
    _emit(
        _success(
            command,
            output_path=str(output_dir / folder_name),
            delivery_id=delivery_id,
            report_id=data.get("report_id"),
            metadata={"would_write": would_write},
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# Parser + dispatch
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scos.commercial.cli",
        description="SCOS Stage 4.3 local commercial CLI (local-only, deterministic).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_version = sub.add_parser("version", help="Print CLI schema version and supported commands.")
    p_version.set_defaults(func=_cmd_version)

    p_report = sub.add_parser("report", help="Build a Stage 4.1 commercial report from a knowledge index.")
    p_report.add_argument("--index-path", required=True)
    p_report.add_argument("--report-type", required=True)
    p_report.add_argument("--output", required=True)
    p_report.add_argument("--created-at", required=True)
    p_report.add_argument("--run-id", default=None)
    p_report.add_argument("--qa-status", default="unknown")
    p_report.set_defaults(func=_cmd_report)

    p_package = sub.add_parser("package", help="Build a Stage 4.2 delivery package from a report.json.")
    p_package.add_argument("--report-json", required=True)
    p_package.add_argument("--output-dir", required=True)
    p_package.add_argument("--created-at", required=True)
    p_package.add_argument("--delivery-id", default=None)
    p_package.add_argument("--video-path", default=None)
    p_package.add_argument("--source-manifest-path", default=None)
    p_package.add_argument("--overwrite", action="store_true")
    p_package.set_defaults(func=_cmd_package)

    p_validate = sub.add_parser("validate", help="Validate package inputs without writing anything.")
    p_validate.add_argument("--report-json", required=True)
    p_validate.add_argument("--output-dir", required=True)
    p_validate.add_argument("--created-at", required=True)
    p_validate.add_argument("--video-path", default=None)
    p_validate.add_argument("--source-manifest-path", default=None)
    p_validate.set_defaults(func=_cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)  # argparse usage errors exit 2
    command = getattr(args, "command", None)
    func = getattr(args, "func", None)
    if func is None:
        _emit(_failure(str(command), "INVALID_COMMAND", "unknown or unsupported command"))
        return 1
    try:
        return func(args)
    except _CliError as exc:
        _emit(_failure(str(command), exc.error_kind, exc.error_detail, exc.metadata))
        return 1


if __name__ == "__main__":
    sys.exit(main())
