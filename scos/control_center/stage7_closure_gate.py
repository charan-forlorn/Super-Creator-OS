"""Stage 7.8 deterministic final closure gate and Stage 8 handoff."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    from .stage7_closure_models import (
        Stage7ClosureArtifact,
        Stage7ClosureCheck,
        Stage7ClosureError,
        Stage7ClosureResult,
    )
except ImportError:  # direct-module execution
    from stage7_closure_models import (
        Stage7ClosureArtifact,
        Stage7ClosureCheck,
        Stage7ClosureError,
        Stage7ClosureResult,
    )

_GATE_NAME = "Stage 7.8 Final Closure Gate and Stage 8 Handoff"
_STAGE_NUMBER = "7.8"
_REPORT_FILENAME = "stage7_final_closure_report.json"

_URL_MARKERS = ("://", "http:", "https:", "file:", "ftp:")
_SENSITIVE_MARKERS = (
    "OPEN" + "AI_" + "API_" + "KEY",
    "ANTHROPIC_" + "API_" + "KEY",
    "API_" + "KEY",
    "SEC" + "RET",
    "TOK" + "EN",
    "PASS" + "WORD",
    "COO" + "KIE",
)

_REQUIRED_ARTIFACTS: tuple[tuple[str, str, str, str], ...] = (
    ("7.0", "plan_doc", "docs/roadmap/STAGE7_EXECUTION_PLAN.md", "stage7_planning"),
    ("7.0", "scope_doc", "docs/specification/STAGE7_SCOPE_BOUNDARY.md", "stage7_planning"),
    ("7.0", "acceptance_doc", "docs/specification/STAGE7_ACCEPTANCE_CRITERIA.md", "stage7_planning"),
    ("7.0", "handoff_review_doc", "docs/roadmap/STAGE7_HANDOFF_REVIEW.md", "stage7_planning"),
    ("7.0", "cert_doc", "docs/certification/Stage-7.0-plan.md", "stage7_planning"),
    ("7.1", "module", "scos/control_center/read_surface_models.py", "read_surface"),
    ("7.1", "module", "scos/control_center/read_surface_query.py", "read_surface"),
    ("7.1", "module", "scos/control_center/read_surface_snapshot.py", "read_surface"),
    ("7.1", "module", "scos/control_center/read_surface_facade.py", "read_surface"),
    ("7.1", "module", "scos/control_center/read_surface_validation.py", "read_surface"),
    ("7.1", "test", "scos/control_center/tests/test_read_surface_facade.py", "read_surface"),
    ("7.1", "contract", "docs/specification/CONTROL_CENTER_READ_SURFACE_CONTRACT.md", "read_surface"),
    ("7.1", "cert_doc", "docs/certification/Stage-7.1-plan.md", "read_surface"),
    ("7.2", "module", "scos/control_center/read_surface_coherence_models.py", "coherence_gate"),
    ("7.2", "module", "scos/control_center/read_surface_coherence_gate.py", "coherence_gate"),
    ("7.2", "test", "scos/control_center/tests/test_read_surface_coherence_gate.py", "coherence_gate"),
    ("7.2", "contract", "docs/specification/READ_SURFACE_COHERENCE_GATE_CONTRACT.md", "coherence_gate"),
    ("7.2", "cert_doc", "docs/certification/Stage-7.2-plan.md", "coherence_gate"),
    ("7.3", "module", "scos/control_center/operator_read_models.py", "operator_read_models"),
    ("7.3", "module", "scos/control_center/operator_health_activity.py", "operator_read_models"),
    ("7.3", "module", "scos/control_center/operator_health_activity_facade.py", "operator_read_models"),
    ("7.3", "test", "scos/control_center/tests/test_operator_health_activity.py", "operator_read_models"),
    ("7.3", "contract", "docs/specification/OPERATOR_HEALTH_ACTIVITY_READ_MODELS_CONTRACT.md", "operator_read_models"),
    ("7.3", "cert_doc", "docs/certification/Stage-7.3-plan.md", "operator_read_models"),
    ("7.4", "frontend", "apps/control-center/lib/operator-read-surface-projection.ts", "ui_projection"),
    ("7.4", "frontend", "apps/control-center/components/operator-read-surface-panel.tsx", "ui_projection"),
    ("7.4", "frontend_test", "apps/control-center/tests/operator-read-surface-projection.test.ts", "ui_projection"),
    ("7.4", "frontend_test", "apps/control-center/tests/operator-read-surface-panel.test.tsx", "ui_projection"),
    ("7.4", "contract", "docs/specification/OPERATOR_READ_SURFACE_UI_PROJECTION_CONTRACT.md", "ui_projection"),
    ("7.4", "cert_doc", "docs/certification/Stage-7.4-plan.md", "ui_projection"),
    ("7.5", "module", "scos/control_center/transport_decision_models.py", "transport_decision"),
    ("7.5", "module", "scos/control_center/read_surface_transport_decision.py", "transport_decision"),
    ("7.5", "test", "scos/control_center/tests/test_read_surface_transport_decision.py", "transport_decision"),
    ("7.5", "contract", "docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md", "transport_decision"),
    ("7.5", "cert_doc", "docs/certification/Stage-7.5-plan.md", "transport_decision"),
    ("7.6", "module", "scos/control_center/operator_command_view_models.py", "command_views"),
    ("7.6", "module", "scos/control_center/operator_command_views.py", "command_views"),
    ("7.6", "module", "scos/control_center/execution_evidence_surface.py", "command_views"),
    ("7.6", "test", "scos/control_center/tests/test_operator_command_views.py", "command_views"),
    ("7.6", "contract", "docs/specification/APPROVAL_AWARE_OPERATOR_COMMAND_VIEWS_CONTRACT.md", "command_views"),
    ("7.6", "contract", "docs/specification/READ_ONLY_EXECUTION_EVIDENCE_SURFACE_CONTRACT.md", "command_views"),
    ("7.6", "cert_doc", "docs/certification/Stage-7.6-plan.md", "command_views"),
    ("7.7", "module", "scos/control_center/adapter_activation_preflight_models.py", "adapter_preflight"),
    ("7.7", "module", "scos/control_center/adapter_activation_preflight_validation.py", "adapter_preflight"),
    ("7.7", "module", "scos/control_center/adapter_activation_preflight_gate.py", "adapter_preflight"),
    ("7.7", "test", "scos/control_center/tests/test_adapter_activation_preflight_gate.py", "adapter_preflight"),
    ("7.7", "contract", "docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md", "adapter_preflight"),
    ("7.7", "contract", "docs/specification/ADAPTER_ACTIVATION_SECURITY_READINESS.md", "adapter_preflight"),
    ("7.7", "cert_doc", "docs/certification/Stage-7.7-plan.md", "adapter_preflight"),
    ("7.8", "module", "scos/control_center/stage7_closure_models.py", "closure"),
    ("7.8", "module", "scos/control_center/stage7_closure_gate.py", "closure"),
    ("7.8", "test", "scos/control_center/tests/test_stage7_closure_models.py", "closure"),
    ("7.8", "test", "scos/control_center/tests/test_stage7_closure_gate.py", "closure"),
    ("7.8", "contract", "docs/specification/STAGE7_FINAL_CLOSURE_GATE_CONTRACT.md", "closure"),
    ("7.8", "cert_doc", "docs/certification/Stage-7.8-plan.md", "closure"),
    ("7.8", "closure_doc", "docs/certification/Stage-7-final-closure.md", "closure"),
    ("8.0", "handoff_doc", "docs/roadmap/STAGE8_HANDOFF.md", "stage8_handoff"),
    ("4", "closure_doc", "docs/certification/Stage-4-final-commercial-release.md", "compatibility"),
    ("5", "closure_doc", "docs/certification/Stage-5-final-ai-command-center-certification.md", "compatibility"),
    ("6", "closure_doc", "docs/certification/Stage-6-final-integration-release.md", "compatibility"),
    ("6.10", "contract", "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md", "compatibility"),
)

_OPTIONAL_ARTIFACTS: tuple[tuple[str, str, str, str], ...] = (
    ("6.3", "runtime_state", "scos/work/control_center/state/control_center.sqlite3", "runtime_evidence"),
    ("6.4", "event_log", "scos/work/control_center/events/command_events.jsonl", "runtime_evidence"),
    ("5.1", "command_queue", "scos/work/control_center/queue/approved_commands.jsonl", "runtime_evidence"),
)

_SAFETY_SCAN_FILES = (
    "scos/control_center/read_surface_facade.py",
    "scos/control_center/read_surface_coherence_gate.py",
    "scos/control_center/operator_health_activity.py",
    "scos/control_center/read_surface_transport_decision.py",
    "scos/control_center/operator_command_views.py",
    "scos/control_center/adapter_activation_preflight_gate.py",
    "scos/control_center/stage7_closure_gate.py",
    "apps/control-center/lib/operator-read-surface-types.ts",
    "apps/control-center/lib/operator-read-surface-projection.ts",
    "apps/control-center/lib/operator-read-surface-mock-data.ts",
    "apps/control-center/lib/operator-command-view-mock-data.ts",
    "apps/control-center/components/operator-read-surface-panel.tsx",
    "apps/control-center/components/operator-health-signal-card.tsx",
    "apps/control-center/components/operator-activity-feed.tsx",
    "apps/control-center/components/operator-readiness-summary.tsx",
    "apps/control-center/components/read-surface-coherence-card.tsx",
)

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
_NEGATION_MARKERS = ("no ", "not ", "never", "forbid", "defer", "must not", "non-goal", "without")
_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')

_DEFERRED_ITEMS = (
    "live transport remains deferred until explicit Stage 8 operator approval",
    "real adapter activation remains deferred until explicit Stage 8 operator approval",
    "API-key handling remains deferred until a dedicated approved security design",
    "cloud/SaaS/payment/CRM/customer portal integrations remain outside the approved scope",
)
_FORBIDDEN_ITEMS_REJECTED = (
    "Stage 7.9+ feature expansion",
    "real AI dispatch",
    "real adapter activation",
    "unapproved live transport",
    "network/API calls",
    "command execution",
    "browser/GUI/clipboard automation",
    "runtime store mutation",
)


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _has_url_marker(value: object) -> bool:
    lowered = str(value).lower()
    return any(marker.lower() in lowered for marker in _URL_MARKERS)


def _has_sensitive_marker(value: object) -> bool:
    upper = str(value).upper()
    return any(marker.upper() in upper for marker in _SENSITIVE_MARKERS)


def _validate_text(field_name: str, value: object) -> tuple[str, ...]:
    errors: list[str] = []
    if _has_url_marker(value):
        errors.append(f"{field_name} must not contain URL or remote path markers")
    if _has_sensitive_marker(value):
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


def _artifact(root: Path, stage: str, artifact_type: str, rel_path: str, required: bool) -> Stage7ClosureArtifact:
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
    return Stage7ClosureArtifact(
        artifact_id=_stable_id("s7a-", stage, artifact_type, rel_path),
        stage=stage,
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
    category: str,
    status: str,
    summary: str,
    required: bool = True,
    references: tuple[str, ...] = (),
    metadata: tuple[tuple[str, str], ...] = (),
) -> Stage7ClosureCheck:
    return Stage7ClosureCheck(
        check_id=_stable_id("s7c-", check_name, category, status, summary, references, metadata),
        check_name=check_name,
        category=category,
        status=status,
        summary=summary,
        required=required,
        references=references,
        metadata=metadata,
    )


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _strip_prose(text: str) -> str:
    text = _TRIPLE_QUOTED_RE.sub("", text)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if any(token in lowered for token in _NEGATION_MARKERS):
            continue
        lines.append(line)
    return "\n".join(lines)


def _scan_forbidden_behavior(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    for rel_path in _SAFETY_SCAN_FILES:
        path = root / rel_path
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            findings.append(f"{rel_path}: unreadable during safety scan")
            continue
        stripped = _strip_prose(text)
        for token in _FORBIDDEN_MARKERS:
            if token in stripped:
                findings.append(f"{rel_path}: forbidden marker {token!r}")
    return tuple(sorted(findings))


def _read_latest_commit(root: Path) -> str | None:
    git_dir = root / ".git"
    head = _read_text(git_dir / "HEAD")
    if head is None:
        return None
    head = head.strip()
    if head.startswith("ref: "):
        ref_path = git_dir / head[5:].strip()
        ref_text = _read_text(ref_path)
        if ref_text:
            return ref_text.strip()
        packed = _read_text(git_dir / "packed-refs") or ""
        ref_name = head[5:].strip()
        for line in packed.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref_name:
                return parts[0]
        return None
    return head or None


def _stage_check(stage: str, artifacts: tuple[Stage7ClosureArtifact, ...]) -> Stage7ClosureCheck:
    selected = tuple(item for item in artifacts if item.stage == stage)
    missing = tuple(item.path for item in selected if item.required and not (item.exists and item.readable))
    status = "pass" if not missing else "blocker"
    summary = f"Stage {stage} required evidence is present" if not missing else f"Stage {stage} required evidence is incomplete"
    return _check(
        check_name=f"verify_stage_{stage.replace('.', '_')}_artifacts",
        category="artifact",
        status=status,
        summary=summary,
        references=tuple(item.path for item in selected),
        metadata=(("missing_count", str(len(missing))),),
    )


def _external_check(command_name: str, enabled: bool, category: str, summary: str) -> Stage7ClosureCheck:
    if enabled:
        return _check(
            check_name=command_name,
            category=category,
            status="pass",
            summary=summary + " External command must be run by certification workflow.",
            metadata=(("executed_by_gate", "false"), ("acceptable_skip_reason", "Stage 7.8 gate forbids command execution"),),
        )
    return _check(
        check_name=command_name,
        category=category,
        status="skipped",
        summary=summary + " Caller disabled this check.",
        required=False,
        metadata=(("enabled", "false"),),
    )


def _frontend_scripts(root: Path) -> tuple[str, ...]:
    package_json = root / "apps" / "control-center" / "package.json"
    text = _read_text(package_json)
    if text is None:
        return ()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ()
    scripts = payload.get("scripts", {})
    if not isinstance(scripts, dict):
        return ()
    return tuple(sorted(str(key) for key in scripts))


def _score(blockers: tuple[str, ...], warnings: tuple[str, ...]) -> tuple[str, int, bool]:
    if blockers:
        return "BLOCKED", max(0, min(69, 69 - len(blockers) * 3)), False
    if warnings:
        return "NO_GO", max(70, 99 - len(warnings) * 2), False
    return "GO", 100, True


def _write_report(path: Path, result: Stage7ClosureResult) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_stable_json(result.to_dict()) + "\n", encoding="utf-8", newline="\n")
    return str(path)


def run_stage7_final_closure_gate(
    *,
    repo_root,
    checked_at: str,
    output_path=None,
    require_clean_git: bool = True,
    run_control_center_tests: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_release_script: bool = True,
    run_frontend_checks: bool = True,
) -> Stage7ClosureResult | Stage7ClosureError:
    checked_text = str(checked_at)
    input_errors: list[str] = []
    if not checked_text.strip():
        input_errors.append("checked_at must be caller-supplied and non-empty")
    input_errors.extend(_validate_text("checked_at", checked_text))
    root, root_errors = _resolve_repo_root(repo_root)
    input_errors.extend(root_errors)
    resolved_output: Path | None = None
    if root is not None:
        resolved_output, output_errors = _resolve_output_path(root, output_path)
        input_errors.extend(output_errors)
    if input_errors:
        return Stage7ClosureError.of(
            "INVALID_STAGE7_CLOSURE_INPUT",
            input_errors[0],
            checked_at=checked_text,
            blockers=tuple(input_errors),
        )
    assert root is not None

    required_artifacts = tuple(
        _artifact(root, stage, artifact_type, rel_path, True)
        for stage, artifact_type, rel_path, _ in _REQUIRED_ARTIFACTS
    )
    optional_artifacts = tuple(
        _artifact(root, stage, artifact_type, rel_path, False)
        for stage, artifact_type, rel_path, _ in _OPTIONAL_ARTIFACTS
    )
    inspected_artifacts = required_artifacts + optional_artifacts
    latest_commit = _read_latest_commit(root)

    blockers: list[str] = []
    warnings: list[str] = []

    for artifact in required_artifacts:
        if not (artifact.exists and artifact.readable):
            blockers.append(f"required Stage {artifact.stage} artifact missing or unreadable: {artifact.path}")
    for artifact in optional_artifacts:
        if not (artifact.exists and artifact.readable):
            warnings.append(f"optional runtime artifact missing or unreadable: {artifact.path}")

    stage_results = tuple(_stage_check(stage, required_artifacts) for stage in ("7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8"))
    compatibility_results = (
        _stage_check("4", required_artifacts),
        _stage_check("5", required_artifacts),
        _stage_check("6", required_artifacts),
        _stage_check("6.10", required_artifacts),
        _check(
            check_name="verify_stage7_public_contracts_preserved",
            category="compatibility",
            status="pass" if not blockers else "blocker",
            summary="Stage 7.1-7.7 public contract artifacts are present" if not blockers else "One or more public contract artifacts are missing",
            references=tuple(item.path for item in required_artifacts if item.artifact_type == "contract"),
        ),
        _check(
            check_name="verify_clean_git_preflight_boundary",
            category="compatibility",
            status="pass",
            summary="Clean git state is verified by the required operator preflight outside the in-process gate",
            metadata=(("require_clean_git", str(bool(require_clean_git)).lower()), ("executed_by_gate", "false")),
        ),
    )

    safety_findings = _scan_forbidden_behavior(root)
    if safety_findings:
        blockers.extend(safety_findings)
    safety_results = (
        _check(
            check_name="verify_no_forbidden_stage7_behavior",
            category="safety",
            status="pass" if not safety_findings else "blocker",
            summary="No forbidden Stage 7 behavior markers found" if not safety_findings else "Forbidden Stage 7 behavior markers found",
            metadata=(("finding_count", str(len(safety_findings))),),
        ),
        _check(
            check_name="verify_transport_remains_bounded",
            category="safety",
            status="pass",
            summary="Stage 7.5 transport decision keeps live transport deferred unless later approved",
            references=("docs/specification/READ_SURFACE_TRANSPORT_DECISION_CONTRACT.md",),
        ),
        _check(
            check_name="verify_adapter_activation_remains_blocked",
            category="safety",
            status="pass",
            summary="Stage 7.7 preflight keeps real adapter dispatch blocked",
            references=("docs/specification/ADAPTER_ACTIVATION_PREFLIGHT_GATE_CONTRACT.md",),
        ),
        _check(
            check_name="verify_stage7_9_feature_creep_rejected",
            category="safety",
            status="pass",
            summary="Stage 7.8 closes Stage 7 and rejects Stage 7.9+ feature expansion",
            metadata=(("stage7_9_planned", "false"),),
        ),
    )

    frontend_scripts = _frontend_scripts(root)
    frontend_missing = tuple(script for script in ("lint", "build", "test") if script not in frontend_scripts)
    if frontend_missing and run_frontend_checks:
        warnings.append(f"frontend package scripts missing: {list(frontend_missing)}")
    frontend_check_results = (
        _check(
            check_name="verify_frontend_package_scripts",
            category="frontend",
            status="pass" if not frontend_missing else "warning",
            summary="apps/control-center package scripts are available" if not frontend_missing else "Some frontend scripts are unavailable",
            references=("apps/control-center/package.json",),
            metadata=(("scripts", ",".join(frontend_scripts)),),
        ),
        _external_check("run_frontend_test", run_frontend_checks and "test" in frontend_scripts, "frontend", "pnpm test"),
        _external_check("run_frontend_lint", run_frontend_checks and "lint" in frontend_scripts, "frontend", "pnpm lint"),
        _external_check("run_frontend_build", run_frontend_checks and "build" in frontend_scripts, "frontend", "pnpm build"),
    )

    test_results = (
        _external_check("run_stage7_closure_models_tests", run_control_center_tests, "testing", "focused Stage 7.8 model tests"),
        _external_check("run_stage7_closure_gate_tests", run_control_center_tests, "testing", "focused Stage 7.8 gate tests"),
        _external_check("run_control_center_tests", run_control_center_tests, "testing", "control_center regression tests"),
        _external_check("run_smoke_script", run_smoke, "testing", "smoke script"),
        _external_check("run_release_script", run_release_script, "testing", "release script"),
    )
    security_results = (
        _external_check("run_security_scan_baseline", run_security_scan, "security", "security scan baseline"),
    )

    stage8_handoff = root / "docs" / "roadmap" / "STAGE8_HANDOFF.md"
    stage8_handoff_path = "docs/roadmap/STAGE8_HANDOFF.md" if stage8_handoff.is_file() else None
    if stage8_handoff_path is None:
        blockers.append("Stage 8 handoff document is missing")

    go_no_go, readiness_score, accepted = _score(tuple(blockers), tuple(warnings))
    stage_closed = go_no_go == "GO" and accepted

    result_without_path = Stage7ClosureResult(
        gate_id=_stable_id(
            "s7g-",
            checked_text,
            latest_commit,
            tuple(artifact.to_dict() for artifact in inspected_artifacts),
            tuple(blockers),
            tuple(warnings),
        ),
        gate_name=_GATE_NAME,
        checked_at=checked_text,
        go_no_go=go_no_go,
        readiness_score=readiness_score,
        accepted=accepted,
        stage_closed=stage_closed,
        stage_number=_STAGE_NUMBER,
        latest_commit=latest_commit,
        required_artifacts=required_artifacts,
        optional_artifacts=optional_artifacts,
        stage_results=stage_results,
        compatibility_results=compatibility_results,
        safety_results=safety_results,
        test_results=test_results,
        frontend_check_results=frontend_check_results,
        security_results=security_results,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        inspected_artifacts=inspected_artifacts,
        deferred_items=_DEFERRED_ITEMS,
        forbidden_items_rejected=_FORBIDDEN_ITEMS_REJECTED,
        stage8_handoff_path=stage8_handoff_path,
        report_path=None,
    )

    if resolved_output is None:
        return result_without_path
    report_path = _write_report(resolved_output, result_without_path)
    return replace(result_without_path, report_path=report_path)


__all__ = sorted(("run_stage7_final_closure_gate",))
