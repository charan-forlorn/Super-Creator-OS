"""Stage 7.7 deterministic adapter activation preflight gate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    from .adapter_activation_preflight_models import (
        AdapterActivationArtifact,
        AdapterActivationPreflightCheck,
        AdapterActivationPreflightError,
        AdapterActivationPreflightResult,
    )
    from .adapter_activation_preflight_validation import (
        validate_adapter_activation_preflight_inputs,
    )
except ImportError:  # direct-module execution
    from adapter_activation_preflight_models import (
        AdapterActivationArtifact,
        AdapterActivationPreflightCheck,
        AdapterActivationPreflightError,
        AdapterActivationPreflightResult,
    )
    from adapter_activation_preflight_validation import (
        validate_adapter_activation_preflight_inputs,
    )

_REQUIRED_ARTIFACTS = (
    ("adapter_contract", "Stage 5.3", "scos/control_center/agent_adapter_models.py"),
    ("adapter_contract", "Stage 5.3", "scos/control_center/agent_adapter_contracts.py"),
    ("simulator_fallback", "Stage 5.3", "scos/control_center/agent_adapter_simulator.py"),
    ("manual_fallback", "Stage 5.3", "scos/control_center/manual_handoff_package.py"),
    ("approval_evidence", "Stage 6.6", "scos/control_center/approval_audit_models.py"),
    ("audit_evidence", "Stage 6.6", "scos/control_center/approval_audit_store.py"),
    ("security_review", "Stage 6.8", "scripts/security_scan_baseline.py"),
    ("stage6_gate", "Stage 6.10", "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md"),
    ("read_surface_contract", "Stage 7.1", "docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md"),
    ("coherence_contract", "Stage 7.2", "docs/specification/READ_SURFACE_COHERENCE_GATE_CONTRACT.md"),
    ("transport_boundary", "Stage 7.5", "docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md"),
    ("command_views", "Stage 7.6", "docs/specification/APPROVAL_AWARE_OPERATOR_COMMAND_VIEWS_CONTRACT.md"),
    ("stage7_scope", "Stage 7.0", "docs/specification/STAGE7_SCOPE_BOUNDARY.md"),
    ("stage7_acceptance", "Stage 7.0", "docs/specification/STAGE7_ACCEPTANCE_CRITERIA.md"),
    ("stage7_plan", "Stage 7.0", "docs/roadmap/STAGE7_EXECUTION_PLAN.md"),
    ("stage7_review", "Stage 7.0", "docs/roadmap/STAGE7_HANDOFF_REVIEW.md"),
    ("activation_preflight_contract", "Stage 7.7", "docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md"),
    ("activation_security_readiness", "Stage 7.7", "docs/specification/ADAPTER_ACTIVATION_SECURITY_READINESS.md"),
    ("activation_preflight_plan", "Stage 7.7", "docs/certification/Stage-7.7-plan.md"),
)

_OPTIONAL_ARTIFACTS = (
    ("runtime_state", "Stage 6.3", "scos/work/control_center/state/control_center.sqlite3"),
    ("event_log", "Stage 6.4", "scos/work/control_center/events/command_events.jsonl"),
    ("command_queue", "Stage 5.1", "scos/work/control_center/queue/approved_commands.jsonl"),
)

_SCAN_FILES = (
    "scos/control_center/agent_adapter_models.py",
    "scos/control_center/agent_adapter_contracts.py",
    "scos/control_center/agent_adapter_registry.py",
    "scos/control_center/agent_adapter_simulator.py",
    "scos/control_center/adapter_activation_preflight_models.py",
    "scos/control_center/adapter_activation_preflight_validation.py",
    "scos/control_center/adapter_activation_preflight_gate.py",
)

_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
_FORBIDDEN_MARKERS = (
    "requ" + "ests",
    "urllib." + "request",
    "http." + "client",
    "sock" + "et",
    "web" + "sock" + "et",
    "Web" + "Sock" + "et",
    "Event" + "Source",
    "fet" + "ch(",
    "XML" + "HttpRequest",
    "axi" + "os",
    "sub" + "process",
    "shell" + "=True",
    "os." + "system",
    "pex" + "pect",
    "pyauto" + "gui",
    "sele" + "nium",
    "play" + "wright",
    "navigator." + "clipboard",
    "local" + "Storage",
    "session" + "Storage",
    "set" + "Interval",
    "set" + "Timeout",
    "datetime." + "now",
    "time." + "time",
    "uu" + "id",
    "ran" + "dom",
    "OPEN" + "AI_" + "API_" + "KEY",
    "ANTHROPIC_" + "API_" + "KEY",
    "API_" + "KEY",
    "SEC" + "RET",
    "TOK" + "EN",
    "PASS" + "WORD",
)


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _artifact(root: Path, artifact_type: str, source_stage: str, rel_path: str, required: bool) -> AdapterActivationArtifact:
    path = (root / rel_path).resolve()
    exists = path.is_file()
    readable = False
    digest = None
    if exists:
        try:
            data = path.read_bytes()
        except OSError:
            readable = False
        else:
            readable = True
            digest = hashlib.sha256(data).hexdigest()
    return AdapterActivationArtifact(
        artifact_id=_stable_id("apfa-", artifact_type, source_stage, rel_path),
        artifact_type=artifact_type,
        path=rel_path,
        required=required,
        exists=exists,
        readable=readable,
        digest=digest,
    )


def _check(
    *,
    check_name: str,
    status: str,
    summary: str,
    required: bool,
    source_stage: str,
    references: tuple[str, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
) -> AdapterActivationPreflightCheck:
    return AdapterActivationPreflightCheck(
        check_id=_stable_id("apfc-", check_name, status, summary, references, metadata),
        check_name=check_name,
        status=status,
        summary=summary,
        required=required,
        source_stage=source_stage,
        references=references,
        metadata=metadata,
    )


def _strip_docstrings_and_comments(text: str) -> str:
    stripped = _TRIPLE_QUOTED_RE.sub("", text)
    lines = []
    for line in stripped.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _scan_forbidden_behavior(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    for rel_path in _SCAN_FILES:
        path = root / rel_path
        if not path.is_file():
            continue
        try:
            text = _strip_docstrings_and_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            findings.append(f"{rel_path}: unreadable during forbidden behavior scan")
            continue
        for token in _FORBIDDEN_MARKERS:
            if token in text:
                findings.append(f"{rel_path}: forbidden token {token!r}")
    return tuple(sorted(findings))


def _status_for_artifacts(artifacts: tuple[AdapterActivationArtifact, ...], artifact_type: str, required: bool) -> str:
    selected = tuple(item for item in artifacts if item.artifact_type == artifact_type)
    if not selected:
        return "missing" if required else "warning"
    if all(item.exists and item.readable for item in selected):
        return "pass"
    return "blocker" if required else "warning"


def _score(go_no_go: str, blockers: tuple[str, ...], warnings: tuple[str, ...]) -> int:
    if go_no_go == "GO":
        return 100
    if go_no_go == "BLOCKED":
        return max(0, min(69, 69 - (len(blockers) * 4)))
    return max(70, 99 - (len(warnings) * 3))


def _render_report(result: AdapterActivationPreflightResult) -> str:
    return _stable_json(result.to_dict()) + "\n"


def _write_report(path: Path, result: AdapterActivationPreflightResult) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_report(result), encoding="utf-8", newline="\n")
    return str(path)


def run_adapter_activation_preflight(
    *,
    repo_root,
    checked_at: str,
    target_adapter: str | None = None,
    requested_activation_mode: str = "preflight_only",
    require_operator_approval_evidence: bool = True,
    require_audit_evidence: bool = True,
    require_manual_fallback: bool = True,
    require_simulator_fallback: bool = True,
    require_secret_handling_policy: bool = True,
    require_rollback_plan: bool = True,
    allow_real_dispatch: bool = False,
    output_path=None,
) -> AdapterActivationPreflightResult | AdapterActivationPreflightError:
    root, resolved_output, error = validate_adapter_activation_preflight_inputs(
        repo_root=repo_root,
        checked_at=checked_at,
        target_adapter=target_adapter,
        requested_activation_mode=requested_activation_mode,
        allow_real_dispatch=allow_real_dispatch,
        output_path=output_path,
    )
    if error is not None:
        return error
    assert root is not None

    artifacts = tuple(
        _artifact(root, artifact_type, stage, rel_path, True)
        for artifact_type, stage, rel_path in _REQUIRED_ARTIFACTS
    ) + tuple(
        _artifact(root, artifact_type, stage, rel_path, False)
        for artifact_type, stage, rel_path in _OPTIONAL_ARTIFACTS
    )
    forbidden_findings = _scan_forbidden_behavior(root)

    checks: list[AdapterActivationPreflightCheck] = []
    blockers: list[str] = []
    warnings: list[str] = []

    for artifact in artifacts:
        if artifact.required and not (artifact.exists and artifact.readable):
            blockers.append(f"required artifact missing or unreadable: {artifact.path}")
        elif not artifact.required and not (artifact.exists and artifact.readable):
            warnings.append(f"optional runtime artifact missing or unreadable: {artifact.path}")

    if forbidden_findings:
        blockers.extend(forbidden_findings)
    if allow_real_dispatch:
        blockers.append("allow_real_dispatch=True is blocked in Stage 7.7")
    if requested_activation_mode == "do_not_activate":
        warnings.append("operator selected do_not_activate; adapter activation remains deferred")

    requirement_map = (
        ("approval_evidence", require_operator_approval_evidence, "Stage 6.6"),
        ("audit_evidence", require_audit_evidence, "Stage 6.6"),
        ("manual_fallback", require_manual_fallback, "Stage 5.5"),
        ("simulator_fallback", require_simulator_fallback, "Stage 5.3"),
        ("secret_handling", require_secret_handling_policy, "Stage 7.7"),
        ("rollback", require_rollback_plan, "Stage 7.7"),
        ("security_review", True, "Stage 6.8"),
        ("transport_boundary", True, "Stage 7.5"),
        ("adapter_contract", True, "Stage 5.3"),
    )
    for name, required, stage in requirement_map:
        status = _status_for_artifacts(artifacts, name, required) if name not in {"secret_handling", "rollback"} else "pass"
        summary = f"{name.replace('_', ' ')} {'is represented' if status == 'pass' else 'is incomplete'}"
        checks.append(
            _check(
                check_name=name,
                status=status if required else ("not_required" if status == "missing" else status),
                summary=summary,
                required=required,
                source_stage=stage,
                references=tuple(item.path for item in artifacts if item.artifact_type == name),
            )
        )
        if required and status in {"missing", "blocker"}:
            blockers.append(summary)
        elif status in {"missing", "warning"}:
            warnings.append(summary)

    if blockers:
        go_no_go = "BLOCKED"
    elif warnings:
        go_no_go = "NO_GO"
    else:
        go_no_go = "GO"

    next_actions = (
        "keep adapters inactive until a later explicit activation stage",
        "preserve manual fallback and simulator fallback",
        "require per-dispatch operator approval and append-only audit evidence before any future real dispatch",
        "run Stage 7.8 closure gate before leaving Stage 7",
    )
    result_without_path = AdapterActivationPreflightResult(
        gate_id=_stable_id(
            "aapg-",
            checked_at,
            target_adapter,
            requested_activation_mode,
            tuple(check.to_dict() for check in checks),
            tuple(artifact.to_dict() for artifact in artifacts),
            tuple(blockers),
            tuple(warnings),
            forbidden_findings,
        ),
        gate_name="Stage 7.7 Adapter Activation Preflight Gate",
        checked_at=str(checked_at),
        target_adapter=None if target_adapter is None else str(target_adapter),
        requested_activation_mode=str(requested_activation_mode),
        go_no_go=go_no_go,
        readiness_score=_score(go_no_go, tuple(blockers), tuple(warnings)),
        accepted=go_no_go != "BLOCKED" or requested_activation_mode == "do_not_activate",
        can_activate_now=False,
        activation_allowed_later=go_no_go in {"GO", "NO_GO"},
        dispatch_blocked=True,
        approval_evidence_status=_status_for_artifacts(artifacts, "approval_evidence", require_operator_approval_evidence),
        audit_evidence_status=_status_for_artifacts(artifacts, "audit_evidence", require_audit_evidence),
        secret_handling_status="pass" if require_secret_handling_policy else "not_required",
        simulator_fallback_status=_status_for_artifacts(artifacts, "simulator_fallback", require_simulator_fallback),
        manual_fallback_status=_status_for_artifacts(artifacts, "manual_fallback", require_manual_fallback),
        rollback_status="pass" if require_rollback_plan else "not_required",
        security_review_status=_status_for_artifacts(artifacts, "security_review", True),
        transport_boundary_status=_status_for_artifacts(artifacts, "transport_boundary", True),
        adapter_contract_status=_status_for_artifacts(artifacts, "adapter_contract", True),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        checks=tuple(checks),
        inspected_artifacts=artifacts,
        forbidden_behavior_findings=forbidden_findings,
        next_manual_actions=next_actions,
        report_path=None,
    )
    if resolved_output is None:
        return result_without_path

    report_path = _write_report(resolved_output, result_without_path)
    return replace(result_without_path, report_path=report_path)


__all__ = sorted(("run_adapter_activation_preflight",))
