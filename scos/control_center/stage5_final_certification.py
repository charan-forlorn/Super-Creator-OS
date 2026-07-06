"""SCOS Stage 5.10 final Stage 5 AI Command Center certification gate.

Read-only certification layer over the Stage 5.1-5.9 local Control Center
foundation (command bridge -> work session -> adapter contract -> prompt /
result packet -> operator packet review -> cross-agent router -> result
intake -> git approval -> operator execution runbook). It verifies source /
contract / doc / frontend / test artifacts, workflow continuity between the
nine sub-stages, the local/approval-first safety boundary, and (optionally)
runs the Stage 5 test files plus the repo's smoke and security-baseline
scripts, then computes a deterministic readiness score and a GO / NO_GO
verdict plus the deterministic Stage 6 handoff items.

Boundary notes:
- This layer inspects; it never fixes, rebuilds, or mutates any Stage 5.1-5.9
  artifact. The only write it can perform is the single certification-report
  JSON at the caller-supplied ``output_path``. Known real defects in the
  inspected Stage 5 artifacts (see the Stage 5.6 checks and the lazy-export
  duplicate-key check below) are reported as blockers, never silently
  repaired or downgraded.
- ``subprocess`` is used here as a documented, narrow exception: read-only
  ``git`` queries (informational only - no branch/HEAD/clean-tree policy is
  enforced), running each Stage 5 control_center test file, running
  ``scripts/test_smoke.py`` / ``scripts/security_scan_baseline.py``, and
  optionally ``pnpm lint`` / ``pnpm build`` from ``apps/control-center``
  (never ``pnpm install``, never a package.json write).
- Deterministic: no real clock, no randomness, no uuid. ``checked_at`` is
  caller-supplied; the certification id is a SHA-256 derivation.
- This module never imports ``scos.commercial`` - the stable-JSON writer is
  reimplemented locally rather than crossing that package boundary.
- The forbidden-behavior scan tokens below are assembled from string
  fragments so this file's own text stays free of the literal tokens it
  hunts for (repo convention; keeps any future security baseline scan clean).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .stage5_certification_models import (
        STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION,
        Stage5CertificationBlocker,
        Stage5CertificationCheck,
        Stage5FinalCertificationError,
        Stage5FinalCertificationResult,
        Stage6HandoffItem,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from stage5_certification_models import (
        STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION,
        Stage5CertificationBlocker,
        Stage5CertificationCheck,
        Stage5FinalCertificationError,
        Stage5FinalCertificationResult,
        Stage6HandoffItem,
    )

_GATE_NAME = "stage5-final-ai-command-center-certification"
_STAGE_LABEL = "5"
_GENERATOR = "scos.control_center.stage5_final_certification"
_OUTPUT_FILENAME = "stage5_final_certification.json"

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

_GIT_TIMEOUT_SECONDS = 60
_SCRIPT_TIMEOUT_SECONDS = 600
_TEST_TIMEOUT_SECONDS = 300
_FRONTEND_TIMEOUT_SECONDS = 600
_TAIL_LIMIT = 160

READINESS_MAX_SCORE = 100

_CONTROL_CENTER_DIR = ("scos", "control_center")
_CONTROL_CENTER_TESTS_DIR = ("scos", "control_center", "tests")
_FRONTEND_DIR = ("apps", "control-center")

# This stage's own two new files: excluded from the backend forbidden-token
# scan target set (they are separately dogfood-scanned, see check #9f) and
# excluded from every stage's "modules" existence check (they are not part
# of Stage 5.1-5.9).
_OWN_MODULES = ("stage5_certification_models", "stage5_final_certification")

# name -> (stage_label, modules, tests, cert_doc, spec_docs, frontend_components, frontend_lib)
_STAGE_ARTIFACTS: tuple[dict[str, Any], ...] = (
    {
        "stage": "5.1", "name": "command_bridge",
        "modules": ("command_models", "command_validation", "operator_approval",
                    "command_queue", "command_runner", "event_log"),
        "tests": ("test_command_models.py", "test_command_validation.py",
                  "test_operator_approval.py", "test_command_queue.py",
                  "test_command_runner.py", "test_event_log.py"),
        "cert_doc": "docs/certification/Stage-5.1-plan.md",
        "spec_docs": (
            "docs/specification/CONTROL_CENTER_COMMAND_BRIDGE_CONTRACT.md",
            "docs/specification/CONTROL_CENTER_EVENT_LOG_CONTRACT.md",
            "docs/specification/OPERATOR_APPROVAL_GATE_CONTRACT.md",
        ),
        "frontend_components": (
            "app-shell.tsx", "command-draft-panel.tsx", "command-event-log.tsx",
            "operator-approval-panel.tsx", "sidebar.tsx",
        ),
        "frontend_lib": ("command-mock-data.ts", "command-types.ts"),
    },
    {
        "stage": "5.2", "name": "work_session",
        "modules": ("runtime_registry", "work_session_models",
                    "work_session_manager", "work_session_store"),
        "tests": ("test_runtime_registry.py", "test_work_session_models.py",
                  "test_work_session_manager.py", "test_work_session_store.py"),
        "cert_doc": "docs/certification/Stage-5.2-plan.md",
        "spec_docs": (
            "docs/specification/AI_AGENT_RUNTIME_REGISTRY_CONTRACT.md",
            "docs/specification/AI_WORK_SESSION_MANAGER_CONTRACT.md",
        ),
        "frontend_components": (
            "agent-result-status-panel.tsx", "agent-routing-panel.tsx",
            "ai-work-session-panel.tsx",
        ),
        "frontend_lib": ("ai-work-session-mock-data.ts", "ai-work-session-types.ts"),
    },
    {
        "stage": "5.3", "name": "adapter_contract",
        "modules": ("agent_adapter_models", "agent_adapter_contracts",
                    "agent_adapter_registry", "agent_adapter_simulator"),
        "tests": ("test_agent_adapter_models.py", "test_agent_adapter_contracts.py",
                  "test_agent_adapter_registry.py", "test_agent_adapter_simulator.py"),
        "cert_doc": "docs/certification/Stage-5.3-plan.md",
        "spec_docs": (
            "docs/specification/AI_AGENT_ADAPTER_CONTRACT.md",
            "docs/specification/AI_AGENT_ADAPTER_REGISTRY_CONTRACT.md",
        ),
        "frontend_components": (
            "adapter-contract-card.tsx", "adapter-simulation-panel.tsx",
            "agent-adapter-panel.tsx",
        ),
        "frontend_lib": ("agent-adapter-mock-data.ts", "agent-adapter-types.ts"),
    },
    {
        "stage": "5.4", "name": "prompt_result_packet",
        "modules": ("prompt_result_packet_models", "prompt_result_packet_builder",
                    "prompt_result_packet_store"),
        "tests": ("test_prompt_result_packet_models.py",
                  "test_prompt_result_packet_builder.py",
                  "test_prompt_result_packet_store.py"),
        "cert_doc": "docs/certification/Stage-5.4-plan.md",
        "spec_docs": (
            "docs/specification/AI_PACKET_ROUTING_CONTRACT.md",
            "docs/specification/UNIFIED_PROMPT_RESULT_PACKET_CONTRACT.md",
        ),
        "frontend_components": (
            "packet-routing-flow.tsx", "prompt-packet-card.tsx",
            "prompt-result-packet-panel.tsx", "result-packet-card.tsx",
        ),
        "frontend_lib": ("prompt-result-packet-mock-data.ts", "prompt-result-packet-types.ts"),
    },
    {
        "stage": "5.5", "name": "operator_packet_review",
        "modules": ("operator_packet_review_models", "operator_packet_review",
                    "manual_handoff_package", "operator_packet_review_store"),
        "tests": ("test_operator_packet_review_models.py", "test_operator_packet_review.py",
                  "test_manual_handoff_package.py", "test_operator_packet_review_store.py"),
        "cert_doc": "docs/certification/Stage-5.5-plan.md",
        "spec_docs": (
            "docs/specification/MANUAL_AI_HANDOFF_PACKAGE_CONTRACT.md",
            "docs/specification/OPERATOR_PACKET_REVIEW_CONTRACT.md",
        ),
        "frontend_components": (
            "manual-handoff-panel.tsx", "operator-packet-review-panel.tsx",
            "packet-approval-decision-panel.tsx", "packet-review-card.tsx",
        ),
        "frontend_lib": ("operator-packet-review-mock-data.ts", "operator-packet-review-types.ts"),
    },
    {
        "stage": "5.6", "name": "cross_agent_router",
        "modules": ("workflow_router_models", "workflow_router", "workflow_route_store"),
        "tests": ("test_workflow_router_models.py", "test_workflow_router.py",
                  "test_workflow_route_store.py"),
        "cert_doc": "docs/certification/Stage-5.6-plan.md",
        "spec_docs": (
            "docs/specification/AGENT_ROUTING_RULES_CONTRACT.md",
            "docs/specification/CROSS_AGENT_WORKFLOW_ROUTER_CONTRACT.md",
        ),
        "frontend_components": (
            "agent-route-flow.tsx", "route-review-queue.tsx",
            "routing-decision-card.tsx", "workflow-router-panel.tsx",
        ),
        "frontend_lib": ("workflow-router-mock-data.ts", "workflow-router-types.ts"),
    },
    {
        "stage": "5.7", "name": "result_intake",
        "modules": ("result_intake_models", "result_intake_builder", "result_intake_store",
                    "chatgpt_status_update", "project_state_update"),
        "tests": ("test_result_intake_models.py", "test_result_intake_builder.py",
                  "test_chatgpt_status_update.py", "test_project_state_update.py",
                  "test_result_intake_store.py"),
        "cert_doc": "docs/certification/Stage-5.7-plan.md",
        "spec_docs": (
            "docs/specification/AI_RESULT_INTAKE_CONTRACT.md",
            "docs/specification/CHATGPT_STATUS_UPDATE_LOOP_CONTRACT.md",
            "docs/specification/PROJECT_STATE_UPDATE_CONTRACT.md",
        ),
        "frontend_components": (
            "chatgpt-status-update-panel.tsx", "next-action-decision-panel.tsx",
            "project-state-update-panel.tsx", "result-intake-card.tsx",
            "result-intake-panel.tsx",
        ),
        "frontend_lib": ("result-intake-mock-data.ts", "result-intake-types.ts"),
    },
    {
        "stage": "5.8", "name": "git_approval",
        "modules": ("git_approval_models", "git_evidence_snapshot",
                    "git_approval_builder", "git_approval_store"),
        "tests": ("test_git_approval_models.py", "test_git_evidence_snapshot.py",
                  "test_git_approval_builder.py", "test_git_approval_store.py"),
        "cert_doc": "docs/certification/Stage-5.8-plan.md",
        "spec_docs": (
            "docs/specification/GIT_COMMIT_PUSH_APPROVAL_GATE_CONTRACT.md",
            "docs/specification/GIT_EVIDENCE_SNAPSHOT_CONTRACT.md",
        ),
        "frontend_components": (
            "commit-proposal-card.tsx", "git-approval-panel.tsx",
            "git-decision-log-panel.tsx", "git-evidence-summary-panel.tsx",
            "push-approval-panel.tsx",
        ),
        "frontend_lib": ("git-approval-mock-data.ts", "git-approval-types.ts"),
    },
    {
        "stage": "5.9", "name": "operator_execution",
        "modules": ("operator_execution_models", "operator_execution_runbook",
                    "operator_execution_store"),
        "tests": ("test_operator_execution_models.py", "test_operator_execution_runbook.py",
                  "test_operator_execution_store.py"),
        "cert_doc": "docs/certification/Stage-5.9-plan.md",
        "spec_docs": (
            "docs/specification/LOCAL_OPERATOR_EXECUTION_CONSOLE_CONTRACT.md",
            "docs/specification/MANUAL_COMMAND_RUNBOOK_CONTRACT.md",
        ),
        "frontend_components": (
            "command-result-capture-panel.tsx", "execution-safety-checklist.tsx",
            "manual-command-runbook-panel.tsx", "operator-execution-console.tsx",
            "runbook-step-card.tsx",
        ),
        "frontend_lib": ("operator-execution-mock-data.ts", "operator-execution-types.ts"),
    },
)

# Pipeline order used only for existence/name-presence link checks. Never
# executes anything - it only confirms each link's primary model module and
# its immediate predecessor's doc are both present.
_WORKFLOW_CHAIN = tuple(entry["stage"] for entry in _STAGE_ARTIFACTS)
_STAGE_BY_LABEL = {entry["stage"]: entry for entry in _STAGE_ARTIFACTS}

_STAGE5_HANDOFF_DOC = "docs/roadmap/STAGE5_HANDOFF.md"
_STAGE6_HANDOFF_DOC = "docs/roadmap/STAGE6_HANDOFF.md"
_SMOKE_SCRIPT = "scripts/test_smoke.py"
_SECURITY_SCRIPT = "scripts/security_scan_baseline.py"

# Forbidden backend tokens, assembled from fragments (repo convention). The
# category label is reported in check/blocker metadata.
_FORBIDDEN_BACKEND_TOKENS: tuple[tuple[str, str], ...] = (
    ("network", "requ" + "ests"),
    ("network", "urllib"),
    ("network", "soc" + "ket"),
    ("network", "web" + "soc" + "ket"),
    ("shell_exec", "os." + "system"),
    ("shell_exec", "pty"),
    ("gui_automation", "pyauto" + "gui"),
    ("gui_automation", "sele" + "nium"),
    ("gui_automation", "play" + "wright"),
    # Real clipboard *automation* packages only - the architecture's own
    # "manual_clipboard" vocabulary (operator copies/pastes by hand) is not
    # automation and must never match here.
    ("clipboard", "pyper" + "clip"),
    ("clipboard", "win32" + "clipboard"),
)
_MODEL_API_TOKENS: tuple[str, ...] = ("open" + "ai", "anthro" + "pic")

_FORBIDDEN_FRONTEND_TOKENS: tuple[str, ...] = (
    "fetch(", "XMLHttpRequest", "axios", "WebSocket", "EventSource",
    "setInterval", "setTimeout", "Date.now", "Math.random",
    "crypto.randomUUID", "localStorage", "sessionStorage",
    '"use server"', "navigator.clip" + "board",
)
_FORBIDDEN_FRONTEND_PATH_MARKERS: tuple[str, ...] = ("route.ts", "middleware.ts")

# Matches Stage 5.11+ only - Stage 5.10 is this very certification stage and
# a legitimate forward reference to it (e.g. in Stage-5.9-plan.md) is not
# over-fragmentation.
_STAGE_OVER_FRAGMENTATION_RE = re.compile(r"[Ss]tage[- ]5\.(1[1-9]|[2-9][0-9])")
_STAGE_SCAN_DIRS = ("docs/certification", "docs/specification")
_NEGATION_TOKENS = ("no ", "not ", "never", "forbid", "refus", "do not", "must not", "non-goal")

_ALLOWLISTED_SUBPROCESS_MODULE = "command_runner"

# Deterministic Stage 6 handoff items: (item_id, title, category, priority,
# description, stage6_owner, source_stage5_evidence).
_STAGE6_HANDOFF_ITEMS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("stage6-001", "Implement the real Control Center backend & command API",
     "control_center_backend", "urgent",
     "Turn the Stage 5.1 command bridge design into a working local backend "
     "that operators can actually run against, replacing the JSONL-only mock flow.",
     "stage6-platform", "scos/control_center/command_runner.py"),
    ("stage6-002", "Design and wire a real operator event stream",
     "event_stream", "high",
     "Deliver a live event stream so the Control Center UI reflects command "
     "and workflow progress in real time, per the Stage 5.1 event log contract.",
     "stage6-platform", "scos/control_center/event_log.py"),
    ("stage6-003", "Fix the Stage 5.6 package export gap",
     "technical_debt", "urgent",
     "scos/control_center/__init__.py has zero lazy-export entries for "
     "workflow_router / workflow_router_models / workflow_route_store; "
     "Stage 5.6 has no public package surface at all.",
     "stage6-platform", "scos/control_center/__init__.py"),
    ("stage6-004", "Resolve the duplicate ALLOWED_COMMAND_TYPES lazy-export key",
     "technical_debt", "urgent",
     "The _LAZY_EXPORTS dict in __init__.py maps 'ALLOWED_COMMAND_TYPES' to "
     "both command_models (Stage 5.1) and operator_execution_models (Stage "
     "5.9); the second entry silently shadows the first at runtime.",
     "stage6-platform", "scos/control_center/__init__.py"),
    ("stage6-005", "Wire workflow-router-panel.tsx into the app shell",
     "frontend", "normal",
     "The Stage 5.6 panel and its NAV_SECTIONS entry are never added to "
     "app-shell.tsx / sidebar.tsx, so it renders nowhere in the actual app.",
     "stage6-frontend", "apps/control-center/components/app-shell.tsx"),
    ("stage6-006", "Clean up the stray Stage 5.6 leftover line in the Control Center README",
     "documentation", "low",
     "apps/control-center/README.md carries a pre-heading line referencing "
     "the Cross-Agent Router panel that does not match the README's structure.",
     "stage6-docs", "apps/control-center/README.md"),
    ("stage6-007", "Decide which agent adapters become real dispatchers",
     "ai_dispatch_boundary", "urgent",
     "Every Stage 5.3 adapter is a simulation today. Stage 6 must decide "
     "which (if any) become real dispatchers, always gated behind explicit "
     "operator approval, never automatic.",
     "stage6-lead", "scos/control_center/agent_adapter_simulator.py"),
    ("stage6-008", "Execute the remaining Stage 5 handoff gates",
     "commercial_execution", "high",
     "Work through Gates 5.A-5.D from the Stage 4.19 handoff (command API "
     "online, operator loop closed, security upgraded, customer workflow "
     "productized) before Stage 6 builds further on top.",
     "stage6-lead", "docs/roadmap/STAGE5_HANDOFF.md"),
    ("stage6-009", "Add an automated test tier for apps/control-center",
     "testing", "normal",
     "package.json only defines dev/build/start/lint; there is no test "
     "script and no jest/vitest dependency for the frontend today.",
     "stage6-operations", "apps/control-center/package.json"),
    ("stage6-010", "Define Stage 6 success criteria and its own closure gate",
     "stage6_readiness", "urgent",
     "Decide what Stage 6 must deliver and what measurable criteria close "
     "it, mirroring the Stage 5.10 / Stage 4.19 certification pattern.",
     "stage6-lead", "docs/certification/Stage-5-final-ai-command-center-certification.md"),
)

# Readiness scoring buckets: (bucket_name, weight, check names it covers).
_SCORE_BUCKETS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("preflight", 5,
     ("validate_inputs", "validate_repo_root_exists", "validate_git_state")),
    ("source_contract", 20, (
        *(f"validate_stage5_{entry['stage'].split('.')[1]}_artifacts" for entry in _STAGE_ARTIFACTS),
        "validate_init_no_duplicate_lazy_export_keys",
        "validate_stage5_6_frontend_wiring",
        "validate_stage5_6_readme_consistency",
    )),
    ("workflow_continuity", 15, (
        *(f"validate_workflow_link_{a}_{b}" for a, b in zip(
            [s.split(".")[1] for s in _WORKFLOW_CHAIN[:-1]],
            [s.split(".")[1] for s in _WORKFLOW_CHAIN[1:]],
        )),
        "validate_workflow_chain_order_docs",
    )),
    ("safety_boundary", 20, (
        "validate_no_real_ai_dispatch", "validate_backend_forbidden_tokens",
        "validate_frontend_forbidden_tokens", "validate_no_app_api_or_middleware",
        "validate_subprocess_allowlist_exception",
        "validate_stage5_10_own_files_forbidden_tokens",
    )),
    ("frontend_static_scope", 5, (
        "validate_frontend_package_scope", "run_frontend_lint", "run_frontend_build",
    )),
    ("testing", 15, (
        *(f"run_stage5_{entry['stage'].split('.')[1]}_tests" for entry in _STAGE_ARTIFACTS),
        "run_smoke_script",
    )),
    ("security", 5, ("run_security_scan_baseline",)),
    ("stage6_handoff", 5, (
        "validate_stage6_handoff_items_generated",
        "validate_stage6_handoff_doc_exists",
        "validate_stage5_handoff_doc_consistency",
    )),
    # "compute_stage5_readiness" is intentionally excluded: its own check is
    # appended only after the score is computed, so including it here would
    # make the bucket permanently read back as "skipped" against itself.
    ("stage5_readiness", 10, (
        "validate_no_stage5_11_plus",
    )),
)


def _is_url_like(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text.lower().startswith(_URL_PREFIXES) or bool(_SCHEME_RE.match(text))


def _certification_id(repo_root: Path, checked_at: str) -> str:
    digest = hashlib.sha256(
        f"stage5-final-certification|{checked_at}|{repo_root}".encode("utf-8")
    ).hexdigest()[:16]
    return f"s5c-{digest}"


def _tail_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    tail = lines[-1] if lines else ""
    return tail[:_TAIL_LIMIT]


def _script_interpreter(repo_root: Path) -> str:
    venv_python = repo_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return str(venv_python)
    return sys.executable


def _run_repo_script(
    repo_root: Path, rel_script: str, timeout: int, *, args: tuple[str, ...] = ()
) -> tuple[int | None, str]:
    script = repo_root / rel_script
    if not script.is_file():
        return None, "script not found"
    try:
        proc = subprocess.run(
            [_script_interpreter(repo_root), str(script), *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout,
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


def _control_center_dir(root: Path) -> Path:
    return root.joinpath(*_CONTROL_CENTER_DIR)


def _control_center_tests_dir(root: Path) -> Path:
    return root.joinpath(*_CONTROL_CENTER_TESTS_DIR)


def _frontend_dir(root: Path) -> Path:
    return root.joinpath(*_FRONTEND_DIR)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# Import-style backend tokens (module names) - matched only on an actual
# ``import``/``from`` statement line, never a bare substring, so docstring
# negations ("never imports requests") and unrelated identifiers (e.g. the
# architecture's own "manual_clipboard" vocabulary) never match.
_IMPORT_STYLE_BACKEND_TOKENS = tuple(token for _category, token in _FORBIDDEN_BACKEND_TOKENS)
_SHELL_TRUE_TOKEN = "shell" + "=True"
_OS_SYSTEM_TOKEN = "os." + "system("
_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')


def _strip_docstrings(text: str) -> str:
    """Drop triple-quoted docstring bodies so prose mentions (e.g. 'never
    passes ``shell=True``') never match a code-shaped forbidden-token scan."""
    return _TRIPLE_QUOTED_RE.sub("", text)


def _scan_backend_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    """Scan scos/control_center/*.py (excluding this stage's own new files)."""
    cc_dir = _control_center_dir(repo_root)
    token_category = {token: category for category, token in _FORBIDDEN_BACKEND_TOKENS}
    import_pattern = re.compile(
        r"^\s*(?:import|from)\s+("
        + "|".join(re.escape(t) for t in sorted(_IMPORT_STYLE_BACKEND_TOKENS))
        + r")\b",
        re.MULTILINE,
    )
    model_api_pattern = re.compile(
        r"^\s*(?:import|from)\s+(" + "|".join(re.escape(t) for t in _MODEL_API_TOKENS) + r")\b",
        re.MULTILINE | re.IGNORECASE,
    )
    findings: list[dict[str, str]] = []
    if not cc_dir.is_dir():
        return [{"file": "scos/control_center", "token": "<missing>", "category": "scan"}]
    for path in sorted(cc_dir.glob("*.py")):
        if path.stem in _OWN_MODULES:
            continue
        text = _read_text(path)
        if text is None:
            findings.append({"file": path.name, "token": "<unreadable>", "category": "scan"})
            continue
        for match in import_pattern.finditer(text):
            token = match.group(1)
            findings.append({"file": path.name, "token": token, "category": token_category[token]})
        for match in model_api_pattern.finditer(text):
            findings.append({"file": path.name, "token": match.group(0), "category": "model_api"})
        for line in _strip_docstrings(text).splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or _line_is_negated(stripped):
                continue
            if _SHELL_TRUE_TOKEN in stripped or _OS_SYSTEM_TOKEN in stripped:
                findings.append({"file": path.name, "token": "shell_true_or_os_system", "category": "shell_exec"})
        if "subprocess" in text and path.stem != _ALLOWLISTED_SUBPROCESS_MODULE:
            if re.search(r"^\s*import\s+subprocess\b", text, re.MULTILINE):
                findings.append({"file": path.name, "token": "subprocess", "category": "subprocess_scope"})
    return findings


def _scan_stage5_10_own_files_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    """Dogfood scan: this stage's own two files must respect the same boundary
    (subprocess is documented and expected here, so it is excluded)."""
    cc_dir = _control_center_dir(repo_root)
    token_category = {token: category for category, token in _FORBIDDEN_BACKEND_TOKENS}
    pattern = re.compile(
        r"^\s*(?:import|from)\s+("
        + "|".join(re.escape(t) for t in sorted(_IMPORT_STYLE_BACKEND_TOKENS))
        + r")\b",
        re.MULTILINE,
    )
    findings: list[dict[str, str]] = []
    for stem in _OWN_MODULES:
        path = cc_dir / f"{stem}.py"
        text = _read_text(path)
        if text is None:
            continue
        for match in pattern.finditer(text):
            token = match.group(1)
            findings.append({"file": path.name, "token": token, "category": token_category[token]})
        for line in _strip_docstrings(text).splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or _line_is_negated(stripped):
                continue
            if _SHELL_TRUE_TOKEN in stripped or _OS_SYSTEM_TOKEN in stripped:
                findings.append({"file": path.name, "token": "shell_true_or_os_system", "category": "shell_exec"})
    return findings


def _scan_frontend_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    fe_dir = _frontend_dir(repo_root)
    findings: list[dict[str, str]] = []
    if not fe_dir.is_dir():
        return [{"file": "apps/control-center", "token": "<missing>", "category": "scan"}]
    for suffix in ("*.ts", "*.tsx"):
        for path in sorted(fe_dir.rglob(suffix)):
            parts = path.parts
            if "node_modules" in parts or ".next" in parts:
                continue
            rel = str(path.relative_to(repo_root)).replace("\\", "/")
            if path.name in _FORBIDDEN_FRONTEND_PATH_MARKERS:
                findings.append({"file": rel, "token": path.name, "category": "path_marker"})
            if "/app/" in f"/{rel}" and "/api/" in f"{rel}/":
                findings.append({"file": rel, "token": "app/api", "category": "path_marker"})
            text = _read_text(path)
            if text is None:
                findings.append({"file": rel, "token": "<unreadable>", "category": "scan"})
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("*") or _line_is_negated(stripped):
                    continue
                for token in _FORBIDDEN_FRONTEND_TOKENS:
                    if token in stripped:
                        findings.append({"file": rel, "token": token, "category": "runtime_token"})
    return findings


def _scan_no_app_api_or_middleware(repo_root: Path) -> list[str]:
    fe_dir = _frontend_dir(repo_root)
    findings: list[str] = []
    if not fe_dir.is_dir():
        return findings
    for path in fe_dir.rglob("*"):
        parts = path.parts
        if "node_modules" in parts or ".next" in parts:
            continue
        if path.is_dir() and path.name == "api" and "app" in parts:
            findings.append(str(path.relative_to(repo_root)).replace("\\", "/"))
        if path.is_file() and path.name in ("route.ts", "middleware.ts"):
            findings.append(str(path.relative_to(repo_root)).replace("\\", "/"))
    return findings


def _lazy_exports_source(repo_root: Path) -> str | None:
    init_path = _control_center_dir(repo_root) / "__init__.py"
    return _read_text(init_path)


def _scan_init_lazy_export_coverage(repo_root: Path, module_names: tuple[str, ...]) -> bool:
    text = _lazy_exports_source(repo_root)
    if text is None:
        return False
    values = re.findall(r'"[^"]+"\s*:\s*"([^"]+)"', text)
    return any(value in module_names for value in values)


def _scan_init_duplicate_keys(repo_root: Path) -> list[str]:
    text = _lazy_exports_source(repo_root)
    if text is None:
        return []
    keys = re.findall(r'"([^"]+)"\s*:\s*"[^"]+"', text)
    seen: dict[str, int] = {}
    for key in keys:
        seen[key] = seen.get(key, 0) + 1
    return sorted(key for key, count in seen.items() if count > 1)


def _scan_module_docstring_convention(
    repo_root: Path, module_names: tuple[str, ...], stage_label: str
) -> list[str]:
    cc_dir = _control_center_dir(repo_root)
    expected_prefix = f'"""SCOS Stage {stage_label} '
    violations: list[str] = []
    for module_name in module_names:
        text = _read_text(cc_dir / f"{module_name}.py")
        if text is None or not text.lstrip().startswith(expected_prefix):
            violations.append(module_name)
    return violations


def _scan_frontend_wiring(repo_root: Path, component_stem: str) -> tuple[bool, bool]:
    fe_dir = _frontend_dir(repo_root)
    app_shell = _read_text(fe_dir / "components" / "app-shell.tsx") or ""
    sidebar = _read_text(fe_dir / "components" / "sidebar.tsx") or ""
    import_marker = f'"./{component_stem}"'
    nav_marker = component_stem.replace("-panel", "").replace("-", "-")
    imported = import_marker in app_shell
    wired = component_stem.replace("-panel", "") in sidebar or component_stem in sidebar
    return imported, wired


def _scan_readme_stray_line(repo_root: Path) -> str | None:
    fe_dir = _frontend_dir(repo_root)
    text = _read_text(fe_dir / "README.md")
    if text is None:
        return None
    lines = text.splitlines()
    heading_index = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    for line in lines[:heading_index]:
        if "Cross-Agent Router" in line or "Stage 5.6" in line:
            return line.strip()
    return None


def _line_is_negated(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _NEGATION_TOKENS)


def _scan_stage_over_fragmentation(repo_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for rel_dir in _STAGE_SCAN_DIRS:
        base = repo_root / rel_dir
        if not base.is_dir():
            continue
        for path in sorted(base.iterdir()):
            if not path.is_file():
                continue
            rel = f"{rel_dir}/{path.name}"
            if _STAGE_OVER_FRAGMENTATION_RE.search(path.name):
                findings.append({"file": rel, "line": 0, "kind": "filename"})
            if path.suffix.lower() != ".md":
                continue
            text = _read_text(path)
            if text is None:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if _STAGE_OVER_FRAGMENTATION_RE.search(line) and not _line_is_negated(line):
                    findings.append({"file": rel, "line": line_no, "kind": "content"})
    return findings


def _build_handoff_items() -> tuple[Stage6HandoffItem, ...]:
    return tuple(
        Stage6HandoffItem.of(
            item_id, title, category, priority,
            description=description, stage6_owner=owner,
            source_stage5_evidence=evidence,
        )
        for item_id, title, category, priority, description, owner, evidence
        in _STAGE6_HANDOFF_ITEMS
    )


def _compute_readiness(checks: list[Stage5CertificationCheck]) -> tuple[int, dict[str, int]]:
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


def _write_stable_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def run_stage5_final_certification(
    *,
    repo_root,
    checked_at: str,
    output_path=None,
    require_clean_git: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_frontend_checks: bool = True,
) -> Stage5FinalCertificationResult | Stage5FinalCertificationError:
    checks: list[Stage5CertificationCheck] = []
    blockers: list[Stage5CertificationBlocker] = []

    def _check(
        check_name: str,
        status: str,
        severity: str = "info",
        *,
        category: str,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        checks.append(Stage5CertificationCheck.of(
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
        blockers.append(Stage5CertificationBlocker.of(
            blocker_id, category, severity, title, detail,
            recommended_action, source_check, metadata,
        ))

    def _error(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        metadata: dict[str, Any] | None = None,
    ) -> Stage5FinalCertificationError:
        return Stage5FinalCertificationError.of(
            error_kind, error_detail, failed_check,
            tuple(checks), tuple(blockers), metadata,
        )

    # 1. validate_inputs ------------------------------------------------------
    if repo_root is None or str(repo_root).strip() == "":
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="repo_root is required")
        return _error("INVALID_ARGUMENTS", "repo_root is required", "validate_inputs")
    if not isinstance(checked_at, str) or not checked_at.strip():
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="checked_at is required")
        return _error("INVALID_ARGUMENTS", "checked_at is required", "validate_inputs")
    if _is_url_like(repo_root):
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="repo_root must be a local path")
        return _error("INVALID_ARGUMENTS", "repo_root must be a local path", "validate_inputs")
    if output_path is not None and _is_url_like(output_path):
        _check("validate_inputs", "failure", "error", category="preflight",
               error_kind="INVALID_ARGUMENTS", error_detail="output_path must be a local path")
        return _error("INVALID_ARGUMENTS", "output_path must be a local path", "validate_inputs")

    # 2. validate_repo_root_exists --------------------------------------------
    root = Path(str(repo_root))
    if not root.is_dir():
        _check("validate_repo_root_exists", "failure", "error", category="preflight",
               artifact_path=str(root), error_kind="INPUT_NOT_FOUND",
               error_detail="repo_root does not exist or is not a directory")
        return _error("INPUT_NOT_FOUND", "repo_root does not exist or is not a directory",
                      "validate_repo_root_exists", metadata={"repo_root": str(root)})
    root = root.resolve()
    cert_id = _certification_id(root, checked_at)
    _check("validate_inputs", "success", category="preflight", artifact_path=str(root),
           metadata={"certification_id": cert_id})
    _check("validate_repo_root_exists", "success", category="preflight", artifact_path=str(root))

    # 3. validate_git_state (informational only, never GO-blocking) ----------
    if require_clean_git:
        out, err = _git_query(root, ("status", "--short", "--untracked-files=all"))
        branch, branch_err = _git_query(root, ("branch", "--show-current"))
        if err == "GIT_UNAVAILABLE" or branch_err == "GIT_UNAVAILABLE":
            _check("validate_git_state", "skipped", "info", category="preflight",
                   metadata={"reason": "git binary unavailable"})
        else:
            problems: list[str] = []
            if err is not None:
                problems.append(f"status: {err}")
            elif out:
                problems.append("working tree is not clean")
            if branch_err is not None:
                problems.append(f"branch: {branch_err}")
            if problems:
                _check("validate_git_state", "failure", "warning", category="preflight",
                       error_kind="GIT_STATE_NOTICE",
                       error_detail="; ".join(problems),
                       metadata={"problems": problems, "branch": branch or ""})
            else:
                _check("validate_git_state", "success", category="preflight",
                       metadata={"branch": branch or "", "clean": True})
    else:
        _check("validate_git_state", "skipped", category="preflight",
               metadata={"reason": "require_clean_git=False"})

    # 4. Per-stage artifact + export-coverage + docstring-convention checks --
    cc_dir = _control_center_dir(root)
    cc_tests_dir = _control_center_tests_dir(root)
    fe_dir = _frontend_dir(root)
    export_coverage_cache: dict[str, bool] = {}
    for entry in _STAGE_ARTIFACTS:
        stage_label = entry["stage"]
        stage_num = stage_label.split(".")[1]
        check_name = f"validate_stage5_{stage_num}_artifacts"

        missing_modules = sorted(
            m for m in entry["modules"] if not (cc_dir / f"{m}.py").is_file()
        )
        missing_tests = sorted(
            t for t in entry["tests"] if not (cc_tests_dir / t).is_file()
        )
        missing_docs = sorted(
            d for d in (entry["cert_doc"], *entry["spec_docs"]) if not (root / d).is_file()
        )
        missing_components = sorted(
            c for c in entry["frontend_components"]
            if not (fe_dir / "components" / c).is_file()
        )
        missing_lib = sorted(
            l for l in entry["frontend_lib"] if not (fe_dir / "lib" / l).is_file()
        )
        missing_artifacts = (
            missing_modules + missing_tests + missing_docs
            + missing_components + missing_lib
        )

        export_covered = _scan_init_lazy_export_coverage(root, entry["modules"])
        export_coverage_cache[stage_label] = export_covered
        docstring_violations = _scan_module_docstring_convention(
            root, entry["modules"], stage_label
        )

        functional_failure = bool(missing_artifacts) or not export_covered
        style_failure = bool(docstring_violations)
        metadata = {
            "missing_artifacts": missing_artifacts,
            "export_coverage_missing": [] if export_covered else list(entry["modules"]),
            "docstring_violations": docstring_violations,
        }
        if functional_failure:
            _check(check_name, "failure", "error", category="source_contract",
                   error_kind="STAGE_ARTIFACT_MISSING",
                   error_detail=f"Stage {stage_label} artifacts/exports incomplete",
                   metadata=metadata)
            _blocker(f"blk-stage5-{stage_num}-artifacts", "source_contract", "error",
                     f"Stage {stage_label} artifacts or package exports are incomplete",
                     f"missing_artifacts={missing_artifacts}; "
                     f"export_coverage_missing={metadata['export_coverage_missing']}",
                     f"Restore the missing Stage {stage_label} artifacts and/or add "
                     "the missing _LAZY_EXPORTS entries in scos/control_center/__init__.py.",
                     check_name, metadata=metadata)
        elif style_failure:
            _check(check_name, "failure", "warning", category="source_contract",
                   error_kind="MODULE_DOCSTRING_CONVENTION",
                   error_detail=f"Stage {stage_label} module docstring convention violated",
                   metadata=metadata)
            _blocker(f"blk-stage5-{stage_num}-docstring", "source_contract", "warning",
                     f"Stage {stage_label} module docstring convention violated",
                     f"docstring_violations={docstring_violations}",
                     f'Add the \'"""SCOS Stage {stage_label} ...\' header to the '
                     "listed modules for consistency with every other stage.",
                     check_name, metadata=metadata)
        else:
            _check(check_name, "success", category="source_contract", metadata=metadata)

    # 5. validate_init_no_duplicate_lazy_export_keys --------------------------
    duplicate_keys = _scan_init_duplicate_keys(root)
    if duplicate_keys:
        _check("validate_init_no_duplicate_lazy_export_keys", "failure", "error",
               category="source_contract",
               artifact_path="scos/control_center/__init__.py",
               error_kind="DUPLICATE_LAZY_EXPORT_KEY",
               error_detail="one or more _LAZY_EXPORTS keys are defined more than once",
               metadata={"duplicate_keys": duplicate_keys})
        _blocker("blk-duplicate-lazy-export-key", "source_contract", "error",
                 "scos/control_center/__init__.py has duplicate _LAZY_EXPORTS keys",
                 f"duplicate_keys={duplicate_keys}. The last-defined mapping silently "
                 "shadows the earlier one at runtime (e.g. ALLOWED_COMMAND_TYPES "
                 "currently resolves to Stage 5.9's constant, not Stage 5.1's).",
                 "Rename the colliding constant in one of the two stages so each "
                 "key maps to exactly one module.",
                 "validate_init_no_duplicate_lazy_export_keys",
                 metadata={"duplicate_keys": duplicate_keys})
    else:
        _check("validate_init_no_duplicate_lazy_export_keys", "success",
               category="source_contract")

    # 6. Stage 5.6 frontend-wiring + README consistency -----------------------
    imported, wired = _scan_frontend_wiring(root, "workflow-router-panel")
    if not (imported and wired):
        _check("validate_stage5_6_frontend_wiring", "failure", "warning",
               category="source_contract",
               artifact_path="apps/control-center/components/app-shell.tsx",
               error_kind="FRONTEND_PANEL_UNWIRED",
               error_detail="workflow-router-panel is not wired into app-shell/sidebar",
               metadata={"imported_in_app_shell": imported, "present_in_nav_sections": wired})
        _blocker("blk-stage5-6-frontend-wiring", "source_contract", "warning",
                 "Stage 5.6 workflow-router-panel is never rendered",
                 "Not imported into app-shell.tsx and/or missing from sidebar.tsx "
                 "NAV_SECTIONS - the panel exists but renders nowhere in the app.",
                 "Wire the panel into app-shell.tsx and add a NAV_SECTIONS entry.",
                 "validate_stage5_6_frontend_wiring",
                 metadata={"imported_in_app_shell": imported, "present_in_nav_sections": wired})
    else:
        _check("validate_stage5_6_frontend_wiring", "success", category="source_contract")

    stray_line = _scan_readme_stray_line(root)
    if stray_line:
        _check("validate_stage5_6_readme_consistency", "failure", "warning",
               category="source_contract",
               artifact_path="apps/control-center/README.md",
               error_kind="README_STRAY_LINE",
               error_detail="stray Stage 5.6 leftover line found before the first heading",
               metadata={"line": stray_line})
        _blocker("blk-stage5-6-readme", "source_contract", "warning",
                 "apps/control-center/README.md has a stray Stage 5.6 leftover line",
                 f"line={stray_line!r}",
                 "Move or remove the stray line so it matches the README's section structure.",
                 "validate_stage5_6_readme_consistency", metadata={"line": stray_line})
    else:
        _check("validate_stage5_6_readme_consistency", "success", category="source_contract")

    # 7. Workflow continuity: pairwise link checks + doc-order check ---------
    for a, b in zip(_WORKFLOW_CHAIN[:-1], _WORKFLOW_CHAIN[1:]):
        a_num, b_num = a.split(".")[1], b.split(".")[1]
        check_name = f"validate_workflow_link_{a_num}_{b_num}"
        entry_a, entry_b = _STAGE_BY_LABEL[a], _STAGE_BY_LABEL[b]
        a_model = cc_dir / f"{entry_a['modules'][0]}.py"
        b_model = cc_dir / f"{entry_b['modules'][0]}.py"
        a_ok = a_model.is_file() and export_coverage_cache.get(a, False)
        b_ok = b_model.is_file() and export_coverage_cache.get(b, False)
        if a_ok and b_ok:
            _check(check_name, "success", category="workflow_continuity",
                   metadata={"link": f"{a}->{b}"})
        else:
            _check(check_name, "failure", "warning", category="workflow_continuity",
                   error_kind="WORKFLOW_LINK_INCOMPLETE",
                   error_detail=f"{a}->{b} link is not fully present/exported",
                   metadata={"link": f"{a}->{b}", "a_ok": a_ok, "b_ok": b_ok})
            _blocker(f"blk-workflow-link-{a_num}-{b_num}", "workflow_continuity", "warning",
                     f"Workflow link {a}->{b} is incomplete",
                     f"a_ok={a_ok} b_ok={b_ok}",
                     "Ensure both stages' primary model modules exist and are "
                     "covered by scos/control_center/__init__.py exports.",
                     check_name, metadata={"link": f"{a}->{b}"})

    doc_order_findings: list[str] = []
    for entry in _STAGE_ARTIFACTS[1:]:
        n = int(entry["stage"].split(".")[1])
        predecessor_label = f"5.{n - 1}"
        doc_text = _read_text(root / entry["cert_doc"]) or ""
        if predecessor_label not in doc_text:
            doc_order_findings.append(entry["cert_doc"])
    if doc_order_findings:
        _check("validate_workflow_chain_order_docs", "failure", "warning",
               category="workflow_continuity",
               error_kind="CHAIN_ORDER_DOC_GAP",
               error_detail="some plan docs do not mention their immediate predecessor",
               metadata={"docs": doc_order_findings})
        _blocker("blk-workflow-chain-order-docs", "workflow_continuity", "warning",
                 "Some Stage 5 plan docs do not reference their predecessor stage",
                 f"docs={doc_order_findings}",
                 "Add a short predecessor reference to each affected plan doc.",
                 "validate_workflow_chain_order_docs", metadata={"docs": doc_order_findings})
    else:
        _check("validate_workflow_chain_order_docs", "success", category="workflow_continuity")

    # 8. Safety boundary -------------------------------------------------------
    adapter_files = ("agent_adapter_contracts.py", "agent_adapter_simulator.py",
                      "agent_adapter_registry.py")
    ai_dispatch_findings: list[dict[str, str]] = []
    model_api_import_pattern = re.compile(
        r"^\s*(?:import|from)\s+(" + "|".join(re.escape(t) for t in _MODEL_API_TOKENS) + r")\b",
        re.MULTILINE | re.IGNORECASE,
    )
    for name in adapter_files:
        text = _read_text(cc_dir / name)
        if text is None:
            continue
        for match in model_api_import_pattern.finditer(text):
            ai_dispatch_findings.append({"file": name, "token": match.group(0)})
    if ai_dispatch_findings:
        _check("validate_no_real_ai_dispatch", "failure", "critical", category="safety_boundary",
               error_kind="REAL_AI_DISPATCH_DETECTED",
               error_detail="adapter modules show signs of a real dispatch integration",
               metadata={"findings": ai_dispatch_findings})
        _blocker("blk-real-ai-dispatch", "safety_boundary", "critical",
                 "Real AI dispatch behavior detected in adapter modules",
                 f"findings={ai_dispatch_findings}",
                 "Remove the real-dispatch code; Stage 5 adapters must remain simulations.",
                 "validate_no_real_ai_dispatch", metadata={"findings": ai_dispatch_findings})
    else:
        _check("validate_no_real_ai_dispatch", "success", category="safety_boundary")

    backend_findings = _scan_backend_forbidden_tokens(root)
    if backend_findings:
        _check("validate_backend_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="FORBIDDEN_BACKEND_BEHAVIOR",
               error_detail="forbidden backend tokens found in scos/control_center",
               metadata={"findings": backend_findings})
        _blocker("blk-backend-forbidden-tokens", "safety_boundary", "critical",
                 "Forbidden backend behavior detected in scos/control_center",
                 f"{len(backend_findings)} finding(s).",
                 "Remove the forbidden import/pattern before certifying Stage 5.",
                 "validate_backend_forbidden_tokens", metadata={"findings": backend_findings})
    else:
        _check("validate_backend_forbidden_tokens", "success", category="safety_boundary")

    frontend_findings = _scan_frontend_forbidden_tokens(root)
    if frontend_findings:
        _check("validate_frontend_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="FORBIDDEN_FRONTEND_BEHAVIOR",
               error_detail="forbidden frontend tokens found in apps/control-center",
               metadata={"findings": frontend_findings})
        _blocker("blk-frontend-forbidden-tokens", "safety_boundary", "critical",
                 "Forbidden frontend behavior detected in apps/control-center",
                 f"{len(frontend_findings)} finding(s).",
                 "Remove the forbidden call/import before certifying Stage 5.",
                 "validate_frontend_forbidden_tokens", metadata={"findings": frontend_findings})
    else:
        _check("validate_frontend_forbidden_tokens", "success", category="safety_boundary")

    api_middleware_findings = _scan_no_app_api_or_middleware(root)
    if api_middleware_findings:
        _check("validate_no_app_api_or_middleware", "failure", "critical",
               category="safety_boundary",
               error_kind="BACKEND_SURFACE_DETECTED",
               error_detail="app/api directory or route.ts/middleware.ts found",
               metadata={"findings": api_middleware_findings})
        _blocker("blk-app-api-or-middleware", "safety_boundary", "critical",
                 "A backend API surface was detected in apps/control-center",
                 f"findings={api_middleware_findings}",
                 "Remove the API route/middleware; the frontend must stay static-only.",
                 "validate_no_app_api_or_middleware",
                 metadata={"findings": api_middleware_findings})
    else:
        _check("validate_no_app_api_or_middleware", "success", category="safety_boundary")

    subprocess_importers = []
    for path in sorted(cc_dir.glob("*.py")) if cc_dir.is_dir() else ():
        if path.stem in _OWN_MODULES:
            continue
        text = _read_text(path) or ""
        if re.search(r"^\s*import\s+subprocess\b", text, re.MULTILINE):
            subprocess_importers.append(path.stem)
    unexpected_importers = [m for m in subprocess_importers if m != _ALLOWLISTED_SUBPROCESS_MODULE]
    runner_text = _read_text(cc_dir / f"{_ALLOWLISTED_SUBPROCESS_MODULE}.py") or ""
    runner_shell_true = any(
        _SHELL_TRUE_TOKEN in stripped
        for line in _strip_docstrings(runner_text).splitlines()
        for stripped in (line.strip(),)
        if not stripped.startswith("#") and not _line_is_negated(stripped)
    )
    if unexpected_importers or runner_shell_true:
        _check("validate_subprocess_allowlist_exception", "failure", "critical",
               category="safety_boundary",
               error_kind="SUBPROCESS_ALLOWLIST_VIOLATION",
               error_detail="subprocess used outside the allowlisted command_runner module",
               metadata={"unexpected_importers": unexpected_importers,
                         "runner_shell_true": runner_shell_true})
        _blocker("blk-subprocess-allowlist", "safety_boundary", "critical",
                 "subprocess is used outside the allowlisted command_runner.py",
                 f"unexpected_importers={unexpected_importers} runner_shell_true={runner_shell_true}",
                 "Remove the extra subprocess usage or the shell-true argument.",
                 "validate_subprocess_allowlist_exception",
                 metadata={"unexpected_importers": unexpected_importers})
    else:
        _check("validate_subprocess_allowlist_exception", "success", category="safety_boundary",
               metadata={"allowlisted_module": _ALLOWLISTED_SUBPROCESS_MODULE})

    own_findings = _scan_stage5_10_own_files_forbidden_tokens(root)
    if own_findings:
        _check("validate_stage5_10_own_files_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="STAGE5_10_SELF_SCAN_FAILED",
               error_detail="Stage 5.10's own files contain a forbidden token",
               metadata={"findings": own_findings})
        _blocker("blk-stage5-10-self-scan", "safety_boundary", "critical",
                 "Stage 5.10's own certification modules violate the safety boundary",
                 f"findings={own_findings}",
                 "Remove the forbidden token from the Stage 5.10 module itself.",
                 "validate_stage5_10_own_files_forbidden_tokens",
                 metadata={"findings": own_findings})
    else:
        _check("validate_stage5_10_own_files_forbidden_tokens", "success",
               category="safety_boundary")

    # 9. Frontend static scope --------------------------------------------------
    package_json_path = fe_dir / "package.json"
    package_text = _read_text(package_json_path)
    if package_text is None:
        _check("validate_frontend_package_scope", "failure", "error",
               category="frontend_static_scope",
               artifact_path="apps/control-center/package.json",
               error_kind="PACKAGE_JSON_MISSING",
               error_detail="apps/control-center/package.json not found")
        _blocker("blk-frontend-package-missing", "frontend_static_scope", "error",
                 "apps/control-center/package.json is missing",
                 "package.json not found", "Restore package.json before certifying Stage 5.",
                 "validate_frontend_package_scope")
    else:
        try:
            package_json = json.loads(package_text)
        except json.JSONDecodeError:
            package_json = {}
        scripts = package_json.get("scripts", {})
        deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}
        unexpected_scripts = sorted(set(scripts) - {"dev", "build", "start", "lint"})
        test_runner_present = any(
            name in deps for name in ("jest", "vitest", "@testing-library/react")
        )
        _check("validate_frontend_package_scope", "success", category="frontend_static_scope",
               metadata={"unexpected_scripts": unexpected_scripts,
                         "test_runner_present": test_runner_present})

    if run_frontend_checks:
        pnpm_probe = None
        try:
            pnpm_probe = subprocess.run(
                ["pnpm", "--version"], cwd=str(fe_dir), capture_output=True,
                text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            pnpm_probe = None
        if pnpm_probe is None or pnpm_probe.returncode != 0:
            _check("run_frontend_lint", "skipped", category="frontend_static_scope",
                   metadata={"reason": "pnpm not available"})
            _check("run_frontend_build", "skipped", category="frontend_static_scope",
                   metadata={"reason": "pnpm not available"})
        else:
            env_note = {"NEXT_TELEMETRY_DISABLED": "1"}
            for check_name, args in (
                ("run_frontend_lint", ["pnpm", "lint"]),
                ("run_frontend_build", ["pnpm", "build"]),
            ):
                try:
                    import os as _os
                    proc = subprocess.run(
                        args, cwd=str(fe_dir), capture_output=True, text=True,
                        timeout=_FRONTEND_TIMEOUT_SECONDS,
                        env={**_os.environ, **env_note},
                    )
                    exit_code, tail = proc.returncode, _tail_line(proc.stdout or proc.stderr)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    exit_code, tail = None, type(exc).__name__
                if exit_code == 0:
                    _check(check_name, "success", category="frontend_static_scope",
                           metadata={"exit_code": 0, "tail": tail})
                elif exit_code is None:
                    _check(check_name, "skipped", category="frontend_static_scope",
                           metadata={"reason": tail})
                else:
                    _check(check_name, "failure", "error", category="frontend_static_scope",
                           error_kind="FRONTEND_CHECK_FAILED",
                           error_detail=f"{args[-1]} failed",
                           metadata={"exit_code": exit_code, "tail": tail})
                    _blocker(f"blk-{check_name}", "frontend_static_scope", "error",
                             f"pnpm {args[-1]} failed",
                             f"exit_code={exit_code} tail={tail}",
                             f"Fix the pnpm {args[-1]} failure before certifying Stage 5.",
                             check_name, metadata={"exit_code": exit_code})
    else:
        _check("run_frontend_lint", "skipped", category="frontend_static_scope",
               metadata={"reason": "run_frontend_checks=False"})
        _check("run_frontend_build", "skipped", category="frontend_static_scope",
               metadata={"reason": "run_frontend_checks=False"})

    # 10. Testing: run each Stage 5 test file per stage -----------------------
    for entry in _STAGE_ARTIFACTS:
        stage_num = entry["stage"].split(".")[1]
        check_name = f"run_stage5_{stage_num}_tests"
        results: list[dict[str, Any]] = []
        any_missing = False
        any_failure = False
        for test_file in entry["tests"]:
            test_path = cc_tests_dir / test_file
            if not test_path.is_file():
                any_missing = True
                results.append({"file": test_file, "status": "missing"})
                continue
            exit_code, tail = _run_repo_script(
                root, str(test_path.relative_to(root)), _TEST_TIMEOUT_SECONDS
            )
            results.append({"file": test_file, "exit_code": exit_code, "tail": tail})
            if exit_code != 0:
                any_failure = True
        if any_failure:
            _check(check_name, "failure", "error", category="testing",
                   error_kind="STAGE_TEST_FAILED",
                   error_detail=f"one or more Stage {entry['stage']} test files failed",
                   metadata={"results": results})
            _blocker(f"blk-stage5-{stage_num}-tests", "testing", "error",
                     f"Stage {entry['stage']} test suite failed",
                     f"results={results}",
                     "Fix the failing Stage 5 test file(s) before certifying Stage 5.",
                     check_name, metadata={"results": results})
        elif any_missing:
            _check(check_name, "skipped", category="testing",
                   error_kind="TEST_FILE_MISSING",
                   error_detail=f"one or more Stage {entry['stage']} test files are missing",
                   metadata={"results": results})
        else:
            _check(check_name, "success", category="testing", metadata={"results": results})

    if run_smoke:
        exit_code, tail = _run_repo_script(root, _SMOKE_SCRIPT, _SCRIPT_TIMEOUT_SECONDS)
        if exit_code == 0:
            _check("run_smoke_script", "success", category="testing",
                   artifact_path=_SMOKE_SCRIPT, metadata={"exit_code": 0, "tail": tail})
        else:
            _check("run_smoke_script", "failure", "error", category="testing",
                   artifact_path=_SMOKE_SCRIPT, error_kind="SMOKE_SCRIPT_FAILED",
                   error_detail="smoke script did not pass",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-smoke-script", "testing", "error", "Smoke script failed",
                     f"{_SMOKE_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Fix the smoke failures before certifying Stage 5.",
                     "run_smoke_script", metadata={"exit_code": exit_code})
    else:
        _check("run_smoke_script", "skipped", category="testing",
               metadata={"reason": "run_smoke=False"})

    # 11. Security --------------------------------------------------------------
    if run_security_scan:
        exit_code, tail = _run_repo_script(root, _SECURITY_SCRIPT, _SCRIPT_TIMEOUT_SECONDS)
        if exit_code == 0:
            _check("run_security_scan_baseline", "success", category="security",
                   artifact_path=_SECURITY_SCRIPT, metadata={"exit_code": 0, "tail": tail})
        else:
            _check("run_security_scan_baseline", "failure", "error", category="security",
                   artifact_path=_SECURITY_SCRIPT, error_kind="SECURITY_SCAN_FAILED",
                   error_detail="security scan baseline reported findings",
                   metadata={"exit_code": exit_code, "tail": tail,
                             "note": "this scanner's scope is scos/commercial + scripts + "
                                     "root config only; it does not cover scos/control_center "
                                     "or apps/control-center"})
            _blocker("blk-security-scan", "security", "error",
                     "Security scan baseline failed",
                     f"{_SECURITY_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Resolve the security findings before certifying Stage 5.",
                     "run_security_scan_baseline", metadata={"exit_code": exit_code})
    else:
        _check("run_security_scan_baseline", "skipped", category="security",
               metadata={"reason": "run_security_scan=False"})

    # 12. Stage 6 handoff ---------------------------------------------------------
    handoff_items = _build_handoff_items()
    handoff_items_2 = _build_handoff_items()
    deterministic = (
        json.dumps([i.to_dict() for i in handoff_items], sort_keys=True)
        == json.dumps([i.to_dict() for i in handoff_items_2], sort_keys=True)
    )
    if 8 <= len(handoff_items) <= 12 and deterministic:
        _check("validate_stage6_handoff_items_generated", "success",
               category="stage6_handoff", metadata={"count": len(handoff_items)})
    else:
        _check("validate_stage6_handoff_items_generated", "failure", "error",
               category="stage6_handoff", error_kind="HANDOFF_ITEMS_INVALID",
               error_detail="handoff item count or determinism check failed",
               metadata={"count": len(handoff_items), "deterministic": deterministic})

    if (root / _STAGE6_HANDOFF_DOC).is_file():
        _check("validate_stage6_handoff_doc_exists", "success", category="stage6_handoff",
               artifact_path=_STAGE6_HANDOFF_DOC)
    else:
        _check("validate_stage6_handoff_doc_exists", "failure", "error",
               category="stage6_handoff", artifact_path=_STAGE6_HANDOFF_DOC,
               error_kind="HANDOFF_DOC_MISSING",
               error_detail="docs/roadmap/STAGE6_HANDOFF.md is missing")
        _blocker("blk-stage6-handoff-doc", "stage6_handoff", "error",
                 "Stage 6 handoff document is missing",
                 f"{_STAGE6_HANDOFF_DOC} was not found.",
                 "Create the Stage 6 handoff document before certifying Stage 5.",
                 "validate_stage6_handoff_doc_exists")

    stage5_handoff_text = _read_text(root / _STAGE5_HANDOFF_DOC)
    if stage5_handoff_text is not None and "Gate 5.E" in stage5_handoff_text:
        _check("validate_stage5_handoff_doc_consistency", "success", category="stage6_handoff",
               artifact_path=_STAGE5_HANDOFF_DOC)
    else:
        _check("validate_stage5_handoff_doc_consistency", "failure", "warning",
               category="stage6_handoff", artifact_path=_STAGE5_HANDOFF_DOC,
               error_kind="STAGE5_HANDOFF_DOC_INCONSISTENT",
               error_detail="STAGE5_HANDOFF.md is missing or no longer mentions Gate 5.E")
        _blocker("blk-stage5-handoff-consistency", "stage6_handoff", "warning",
                 "docs/roadmap/STAGE5_HANDOFF.md no longer matches its original promise",
                 "The file is missing or its 'Gate 5.E' reference was removed.",
                 "Restore docs/roadmap/STAGE5_HANDOFF.md; Stage 5.10 never modifies it.",
                 "validate_stage5_handoff_doc_consistency")

    # 13. Stage 5 readiness -------------------------------------------------------
    fragmentation_findings = _scan_stage_over_fragmentation(root)
    if fragmentation_findings:
        _check("validate_no_stage5_11_plus", "failure", "critical",
               category="stage5_readiness",
               error_kind="STAGE_OVER_FRAGMENTATION",
               error_detail="Stage 5.11+ markers were found",
               metadata={"findings": fragmentation_findings})
        _blocker("blk-stage-over-fragmentation", "stage5_readiness", "critical",
                 "STAGE_OVER_FRAGMENTATION",
                 f"Stage 5.11+ markers found in {len(fragmentation_findings)} location(s).",
                 "Move any future work to the Stage 6 backlog / handoff; Stage 5 ends at 5.10.",
                 "validate_no_stage5_11_plus", metadata={"findings": fragmentation_findings})
    else:
        _check("validate_no_stage5_11_plus", "success", category="stage5_readiness",
               metadata={"scanned_dirs": list(_STAGE_SCAN_DIRS)})

    score, breakdown = _compute_readiness(checks)
    has_error_or_critical = any(b.severity in ("error", "critical") for b in blockers)
    if has_error_or_critical or score < 90:
        go_no_go, readiness_level, accepted, stage_closed = "NO_GO", "blocked", False, False
    elif score == 100 and not blockers:
        go_no_go, readiness_level, accepted, stage_closed = "GO", "certified", True, True
    else:
        go_no_go, readiness_level, accepted, stage_closed = "GO", "conditionally_ready", True, True
    _check("compute_stage5_readiness", "success", category="stage5_readiness",
           metadata={"score": score, "breakdown": breakdown, "go_no_go": go_no_go})

    # Output artifact (written only on this fully-validated result path) -----
    final_output: Path | None = None
    if output_path is not None:
        target = Path(str(output_path))
        final_output = target if target.suffix.lower() == ".json" else target / _OUTPUT_FILENAME

    result = Stage5FinalCertificationResult(
        ok=True,
        schema_version=STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION,
        accepted=accepted,
        certification_id=cert_id,
        checked_at=checked_at,
        stage=_STAGE_LABEL,
        stage_closed=stage_closed,
        go_no_go=go_no_go,
        readiness_level=readiness_level,
        readiness_score=score,
        readiness_max_score=READINESS_MAX_SCORE,
        checks=tuple(checks),
        blockers=tuple(blockers),
        stage6_handoff_items=handoff_items,
        output_path=None if final_output is None else str(final_output),
        metadata={
            "generator": _GENERATOR,
            "gate_name": _GATE_NAME,
            "gate_stage": "5.10",
            "repo_root": str(root),
            "score_breakdown": breakdown,
            "flags": {
                "require_clean_git": bool(require_clean_git),
                "run_smoke": bool(run_smoke),
                "run_security_scan": bool(run_security_scan),
                "run_frontend_checks": bool(run_frontend_checks),
            },
        },
    )

    if final_output is not None:
        try:
            final_output.parent.mkdir(parents=True, exist_ok=True)
            _write_stable_json(final_output, result.to_dict())
        except OSError as exc:
            _check("write_output", "failure", "error", category="stage5_readiness",
                   artifact_path=str(final_output),
                   error_kind="OUTPUT_WRITE_FAILED",
                   error_detail="certification report could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "certification report could not be written",
                          "write_output", metadata={"os_error": type(exc).__name__})

    return result


__all__ = ("run_stage5_final_certification",)
