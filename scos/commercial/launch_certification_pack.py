"""SCOS Stage 4.9 commercial launch certification pack generator.

Packages existing Stage 4.8 dry-run evidence into a deterministic local
certification folder. This layer reads source artifacts and writes only its own
five pack files; it never rebuilds upstream commercial evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .launch_certification_models import (
        COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION,
        LaunchCertificationArtifact,
        LaunchCertificationBlocker,
        LaunchCertificationCheck,
        LaunchCertificationError,
        LaunchCertificationResult,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from launch_certification_models import (
        COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION,
        LaunchCertificationArtifact,
        LaunchCertificationBlocker,
        LaunchCertificationCheck,
        LaunchCertificationError,
        LaunchCertificationResult,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")

_REPORT_FILENAME = "launch_certification_report.json"
_SUMMARY_FILENAME = "launch_certification_summary.md"
_CHECKLIST_FILENAME = "launch_readiness_checklist.md"
_BLOCKERS_FILENAME = "launch_blockers.md"
_NEXT_STEPS_FILENAME = "operator_next_steps.md"

_REQUIRED_DRY_RUN_KEYS = (
    "ok",
    "schema_version",
    "passed",
    "dry_run_id",
    "checked_at",
    "customer_case",
    "go_no_go",
    "readiness_level",
    "readiness_score",
    "readiness_max_score",
    "commercial_run_manifest_path",
    "acceptance_report_path",
    "operating_kit_path",
    "monetization_readiness_report_path",
    "dry_run_report_path",
    "steps",
    "blockers",
    "metadata",
)

_REQUIRED_OPERATING_KIT_FILES = (
    "customer_intake_checklist.md",
    "operator_sop.md",
    "delivery_handoff.md",
    "acceptance_certificate.md",
    "pricing_offer_checklist.md",
    "customer_followup_checklist.md",
    "files_to_send.md",
    "customer_kit_manifest.json",
)

_SENSITIVE_KEY_MARKERS = ("phone", "email", "address")


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _check(
    checks: list[LaunchCertificationCheck],
    check_name: str,
    status: str,
    severity: str,
    *,
    artifact_path: str | None = None,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    checks.append(
        LaunchCertificationCheck.of(
            check_name,
            status,
            severity,
            artifact_path=artifact_path,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=metadata,
        )
    )


def _blocker(
    blockers: list[LaunchCertificationBlocker],
    blocker_id: str,
    category: str,
    severity: str,
    title: str,
    detail: str,
    recommended_action: str,
    source_check: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    blockers.append(
        LaunchCertificationBlocker.of(
            blocker_id,
            category,
            severity,
            title,
            detail,
            recommended_action,
            source_check,
            metadata=metadata,
        )
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_check: str,
    checks: list[LaunchCertificationCheck],
    blockers: list[LaunchCertificationBlocker],
    metadata: dict[str, Any] | None = None,
) -> LaunchCertificationError:
    return LaunchCertificationError.of(
        error_kind,
        error_detail,
        failed_check,
        tuple(checks),
        tuple(blockers),
        metadata,
    )


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_exists_as(path_text: Any, artifact_type: str) -> bool:
    if path_text is None or _is_url(path_text):
        return False
    path = Path(str(path_text))
    if artifact_type == "directory":
        return path.exists() and path.is_dir()
    return path.exists() and path.is_file()


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _safe_relative(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _prepare_output_paths(
    output_dir: str | Path,
    certification_id: str,
) -> tuple[Path, dict[str, Path]]:
    base_dir = Path(str(output_dir))
    base_dir.mkdir(parents=True, exist_ok=True)
    resolved_base = base_dir.resolve(strict=True)
    pack_dir = (resolved_base / certification_id).resolve()
    pack_dir.relative_to(resolved_base)
    return pack_dir, {
        "report": pack_dir / _REPORT_FILENAME,
        "summary": pack_dir / _SUMMARY_FILENAME,
        "checklist": pack_dir / _CHECKLIST_FILENAME,
        "blockers": pack_dir / _BLOCKERS_FILENAME,
        "next_steps": pack_dir / _NEXT_STEPS_FILENAME,
    }


def _artifact_record(
    name: str,
    path_text: Any,
    artifact_type: str,
    *,
    required: bool = True,
) -> LaunchCertificationArtifact:
    return LaunchCertificationArtifact.of(
        name,
        "" if path_text is None else str(path_text),
        artifact_type,
        required=required,
        exists=_path_exists_as(path_text, artifact_type),
    )


def _validate_acceptance_report(data: dict[str, Any]) -> bool:
    if "accepted" in data:
        return data.get("accepted") is True
    return data.get("ok") is True and data.get("overall_status") == "PASS"


def _markdown_summary(result: LaunchCertificationResult) -> str:
    lines = [
        "# Commercial Launch Certification Summary",
        "",
        f"- Certification id: `{result.launch_certification_id}`",
        f"- Checked at: {result.checked_at}",
        f"- Status: {result.certification_status}",
        f"- Go/no-go: {result.go_no_go}",
        f"- Readiness score: {result.readiness_score}/{result.readiness_max_score}",
        "",
        "## Evidence Summary",
        "",
    ]
    for artifact in result.artifacts:
        state = "exists" if artifact.exists else "missing"
        lines.append(f"- {artifact.artifact_name}: {state} (`{artifact.artifact_path}`)")
    lines.extend([
        "",
        "## Final Verdict",
        "",
    ])
    if result.certification_status == "PASS":
        lines.append("SCOS launch evidence supports manual first real customer outreach and delivery.")
    elif result.certification_status == "CONDITIONAL_PASS":
        lines.append("SCOS launch evidence is present, but listed blockers must be resolved before launch.")
    else:
        lines.append("SCOS launch evidence does not support launch until critical or required blockers are fixed.")
    lines.append("")
    return "\n".join(lines)


def _markdown_checklist(result: LaunchCertificationResult) -> str:
    artifact_names = {artifact.artifact_name: artifact.exists for artifact in result.artifacts}
    items = (
        ("commercial run evidence exists", artifact_names.get("commercial_run_manifest_path") is True),
        ("acceptance evidence exists", artifact_names.get("acceptance_report_path") is True),
        ("operating kit exists", artifact_names.get("operating_kit_path") is True),
        ("monetization readiness exists", artifact_names.get("monetization_readiness_report_path") is True),
        ("dry run passed", result.metadata.to_dict().get("dry_run_passed") is True),
        ("no critical blockers", not any(blocker.severity == "critical" for blocker in result.blockers)),
        ("no real PII", result.metadata.to_dict().get("pii_detected") is False),
        ("local-only evidence", result.metadata.to_dict().get("local_only_evidence") is True),
    )
    lines = ["# Launch Readiness Checklist", ""]
    for label, complete in items:
        mark = "x" if complete else " "
        lines.append(f"- [{mark}] {label}")
    lines.append("")
    return "\n".join(lines)


def _markdown_blockers(result: LaunchCertificationResult) -> str:
    lines = ["# Launch Blockers", ""]
    if not result.blockers:
        lines.append("No launch blockers detected.")
        lines.append("")
        return "\n".join(lines)
    for severity in ("critical", "error", "warning"):
        group = [blocker for blocker in result.blockers if blocker.severity == severity]
        if not group:
            continue
        lines.extend([f"## {severity.title()}", ""])
        for blocker in group:
            lines.append(f"- `{blocker.blocker_id}`: {blocker.title}")
            lines.append(f"  - Source check: {blocker.source_check}")
            lines.append(f"  - Detail: {blocker.detail}")
            lines.append(f"  - Recommended action: {blocker.recommended_action}")
        lines.append("")
    return "\n".join(lines)


def _markdown_next_steps(result: LaunchCertificationResult) -> str:
    lines = ["# Operator Next Steps", ""]
    if result.certification_status == "PASS":
        lines.extend([
            "- Prepare first outreach manually.",
            "- Use the operating kit.",
            "- Run the acceptance gate before delivery.",
            "- Keep customer PII outside SCOS evidence.",
        ])
    elif result.certification_status == "CONDITIONAL_PASS":
        lines.append("- Resolve listed blockers before real launch.")
    else:
        lines.extend([
            "- Do not launch.",
            "- Fix critical blockers first.",
        ])
    lines.append("")
    return "\n".join(lines)


def _write_pack_files(result: LaunchCertificationResult, paths: dict[str, Path]) -> None:
    paths["report"].write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
    paths["summary"].write_text(_markdown_summary(result), encoding="utf-8", newline="\n")
    paths["checklist"].write_text(_markdown_checklist(result), encoding="utf-8", newline="\n")
    paths["blockers"].write_text(_markdown_blockers(result), encoding="utf-8", newline="\n")
    paths["next_steps"].write_text(_markdown_next_steps(result), encoding="utf-8", newline="\n")


def create_commercial_launch_certification_pack(
    *,
    dry_run_report_path: str | Path,
    output_dir: str | Path,
    checked_at: str,
    certification_id: str | None = None,
    require_go: bool = True,
    require_no_critical_blockers: bool = True,
    overwrite: bool = False,
) -> LaunchCertificationResult | LaunchCertificationError:
    checks: list[LaunchCertificationCheck] = []
    blockers: list[LaunchCertificationBlocker] = []
    artifacts: list[LaunchCertificationArtifact] = []

    # validate_inputs
    if dry_run_report_path is None or str(dry_run_report_path) == "":
        _check(checks, "validate_inputs", "failure", "critical",
               error_kind="INVALID_ARGUMENTS", error_detail="dry_run_report_path is required")
        return _error("INVALID_ARGUMENTS", "dry_run_report_path is required", "validate_inputs", checks, blockers)
    if output_dir is None or str(output_dir) == "":
        _check(checks, "validate_inputs", "failure", "critical",
               error_kind="INVALID_ARGUMENTS", error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", checks, blockers)
    if not isinstance(checked_at, str) or not checked_at:
        _check(checks, "validate_inputs", "failure", "critical",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", checks, blockers)
    if _is_url(dry_run_report_path) or _is_url(output_dir):
        _check(checks, "validate_inputs", "failure", "critical",
               error_kind="INVALID_ARGUMENTS", error_detail="paths must be local filesystem paths, not URLs")
        return _error(
            "INVALID_ARGUMENTS",
            "paths must be local filesystem paths, not URLs",
            "validate_inputs",
            checks,
            blockers,
        )
    dry_path = Path(str(dry_run_report_path))
    if not dry_path.exists() or not dry_path.is_file():
        _check(checks, "validate_inputs", "failure", "critical", artifact_path=str(dry_path),
               error_kind="INPUT_NOT_FOUND", error_detail="dry_run_report_path does not exist or is not a file")
        return _error(
            "INPUT_NOT_FOUND",
            "dry_run_report_path does not exist or is not a file",
            "validate_inputs",
            checks,
            blockers,
            {"path": str(dry_path)},
        )
    _check(checks, "validate_inputs", "success", "info", artifact_path=str(dry_path))

    # load_dry_run_report
    try:
        dry_run = _load_json_file(dry_path)
    except (OSError, ValueError):
        _check(checks, "load_dry_run_report", "failure", "critical", artifact_path=str(dry_path),
               error_kind="INVALID_DRY_RUN_REPORT", error_detail="dry-run report is not valid JSON")
        return _error("INVALID_DRY_RUN_REPORT", "dry-run report is not valid JSON",
                      "load_dry_run_report", checks, blockers, {"path": str(dry_path)})
    if not isinstance(dry_run, dict):
        _check(checks, "load_dry_run_report", "failure", "critical", artifact_path=str(dry_path),
               error_kind="INVALID_DRY_RUN_REPORT", error_detail="dry-run report must be a JSON object")
        return _error("INVALID_DRY_RUN_REPORT", "dry-run report must be a JSON object",
                      "load_dry_run_report", checks, blockers, {"path": str(dry_path)})
    missing_keys = tuple(key for key in _REQUIRED_DRY_RUN_KEYS if key not in dry_run)
    if missing_keys:
        _check(checks, "load_dry_run_report", "failure", "critical", artifact_path=str(dry_path),
               error_kind="INVALID_DRY_RUN_REPORT", error_detail="dry-run report is missing required keys",
               metadata={"missing_keys": list(missing_keys)})
        return _error("INVALID_DRY_RUN_REPORT", "dry-run report is missing required keys",
                      "load_dry_run_report", checks, blockers, {"missing_keys": list(missing_keys)})
    _check(checks, "load_dry_run_report", "success", "info", artifact_path=str(dry_path))

    # validate_no_real_customer_pii
    customer_case = dry_run.get("customer_case")
    metadata = dry_run.get("metadata")
    pii_detected = _contains_sensitive_key(customer_case) or _contains_sensitive_key(metadata)
    if pii_detected:
        _blocker(
            blockers,
            "BLOCKER_PII_DETECTED",
            "pii",
            "critical",
            "PII-like key detected",
            "The dry-run customer case or metadata contains a sensitive contact-like key.",
            "Remove real customer contact data from SCOS evidence before certification.",
            "validate_no_real_customer_pii",
        )
        _check(checks, "validate_no_real_customer_pii", "failure", "critical",
               error_kind="PII_DETECTED", error_detail="PII-like key detected")
        return _error("PII_DETECTED", "PII-like key detected",
                      "validate_no_real_customer_pii", checks, blockers)
    _check(checks, "validate_no_real_customer_pii", "success", "info")

    resolved_certification_id = (
        str(certification_id)
        if certification_id is not None
        else f"commercial-launch-certification-{dry_run.get('dry_run_id')}"
    )

    # validate_path_containment
    try:
        pack_dir, output_paths = _prepare_output_paths(output_dir, resolved_certification_id)
    except (OSError, ValueError):
        _check(checks, "validate_path_containment", "failure", "critical",
               error_kind="PATH_CONTAINMENT_FAILED",
               error_detail="generated output must stay under output_dir")
        return _error(
            "PATH_CONTAINMENT_FAILED",
            "generated output must stay under output_dir",
            "validate_path_containment",
            checks,
            blockers,
        )
    if pack_dir.exists() and not overwrite:
        _check(checks, "validate_path_containment", "failure", "error", artifact_path=str(pack_dir),
               error_kind="OUTPUT_ALREADY_EXISTS",
               error_detail="launch certification pack already exists and overwrite is False")
        return _error(
            "OUTPUT_ALREADY_EXISTS",
            "launch certification pack already exists and overwrite is False",
            "validate_path_containment",
            checks,
            blockers,
            {"path": str(pack_dir)},
        )
    if not all(_safe_relative(path, Path(str(output_dir))) for path in output_paths.values()):
        _check(checks, "validate_path_containment", "failure", "critical",
               error_kind="PATH_CONTAINMENT_FAILED",
               error_detail="generated file path escaped output_dir")
        return _error("PATH_CONTAINMENT_FAILED", "generated file path escaped output_dir",
                      "validate_path_containment", checks, blockers)
    _check(checks, "validate_path_containment", "success", "info", artifact_path=str(pack_dir))

    # validate_required_evidence_artifacts
    evidence_specs = (
        ("commercial_run_manifest_path", "file"),
        ("acceptance_report_path", "file"),
        ("operating_kit_path", "directory"),
        ("monetization_readiness_report_path", "file"),
        ("dry_run_report_path", "file"),
    )
    missing_evidence: list[str] = []
    for name, artifact_type in evidence_specs:
        artifact = _artifact_record(name, dry_run.get(name), artifact_type)
        artifacts.append(artifact)
        if not artifact.exists:
            missing_evidence.append(name)
    if missing_evidence:
        detail = "required launch evidence is missing"
        _check(checks, "validate_required_evidence_artifacts", "failure", "critical",
               error_kind="MISSING_EVIDENCE", error_detail=detail,
               metadata={"missing_evidence": missing_evidence})
        return _error("MISSING_EVIDENCE", detail, "validate_required_evidence_artifacts",
                      checks, blockers, {"missing_evidence": missing_evidence})
    _check(checks, "validate_required_evidence_artifacts", "success", "info",
           metadata={"artifact_count": len(artifacts)})

    # validate_dry_run_pass_status
    dry_run_passed = dry_run.get("passed") is True
    dry_run_go = str(dry_run.get("go_no_go"))
    if not dry_run_passed:
        severity = "error" if require_go else "warning"
        _blocker(blockers, "BLOCKER_DRY_RUN_NOT_PASSED", "dry_run", severity,
                 "Dry run did not pass", "Stage 4.8 reports passed=false.",
                 "Resolve dry-run blockers before launch.", "validate_dry_run_pass_status",
                 metadata={"passed": False})
    if dry_run_go != "GO":
        severity = "error" if require_go else "warning"
        _blocker(blockers, "BLOCKER_DRY_RUN_NOT_GO", "dry_run", severity,
                 "Dry run is not GO", f"Stage 4.8 go_no_go is {dry_run_go}.",
                 "Resolve dry-run go/no-go blockers before launch.",
                 "validate_dry_run_pass_status", metadata={"go_no_go": dry_run_go})
    _check(
        checks,
        "validate_dry_run_pass_status",
        "success" if dry_run_passed and dry_run_go == "GO" else "failure",
        "info" if dry_run_passed and dry_run_go == "GO" else ("error" if require_go else "warning"),
        metadata={"passed": dry_run_passed, "go_no_go": dry_run_go, "require_go": bool(require_go)},
    )

    # validate_acceptance_evidence
    acceptance_path = Path(str(dry_run.get("acceptance_report_path")))
    try:
        acceptance = _load_json_file(acceptance_path)
    except (OSError, ValueError):
        _check(checks, "validate_acceptance_evidence", "failure", "critical",
               artifact_path=str(acceptance_path), error_kind="INVALID_ACCEPTANCE_REPORT",
               error_detail="acceptance report is not valid JSON")
        return _error("INVALID_ACCEPTANCE_REPORT", "acceptance report is not valid JSON",
                      "validate_acceptance_evidence", checks, blockers, {"path": str(acceptance_path)})
    if not isinstance(acceptance, dict):
        _check(checks, "validate_acceptance_evidence", "failure", "critical",
               artifact_path=str(acceptance_path), error_kind="INVALID_ACCEPTANCE_REPORT",
               error_detail="acceptance report must be a JSON object")
        return _error("INVALID_ACCEPTANCE_REPORT", "acceptance report must be a JSON object",
                      "validate_acceptance_evidence", checks, blockers, {"path": str(acceptance_path)})
    accepted = _validate_acceptance_report(acceptance)
    if not accepted:
        severity = "error" if require_go else "warning"
        _blocker(blockers, "BLOCKER_ACCEPTANCE_NOT_ACCEPTED", "acceptance", severity,
                 "Acceptance evidence is not accepted",
                 "Acceptance evidence is not accepted for final launch certification.",
                 "Run acceptance review to PASS before launch.", "validate_acceptance_evidence")
    _check(checks, "validate_acceptance_evidence", "success" if accepted else "failure",
           "info" if accepted else ("error" if require_go else "warning"),
           artifact_path=str(acceptance_path), metadata={"accepted": accepted})

    # validate_monetization_readiness_evidence
    readiness_path = Path(str(dry_run.get("monetization_readiness_report_path")))
    try:
        readiness = _load_json_file(readiness_path)
    except (OSError, ValueError):
        _check(checks, "validate_monetization_readiness_evidence", "failure", "critical",
               artifact_path=str(readiness_path), error_kind="INVALID_READINESS_REPORT",
               error_detail="monetization readiness report is not valid JSON")
        return _error("INVALID_READINESS_REPORT", "monetization readiness report is not valid JSON",
                      "validate_monetization_readiness_evidence", checks, blockers, {"path": str(readiness_path)})
    if not isinstance(readiness, dict):
        _check(checks, "validate_monetization_readiness_evidence", "failure", "critical",
               artifact_path=str(readiness_path), error_kind="INVALID_READINESS_REPORT",
               error_detail="monetization readiness report must be a JSON object")
        return _error("INVALID_READINESS_REPORT", "monetization readiness report must be a JSON object",
                      "validate_monetization_readiness_evidence", checks, blockers, {"path": str(readiness_path)})
    readiness_go = str(readiness.get("go_no_go"))
    if readiness_go != "GO":
        severity = "error" if require_go else "warning"
        _blocker(blockers, "BLOCKER_READINESS_NOT_GO", "monetization_readiness", severity,
                 "Monetization readiness is not GO",
                 f"Monetization readiness evidence reports {readiness_go}.",
                 "Resolve readiness gaps before launch.", "validate_monetization_readiness_evidence",
                 metadata={"go_no_go": readiness_go})
    _check(checks, "validate_monetization_readiness_evidence",
           "success" if readiness_go == "GO" else "failure",
           "info" if readiness_go == "GO" else ("error" if require_go else "warning"),
           artifact_path=str(readiness_path), metadata={"go_no_go": readiness_go})

    # validate_operating_kit_evidence
    kit_path = Path(str(dry_run.get("operating_kit_path")))
    missing_kit_files = [name for name in _REQUIRED_OPERATING_KIT_FILES if not (kit_path / name).is_file()]
    if missing_kit_files:
        _blocker(blockers, "BLOCKER_OPERATING_KIT_INCOMPLETE", "operating_kit", "error",
                 "Operating kit evidence is incomplete",
                 "One or more documented operating kit files are missing.",
                 "Regenerate or repair the operating kit before launch.",
                 "validate_operating_kit_evidence", metadata={"missing_files": missing_kit_files})
    _check(checks, "validate_operating_kit_evidence",
           "success" if not missing_kit_files else "failure",
           "info" if not missing_kit_files else "error",
           artifact_path=str(kit_path), metadata={"missing_files": missing_kit_files})

    # validate_blockers
    dry_blockers = dry_run.get("blockers")
    if isinstance(dry_blockers, list):
        for idx, dry_blocker in enumerate(dry_blockers):
            if not isinstance(dry_blocker, dict):
                continue
            severity = str(dry_blocker.get("severity", "warning"))
            if severity not in ("warning", "error", "critical"):
                severity = "warning"
            _blocker(
                blockers,
                str(dry_blocker.get("blocker_id") or f"BLOCKER_DRY_RUN_{idx + 1}"),
                str(dry_blocker.get("category") or "dry_run"),
                severity,
                str(dry_blocker.get("title") or "Dry-run blocker"),
                str(dry_blocker.get("detail") or "Stage 4.8 recorded a launch blocker."),
                str(dry_blocker.get("recommended_action") or "Resolve the Stage 4.8 blocker before launch."),
                "validate_blockers",
                metadata={"source_step": str(dry_blocker.get("source_step") or "")},
            )
    critical_count = sum(1 for blocker in blockers if blocker.severity == "critical")
    _check(checks, "validate_blockers",
           "success" if critical_count == 0 else "failure",
           "info" if critical_count == 0 else "critical",
           metadata={"critical_blocker_count": critical_count,
                     "require_no_critical_blockers": bool(require_no_critical_blockers)})

    require_go_failure = require_go and (
        not dry_run_passed or dry_run_go != "GO" or not accepted or readiness_go != "GO"
    )
    critical_failure = require_no_critical_blockers and critical_count > 0
    if require_go_failure or critical_failure:
        certification_status = "FAIL"
    elif blockers:
        certification_status = "CONDITIONAL_PASS"
    else:
        certification_status = "PASS"

    pack_dir.mkdir(parents=True, exist_ok=True)
    result = LaunchCertificationResult(
        ok=True,
        schema_version=COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION,
        certification_status=certification_status,
        launch_certification_id=resolved_certification_id,
        checked_at=checked_at,
        dry_run_report_path=str(dry_path),
        output_dir=str(pack_dir),
        launch_certification_report_path=str(output_paths["report"]),
        launch_certification_summary_path=str(output_paths["summary"]),
        launch_readiness_checklist_path=str(output_paths["checklist"]),
        launch_blockers_path=str(output_paths["blockers"]),
        operator_next_steps_path=str(output_paths["next_steps"]),
        readiness_score=int(dry_run.get("readiness_score")),
        readiness_max_score=int(dry_run.get("readiness_max_score")),
        go_no_go=dry_run_go,
        checks=tuple(checks),
        blockers=tuple(blockers),
        artifacts=tuple(artifacts),
        metadata=FrozenMap.from_mapping(
            {
                "generator": "scos.commercial.launch_certification_pack",
                "dry_run_id": str(dry_run.get("dry_run_id")),
                "dry_run_passed": dry_run_passed,
                "require_go": bool(require_go),
                "require_no_critical_blockers": bool(require_no_critical_blockers),
                "blocker_count": len(blockers),
                "critical_blocker_count": critical_count,
                "pii_detected": False,
                "local_only_evidence": True,
            }
        ),
    )

    try:
        _write_pack_files(result, output_paths)
    except OSError as exc:
        _check(checks, "write_launch_certification_pack", "failure", "critical",
               error_kind="OUTPUT_WRITE_FAILED",
               error_detail="launch certification pack could not be written",
               metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "launch certification pack could not be written",
                      "write_launch_certification_pack", checks, blockers,
                      {"os_error": type(exc).__name__})

    return result


__all__ = ("create_commercial_launch_certification_pack",)
