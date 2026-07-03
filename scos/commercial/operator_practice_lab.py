"""SCOS Stage 4.10 operator practice lab.

Runs deterministic synthetic practice scenarios through the existing rehearsal
and launch certification boundaries, then writes local practice guidance for an
operator. This module is practice-only and does not create ready-to-send copy.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

try:
    from .dry_run_models import (
        FirstPaidCustomerDryRunError,
        FirstPaidCustomerDryRunResult,
        SyntheticCustomerCase,
    )
    from .first_paid_customer_dry_run import run_first_paid_customer_dry_run
    from .launch_certification_models import LaunchCertificationError, LaunchCertificationResult
    from .launch_certification_pack import create_commercial_launch_certification_pack
    from .practice_models import (
        OPERATOR_PRACTICE_SCHEMA_VERSION,
        OperatorPracticeError,
        OperatorPracticeResult,
        PracticeObservation,
        PracticeScenario,
        PracticeStep,
    )
    from .report_models import FrozenMap
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from dry_run_models import (
        FirstPaidCustomerDryRunError,
        FirstPaidCustomerDryRunResult,
        SyntheticCustomerCase,
    )
    from first_paid_customer_dry_run import run_first_paid_customer_dry_run
    from launch_certification_models import LaunchCertificationError, LaunchCertificationResult
    from launch_certification_pack import create_commercial_launch_certification_pack
    from practice_models import (
        OPERATOR_PRACTICE_SCHEMA_VERSION,
        OperatorPracticeError,
        OperatorPracticeResult,
        PracticeObservation,
        PracticeScenario,
        PracticeStep,
    )
    from report_models import FrozenMap

_URL_PREFIXES = ("http://", "https://")
_SENSITIVE_KEY_MARKERS = ("phone", "email", "address")

_SUMMARY_FILENAME = "practice_summary.json"
_WALKTHROUGH_FILENAME = "practice_walkthrough.md"
_CUSTOMER_FILES_FILENAME = "customer_facing_files.md"
_INTERNAL_FILES_FILENAME = "internal_evidence_files.md"
_OBSERVATIONS_FILENAME = "operator_observations.md"

_CUSTOMER_FILE_NAMES = (
    "report.md",
    "qa_summary.md",
    "improvement_plan.md",
    "customer_intake_checklist.md",
    "delivery_handoff.md",
    "acceptance_certificate.md",
    "pricing_offer_checklist.md",
)

_SCENARIO_DATA: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "clinic-ready",
        "title": "Synthetic Clinic Ready Scenario",
        "business_type": "clinic",
        "target_offer": "AI Content & Booking Readiness Audit",
        "target_price": "4900 THB practice offer",
        "operator_goal": "Practice a clean end-to-end customer-ready delivery.",
        "expected_outcome": "PASS or GO-ready practice output.",
        "required_observations": (
            "Confirm the report is understandable without engineering context.",
            "Confirm customer-facing files are separated from internal evidence.",
        ),
        "metadata": {"training_focus": "clean_end_to_end"},
    },
    {
        "scenario_id": "clinic-missing-offer",
        "title": "Synthetic Clinic Missing Offer Scenario",
        "business_type": "clinic",
        "target_offer": "Missing or unclear offer",
        "target_price": "4900 THB practice offer",
        "operator_goal": "Practice identifying offer-readiness blockers.",
        "expected_outcome": "CONDITIONAL or blocker-documented output.",
        "required_observations": (
            "Review whether the offer is specific enough for a real handoff.",
            "Write down what the operator would clarify before outreach.",
        ),
        "metadata": {"training_focus": "offer_clarity"},
    },
    {
        "scenario_id": "spa-low-content",
        "title": "Synthetic Spa Low Content Scenario",
        "business_type": "spa",
        "target_offer": "Local spa content audit",
        "target_price": "2900 THB practice offer",
        "operator_goal": "Practice a lower-content business case.",
        "expected_outcome": "Practice output with content gap observations.",
        "required_observations": (
            "Note whether the sample has enough source material to explain value.",
            "Identify what extra examples the operator would request.",
        ),
        "metadata": {"training_focus": "content_depth"},
    },
    {
        "scenario_id": "creator-video-audit",
        "title": "Synthetic Creator Video Audit Scenario",
        "business_type": "creator",
        "target_offer": "Video performance audit",
        "target_price": "1900 THB practice offer",
        "operator_goal": "Practice creator-focused delivery language.",
        "expected_outcome": "Practice output focused on video/content improvement.",
        "required_observations": (
            "Check whether the improvement notes are useful to a creator.",
            "Confirm internal evidence is not mixed into customer-facing files.",
        ),
        "metadata": {"training_focus": "creator_review"},
    },
    {
        "scenario_id": "restaurant-local-promo",
        "title": "Synthetic Restaurant Local Promo Scenario",
        "business_type": "restaurant",
        "target_offer": "Local promotion content audit",
        "target_price": "1900 THB practice offer",
        "operator_goal": "Practice local business promotional audit.",
        "expected_outcome": "Practice output focused on CTA, offer, and repeatable content.",
        "required_observations": (
            "Check whether the call-to-action is clear enough for a local business.",
            "Record what repeatable content idea needs operator review.",
        ),
        "metadata": {"training_focus": "local_promo"},
    },
)


class _PracticeRunView:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _PracticeBoundary:
    def __init__(self, scenario: PracticeScenario, run_id: str) -> None:
        self._scenario = scenario
        self._run_id = run_id

    def run_view(self, run_id: str) -> _PracticeRunView:
        if run_id != self._run_id:
            return _PracticeRunView({"error": "RunNotFound", "target": run_id})
        focus = self._scenario.metadata.to_dict().get("training_focus")
        summary = (
            f"Synthetic practice run for {self._scenario.business_type}. "
            f"Operator goal: {self._scenario.operator_goal}"
        )
        return _PracticeRunView(
            {
                "schema_version": 1,
                "subject_type": "run",
                "view_id": f"run:{run_id}",
                "run_id": run_id,
                "run_insight": {
                    "summary": summary,
                    "title": self._scenario.title,
                    "insight_type": "run",
                    "insight_id": f"practice:{self._scenario.scenario_id}",
                },
                "provenance": {
                    "run_id": run_id,
                    "style_id": f"practice-style-{self._scenario.business_type}",
                    "decision": "APPLY",
                    "session_id": f"practice-session-{self._scenario.scenario_id}",
                    "asset_hash": f"practice-asset-{self._scenario.scenario_id}",
                    "current_version": 1,
                },
                "confidence": {
                    "level": "complete",
                    "present": 4,
                    "expected": 4,
                    "missing": [],
                },
                "references": [
                    {"category": "run", "id": run_id},
                    {"category": "style", "id": f"practice-style-{self._scenario.business_type}"},
                    {"category": "session", "id": f"practice-session-{self._scenario.scenario_id}"},
                ],
                "metadata": {
                    "practice_scenario_id": self._scenario.scenario_id,
                    "training_focus": focus,
                },
            }
        )


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(text.startswith(prefix) for prefix in _URL_PREFIXES)


def _scenario_map() -> dict[str, PracticeScenario]:
    scenarios: dict[str, PracticeScenario] = {}
    for item in _SCENARIO_DATA:
        scenario_id = str(item["scenario_id"])
        scenarios[scenario_id] = PracticeScenario.of(
            scenario_id=scenario_id,
            title=str(item["title"]),
            business_type=str(item["business_type"]),
            target_offer=str(item["target_offer"]),
            target_price=str(item["target_price"]),
            operator_goal=str(item["operator_goal"]),
            expected_outcome=str(item["expected_outcome"]),
            customer_case_metadata={
                "case_type": "synthetic_practice",
                "contains_real_pii": False,
                "scenario_id": scenario_id,
            },
            required_observations=tuple(item["required_observations"]),
            metadata=dict(item["metadata"]),
        )
    return scenarios


def available_practice_scenarios() -> tuple[PracticeScenario, ...]:
    return tuple(_scenario_map()[key] for key in sorted(_scenario_map()))


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, FrozenMap):
        value = value.to_dict()
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _step(
    steps: list[PracticeStep],
    step_name: str,
    status: str,
    *,
    artifact_path: str | None = None,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    steps.append(
        PracticeStep.of(
            step_name,
            status,
            artifact_path=artifact_path,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=metadata,
        )
    )


def _observation(
    observations: list[PracticeObservation],
    observation_id: str,
    category: str,
    severity: str,
    title: str,
    detail: str,
    recommended_action: str,
    *,
    source_artifact: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    observations.append(
        PracticeObservation.of(
            observation_id,
            category,
            severity,
            title,
            detail,
            recommended_action,
            source_artifact=source_artifact,
            metadata=metadata,
        )
    )


def _error(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    steps: list[PracticeStep],
    observations: list[PracticeObservation],
    metadata: dict[str, Any] | None = None,
) -> OperatorPracticeError:
    return OperatorPracticeError.of(
        error_kind,
        error_detail,
        failed_step,
        tuple(steps),
        tuple(observations),
        metadata,
    )


def _prepare_scenario_dir(
    output_dir: str | Path,
    scenario_id: str,
    overwrite: bool,
) -> tuple[Path | None, OperatorPracticeError | None]:
    base_dir = Path(str(output_dir))
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        resolved_base = base_dir.resolve(strict=True)
        scenario_dir = (resolved_base / scenario_id).resolve()
        scenario_dir.relative_to(resolved_base)
    except (OSError, ValueError):
        return None, OperatorPracticeError.of(
            "VALIDATION_FAILED",
            "scenario output must stay under output_dir",
            "prepare_output",
            metadata={"output_dir": str(output_dir), "scenario_id": scenario_id},
        )
    if scenario_dir.exists() and not overwrite:
        return None, OperatorPracticeError.of(
            "OUTPUT_ALREADY_EXISTS",
            "practice scenario output already exists and overwrite is False",
            "prepare_output",
            metadata={"path": str(scenario_dir)},
        )
    if scenario_dir.exists() and overwrite:
        try:
            shutil.rmtree(scenario_dir)
        except OSError as exc:
            return None, OperatorPracticeError.of(
                "OUTPUT_WRITE_FAILED",
                "practice scenario output could not be replaced",
                "prepare_output",
                metadata={"path": str(scenario_dir), "os_error": type(exc).__name__},
            )
    return scenario_dir, None


def _customer_case(scenario: PracticeScenario) -> SyntheticCustomerCase:
    return SyntheticCustomerCase.of(
        customer_id=f"practice-{scenario.scenario_id}",
        business_name=f"Synthetic {scenario.business_type.title()} Practice Case",
        business_type=scenario.business_type,
        target_offer=scenario.target_offer,
        target_price=scenario.target_price,
        intake_summary=(
            f"Synthetic practice intake for {scenario.title}. "
            f"Operator goal: {scenario.operator_goal}"
        ),
        expected_deliverables=(
            "commercial_report",
            "delivery_package",
            "acceptance_report",
            "first_customer_operating_kit",
            "monetization_readiness_report",
            "launch_certification_pack",
            "operator_practice_notes",
        ),
        metadata=scenario.customer_case_metadata.to_dict(),
    )


def _load_json(path_text: str | None) -> dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_customer_file_paths(dry_run: FirstPaidCustomerDryRunResult) -> list[tuple[str, str]]:
    dry_data = _load_json(dry_run.dry_run_report_path)
    run_data = _load_json(str(dry_data.get("commercial_run_manifest_path") or ""))
    package_path = str(run_data.get("package_path") or "")
    kit_path = str(dry_data.get("operating_kit_path") or "")
    rows: list[tuple[str, str]] = []
    for name in ("report.md", "qa_summary.md", "improvement_plan.md"):
        path = Path(package_path) / name if package_path else Path(name)
        rows.append((name, str(path)))
    for name in (
        "customer_intake_checklist.md",
        "delivery_handoff.md",
        "acceptance_certificate.md",
        "pricing_offer_checklist.md",
    ):
        path = Path(kit_path) / name if kit_path else Path(name)
        rows.append((name, str(path)))
    return rows


def _internal_file_paths(
    dry_run: FirstPaidCustomerDryRunResult,
    cert: LaunchCertificationResult,
) -> list[tuple[str, str]]:
    dry_data = _load_json(dry_run.dry_run_report_path)
    run_data = _load_json(str(dry_data.get("commercial_run_manifest_path") or ""))
    rows = [
        ("dry run report", str(dry_run.dry_run_report_path)),
        ("commercial run manifest", str(dry_data.get("commercial_run_manifest_path") or "")),
        ("acceptance report", str(dry_data.get("acceptance_report_path") or "")),
        ("monetization readiness report", str(dry_data.get("monetization_readiness_report_path") or "")),
        ("delivery package manifest", str(run_data.get("package_manifest_path") or "")),
        ("launch certification report", cert.launch_certification_report_path),
        ("launch blockers", cert.launch_blockers_path),
        ("operator next steps", cert.operator_next_steps_path),
    ]
    return rows


def _scenario_observations(
    scenario: PracticeScenario,
    dry_run: FirstPaidCustomerDryRunResult,
    cert: LaunchCertificationResult,
) -> tuple[PracticeObservation, ...]:
    observations: list[PracticeObservation] = []
    _observation(
        observations,
        "OBS_REVIEW_OUTPUT_CLARITY",
        "operator_review",
        "info",
        "Review practice output clarity",
        "Read the generated report and handoff files as an operator before any real customer work.",
        "Mark confusing sections and rewrite the operator process notes outside this practice pack.",
        source_artifact=dry_run.dry_run_report_path,
    )
    for index, text in enumerate(scenario.required_observations, start=1):
        severity = "info" if scenario.scenario_id == "clinic-ready" else "warning"
        _observation(
            observations,
            f"OBS_SCENARIO_{index}",
            "scenario_training",
            severity,
            f"Scenario training note {index}",
            text,
            "Capture a manual operator note after reviewing the generated files.",
            source_artifact=cert.launch_certification_summary_path,
            metadata={"scenario_id": scenario.scenario_id},
        )
    if dry_run.passed is not True:
        _observation(
            observations,
            "OBS_DRY_RUN_NOT_PASSED",
            "dry_run",
            "error",
            "Dry run did not pass",
            "The existing rehearsal boundary reported a non-passing dry run.",
            "Resolve the upstream blockers before using this scenario as a sample.",
            source_artifact=dry_run.dry_run_report_path,
        )
    if cert.certification_status == "FAIL":
        _observation(
            observations,
            "OBS_CERTIFICATION_FAIL",
            "launch_certification",
            "error",
            "Launch certification failed",
            "The certification pack reports FAIL for this practice run.",
            "Review launch blockers before using this scenario for practice.",
            source_artifact=cert.launch_certification_report_path,
        )
    elif cert.certification_status == "CONDITIONAL_PASS":
        _observation(
            observations,
            "OBS_CERTIFICATION_CONDITIONAL",
            "launch_certification",
            "warning",
            "Launch certification is conditional",
            "The certification pack reports conditional readiness.",
            "Review blockers and record the operator action needed.",
            source_artifact=cert.launch_certification_report_path,
        )
    return tuple(observations)


def _practice_status(
    dry_run: FirstPaidCustomerDryRunResult,
    cert: LaunchCertificationResult,
    observations: tuple[PracticeObservation, ...],
) -> str:
    if dry_run.passed is not True or cert.certification_status == "FAIL":
        return "FAIL"
    if any(item.severity == "error" for item in observations):
        return "FAIL"
    if cert.certification_status == "CONDITIONAL_PASS" or any(item.severity == "warning" for item in observations):
        return "CONDITIONAL_PASS"
    return "PASS"


def _summary_payload(result: OperatorPracticeResult) -> dict[str, Any]:
    return {
        "schema_version": result.schema_version,
        "practice_id": result.practice_id,
        "scenario_id": result.scenario_id,
        "checked_at": result.checked_at,
        "dry_run_report_path": result.dry_run_report_path,
        "launch_certification_report_path": result.launch_certification_report_path,
        "practice_status": result.practice_status,
        "observations": [item.to_dict() for item in result.observations],
        "steps": [step.to_dict() for step in result.steps],
    }


def _walkthrough(result: OperatorPracticeResult) -> str:
    return (
        "# Practice Walkthrough\n\n"
        f"Scenario run: {result.scenario.title}\n\n"
        "This practice run is for operator training only. It uses synthetic data and should not be treated as real customer work.\n\n"
        "## What happened\n\n"
        "- SCOS ran the synthetic scenario through the first customer rehearsal.\n"
        "- SCOS created a launch certification pack from that rehearsal evidence.\n"
        "- This folder separates files that may be adapted later from internal evidence files.\n\n"
        "## Where to inspect\n\n"
        f"- Dry-run report: `{result.dry_run_report_path}`\n"
        f"- Launch certification report: `{result.launch_certification_report_path}`\n"
        f"- Customer-facing practice list: `{result.customer_facing_files_path}`\n"
        f"- Internal evidence list: `{result.internal_evidence_files_path}`\n"
        f"- Operator observations: `{result.operator_observations_path}`\n\n"
        "## How to read the status\n\n"
        "- PASS means the practice run completed cleanly through the existing checks.\n"
        "- CONDITIONAL means the run completed, but the operator should review warnings or training notes.\n"
        "- FAIL means the operator should stop and fix blockers before using the scenario as a sample.\n\n"
        "## Before real customer work\n\n"
        "- Review all practice notes manually.\n"
        "- Keep synthetic material separate from real customer material.\n"
        "- Do not use this file as outreach text.\n"
    )


def _customer_files_markdown(result: OperatorPracticeResult, rows: list[tuple[str, str]]) -> str:
    lines = [
        "# Customer-Facing Practice Files",
        "",
        "Every file listed here is synthetic/practice only. Adapt manually before any real customer use.",
        "",
    ]
    for name, path in rows:
        lines.append(f"- Synthetic/practice only: `{name}` -> `{path}`")
    lines.extend([
        "",
        "Do not treat this list as prepared customer material.",
        "",
    ])
    return "\n".join(lines)


def _internal_files_markdown(rows: list[tuple[str, str]]) -> str:
    lines = [
        "# Internal Evidence Files",
        "",
        "Warning: do not send raw JSON files, manifests, blockers, or internal evidence to customers by default.",
        "",
    ]
    for label, path in rows:
        lines.append(f"- Internal evidence: {label} -> `{path}`")
    lines.append("")
    return "\n".join(lines)


def _observations_markdown(result: OperatorPracticeResult) -> str:
    lines = [
        "# Operator Observations",
        "",
        "## Recorded observations",
        "",
    ]
    for item in result.observations:
        lines.append(f"- {item.severity.upper()} `{item.observation_id}`: {item.title}")
        lines.append(f"  - Detail: {item.detail}")
        lines.append(f"  - Action: {item.recommended_action}")
    lines.extend([
        "",
        "## Manual checklist after each run",
        "",
        "- [ ] Is the report understandable?",
        "- [ ] Are customer-facing files clear?",
        "- [ ] Are internal files separated?",
        "- [ ] Are blockers actionable?",
        "- [ ] Is this scenario ready to use as a sample?",
        "- [ ] What needs improvement before customer outreach?",
        "",
    ])
    return "\n".join(lines)


def _write_outputs(
    result: OperatorPracticeResult,
    customer_rows: list[tuple[str, str]],
    internal_rows: list[tuple[str, str]],
) -> None:
    Path(result.practice_summary_path).write_text(_json_text(_summary_payload(result)), encoding="utf-8", newline="\n")
    Path(result.practice_walkthrough_path).write_text(_walkthrough(result), encoding="utf-8", newline="\n")
    Path(result.customer_facing_files_path).write_text(
        _customer_files_markdown(result, customer_rows),
        encoding="utf-8",
        newline="\n",
    )
    Path(result.internal_evidence_files_path).write_text(
        _internal_files_markdown(internal_rows),
        encoding="utf-8",
        newline="\n",
    )
    Path(result.operator_observations_path).write_text(_observations_markdown(result), encoding="utf-8", newline="\n")


def run_operator_practice_scenario(
    *,
    scenario_id: str,
    output_dir: str | Path,
    checked_at: str,
    overwrite: bool = False,
    require_go: bool = True,
) -> OperatorPracticeResult | OperatorPracticeError:
    steps: list[PracticeStep] = []
    observations: list[PracticeObservation] = []

    if not isinstance(scenario_id, str) or not scenario_id:
        _step(steps, "validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
              error_detail="scenario_id is required")
        return _error("INVALID_ARGUMENTS", "scenario_id is required", "validate_inputs", steps, observations)
    if output_dir is None or str(output_dir) == "":
        _step(steps, "validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
              error_detail="output_dir is required")
        return _error("INVALID_ARGUMENTS", "output_dir is required", "validate_inputs", steps, observations)
    if not isinstance(checked_at, str) or not checked_at:
        _step(steps, "validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
              error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs", steps, observations)
    if _is_url(output_dir):
        _step(steps, "validate_inputs", "failure", error_kind="INVALID_ARGUMENTS",
              error_detail="output_dir must be a local filesystem path")
        return _error("INVALID_ARGUMENTS", "output_dir must be a local filesystem path",
                      "validate_inputs", steps, observations)
    scenarios = _scenario_map()
    scenario = scenarios.get(scenario_id)
    if scenario is None:
        _step(steps, "validate_inputs", "failure", error_kind="UNKNOWN_SCENARIO",
              error_detail="unknown practice scenario")
        return _error("UNKNOWN_SCENARIO", "unknown practice scenario", "validate_inputs",
                      steps, observations, {"scenario_id": scenario_id, "available": sorted(scenarios)})
    _step(steps, "validate_inputs", "success", metadata={"scenario_id": scenario_id})

    if _contains_sensitive_key(scenario.customer_case_metadata) or _contains_sensitive_key(scenario.metadata):
        _step(steps, "prepare_practice_scenario", "failure", error_kind="VALIDATION_FAILED",
              error_detail="practice scenario metadata contains sensitive contact-like keys")
        return _error("VALIDATION_FAILED", "practice scenario metadata contains sensitive contact-like keys",
                      "prepare_practice_scenario", steps, observations)

    scenario_dir, prepare_error = _prepare_scenario_dir(output_dir, scenario_id, overwrite)
    if prepare_error is not None:
        _step(steps, "prepare_practice_scenario", "failure",
              error_kind=prepare_error.error_kind, error_detail=prepare_error.error_detail)
        return _error(prepare_error.error_kind, prepare_error.error_detail,
                      "prepare_practice_scenario", steps, observations, prepare_error.metadata.to_dict())
    practice_id = f"operator-practice-{scenario_id}"
    dry_dir = scenario_dir / "dry_run"
    cert_dir = scenario_dir / "launch_certification"
    _step(steps, "prepare_practice_scenario", "success", artifact_path=str(scenario_dir),
          metadata={"practice_id": practice_id})

    dry_run = run_first_paid_customer_dry_run(
        knowledge_service=_PracticeBoundary(scenario, "practice-run"),
        output_dir=dry_dir,
        checked_at=checked_at,
        customer_case=_customer_case(scenario),
        run_id="practice-run",
        delivery_id="practice-delivery",
        overwrite=overwrite,
        require_go=require_go,
    )
    if isinstance(dry_run, FirstPaidCustomerDryRunError):
        _step(steps, "run_first_paid_customer_dry_run", "failure",
              error_kind="DRY_RUN_FAILED", error_detail=dry_run.error_detail)
        return _error("DRY_RUN_FAILED", dry_run.error_detail,
                      "run_first_paid_customer_dry_run", steps, observations,
                      {"dry_run_error": dry_run.to_dict()})
    _step(steps, "run_first_paid_customer_dry_run", "success",
          artifact_path=dry_run.dry_run_report_path,
          metadata={"passed": dry_run.passed, "go_no_go": dry_run.go_no_go})

    cert = create_commercial_launch_certification_pack(
        dry_run_report_path=dry_run.dry_run_report_path,
        output_dir=cert_dir,
        checked_at=checked_at,
        overwrite=overwrite,
        require_go=require_go,
    )
    if isinstance(cert, LaunchCertificationError):
        _step(steps, "run_launch_certification_pack", "failure",
              error_kind="LAUNCH_CERTIFICATION_FAILED", error_detail=cert.error_detail)
        return _error("LAUNCH_CERTIFICATION_FAILED", cert.error_detail,
                      "run_launch_certification_pack", steps, observations,
                      {"launch_certification_error": cert.to_dict()})
    _step(steps, "run_launch_certification_pack", "success",
          artifact_path=cert.launch_certification_report_path,
          metadata={"certification_status": cert.certification_status})

    observations = list(_scenario_observations(scenario, dry_run, cert))
    status = _practice_status(dry_run, cert, tuple(observations))

    paths = {
        "summary": scenario_dir / _SUMMARY_FILENAME,
        "walkthrough": scenario_dir / _WALKTHROUGH_FILENAME,
        "customer_files": scenario_dir / _CUSTOMER_FILES_FILENAME,
        "internal_files": scenario_dir / _INTERNAL_FILES_FILENAME,
        "observations": scenario_dir / _OBSERVATIONS_FILENAME,
    }
    _step(steps, "generate_practice_outputs", "success", artifact_path=str(scenario_dir))
    result = OperatorPracticeResult(
        ok=True,
        schema_version=OPERATOR_PRACTICE_SCHEMA_VERSION,
        practice_id=practice_id,
        scenario_id=scenario_id,
        checked_at=checked_at,
        scenario=scenario,
        practice_status=status,
        dry_run_report_path=dry_run.dry_run_report_path,
        launch_certification_report_path=cert.launch_certification_report_path,
        practice_summary_path=str(paths["summary"]),
        practice_walkthrough_path=str(paths["walkthrough"]),
        customer_facing_files_path=str(paths["customer_files"]),
        internal_evidence_files_path=str(paths["internal_files"]),
        operator_observations_path=str(paths["observations"]),
        steps=tuple(steps),
        observations=tuple(observations),
        metadata=FrozenMap.from_mapping(
            {
                "runner": "scos.commercial.operator_practice_lab",
                "dry_run_passed": bool(dry_run.passed),
                "launch_certification_status": cert.certification_status,
                "require_go": bool(require_go),
                "practice_only": True,
            }
        ),
    )
    customer_rows = _resolve_customer_file_paths(dry_run)
    internal_rows = _internal_file_paths(dry_run, cert)
    try:
        scenario_dir.mkdir(parents=True, exist_ok=True)
        _write_outputs(result, customer_rows, internal_rows)
    except OSError as exc:
        _step(steps, "generate_practice_outputs", "failure",
              error_kind="OUTPUT_WRITE_FAILED",
              error_detail="practice files could not be written",
              metadata={"os_error": type(exc).__name__})
        return _error("OUTPUT_WRITE_FAILED", "practice files could not be written",
                      "generate_practice_outputs", steps, observations,
                      {"os_error": type(exc).__name__})
    return result


__all__ = ("available_practice_scenarios", "run_operator_practice_scenario")
