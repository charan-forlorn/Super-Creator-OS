"""SCOS Stage 4.19 final commercial release gate (Stage 4 closure).

Read-only certification layer over the Stage 4.1-4.18 commercial foundation.
It verifies the Stage 4 contract docs, executable source inventory, the Stage
4.18 hardening assets, the no-further-Stage-4-fragmentation rule, and
(optionally) runs the approved local verification scripts, then computes a
deterministic readiness score and a GO / CONDITIONAL_GO / NO_GO verdict plus
the deterministic Stage 5 handoff items.

Boundary notes:
- This layer inspects; it never rebuilds reports, never sends anything, and
  never mutates any Stage 4.1-4.18 artifact. The only write it can perform is
  the single gate-report JSON at the caller-supplied ``output_path``.
- ``subprocess`` is used here as a documented, narrow exception to the
  commercial no-subprocess convention: read-only ``git`` queries and the
  approved local verification scripts under ``scripts/`` only. Nothing else.
- Deterministic: no real clock, no randomness, no uuid, no environment reads.
  ``checked_at`` is caller-supplied; the gate id is a SHA-256 derivation.
- The forbidden-behavior scan tokens below are assembled from string
  fragments so this file's own text stays free of the literal tokens it
  hunts for (repo convention; keeps the security baseline scan clean).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .release_gate_models import (
        STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
        Stage4FinalReleaseGateError,
        Stage4FinalReleaseGateResult,
        Stage4ReleaseBlocker,
        Stage4ReleaseCheck,
        Stage5HandoffItem,
    )
    from .manifest_tools import write_stable_json
except ImportError:  # direct-module execution (tests insert the package dir)
    from release_gate_models import (
        STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
        Stage4FinalReleaseGateError,
        Stage4FinalReleaseGateResult,
        Stage4ReleaseBlocker,
        Stage4ReleaseCheck,
        Stage5HandoffItem,
    )
    from manifest_tools import write_stable_json

_GATE_NAME = "stage4-final-commercial-release-gate"
_STAGE = "stage-4.19"
_GENERATOR = "scos.commercial.stage4_final_release_gate"
_OUTPUT_FILENAME = "stage4_final_release_gate.json"

_URL_PREFIXES = ("http://", "https://")
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9]+")

_GIT_TIMEOUT_SECONDS = 60
_SCRIPT_TIMEOUT_SECONDS = 600
_TAIL_LIMIT = 160

READINESS_MAX_SCORE = 100

# Stage 4 contract docs the gate requires, keyed by pipeline label. Actual
# repo filenames differ from some spec labels (e.g. monetization has a
# _REVIEW_ infix; the mini-audit docs carry a FIRST_PROSPECT_ prefix; the
# Control Center doc ends in _DESIGN.md). The label->path mapping is reported
# in check metadata instead of renaming any existing doc.
_CONTRACT_DOCS = (
    ("commercial_report", "docs/specification/COMMERCIAL_REPORT_CONTRACT.md"),
    ("delivery_package", "docs/specification/DELIVERY_PACKAGE_CONTRACT.md"),
    ("commercial_cli", "docs/specification/COMMERCIAL_CLI_CONTRACT.md"),
    ("run_orchestrator", "docs/specification/COMMERCIAL_RUN_ORCHESTRATOR_CONTRACT.md"),
    ("acceptance_gate", "docs/specification/COMMERCIAL_ACCEPTANCE_GATE_CONTRACT.md"),
    ("customer_kit", "docs/specification/FIRST_CUSTOMER_OPERATING_KIT_CONTRACT.md"),
    ("monetization_readiness", "docs/specification/MONETIZATION_READINESS_REVIEW_CONTRACT.md"),
    ("dry_run", "docs/specification/FIRST_PAID_CUSTOMER_DRY_RUN_CONTRACT.md"),
    ("launch_certification", "docs/specification/COMMERCIAL_LAUNCH_CERTIFICATION_PACK_CONTRACT.md"),
    ("operator_practice_lab", "docs/specification/OPERATOR_PRACTICE_LAB_CONTRACT.md"),
    ("first_outreach_launch_kit", "docs/specification/FIRST_OUTREACH_LAUNCH_KIT_CONTRACT.md"),
    ("prospect_execution_log", "docs/specification/FIRST_PROSPECT_EXECUTION_LOG_CONTRACT.md"),
    ("follow_up_decision", "docs/specification/FIRST_PROSPECT_FOLLOW_UP_DECISION_CONTRACT.md"),
    ("mini_audit_handoff", "docs/specification/FIRST_PROSPECT_MINI_AUDIT_HANDOFF_CONTRACT.md"),
    ("mini_audit_delivery_log", "docs/specification/FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_CONTRACT.md"),
    ("outcome_review", "docs/specification/FIRST_PROSPECT_OUTCOME_REVIEW_CONTRACT.md"),
    ("conversion_handoff", "docs/specification/FIRST_CUSTOMER_CONVERSION_HANDOFF_CONTRACT.md"),
    ("final_release_gate", "docs/specification/STAGE4_FINAL_RELEASE_GATE_CONTRACT.md"),
)

# Core Stage 4 executable source inventory, keyed by pipeline category.
_SOURCE_FILES = (
    ("report_builder", "report_builder.py"),
    ("delivery_package", "delivery_package.py"),
    ("cli", "cli.py"),
    ("run_orchestrator", "run_orchestrator.py"),
    ("acceptance_gate", "acceptance_gate.py"),
    ("customer_kit", "customer_kit.py"),
    ("monetization_readiness", "monetization_readiness.py"),
    ("dry_run", "first_paid_customer_dry_run.py"),
    ("launch_certification", "launch_certification_pack.py"),
    ("operator_practice_lab", "operator_practice_lab.py"),
    ("first_outreach_launch_kit", "first_outreach_launch_kit.py"),
    ("prospect_execution_log", "first_prospect_execution_log.py"),
    ("follow_up_decision", "first_prospect_follow_up_decision.py"),
    ("mini_audit_handoff", "first_prospect_mini_audit_handoff.py"),
    ("mini_audit_delivery_log", "first_prospect_mini_audit_delivery_log.py"),
    ("outcome_review", "first_prospect_outcome_review.py"),
    ("conversion_handoff", "first_customer_conversion_handoff.py"),
    ("stage418_domain_models", "domain_models.py"),
    ("stage418_validation", "validation.py"),
    ("stage418_manifest_tools", "manifest_tools.py"),
)

# Stage 4.18 hardening assets (modules + docs + scripts).
_HARDENING_ASSETS = (
    "scos/commercial/domain_models.py",
    "scos/commercial/validation.py",
    "scos/commercial/manifest_tools.py",
    "docs/testing/TEST_SUITE_STRATEGY.md",
    "docs/security/SECURITY_HARDENING_BASELINE.md",
    "docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md",
    "docs/specification/SHARED_REPORTING_FRAMEWORK_CONTRACT.md",
    "scripts/test_smoke.py",
    "scripts/test_release.py",
    "scripts/security_scan_baseline.py",
)

_SMOKE_SCRIPT = "scripts/test_smoke.py"
_SECURITY_SCRIPT = "scripts/security_scan_baseline.py"
_RELEASE_SCRIPT = "scripts/test_release.py"

# Stage-over-fragmentation markers (Stage 4.20 and later). The regex matches
# Stage 4.20-4.29 markers but never plain "Stage 4.2" (a legitimate stage).
_STAGE_MARKER_RE = re.compile(r"[Ss]tage[- ]4\.2[0-9]")
_STAGE_SCAN_DIRS = ("docs/certification", "docs/specification")
# A marker mention on a negation / non-goal line is allowed (e.g. a plan doc
# stating the rule that later stages must not be created).
_NEGATION_TOKENS = ("no ", "not ", "never", "forbid", "refus", "do not", "must not", "non-goal")

# Forbidden implementation imports for executable commercial source, grouped
# by behavior category. Tokens are assembled from fragments (repo convention).
_FORBIDDEN_IMPORT_TOKENS = (
    ("network", "requ" + "ests"),
    ("network", "urllib" + ".request"),
    ("network", "http" + ".client"),
    ("network", "soc" + "ket"),
    ("network", "aio" + "http"),
    ("network", "htt" + "px"),
    ("network", "smt" + "plib"),
    ("network", "web" + "soc" + "ket"),
    ("network", "web" + "soc" + "kets"),
    ("api_server", "fla" + "sk"),
    ("api_server", "fast" + "api"),
    ("api_server", "dja" + "ngo"),
    ("api_server", "torn" + "ado"),
    ("api_server", "http" + ".server"),
    ("database", "sql" + "ite3"),
    ("database", "psy" + "copg"),
    ("database", "pym" + "ongo"),
    ("database", "sqlal" + "chemy"),
    ("database", "red" + "is"),
    ("money_capture", "stri" + "pe"),
    ("money_capture", "pay" + "pal"),
    ("money_capture", "brain" + "tree"),
    ("relationship_sync", "hub" + "spot"),
    ("relationship_sync", "sales" + "force"),
    ("relationship_sync", "pipe" + "drive"),
    ("relationship_sync", "zo" + "ho"),
    ("messaging_service", "send" + "grid"),
    ("messaging_service", "twi" + "lio"),
    ("model_api", "open" + "ai"),
    ("model_api", "anthro" + "pic"),
    ("cloud_storage", "bot" + "o3"),
)

# Deterministic Stage 5 handoff items: (item_id, title, category, priority,
# description, stage5_owner, source_stage4_evidence).
_STAGE5_HANDOFF_ITEMS = (
    ("stage5-001", "Implement the Control Center backend",
     "control_center_backend", "urgent",
     "Build the real Control Center backend that executes operator commands, "
     "following the Stage 4.18 command API design. Stage 4 shipped the design only.",
     "stage5-platform", "docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md"),
    ("stage5-002", "Implement the Control Center command API",
     "command_api", "urgent",
     "Turn the Stage 4.18 command API design into a working local command "
     "surface with typed request, result, and error envelopes.",
     "stage5-platform", "docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md"),
    ("stage5-003", "Design and implement the operator event stream",
     "event_stream", "high",
     "Deliver the event stream that surfaces command progress and pipeline "
     "state changes to the Control Center, per the Stage 4.18 design notes.",
     "stage5-platform", "docs/specification/CONTROL_CENTER_COMMAND_API_DESIGN.md"),
    ("stage5-004", "Build the operator approval workflow",
     "operator_approval", "urgent",
     "Every outward-facing action must pass an explicit operator approval "
     "step before execution, preserving the Stage 4 manual-only boundary.",
     "stage5-operations", "docs/security/SECURITY_HARDENING_BASELINE.md"),
    ("stage5-005", "Enhance release provenance",
     "security", "high",
     "Extend the local release gate with machine-readable release reports, "
     "branch/HEAD policy enforcement, and a recorded provenance chain.",
     "stage5-security", "scripts/test_release.py"),
    ("stage5-006", "Adopt SBOM and dependency vulnerability tooling",
     "security", "high",
     "Generate a software bill of materials and scan dependencies for known "
     "vulnerabilities as part of the release flow.",
     "stage5-security", "docs/security/SECURITY_HARDENING_BASELINE.md"),
    ("stage5-007", "Add artifact signing or stronger integrity",
     "security", "normal",
     "Upgrade artifact integrity from SHA-256 manifests to signed artifacts "
     "or an equivalent tamper-evident mechanism.",
     "stage5-security", "scos/commercial/manifest_tools.py"),
    ("stage5-008", "Productize the first-customer workflow",
     "productization", "high",
     "Turn the Stage 4.10-4.17 first-customer pipeline into a repeatable, "
     "documented operator workflow with templates and playbooks.",
     "stage5-commercial", "docs/specification/FIRST_CUSTOMER_CONVERSION_HANDOFF_CONTRACT.md"),
    ("stage5-009", "Add monitoring and maintenance hooks",
     "monitoring", "normal",
     "Define health checks, drift detection, and maintenance routines for the "
     "commercial pipeline per the test-suite strategy tiers.",
     "stage5-operations", "docs/testing/TEST_SUITE_STRATEGY.md"),
    ("stage5-010", "Define the real-integration boundary and Stage 5 success criteria",
     "commercial_execution", "urgent",
     "Decide which external integrations Stage 5 may build, how they stay "
     "behind the operator approval boundary, and what measurable criteria "
     "close Stage 5.",
     "stage5-lead", "docs/roadmap/STAGE5_HANDOFF.md"),
)

_STAGE5_HANDOFF_DOC = "docs/roadmap/STAGE5_HANDOFF.md"

# Readiness scoring buckets: (bucket_name, weight, check names it covers).
_SCORE_BUCKETS = (
    ("contract_source", 25,
     ("validate_stage4_contract_files", "validate_commercial_source_files")),
    ("hardening_foundation", 20, ("validate_hardening_foundation",)),
    ("verification_scripts", 20, ("run_smoke_script", "run_security_scan_baseline")),
    ("forbidden_behavior", 15, ("validate_static_forbidden_behavior",)),
    ("git_release_safety", 10, ("validate_git_state",)),
    ("stage5_handoff", 10, ("validate_stage5_handoff_readiness",)),
)


def _is_url(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower().startswith(_URL_PREFIXES)


def _sanitize(text: str) -> str:
    cleaned = _SANITIZE_RE.sub("-", str(text)).strip("-").lower()
    return cleaned or "repo"


def _release_gate_id(repo_root: Path, checked_at: str) -> str:
    digest = hashlib.sha256(
        "|".join((checked_at, repo_root.name, _GATE_NAME)).encode("utf-8")
    ).hexdigest()[:12]
    return f"{_GATE_NAME}-{_sanitize(repo_root.name)}-{_sanitize(checked_at)}-{digest}"


def _tail_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    return tail[:_TAIL_LIMIT]


def _script_interpreter(repo_root: Path) -> str:
    """Windows venv interpreter when present, else the current interpreter.

    ``sys.executable`` is the deterministic stand-in for the documented
    ``python`` fallback: it avoids PATH ambiguity while satisfying the same
    intent (run the script with a plain local Python).
    """
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def _run_repo_script(repo_root: Path, rel_script: str) -> tuple[int | None, str]:
    """Run one approved local verification script; return (exit_code, tail).

    ``exit_code`` is None when the script is missing or could not be started.
    Only stdout's last non-empty line is captured (scripts print deterministic
    summaries and redact their own findings; no secrets are echoed).
    """
    script = repo_root / rel_script
    if not script.is_file():
        return None, "script not found"
    try:
        proc = subprocess.run(
            [_script_interpreter(repo_root), str(script)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_SCRIPT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, type(exc).__name__
    return proc.returncode, _tail_line(proc.stdout)


def _git_query(repo_root: Path, args: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Run one read-only git query; return (stdout, error). Never mutates."""
    try:
        proc = subprocess.run(
            ("git",) + args,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return None, "GIT_UNAVAILABLE"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, type(exc).__name__
    if proc.returncode != 0:
        return None, f"exit {proc.returncode}: {_tail_line(proc.stderr)}"
    return proc.stdout.strip(), None


def _line_is_negated(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _NEGATION_TOKENS)


def _scan_stage_markers(repo_root: Path) -> list[dict[str, Any]]:
    """Find Stage 4.20+ markers in certification/specification docs.

    Filename matches always count. Content matches on negation / non-goal
    lines are allowed (documenting the rule is not violating it).
    """
    findings: list[dict[str, Any]] = []
    for rel_dir in _STAGE_SCAN_DIRS:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            rel = f"{rel_dir}/{path.name}"
            if _STAGE_MARKER_RE.search(path.name):
                findings.append({"file": rel, "line": 0, "kind": "filename"})
            if path.suffix.lower() != ".md":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if _STAGE_MARKER_RE.search(line) and not _line_is_negated(line):
                    findings.append({"file": rel, "line": line_no, "kind": "content"})
    return findings


def _scan_forbidden_imports(repo_root: Path) -> list[dict[str, str]]:
    """Scan executable commercial source (not tests, not docs) for forbidden imports."""
    commercial_dir = repo_root / "scos" / "commercial"
    token_category = {token: category for category, token in _FORBIDDEN_IMPORT_TOKENS}
    pattern = re.compile(
        r"^\s*(?:import|from)\s+("
        + "|".join(re.escape(token) for token in sorted(token_category))
        + r")\b",
        re.MULTILINE,
    )
    findings: list[dict[str, str]] = []
    for path in sorted(commercial_dir.glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append({"file": path.name, "token": "<unreadable>", "category": "scan"})
            continue
        for match in pattern.finditer(text):
            token = match.group(1)
            findings.append({
                "file": path.name,
                "token": token,
                "category": token_category[token],
            })
    return findings


def _build_handoff_items() -> tuple[Stage5HandoffItem, ...]:
    return tuple(
        Stage5HandoffItem.of(
            item_id,
            title,
            category,
            priority,
            description=description,
            stage5_owner=owner,
            source_stage4_evidence=evidence,
        )
        for item_id, title, category, priority, description, owner, evidence
        in _STAGE5_HANDOFF_ITEMS
    )


def _compute_readiness(checks: list[Stage4ReleaseCheck]) -> tuple[int, dict[str, int]]:
    """Score buckets: full when all covered checks succeed, zero on any
    failure, half (floor) when skipped without failure."""
    by_name: dict[str, list[str]] = {}
    for check in checks:
        by_name.setdefault(check.check_name, []).append(check.status)
    score = 0
    breakdown: dict[str, int] = {}
    for bucket_name, weight, names in _SCORE_BUCKETS:
        statuses = [status for name in names for status in by_name.get(name, ["skipped"])]
        if any(status == "failure" for status in statuses):
            earned = 0
        elif any(status == "skipped" for status in statuses):
            earned = weight // 2
        else:
            earned = weight
        breakdown[bucket_name] = earned
        score += earned
    return score, breakdown


def run_stage4_final_release_gate(
    *,
    repo_root,
    checked_at: str,
    output_path=None,
    require_clean_git: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_release_script: bool = False,
    allow_warnings: bool = True,
) -> Stage4FinalReleaseGateResult | Stage4FinalReleaseGateError:
    checks: list[Stage4ReleaseCheck] = []
    blockers: list[Stage4ReleaseBlocker] = []

    def _check(
        check_name: str,
        status: str,
        severity: str = "info",
        *,
        category: str = "release_readiness",
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        checks.append(Stage4ReleaseCheck.of(
            check_name, status, severity,
            category=category, artifact_path=artifact_path,
            error_kind=error_kind, error_detail=error_detail, metadata=metadata,
        ))

    def _blocker(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        source_check: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        blockers.append(Stage4ReleaseBlocker.of(
            blocker_id, category, severity, title, detail,
            recommended_action, source_check, metadata,
        ))

    def _error(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        metadata: dict[str, Any] | None = None,
    ) -> Stage4FinalReleaseGateError:
        return Stage4FinalReleaseGateError.of(
            error_kind, error_detail, failed_check,
            tuple(checks), tuple(blockers), metadata,
        )

    # 1. validate_inputs ----------------------------------------------------
    if repo_root is None or str(repo_root).strip() == "":
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="repo_root is required")
        return _error("INVALID_ARGUMENTS", "repo_root is required", "validate_inputs")
    if not isinstance(checked_at, str) or not checked_at.strip():
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs")
    if _is_url(repo_root):
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="repo_root must be a local path")
        return _error("INVALID_ARGUMENTS", "repo_root must be a local path", "validate_inputs")
    if output_path is not None and _is_url(output_path):
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="output_path must be a local path")
        return _error("INVALID_ARGUMENTS", "output_path must be a local path", "validate_inputs")
    root = Path(str(repo_root))
    if not root.is_dir():
        _check("validate_inputs", "failure", "error", category="preflight",
               artifact_path=str(root),
               error_kind="INPUT_NOT_FOUND",
               error_detail="repo_root does not exist or is not a directory")
        return _error("INPUT_NOT_FOUND", "repo_root does not exist or is not a directory",
                      "validate_inputs", metadata={"repo_root": str(root)})
    root = root.resolve()
    gate_id = _release_gate_id(root, checked_at)
    _check("validate_inputs", "success", category="preflight", artifact_path=str(root),
           metadata={"release_gate_id": gate_id})

    # 2. validate_git_state --------------------------------------------------
    if require_clean_git:
        git_facts: dict[str, str] = {}
        git_problems: list[str] = []
        unavailable = False
        for label, args in (
            ("status", ("status", "--short", "--untracked-files=all")),
            ("head", ("rev-parse", "HEAD")),
            ("origin_main", ("rev-parse", "origin/main")),
            ("branch", ("branch", "--show-current")),
        ):
            out, err = _git_query(root, args)
            if err == "GIT_UNAVAILABLE":
                unavailable = True
                break
            if err is not None:
                git_problems.append(f"{label}: {err}")
            else:
                git_facts[label] = out or ""
        if unavailable:
            _check("validate_git_state", "failure", "critical", category="preflight",
                   error_kind="GIT_UNAVAILABLE",
                   error_detail="git binary is not available")
            return _error("GIT_UNAVAILABLE", "git binary is not available",
                          "validate_git_state")
        if not git_problems:
            if git_facts.get("branch") != "main":
                git_problems.append(f"branch is {git_facts.get('branch')!r}, expected 'main'")
            if git_facts.get("head") != git_facts.get("origin_main"):
                git_problems.append("HEAD does not equal origin/main")
            if git_facts.get("status"):
                git_problems.append("working tree is not clean")
        if git_problems:
            _check("validate_git_state", "failure", "critical", category="preflight",
                   error_kind="GIT_STATE_FAILED",
                   error_detail="; ".join(git_problems),
                   metadata={"problems": git_problems})
            _blocker("blk-git-state", "preflight", "critical",
                     "Git state does not meet the release policy",
                     "; ".join(git_problems),
                     "Commit or restore the working tree on main with HEAD == origin/main, "
                     "then re-run the gate.",
                     "validate_git_state", metadata={"problems": git_problems})
        else:
            _check("validate_git_state", "success", category="preflight",
                   metadata={"branch": git_facts.get("branch", ""),
                             "head": git_facts.get("head", ""),
                             "clean": True})
    else:
        # Explicit operator waiver: recorded transparently, scored at half
        # weight, and deliberately not counted as a warning.
        _check("validate_git_state", "skipped", category="preflight",
               metadata={"reason": "require_clean_git=False"})

    # 3. validate_stage4_contract_files ---------------------------------------
    contract_mapping = {label: rel for label, rel in _CONTRACT_DOCS}
    missing_contracts = sorted(
        label for label, rel in _CONTRACT_DOCS if not (root / rel).is_file()
    )
    if missing_contracts:
        _check("validate_stage4_contract_files", "failure", "error",
               category="source_contract",
               error_kind="CONTRACT_DOC_MISSING",
               error_detail="required Stage 4 contract docs are missing",
               metadata={"missing": missing_contracts, "mapping": contract_mapping})
        _blocker("blk-contract-docs", "source_contract", "error",
                 "Stage 4 contract docs are missing",
                 f"missing: {', '.join(missing_contracts)}",
                 "Restore the missing contract docs before closing Stage 4.",
                 "validate_stage4_contract_files", metadata={"missing": missing_contracts})
    else:
        _check("validate_stage4_contract_files", "success", category="source_contract",
               metadata={"verified": len(_CONTRACT_DOCS), "mapping": contract_mapping})

    # 4. validate_commercial_source_files -------------------------------------
    source_mapping = {label: name for label, name in _SOURCE_FILES}
    commercial_dir = root / "scos" / "commercial"
    missing_sources = sorted(
        label for label, name in _SOURCE_FILES if not (commercial_dir / name).is_file()
    )
    if missing_sources:
        _check("validate_commercial_source_files", "failure", "error",
               category="commercial_pipeline",
               error_kind="SOURCE_FILE_MISSING",
               error_detail="required Stage 4 source files are missing",
               metadata={"missing": missing_sources, "mapping": source_mapping})
        _blocker("blk-source-files", "commercial_pipeline", "error",
                 "Stage 4 commercial source files are missing",
                 f"missing: {', '.join(missing_sources)}",
                 "Restore the missing source files before closing Stage 4.",
                 "validate_commercial_source_files", metadata={"missing": missing_sources})
    else:
        _check("validate_commercial_source_files", "success",
               category="commercial_pipeline",
               metadata={"verified": len(_SOURCE_FILES), "mapping": source_mapping})

    # 5. validate_hardening_foundation ----------------------------------------
    missing_hardening = sorted(
        rel for rel in _HARDENING_ASSETS if not (root / rel).is_file()
    )
    if missing_hardening:
        _check("validate_hardening_foundation", "failure", "error",
               category="hardening_foundation",
               error_kind="HARDENING_ASSET_MISSING",
               error_detail="Stage 4.18 hardening assets are missing",
               metadata={"missing": missing_hardening})
        _blocker("blk-hardening-assets", "hardening_foundation", "error",
                 "Stage 4.18 hardening assets are missing",
                 f"missing: {', '.join(missing_hardening)}",
                 "Restore the Stage 4.18 hardening assets before closing Stage 4.",
                 "validate_hardening_foundation", metadata={"missing": missing_hardening})
    else:
        _check("validate_hardening_foundation", "success",
               category="hardening_foundation",
               metadata={"verified": len(_HARDENING_ASSETS)})

    # 6. validate_no_stage4_20 -------------------------------------------------
    marker_findings = _scan_stage_markers(root)
    if marker_findings:
        _check("validate_no_stage4_20", "failure", "critical",
               category="release_readiness",
               error_kind="STAGE_OVER_FRAGMENTATION",
               error_detail="Stage 4.20+ markers were found",
               metadata={"findings": marker_findings})
        _blocker("blk-stage-over-fragmentation", "release_readiness", "critical",
                 "STAGE_OVER_FRAGMENTATION",
                 f"Stage 4.20+ markers found in {len(marker_findings)} location(s).",
                 "Move any future work to the Stage 5 backlog / handoff; "
                 "Stage 4 ends at 4.19.",
                 "validate_no_stage4_20", metadata={"findings": marker_findings})
    else:
        _check("validate_no_stage4_20", "success", category="release_readiness",
               metadata={"scanned_dirs": list(_STAGE_SCAN_DIRS)})

    # 7. run_smoke_script --------------------------------------------------------
    if run_smoke:
        exit_code, tail = _run_repo_script(root, _SMOKE_SCRIPT)
        if exit_code == 0:
            _check("run_smoke_script", "success", category="testing",
                   artifact_path=_SMOKE_SCRIPT,
                   metadata={"exit_code": 0, "tail": tail})
        else:
            _check("run_smoke_script", "failure", "error", category="testing",
                   artifact_path=_SMOKE_SCRIPT,
                   error_kind="SMOKE_SCRIPT_FAILED",
                   error_detail="smoke script did not pass",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-smoke-script", "testing", "error",
                     "Smoke script failed",
                     f"{_SMOKE_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Fix the smoke failures before closing Stage 4.",
                     "run_smoke_script", metadata={"exit_code": exit_code})
    else:
        _check("run_smoke_script", "skipped", category="testing",
               metadata={"reason": "run_smoke=False"})

    # 8. run_security_scan_baseline -----------------------------------------------
    if run_security_scan:
        exit_code, tail = _run_repo_script(root, _SECURITY_SCRIPT)
        if exit_code == 0:
            _check("run_security_scan_baseline", "success", category="security",
                   artifact_path=_SECURITY_SCRIPT,
                   metadata={"exit_code": 0, "tail": tail})
        else:
            # The baseline scanner never scans docs, so a failure here is a
            # real finding in executable/config scope, never a docs-only
            # wording false positive. Findings stay redacted in the scanner.
            _check("run_security_scan_baseline", "failure", "error", category="security",
                   artifact_path=_SECURITY_SCRIPT,
                   error_kind="SECURITY_SCAN_FAILED",
                   error_detail="security scan baseline reported findings",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-security-scan", "security", "error",
                     "Security scan baseline failed",
                     f"{_SECURITY_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Resolve the security findings before closing Stage 4.",
                     "run_security_scan_baseline", metadata={"exit_code": exit_code})
    else:
        _check("run_security_scan_baseline", "skipped", category="security",
               metadata={"reason": "run_security_scan=False"})

    # 9. run_release_script_optional ------------------------------------------------
    if run_release_script:
        exit_code, tail = _run_repo_script(root, _RELEASE_SCRIPT)
        if exit_code == 0:
            _check("run_release_script", "success", category="testing",
                   artifact_path=_RELEASE_SCRIPT,
                   metadata={"exit_code": 0, "tail": tail})
        else:
            _check("run_release_script", "failure", "error", category="testing",
                   artifact_path=_RELEASE_SCRIPT,
                   error_kind="RELEASE_SCRIPT_FAILED",
                   error_detail="release script did not pass",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-release-script", "testing", "error",
                     "Release script failed",
                     f"{_RELEASE_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Fix the release-script failures before closing Stage 4.",
                     "run_release_script", metadata={"exit_code": exit_code})
    else:
        _check("run_release_script", "skipped", category="testing",
               metadata={"reason": "run_release_script=False; run manually before tagging"})

    # 10. validate_static_forbidden_behavior ------------------------------------------
    if commercial_dir.is_dir():
        forbidden_findings = _scan_forbidden_imports(root)
    else:
        forbidden_findings = [{"file": "scos/commercial", "token": "<missing>",
                               "category": "scan"}]
    if forbidden_findings:
        _check("validate_static_forbidden_behavior", "failure", "critical",
               category="security",
               error_kind="FORBIDDEN_BEHAVIOR_DETECTED",
               error_detail="forbidden implementation imports found in executable source",
               metadata={"findings": forbidden_findings})
        _blocker("blk-forbidden-behavior", "security", "critical",
                 "Forbidden behavior detected in executable source",
                 f"{len(forbidden_findings)} forbidden import finding(s) in "
                 "scos/commercial executable source.",
                 "Remove the forbidden implementation before closing Stage 4; "
                 "docs may mention these capabilities only as non-goals.",
                 "validate_static_forbidden_behavior",
                 metadata={"findings": forbidden_findings})
    else:
        _check("validate_static_forbidden_behavior", "success", category="security",
               metadata={"scanned_scope": "scos/commercial/*.py",
                         "token_count": len(_FORBIDDEN_IMPORT_TOKENS)})

    # 11. validate_stage5_handoff_readiness ---------------------------------------------
    handoff_items = _build_handoff_items()
    handoff_doc = root / _STAGE5_HANDOFF_DOC
    if handoff_doc.is_file():
        _check("validate_stage5_handoff_readiness", "success", category="stage5_handoff",
               artifact_path=_STAGE5_HANDOFF_DOC,
               metadata={"handoff_items": len(handoff_items)})
    else:
        _check("validate_stage5_handoff_readiness", "failure", "error",
               category="stage5_handoff",
               artifact_path=_STAGE5_HANDOFF_DOC,
               error_kind="HANDOFF_DOC_MISSING",
               error_detail="docs/roadmap/STAGE5_HANDOFF.md is missing",
               metadata={"handoff_items": len(handoff_items)})
        _blocker("blk-stage5-handoff-doc", "stage5_handoff", "error",
                 "Stage 5 handoff document is missing",
                 f"{_STAGE5_HANDOFF_DOC} was not found.",
                 "Create the Stage 5 handoff document before closing Stage 4.",
                 "validate_stage5_handoff_readiness")

    # 12. compute_readiness --------------------------------------------------------------
    score, breakdown = _compute_readiness(checks)
    has_critical = any(blocker.severity == "critical" for blocker in blockers)
    has_warnings = (
        bool(blockers)
        or any(check.status == "failure" for check in checks)
        or any(check.status == "skipped" and check.severity != "info" for check in checks)
    )
    if has_critical or score < 75:
        go_no_go = "NO_GO"
        readiness_level = "stage4_blocked"
        stage_closed = False
    elif score >= 90 and not has_warnings:
        go_no_go = "GO"
        readiness_level = "stage4_complete"
        stage_closed = True
    else:
        go_no_go = "CONDITIONAL_GO"
        readiness_level = "stage4_complete_with_warnings"
        stage_closed = bool(allow_warnings)
    _check("compute_readiness", "success", category="release_readiness",
           metadata={"score": score, "breakdown": breakdown,
                     "go_no_go": go_no_go, "has_warnings": has_warnings})

    # Output artifact (written only on this fully-validated result path) ------
    final_output: Path | None = None
    if output_path is not None:
        target = Path(str(output_path))
        final_output = target if target.suffix.lower() == ".json" else target / _OUTPUT_FILENAME

    result = Stage4FinalReleaseGateResult(
        ok=True,
        schema_version=STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
        accepted=stage_closed,
        release_gate_id=gate_id,
        checked_at=checked_at,
        stage=_STAGE,
        stage_closed=stage_closed,
        go_no_go=go_no_go,
        readiness_level=readiness_level,
        readiness_score=score,
        readiness_max_score=READINESS_MAX_SCORE,
        checks=tuple(checks),
        blockers=tuple(blockers),
        stage5_handoff_items=handoff_items,
        output_path=None if final_output is None else str(final_output),
        metadata={
            "generator": _GENERATOR,
            "gate_name": _GATE_NAME,
            "repo_root": str(root),
            "score_breakdown": breakdown,
            "flags": {
                "require_clean_git": bool(require_clean_git),
                "run_smoke": bool(run_smoke),
                "run_security_scan": bool(run_security_scan),
                "run_release_script": bool(run_release_script),
                "allow_warnings": bool(allow_warnings),
            },
        },
    )

    if final_output is not None:
        try:
            final_output.parent.mkdir(parents=True, exist_ok=True)
            write_stable_json(final_output, result.to_dict())
        except OSError as exc:
            _check("write_output", "failure", "error", category="release_readiness",
                   artifact_path=str(final_output),
                   error_kind="OUTPUT_WRITE_FAILED",
                   error_detail="gate report could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "gate report could not be written",
                          "write_output", metadata={"os_error": type(exc).__name__})

    return result


__all__ = ("run_stage4_final_release_gate",)
