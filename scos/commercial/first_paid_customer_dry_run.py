"""SCOS Stage 4.8 first paid customer dry run.

Rehearses one complete first paid customer delivery from intake through
monetization readiness using existing public Stage 4 APIs. The layer is
deterministic, local-only, and writes one dry-run report. It does not contact
external services, create customer records, or alter upstream contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .acceptance_models import CommercialAcceptanceError, CommercialAcceptanceReport
    from .acceptance_gate import run_commercial_acceptance_gate
    from .customer_kit import generate_first_customer_kit
    from .customer_kit_models import CustomerKitError, CustomerKitResult
    from .dry_run_models import (
        FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION,
        DryRunBlocker,
        DryRunStep,
        FirstPaidCustomerDryRunError,
        FirstPaidCustomerDryRunResult,
        SyntheticCustomerCase,
    )
    from .monetization_models import MonetizationReadinessError, MonetizationReadinessResult
    from .monetization_readiness import review_monetization_readiness
    from .report_models import FrozenMap
    from .run_models import CommercialRunError, CommercialRunResult
    from .run_orchestrator import run_commercial_delivery
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from acceptance_models import CommercialAcceptanceError, CommercialAcceptanceReport
    from acceptance_gate import run_commercial_acceptance_gate
    from customer_kit import generate_first_customer_kit
    from customer_kit_models import CustomerKitError, CustomerKitResult
    from dry_run_models import (
        FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION,
        DryRunBlocker,
        DryRunStep,
        FirstPaidCustomerDryRunError,
        FirstPaidCustomerDryRunResult,
        SyntheticCustomerCase,
    )
    from monetization_models import MonetizationReadinessError, MonetizationReadinessResult
    from monetization_readiness import review_monetization_readiness
    from report_models import FrozenMap
    from run_models import CommercialRunError, CommercialRunResult
    from run_orchestrator import run_commercial_delivery

_URL_PREFIXES = ("http://", "https://")
_REPORT_FILENAME = "first_paid_customer_dry_run_report.json"
_READINESS_FILENAME = "monetization_readiness_report.json"
_RISK_FILENAME = "risk_checklist.md"
_SENSITIVE_METADATA_KEYS = ("phone", "email", "address")


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _default_customer_case() -> SyntheticCustomerCase:
    return SyntheticCustomerCase.of(
        customer_id="synthetic-first-customer-001",
        business_name="Synthetic Local Clinic",
        business_type="clinic",
        target_offer="AI Content Delivery Audit",
        target_price="4900 THB dry-run offer",
        intake_summary="Synthetic dry-run customer for first paid customer rehearsal.",
        expected_deliverables=(
            "commercial_report",
            "delivery_package",
            "acceptance_report",
            "first_customer_operating_kit",
            "monetization_readiness_report",
        ),
        metadata={"case_type": "synthetic", "contains_real_pii": False},
    )


def _metadata_keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, FrozenMap):
        value = value.to_dict()
    if not isinstance(value, dict):
        return ()
    return tuple(str(key).lower() for key in value)


def _has_sensitive_metadata(case: SyntheticCustomerCase) -> bool:
    keys = _metadata_keys(case.metadata)
    return any(flag in key for key in keys for flag in _SENSITIVE_METADATA_KEYS)


def _blocker(
    blocker_id: str,
    category: str,
    severity: str,
    title: str,
    detail: str,
    recommended_action: str,
    source_step: str,
    metadata: dict[str, Any] | None = None,
) -> DryRunBlocker:
    return DryRunBlocker.of(
        blocker_id,
        category,
        severity,
        title,
        detail,
        recommended_action,
        source_step,
        metadata=metadata,
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    steps: list[DryRunStep],
    blockers: list[DryRunBlocker],
    metadata: dict[str, Any] | None = None,
) -> FirstPaidCustomerDryRunError:
    return FirstPaidCustomerDryRunError.of(
        error_kind,
        error_detail,
        failed_step,
        tuple(steps),
        tuple(blockers),
        metadata,
    )


def _acceptance_report_path(output_dir: Path, report: CommercialAcceptanceReport) -> Path:
    return output_dir / report.certification_id.replace(":", "_") / "commercial_acceptance_report.json"


def _write_synthetic_risk_file(kit_dir: Path, checked_at: str) -> Path:
    target = kit_dir / _RISK_FILENAME
    text = (
        "# Synthetic Dry-Run Risk Checklist\n\n"
        "This file is synthetic dry-run evidence for Stage 4.8 rehearsal only.\n"
        "It is not real customer advice and must be replaced before serving a real customer.\n\n"
        f"- Checked at: {checked_at}\n"
        "- [ ] Scope reviewed for rehearsal\n"
        "- [ ] Handoff artifacts reviewed for rehearsal\n"
        "- [ ] Operator escalation path reviewed for rehearsal\n"
    )
    target.write_text(text, encoding="utf-8", newline="\n")
    return target


def run_first_paid_customer_dry_run(
    *,
    knowledge_service: Any,
    output_dir: str | Path,
    checked_at: str,
    customer_case: SyntheticCustomerCase | None = None,
    run_id: str = "first-paid-customer-dry-run",
    delivery_id: str | None = None,
    video_path: str | Path | None = None,
    source_manifest_path: str | Path | None = None,
    overwrite: bool = False,
    require_go: bool = True,
    add_synthetic_risk_checklist: bool = True,
) -> FirstPaidCustomerDryRunResult | FirstPaidCustomerDryRunError:
    steps: list[DryRunStep] = []
    blockers: list[DryRunBlocker] = []

    # 1. validate_inputs
    if knowledge_service is None:
        steps.append(DryRunStep.of("validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
                                   error_detail="knowledge_service is required"))
        return _error("INVALID_ARGUMENTS", "knowledge_service is required", "validate_inputs", steps, blockers)
    if output_dir is None or str(output_dir) == "":
        steps.append(DryRunStep.of("validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
                                   error_detail="output_dir is required"))
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", steps, blockers)
    if not isinstance(checked_at, str) or not checked_at:
        steps.append(DryRunStep.of("validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
                                   error_detail="checked_at is required"))
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", steps, blockers)
    for label, value in (
        ("output_dir", output_dir),
        ("video_path", video_path),
        ("source_manifest_path", source_manifest_path),
    ):
        if _is_url(value):
            steps.append(DryRunStep.of("validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
                                       error_detail="paths must be local filesystem paths, not URLs",
                                       metadata={"argument": label, "path": str(value)}))
            return _error(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                "validate_inputs",
                steps,
                blockers,
                {"argument": label, "path": str(value)},
            )
    for label, value in (("video_path", video_path), ("source_manifest_path", source_manifest_path)):
        if value is None:
            continue
        path = Path(str(value))
        if not path.exists() or not path.is_file():
            steps.append(DryRunStep.of("validate_inputs", "failure", error_kind="INPUT_NOT_FOUND",
                                       error_detail=f"{label} does not exist or is not a file",
                                       metadata={"argument": label, "path": str(path)}))
            return _error(
                "INPUT_NOT_FOUND",
                f"{label} does not exist or is not a file",
                "validate_inputs",
                steps,
                blockers,
                {"argument": label, "path": str(path)},
            )

    base_dir = Path(str(output_dir))
    steps.append(DryRunStep.of("validate_inputs", "success", metadata={"output_dir": str(base_dir)}))

    # 2. prepare_customer_case
    case = customer_case if customer_case is not None else _default_customer_case()
    if not isinstance(case, SyntheticCustomerCase):
        steps.append(DryRunStep.of("prepare_customer_case", "failure", error_kind="INVALID_CUSTOMER_CASE",
                                   error_detail="customer_case must be a SyntheticCustomerCase"))
        return _error(
            "INVALID_CUSTOMER_CASE",
            "customer_case must be a SyntheticCustomerCase",
            "prepare_customer_case",
            steps,
            blockers,
        )
    if _has_sensitive_metadata(case):
        steps.append(DryRunStep.of("prepare_customer_case", "failure", error_kind="INVALID_CUSTOMER_CASE",
                                   error_detail="customer metadata contains sensitive contact keys"))
        return _error(
            "INVALID_CUSTOMER_CASE",
            "customer metadata contains sensitive contact keys",
            "prepare_customer_case",
            steps,
            blockers,
        )
    steps.append(DryRunStep.of("prepare_customer_case", "success", metadata={"customer_id": case.customer_id}))

    run_output_dir = base_dir / "commercial_run"
    acceptance_output_dir = base_dir / "acceptance"
    kit_output_dir = base_dir / "operating_kit"
    readiness_output_path = base_dir / _READINESS_FILENAME
    dry_run_report_path = base_dir / _REPORT_FILENAME

    # 3. run_commercial_delivery
    commercial_run = run_commercial_delivery(
        knowledge_service=knowledge_service,
        run_id=run_id,
        output_dir=run_output_dir,
        created_at=checked_at,
        delivery_id=delivery_id,
        video_path=video_path,
        source_manifest_path=source_manifest_path,
        overwrite=overwrite,
        qa_status="dry_run",
        risks=(
            {
                "risk_id": "synthetic-dry-run-risk",
                "risk_type": "dry_run",
                "source": "stage_4_8",
                "detail": "Synthetic rehearsal risk record.",
            },
        ),
    )
    if not isinstance(commercial_run, CommercialRunResult):
        detail = "commercial dry-run delivery failed"
        meta: dict[str, Any] = {}
        if isinstance(commercial_run, CommercialRunError):
            meta = {"commercial_run_error": commercial_run.to_dict()}
            detail = commercial_run.error_detail
        steps.append(DryRunStep.of("run_commercial_delivery", "failure", error_kind="COMMERCIAL_RUN_FAILED",
                                   error_detail=detail, metadata=meta))
        return _error("COMMERCIAL_RUN_FAILED", detail, "run_commercial_delivery", steps, blockers, meta)
    steps.append(DryRunStep.of("run_commercial_delivery", "success",
                               artifact_path=commercial_run.manifest_path,
                               metadata={"run_id": commercial_run.run_id}))

    # 4. run_acceptance_gate
    acceptance = run_commercial_acceptance_gate(
        commercial_run_result=commercial_run,
        output_dir=acceptance_output_dir,
        created_at=checked_at,
    )
    if isinstance(acceptance, CommercialAcceptanceError):
        detail = acceptance.error_detail
        blockers.append(_blocker(
            "BLOCKER_ACCEPTANCE_ERROR",
            "acceptance",
            "critical",
            "Acceptance gate failed",
            detail,
            "Resolve the Stage 4.5 acceptance error before dry-run rehearsal.",
            "run_acceptance_gate",
            {"acceptance_error": acceptance.to_dict()},
        ))
        steps.append(DryRunStep.of("run_acceptance_gate", "failure", error_kind="ACCEPTANCE_FAILED",
                                   error_detail=detail))
        return _error("ACCEPTANCE_FAILED", detail, "run_acceptance_gate", steps, blockers)
    acceptance_report_path = _acceptance_report_path(acceptance_output_dir, acceptance)
    if not acceptance.ok:
        blockers.append(_blocker(
            "BLOCKER_ACCEPTANCE_NOT_READY",
            "acceptance",
            "critical",
            "Acceptance did not pass",
            f"Acceptance status is {acceptance.overall_status}.",
            "Fix acceptance blockers before accepting a real first customer.",
            "run_acceptance_gate",
            {"overall_status": acceptance.overall_status},
        ))
    steps.append(DryRunStep.of("run_acceptance_gate", "success" if acceptance.ok else "failure",
                               artifact_path=str(acceptance_report_path),
                               error_kind=None if acceptance.ok else "ACCEPTANCE_FAILED",
                               error_detail=None if acceptance.ok else "acceptance report did not PASS",
                               metadata={"overall_status": acceptance.overall_status}))

    # 5. generate_operating_kit
    kit = generate_first_customer_kit(
        acceptance_report_path=acceptance_report_path,
        output_dir=kit_output_dir,
        customer_id=case.customer_id,
        created_at=checked_at,
        customer_name=case.business_name,
        offer_name=case.target_offer,
        overwrite=overwrite,
    )
    if not isinstance(kit, CustomerKitResult):
        detail = "operating kit generation failed"
        meta = {}
        if isinstance(kit, CustomerKitError):
            detail = kit.error_detail
            meta = {"operating_kit_error": kit.to_dict()}
        blockers.append(_blocker(
            "BLOCKER_OPERATING_KIT_FAILED",
            "operating_kit",
            "critical",
            "Operating kit generation failed",
            detail,
            "Generate a valid Stage 4.6 operating kit before dry-run rehearsal.",
            "generate_operating_kit",
            meta,
        ))
        steps.append(DryRunStep.of("generate_operating_kit", "failure", error_kind="OPERATING_KIT_FAILED",
                                   error_detail=detail, metadata=meta))
        return _error("OPERATING_KIT_FAILED", detail, "generate_operating_kit", steps, blockers, meta)
    kit_dir = Path(kit.output_dir)
    steps.append(DryRunStep.of("generate_operating_kit", "success", artifact_path=kit.output_dir,
                               metadata={"kit_id": kit.kit_id}))

    # 6. ensure_required_readiness_artifacts
    if add_synthetic_risk_checklist:
        try:
            risk_path = _write_synthetic_risk_file(kit_dir, checked_at)
        except OSError as exc:
            detail = "synthetic risk checklist could not be written"
            steps.append(DryRunStep.of("ensure_required_readiness_artifacts", "failure",
                                       error_kind="OUTPUT_WRITE_FAILED", error_detail=detail,
                                       metadata={"os_error": type(exc).__name__}))
            return _error("OUTPUT_WRITE_FAILED", detail, "ensure_required_readiness_artifacts", steps, blockers)
        steps.append(DryRunStep.of("ensure_required_readiness_artifacts", "success",
                                   artifact_path=str(risk_path),
                                   metadata={"synthetic_risk_checklist": True}))
    else:
        blockers.append(_blocker(
            "BLOCKER_RISK_CHECKLIST_NOT_ADDED",
            "risk",
            "warning",
            "Synthetic risk checklist disabled",
            "Risk readiness will depend on existing operating-kit artifacts.",
            "Enable the synthetic risk checklist or provide an explicit risk file.",
            "ensure_required_readiness_artifacts",
        ))
        steps.append(DryRunStep.of("ensure_required_readiness_artifacts", "skipped",
                                   metadata={"synthetic_risk_checklist": False}))

    # 7. run_monetization_readiness
    readiness = review_monetization_readiness(
        acceptance_report_path=acceptance_report_path,
        operating_kit_path=kit_dir,
        checked_at=checked_at,
        output_path=readiness_output_path,
    )
    if isinstance(readiness, MonetizationReadinessError):
        detail = readiness.error_detail
        blockers.append(_blocker(
            "BLOCKER_MONETIZATION_READINESS_ERROR",
            "monetization_readiness",
            "critical",
            "Monetization readiness review failed",
            detail,
            "Resolve the Stage 4.7 review error before first customer rehearsal.",
            "run_monetization_readiness",
            {"readiness_error": readiness.to_dict()},
        ))
        steps.append(DryRunStep.of("run_monetization_readiness", "failure",
                                   error_kind="MONETIZATION_READINESS_FAILED",
                                   error_detail=detail))
        return _error("MONETIZATION_READINESS_FAILED", detail, "run_monetization_readiness", steps, blockers)

    for gap in readiness.gaps:
        if gap.blocking:
            blockers.append(_blocker(
                f"BLOCKER_{gap.gap_id}",
                gap.category,
                "critical" if gap.severity == "critical" else "error",
                gap.title,
                gap.detail,
                gap.recommended_action,
                "run_monetization_readiness",
                {"gap_id": gap.gap_id},
            ))
    if readiness.go_no_go != "GO":
        blockers.append(_blocker(
            "BLOCKER_MONETIZATION_NOT_GO",
            "monetization_readiness",
            "error",
            "Monetization readiness is not GO",
            f"Stage 4.7 returned {readiness.go_no_go}.",
            "Resolve monetization readiness gaps before accepting a real first customer.",
            "run_monetization_readiness",
            {"go_no_go": readiness.go_no_go, "readiness_level": readiness.readiness_level},
        ))
    steps.append(DryRunStep.of("run_monetization_readiness", "success",
                               artifact_path=str(readiness_output_path),
                               metadata={"go_no_go": readiness.go_no_go,
                                         "readiness_score": readiness.score}))

    critical_blockers = [b for b in blockers if b.severity == "critical"]
    blocking_blockers = [b for b in blockers if b.severity in ("error", "critical")]
    passed = (
        commercial_run.ok
        and acceptance.ok
        and kit.ok
        and (readiness.go_no_go == "GO" if require_go else True)
        and not blocking_blockers
    )

    # 8-9. write_dry_run_report, summarize_go_no_go
    steps.append(DryRunStep.of("write_dry_run_report", "success", artifact_path=str(dry_run_report_path)))
    steps.append(DryRunStep.of("summarize_go_no_go", "success",
                               metadata={"passed": bool(passed), "go_no_go": readiness.go_no_go}))
    result = FirstPaidCustomerDryRunResult(
        ok=True,
        schema_version=FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION,
        passed=passed,
        dry_run_id=f"first-paid-customer-dry-run-{case.customer_id}",
        checked_at=checked_at,
        customer_case=case,
        go_no_go=readiness.go_no_go,
        readiness_level=readiness.readiness_level,
        readiness_score=readiness.score,
        readiness_max_score=readiness.max_score,
        commercial_run_manifest_path=commercial_run.manifest_path,
        acceptance_report_path=str(acceptance_report_path),
        operating_kit_path=kit.output_dir,
        monetization_readiness_report_path=str(readiness_output_path),
        dry_run_report_path=str(dry_run_report_path),
        steps=tuple(steps),
        blockers=tuple(blockers),
        metadata=FrozenMap.from_mapping(
            {
                "runner": "scos.commercial.first_paid_customer_dry_run",
                "require_go": bool(require_go),
                "add_synthetic_risk_checklist": bool(add_synthetic_risk_checklist),
                "critical_blocker_count": len(critical_blockers),
                "blocking_blocker_count": len(blocking_blockers),
                "blocker_count": len(blockers),
            }
        ),
    )
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        dry_run_report_path.write_text(_json_text(result.to_dict()), encoding="utf-8", newline="\n")
    except OSError as exc:
        detail = "first paid customer dry-run report could not be written"
        steps = steps[:-2]
        steps.append(DryRunStep.of("write_dry_run_report", "failure",
                                   error_kind="OUTPUT_WRITE_FAILED", error_detail=detail,
                                   metadata={"os_error": type(exc).__name__}))
        return _error("OUTPUT_WRITE_FAILED", detail, "write_dry_run_report", steps, blockers)

    return result


__all__ = ("run_first_paid_customer_dry_run",)
