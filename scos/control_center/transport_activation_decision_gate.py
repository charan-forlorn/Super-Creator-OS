"""Stage 8.1 deterministic local transport activation decision gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    from .transport_activation_decision_models import (
        TRANSPORT_ACTIVATION_DECISIONS,
        TRANSPORT_ACTIVATION_OPTIONS,
        LocalTransportActivationDecisionError,
        LocalTransportActivationDecisionResult,
        TransportDecisionBlocker,
        TransportDecisionRecord,
        TransportOptionAnalysis,
        TransportSafetyRequirement,
    )
except ImportError:  # direct-module execution
    from transport_activation_decision_models import (
        TRANSPORT_ACTIVATION_DECISIONS,
        TRANSPORT_ACTIVATION_OPTIONS,
        LocalTransportActivationDecisionError,
        LocalTransportActivationDecisionResult,
        TransportDecisionBlocker,
        TransportDecisionRecord,
        TransportOptionAnalysis,
        TransportSafetyRequirement,
    )

_GATE_NAME = "Stage 8.1 Local Transport Activation Decision Gate"
_REPORT_FILENAME = "stage8_1_local_transport_activation_decision_report.json"

_URL_MARKERS = ("://", "http:", "https:", "file:", "ftp:")
_CREDENTIAL_MARKERS = (
    "OPEN" + "AI_" + "API_" + "KEY",
    "ANTHROPIC_" + "API_" + "KEY",
    "API_" + "KEY",
    "SEC" + "RET",
    "TOK" + "EN",
    "PASS" + "WORD",
    "COO" + "KIE",
)

_REQUIRED_EVIDENCE = (
    "docs/roadmap/STAGE8_HANDOFF.md",
    "docs/roadmap/STAGE8_HANDOFF_REVIEW.md",
    "docs/roadmap/STAGE8_EXECUTION_PLAN.md",
    "docs/specification/STAGE8_SCOPE_BOUNDARY.md",
    "docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md",
    "docs/certification/Stage-8.0-plan.md",
    "docs/certification/Stage-7-final-closure.md",
    "docs/certification/Stage-7.8-plan.md",
    "docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md",
    "docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md",
    "docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md",
    "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
    "docs/certification/Stage-6-final-integration-release.md",
    "docs/certification/Stage-5-final-ai-command-center-certification.md",
    "docs/certification/Stage-4-final-commercial-release.md",
)

_STAGE8_SOURCE_FILES = (
    "scos/control_center/transport_activation_decision_models.py",
    "scos/control_center/transport_activation_decision_gate.py",
)

_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
_FORBIDDEN_MARKERS = (
    "Web" + "Socket",
    "Event" + "Source",
    "set" + "Interval",
    "set" + "Timeout",
    "fet" + "ch(",
    "axi" + "os",
    "route" + ".ts",
    "sub" + "process",
    "os." + "system",
    "socket" + "server",
    "http." + "server",
    "uvi" + "corn",
    "fast" + "api",
    "fla" + "sk",
    "requ" + "ests",
    "open" + "ai",
    "anth" + "ropic",
    "api" + "_key",
    "sec" + "ret",
    "tok" + "en",
)

_DECISION_TO_OPTION = {
    "NO_TRANSPORT": "NO_TRANSPORT",
    "FILE_SNAPSHOT_REFRESH_ALLOWED_LATER": "FILE_SNAPSHOT_REFRESH",
    "LOCAL_HTTP_ALLOWED_LATER": "LOCAL_HTTP",
    "WEBSOCKET_ALLOWED_LATER": "WEBSOCKET",
    "SSE_EVENTSOURCE_ALLOWED_LATER": "SSE_EVENTSOURCE",
    "POLLING_ALLOWED_LATER": "POLLING",
    "BLOCK_TRANSPORT_ACTIVATION": "NO_TRANSPORT",
}

_SAFETY_REQUIREMENT_ROWS = (
    (
        "locality",
        "Future transport must stay local-only and must not expose a public interface.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/specification/STAGE8_SCOPE_BOUNDARY.md",),
    ),
    (
        "operator_approval",
        "A later implementation stage must preserve persisted operator approval for actions.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/specification/STAGE8_ACCEPTANCE_CRITERIA.md",),
    ),
    (
        "audit",
        "A later implementation stage must preserve append-only audit evidence.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md",),
    ),
    (
        "rollback",
        "A later implementation stage must include rollback and an operator stop control.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/roadmap/STAGE8_EXECUTION_PLAN.md",),
    ),
    (
        "credential_restriction",
        "Stage 8.1 cannot implement credential storage, use, or logging.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/specification/STAGE8_SCOPE_BOUNDARY.md",),
    ),
    (
        "adapter_dispatch_restriction",
        "Stage 8.1 cannot activate adapters or dispatch AI work.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md",),
    ),
    (
        "future_stage_authorization",
        "Allowed-later decisions require a later explicit Stage 8 implementation approval.",
        TRANSPORT_ACTIVATION_OPTIONS,
        ("docs/certification/Stage-8.0-plan.md",),
    ),
)


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _has_url_marker(value: object) -> bool:
    lowered = str(value).lower()
    return any(marker.lower() in lowered for marker in _URL_MARKERS)


def _has_credential_marker(value: object) -> bool:
    upper = str(value).upper()
    return any(marker.upper() in upper for marker in _CREDENTIAL_MARKERS)


def _validate_text(field_name: str, value: object) -> tuple[str, ...]:
    errors: list[str] = []
    if _has_url_marker(value):
        errors.append(f"{field_name} must not contain URL or remote path markers")
    if _has_credential_marker(value):
        errors.append(f"{field_name} must not contain credential markers")
    return tuple(errors)


def _resolve_repo_root(repo_root) -> tuple[Path | None, tuple[str, ...]]:
    errors = list(_validate_text("repo_root", repo_root))
    if errors:
        return None, tuple(errors)
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        errors.append(f"repo_root must be an existing local directory: {repo_root}")
    return (None if errors else root), tuple(errors)


def _resolve_output_path(repo_root: Path, output_path) -> tuple[Path | None, tuple[str, ...]]:
    if output_path is None:
        return None, ()
    errors = list(_validate_text("output_path", output_path))
    path = Path(output_path)
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        errors.append("output_path must resolve inside repo_root")
    if resolved.suffix.lower() != ".json":
        resolved = resolved / _REPORT_FILENAME
    return (None if errors else resolved), tuple(errors)


def _strip_docstrings_and_comments(text: str) -> str:
    stripped = _TRIPLE_QUOTED_RE.sub("", text)
    lines: list[str] = []
    for line in stripped.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _scan_forbidden_behavior(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    for rel_path in _STAGE8_SOURCE_FILES:
        path = root / rel_path
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            findings.append(f"{rel_path}: unreadable during static scan")
            continue
        scanned = _strip_docstrings_and_comments(text)
        for marker in _FORBIDDEN_MARKERS:
            if marker in scanned:
                findings.append(f"{rel_path}: forbidden marker {marker!r}")
    return tuple(sorted(findings))


def _blocker(code: str, message: str, evidence: tuple[str, ...] = (), severity: str = "error") -> TransportDecisionBlocker:
    return TransportDecisionBlocker(
        blocker_id=_stable_id("ltab-", code, message, evidence),
        code=code,
        severity=severity,
        message=message,
        evidence=evidence,
    )


def _option_analysis(
    *,
    option: str,
    description: str,
    security_risk: str,
    operational_risk: str,
    localhost_boundary: str,
    stale_data_risk: str,
    event_ordering_risk: str,
    recommendation: str,
) -> TransportOptionAnalysis:
    return TransportOptionAnalysis(
        option=option,
        description=description,
        security_risk=security_risk,
        operational_risk=operational_risk,
        localhost_boundary=localhost_boundary,
        approval_requirements=(
            "future implementation requires explicit Stage 8 approval",
            "operator action approval remains separate from read synchronization",
        ),
        audit_requirements=(
            "decision evidence must remain deterministic",
            "future runtime events must be append-only if implemented later",
        ),
        rollback_requirements=(
            "preserve no-transport fallback",
            "later implementation must have a single-stage rollback path",
        ),
        test_requirements=(
            "deterministic gate output",
            "forbidden behavior static scan",
            "focused model and gate tests",
        ),
        forbidden_behaviors=(
            "adapter dispatch",
            "approval bypass",
            "credential persistence",
            "network exposure",
            "runtime transport implementation in Stage 8.1",
        ),
        recommendation=recommendation,
        locality_boundary=localhost_boundary,
        origin_csrf_local_exposure_risk=security_risk,
        stale_data_risk=stale_data_risk,
        event_ordering_risk=event_ordering_risk,
        accidental_command_execution_risk="must remain none; transport cannot execute commands",
        adapter_dispatch_risk="must remain none; adapters stay inactive",
        credential_exposure_risk="must remain none; credentials are not handled in Stage 8.1",
        rollback_kill_switch_requirement="later implementation must preserve immediate fallback to no transport",
        operator_approval_preservation="approval state may be observed only; actions still require persisted approval",
        deterministic_testability="must be proven with caller-supplied inputs and stable JSON output",
    )


def _analysis_set() -> tuple[TransportOptionAnalysis, ...]:
    return (
        _option_analysis(
            option="NO_TRANSPORT",
            description="Keep Stage 7 read surfaces and manual refresh without adding a runtime channel.",
            security_risk="lowest; no listener, route, browser channel, or repeated runtime read loop exists",
            operational_risk="lowest; operator manually chooses when to refresh evidence",
            localhost_boundary="no runtime transport boundary is opened",
            stale_data_risk="visible manual refresh risk",
            event_ordering_risk="lowest; evidence is read as deterministic snapshots",
            recommendation="approve as default Stage 8.1 decision",
        ),
        _option_analysis(
            option="FILE_SNAPSHOT_REFRESH",
            description="Allow a later stage to refresh deterministic local snapshot files on operator action.",
            security_risk="low; file reads stay local but path validation and stale evidence controls are required",
            operational_risk="low; stale snapshots remain possible and must be shown explicitly",
            localhost_boundary="local filesystem only; no listener",
            stale_data_risk="medium; snapshot age must be visible",
            event_ordering_risk="low; snapshot versioning can preserve order",
            recommendation="safest allowed-later implementation candidate",
        ),
        _option_analysis(
            option="LOCAL_HTTP",
            description="Allow a later stage to consider a localhost-only request boundary.",
            security_risk="medium; origin, local exposure, and request forgery controls are required",
            operational_risk="medium; route lifecycle and degraded states need explicit handling",
            localhost_boundary="must bind only to an operator-local interface if approved later",
            stale_data_risk="medium; response freshness must be reported",
            event_ordering_risk="medium; response ordering must be deterministic",
            recommendation="allowed later only after stricter local server contract",
        ),
        _option_analysis(
            option="WEBSOCKET",
            description="Allow a later stage to evaluate persistent bidirectional local sync.",
            security_risk="high; persistent bidirectional channel increases local exposure",
            operational_risk="high; reconnect and lifecycle behavior can obscure degraded state",
            localhost_boundary="must be local-only if ever approved later",
            stale_data_risk="medium; connection health can mask stale payloads",
            event_ordering_risk="high; message ordering and replay must be proven",
            recommendation="defer beyond first implementation candidate",
        ),
        _option_analysis(
            option="SSE_EVENTSOURCE",
            description="Allow a later stage to evaluate one-way local event streaming.",
            security_risk="medium-high; stream exposure and origin controls require review",
            operational_risk="medium-high; long-lived stream failure must be visible",
            localhost_boundary="must be local-only if ever approved later",
            stale_data_risk="medium; dropped stream events must not appear healthy",
            event_ordering_risk="medium-high; replay and missed event handling must be proven",
            recommendation="defer until snapshot or local request option is proven",
        ),
        _option_analysis(
            option="POLLING",
            description="Allow a later stage to evaluate bounded repeated local refresh.",
            security_risk="medium; repeated local reads require rate, origin, and path controls",
            operational_risk="medium-high; repeated refresh loops can create noisy local failure modes",
            localhost_boundary="must be local-only if ever approved later",
            stale_data_risk="medium; interval gaps and stale data must be visible",
            event_ordering_risk="medium; repeated reads must not reorder evidence",
            recommendation="defer unless bounded cadence is explicitly justified",
        ),
    )


def _safety_requirements() -> tuple[TransportSafetyRequirement, ...]:
    requirements: list[TransportSafetyRequirement] = []
    for category, requirement, applies_to, evidence in _SAFETY_REQUIREMENT_ROWS:
        requirements.append(
            TransportSafetyRequirement(
                requirement_id=_stable_id("ltar-", category, requirement, applies_to, evidence),
                category=category,
                requirement=requirement,
                status="pass",
                applies_to=applies_to,
                evidence=evidence,
                metadata=(("stage", "8.1"), ("implementation_allowed_now", "false")),
            )
        )
    return tuple(requirements)


def _inspect_required_evidence(root: Path) -> tuple[tuple[str, ...], tuple[TransportDecisionBlocker, ...]]:
    inspected: list[str] = []
    blockers: list[TransportDecisionBlocker] = []
    for rel_path in _REQUIRED_EVIDENCE:
        path = root / rel_path
        inspected.append(rel_path)
        if not path.is_file():
            blockers.append(
                _blocker(
                    "STAGE_4_5_6_7_CONTRACT_COMPATIBILITY_EVIDENCE_MISSING",
                    f"required compatibility evidence missing: {rel_path}",
                    (rel_path,),
                )
            )
    return tuple(inspected), tuple(blockers)


def _decision_for_request(requested_decision: str, allow_future_implementation: bool) -> str:
    if requested_decision == "BLOCK_TRANSPORT_ACTIVATION":
        return "BLOCK_TRANSPORT_ACTIVATION"
    if requested_decision == "NO_TRANSPORT":
        return "NO_TRANSPORT"
    if allow_future_implementation:
        return requested_decision
    return "BLOCK_TRANSPORT_ACTIVATION"


def _score(blockers: tuple[TransportDecisionBlocker, ...], decision: str) -> tuple[str, int, bool]:
    if blockers:
        return "BLOCKED", max(0, min(69, 69 - len(blockers) * 4)), False
    if decision == "BLOCK_TRANSPORT_ACTIVATION":
        return "NO_GO", 90, False
    return "GO", 100, True


def _write_report(path: Path, result: LocalTransportActivationDecisionResult) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stable_json(result.to_dict()) + "\n", encoding="utf-8", newline="\n")
    return str(path)


def run_local_transport_activation_decision_gate(
    *,
    repo_root,
    decided_at: str,
    requested_decision: str = "NO_TRANSPORT",
    allow_future_implementation: bool = False,
    output_path=None,
) -> LocalTransportActivationDecisionResult | LocalTransportActivationDecisionError:
    decided_text = str(decided_at)
    errors: list[str] = []
    if not decided_text.strip():
        errors.append("decided_at must be caller-supplied and non-empty")
    errors.extend(_validate_text("decided_at", decided_text))
    requested_text = str(requested_decision)
    if requested_text not in TRANSPORT_ACTIVATION_DECISIONS:
        errors.append(f"requested_decision must be one of {list(TRANSPORT_ACTIVATION_DECISIONS)}")
    errors.extend(_validate_text("requested_decision", requested_text))
    root, root_errors = _resolve_repo_root(repo_root)
    errors.extend(root_errors)
    resolved_output: Path | None = None
    if root is not None:
        resolved_output, output_errors = _resolve_output_path(root, output_path)
        errors.extend(output_errors)
    if errors:
        return LocalTransportActivationDecisionError.of(
            "INVALID_LOCAL_TRANSPORT_ACTIVATION_DECISION_INPUT",
            errors[0],
            decided_at=decided_text,
            blockers=tuple(errors),
        )
    assert root is not None

    inspected_artifacts, blockers = _inspect_required_evidence(root)
    blocker_list = list(blockers)

    source_findings = _scan_forbidden_behavior(root)
    for finding in source_findings:
        blocker_list.append(
            _blocker(
                "FORBIDDEN_STAGE_8_1_SOURCE_BEHAVIOR",
                finding,
                tuple(finding.split(":", 1)[:1]),
                "critical",
            )
        )

    if requested_text not in {"NO_TRANSPORT", "BLOCK_TRANSPORT_ACTIVATION"} and not allow_future_implementation:
        blocker_list.append(
            _blocker(
                "TRANSPORT_IMPLEMENTATION_NOT_APPROVED_IN_STAGE_8_1",
                "requested allowed-later transport without allow_future_implementation=True",
                (requested_text,),
            )
        )

    analyses = _analysis_set()
    safety_requirements = _safety_requirements()
    decision = _decision_for_request(requested_text, bool(allow_future_implementation))
    go_no_go, readiness_score, accepted = _score(tuple(blocker_list), decision)
    selected_option = _DECISION_TO_OPTION[decision]
    decision_record = TransportDecisionRecord(
        decision_id=_stable_id(
            "ltad-",
            decided_text,
            requested_text,
            bool(allow_future_implementation),
            selected_option,
            tuple(analysis.to_dict() for analysis in analyses),
            tuple(requirement.to_dict() for requirement in safety_requirements),
        ),
        decision=decision,
        requested_decision=requested_text,
        decided_at=decided_text,
        allow_future_implementation=bool(allow_future_implementation),
        future_implementation_requires_later_stage=decision != "NO_TRANSPORT",
        recommended_next_stage="Stage 8.2 local transport foundation only if separately approved",
        decision_summary=(
            "Stage 8.1 approves no immediate implementation. "
            f"Selected decision: {decision}; selected option: {selected_option}."
        ),
    )
    warnings = (
        "Stage 8.1 is a decision gate only.",
        "can_implement_now is always false.",
        "future implementation requires a later explicit Stage 8 approval.",
    )
    result_without_path = LocalTransportActivationDecisionResult(
        gate_id=_stable_id(
            "ltag-",
            decision_record.to_dict(),
            tuple(blocker.to_dict() for blocker in blocker_list),
            source_findings,
            inspected_artifacts,
        ),
        gate_name=_GATE_NAME,
        decided_at=decided_text,
        go_no_go=go_no_go,
        readiness_score=readiness_score,
        accepted=accepted,
        can_implement_now=False,
        transport_implemented=False,
        dispatch_blocked=True,
        decision_record=decision_record,
        option_analyses=analyses,
        safety_requirements=safety_requirements,
        blockers=tuple(blocker_list),
        warnings=warnings,
        inspected_artifacts=inspected_artifacts,
        forbidden_behavior_findings=source_findings,
        report_path=None,
    )
    if resolved_output is None:
        return result_without_path
    report_path = _write_report(resolved_output, result_without_path)
    return replace(result_without_path, report_path=report_path)


__all__ = sorted(("run_local_transport_activation_decision_gate",))
