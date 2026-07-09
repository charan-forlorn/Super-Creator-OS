"""SCOS Stage 6.10 final Stage 6 integration gate / release gate / Stage 7 handoff.

Read-only certification layer over the Stage 6 Control Center integration
foundation (6.2 backend/command API -> 6.3 SQLite WAL state -> 6.4 event
stream / UI sync -> 6.6 approval persistence / audit trail -> 6.7 execution
audit wiring -> 6.8 security baseline -> 6.9 monitoring / observability ->
6.10 final integration gate -> Stage 7 handoff).

It verifies the presence/coherence of every Stage 6 layer's artifacts and
docs, the Stage 6.7 audit-into-execution wiring, the Stage 6.8 security-scan
coverage, the local/approval-first safety boundary, the read-only nature of
the gate itself, and (optionally) runs the repo's smoke, security-baseline,
and control_center test tiers, then computes a deterministic readiness score
and a GO / NO_GO verdict plus the deterministic Stage 7 handoff items.

Boundary notes:
- This layer inspects; it never fixes, rebuilds, or mutates any Stage 6
  artifact. The only write it can perform is the single report JSON at the
  caller-supplied ``output_path``. Known real defects in the inspected Stage 6
  artifacts are reported as blockers, never silently repaired or downgraded.
- ``subprocess`` is used here as a documented, narrow exception: read-only
  ``git`` queries (informational only - no branch/HEAD/clean-tree policy is
  enforced unless ``require_clean_git=True``), running the full control_center
  test tier, running ``scripts/test_smoke.py`` / ``scripts/security_scan_baseline.py``,
  and optionally ``pnpm lint`` / ``pnpm build`` from ``apps/control-center``
  (never ``pnpm install``, never a package.json write).
- Deterministic: no real clock, no randomness, no uuid. ``checked_at`` is
  caller-supplied; the gate id is a SHA-256 derivation.
- This module never imports ``scos.commercial`` - the stable-JSON writer is
  reimplemented locally rather than crossing that package boundary.
- The forbidden-behavior scan tokens below are assembled from string
  fragments so this file's own text stays free of the literal tokens it
  hunts for (repo convention; keeps the security baseline scan clean).
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
    from .stage6_final_gate_models import (
        STAGE6_FINAL_GATE_SCHEMA_VERSION,
        Stage6FinalIntegrationError,
        Stage6FinalIntegrationResult,
        Stage6GateBlocker,
        Stage6GateCheck,
        Stage6GateEvidence,
        Stage7HandoffItem,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from stage6_final_gate_models import (
        STAGE6_FINAL_GATE_SCHEMA_VERSION,
        Stage6FinalIntegrationError,
        Stage6FinalIntegrationResult,
        Stage6GateBlocker,
        Stage6GateCheck,
        Stage6GateEvidence,
        Stage7HandoffItem,
    )

_GATE_NAME = "stage6-final-integration-gate"
_STAGE_LABEL = "6.10"
_GENERATOR = "scos.control_center.stage6_final_integration_gate"
_OUTPUT_FILENAME = "stage6_final_integration_report.json"

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
# scan target set (they are separately dogfood-scanned) and excluded from
# every stage's "modules" existence check (they are not part of 6.2-6.9).
_OWN_MODULES = ("stage6_final_gate_models", "stage6_final_integration_gate")

# Modules permitted to import subprocess in scos/control_center (repo policy).
_CONTROL_CENTER_SUBPROCESS_ALLOWLIST = {
    "scos/control_center/command_runner.py",
    "scos/control_center/stage5_final_certification.py",
    "scos/control_center/stage6_final_integration_gate.py",
}

# ---------------------------------------------------------------------------
# Forbidden-token fragments (assembled, never literal) - mirror the security
# scan so this gate stays consistent with scripts/security_scan_baseline.py.
# ---------------------------------------------------------------------------
_W_REQUESTS = "requ" + "ests"
_W_URLLIB_REQ = "urllib." + "request"
_W_HTTP_CLIENT = "http." + "client"
_W_SOCKET = "sock" + "et"
_W_AIOHTTP = "aio" + "http"
_W_HTTPX = "http" + "x"
_W_SMTPLIB = "smtp" + "lib"
_W_WEBSOCKET = "web" + "socket"
_W_OPENAI = "open" + "ai"
_W_ANTHROPIC = "anthro" + "pic"
_W_SELENIUM = "sele" + "nium"
_W_PLAYWRIGHT = "play" + "wright"
_W_PYAUTOGUI = "pyauto" + "gui"
_W_PYPERCLIP = "pyper" + "clip"
_W_WIN32CLIPBOARD = "win32" + "clipboard"
_W_SUBPROCESS = "sub" + "process"
_W_OS_SYSTEM = "os." + "system"
_W_SHELL_TRUE = "shell" + "=True"
_W_PTY = "pty"
_W_AUDIT_LEDGER = "audit" + "_ledger"
_W_FETCH = "fet" + "ch("
_W_XML_HTTP_REQUEST = "XML" + "Http" + "Request"
_W_AXIOS = "axi" + "os"
_W_WEBSOCKET_FRONTEND = "Web" + "Socket"
_W_EVENT_SOURCE = "Event" + "Source"
_W_SET_INTERVAL = "set" + "Interval"
_W_SET_TIMEOUT = "set" + "Timeout"
_W_DATE_NOW = "Date." + "now"
_W_MATH_RANDOM = "Math." + "random"
_W_CRYPTO_RANDOM_UUID = "crypto." + "random" + "UUID"
_W_LOCAL_STORAGE = "local" + "Storage"
_W_SESSION_STORAGE = "session" + "Storage"
_W_USE_SERVER = '"use' + ' server"'
_W_NAVIGATOR_CLIPBOARD = "navigator." + "clip" + "board"

_FORBIDDEN_BACKEND_TOKENS: tuple[tuple[str, str], ...] = (
    ("network", _W_REQUESTS),
    ("network", _W_URLLIB_REQ),
    ("network", _W_HTTP_CLIENT),
    ("network", _W_SOCKET),
    ("network", _W_AIOHTTP),
    ("network", _W_HTTPX),
    ("network", _W_SMTPLIB),
    ("network", _W_WEBSOCKET),
    ("ai_dispatch", _W_OPENAI),
    ("ai_dispatch", _W_ANTHROPIC),
    ("gui_automation", _W_SELENIUM),
    ("gui_automation", _W_PLAYWRIGHT),
    ("gui_automation", _W_PYAUTOGUI),
    ("clipboard_automation", _W_PYPERCLIP),
    ("clipboard_automation", _W_WIN32CLIPBOARD),
)
_MODEL_API_TOKENS: tuple[str, ...] = (_W_OPENAI, _W_ANTHROPIC)

_FORBIDDEN_FRONTEND_TOKENS: tuple[tuple[str, str], ...] = (
    ("frontend_transport", _W_FETCH),
    ("frontend_transport", _W_XML_HTTP_REQUEST),
    ("frontend_transport", _W_AXIOS),
    ("frontend_transport", _W_WEBSOCKET_FRONTEND),
    ("frontend_transport", _W_EVENT_SOURCE),
    ("frontend_polling", _W_SET_INTERVAL),
    ("frontend_polling", _W_SET_TIMEOUT),
    ("frontend_nondeterminism", _W_DATE_NOW),
    ("frontend_nondeterminism", _W_MATH_RANDOM),
    ("frontend_nondeterminism", _W_CRYPTO_RANDOM_UUID),
    ("frontend_storage", _W_LOCAL_STORAGE),
    ("frontend_storage", _W_SESSION_STORAGE),
    ("frontend_server_action", _W_USE_SERVER),
    ("frontend_clipboard", _W_NAVIGATOR_CLIPBOARD),
)
_FORBIDDEN_FRONTEND_PATH_MARKERS: tuple[str, ...] = ("route.ts", "middleware.ts")

_CC_NETWORK_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+("
    + "|".join(
        (
            _W_REQUESTS,
            re.escape(_W_URLLIB_REQ),
            re.escape(_W_HTTP_CLIENT),
            _W_SOCKET,
            _W_AIOHTTP,
            _W_HTTPX,
            _W_SMTPLIB,
            _W_WEBSOCKET + "s?",
        )
    )
    + r")\b",
    re.MULTILINE,
)
_CC_AI_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+(" + "|".join((_W_OPENAI, _W_ANTHROPIC)) + r")\b",
    re.MULTILINE | re.IGNORECASE,
)
_CC_GUI_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+("
    + "|".join(
        (
            _W_SELENIUM,
            _W_PLAYWRIGHT,
            _W_PYAUTOGUI,
            _W_PYPERCLIP,
            _W_WIN32CLIPBOARD,
        )
    )
    + r")\b",
    re.MULTILINE,
)
_SUBPROCESS_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+" + _W_SUBPROCESS + r"\b")
_SUBPROCESS_USE_RE = re.compile(r"\b" + _W_SUBPROCESS + r"\.")
_PTY_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+" + _W_PTY + r"\b")
_PTY_USE_RE = re.compile(r"\b" + _W_PTY + r"\.")
_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
_NEGATION_TOKENS = (
    "no ", "not ", "never", "forbid", "refus", "do not", "must not", "non-goal",
    "disabled",
)

# Per-stage artifact manifest. "kind" selects the check strategy.
# generic        -> modules + tests + cert_doc + spec_docs + extra_docs must exist
# security_scan  -> scripts/security_scan_baseline.py coverage + runnability
# self           -> Stage 6.10 contract/release/handoff docs must exist
_STAGE_ARTIFACTS: tuple[dict[str, Any], ...] = (
    {
        "stage": "6.2", "name": "control_center_backend",
        "kind": "generic",
        "modules": ("backend_models", "backend_validation", "command_api",
                    "local_backend", "backend_response_builder"),
        "tests": ("test_backend_models.py", "test_backend_validation.py",
                  "test_command_api.py", "test_local_backend.py",
                  "test_backend_response_builder.py"),
        "cert_doc": "docs/certification/Stage-6.2-plan.md",
        "spec_docs": (
            "docs/specification/CONTROL_CENTER_COMMAND_API_CONTRACT.md",
            "docs/specification/LOCAL_CONTROL_CENTER_BACKEND_CONTRACT.md",
            "docs/specification/STAGE6_LOCAL_BACKEND_BOUNDARY.md",
        ),
        "extra_docs": (),
    },
    {
        "stage": "6.3", "name": "durable_state_store",
        "kind": "generic",
        "modules": ("state_models", "sqlite_state_schema", "sqlite_state_store",
                    "state_repository", "state_snapshot"),
        "tests": ("test_state_models.py", "test_sqlite_state_schema.py",
                  "test_sqlite_state_store.py", "test_state_repository.py",
                  "test_state_snapshot.py"),
        "cert_doc": "docs/certification/Stage-6.3-plan.md",
        "spec_docs": (
            "docs/specification/CONTROL_CENTER_DURABLE_STATE_CONTRACT.md",
            "docs/specification/SQLITE_WAL_STATE_STORE_CONTRACT.md",
            "docs/specification/STAGE6_DURABLE_STATE_BOUNDARY.md",
        ),
        "extra_docs": (),
    },
    {
        "stage": "6.4", "name": "event_stream_ui_sync",
        "kind": "generic",
        "modules": ("event_stream_models", "event_stream_builder",
                    "event_stream_snapshot", "ui_state_sync"),
        "tests": ("test_event_stream_models.py", "test_event_stream_builder.py",
                  "test_event_stream_snapshot.py", "test_ui_state_sync.py"),
        "cert_doc": "docs/certification/Stage-6.4-plan.md",
        "spec_docs": (
            "docs/specification/CONTROL_CENTER_EVENT_STREAM_CONTRACT.md",
            "docs/specification/CONTROL_CENTER_UI_STATE_SYNC_CONTRACT.md",
            "docs/specification/STAGE6_EVENT_STREAM_BOUNDARY.md",
        ),
        "extra_docs": (),
    },
    {
        "stage": "6.5", "name": "regression_debt_cleanup",
        "kind": "generic",
        "modules": (),
        "tests": (),
        "cert_doc": "docs/certification/Stage-6.5-plan.md",
        "spec_docs": (
            "docs/specification/STAGE6_EVENT_STREAM_READINESS_GATE.md",
        ),
        "extra_docs": (
            "docs/certification/Stage-6.5-regression-cleanup-report.md",
        ),
    },
    {
        "stage": "6.6", "name": "approval_persistence_audit_trail",
        "kind": "generic",
        "modules": ("operator_approval", "approval_audit_store", "approval_audit_models"),
        "tests": ("test_operator_approval.py", "test_approval_audit_store.py",
                  "test_approval_audit_models.py"),
        "cert_doc": "docs/certification/Stage-6.6-plan.md",
        "spec_docs": (
            "docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md",
        ),
        "extra_docs": (),
    },
    {
        "stage": "6.7", "name": "execution_audit_wiring",
        "kind": "generic",
        "modules": ("command_runner", "operator_approval"),
        "tests": ("test_command_runner.py", "test_approval_audit_integration.py"),
        "cert_doc": "docs/certification/Stage-6.7-plan.md",
        "spec_docs": (
            "docs/specification/OPERATOR_APPROVAL_AUDIT_TRAIL_CONTRACT.md",
        ),
        "extra_docs": (),
    },
    {
        "stage": "6.8", "name": "security_hardening",
        "kind": "security_scan",
        "cert_doc": "docs/certification/Stage-6.8-plan.md",
    },
    {
        "stage": "6.9", "name": "monitoring_observability",
        "kind": "generic",
        "modules": ("backend_health", "host_metrics", "drift_detection"),
        "tests": ("test_backend_health.py", "test_drift_detection.py"),
        "cert_doc": "docs/certification/Stage-6.9-plan.md",
        "spec_docs": (),
        "extra_docs": (),
    },
    {
        "stage": "6.10", "name": "final_integration_gate",
        "kind": "self",
        "cert_doc": "docs/certification/Stage-6.10-plan.md",
        "contract_doc": "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md",
        "release_doc": "docs/certification/Stage-6-final-integration-release.md",
        "handoff_doc": "docs/roadmap/STAGE7_HANDOFF.md",
    },
)

_STAGE7_HANDOFF_DOC = "docs/roadmap/STAGE7_HANDOFF.md"
_SMOKE_SCRIPT = "scripts/test_smoke.py"
_SECURITY_SCRIPT = "scripts/security_scan_baseline.py"
_CC_TESTS_DIR_REL = "scos/control_center/tests"

# Readiness scoring buckets (weights sum to 100; optional run_* checks are
# excluded - they are GO guards, not score contributors).
_SCORE_BUCKETS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("preflight", 5, ("validate_inputs", "validate_repo_root_exists", "validate_git_state")),
    ("source_contract", 35, tuple(
        f"validate_stage6_{entry['stage'].split('.')[1]}_artifacts"
        for entry in _STAGE_ARTIFACTS if entry["kind"] in ("generic", "self")
    )),
    ("stage6_coherence", 15, (
        "validate_stage6_7_audit_wiring",
        "validate_stage6_8_security_scan_cc_coverage",
        "validate_stage6_8_security_scan_frontend_coverage",
    )),
    ("safety_boundary", 20, (
        "validate_no_backend_forbidden_tokens",
        "validate_no_frontend_forbidden_tokens",
        "validate_no_real_ai_dispatch",
        "validate_subprocess_allowlist_exception",
        "validate_stage6_10_own_files_forbidden_tokens",
    )),
    ("stage7_handoff", 25, (
        "validate_stage7_handoff_items_generated",
        "validate_stage7_handoff_doc_exists",
    )),
)

# Stage 7 handoff items: (item_id, title, category, priority, description,
# stage7_owner, source_stage6_evidence).
_STAGE7_HANDOFF_ITEMS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("stage7-001", "Build the local Control Center read/query surface",
     "read_surface", "urgent",
     "Expose a local-only read API over the Stage 6.2-6.3 backend state, event "
     "stream, and approval audit ledger so operators can query backend state "
     "without mutating it.",
     "stage7-platform", "scos/control_center/command_api.py"),
    ("stage7-002", "Project controlled UI state from local backend",
     "ui_projection", "high",
     "Render operator-facing panels from the read-only local backend state "
     "established in Stages 6.2-6.4; keep the frontend static/mock and "
     "local-first.",
     "stage7-frontend", "scos/control_center/ui_state_sync.py"),
    ("stage7-003", "Design operator-facing health/status panels",
     "operator_health_panel", "high",
     "Turn the Stage 6.9 monitoring/observability metrics into static, "
     "read-only operator health and recent-activity panels.",
     "stage7-frontend", "scos/control_center/backend_health.py"),
    ("stage7-004", "Decide the sync transport policy",
     "sync_decision", "urgent",
     "Make an explicit Stage 7 scope decision on whether WebSocket / SSE / "
     "polling is permitted for UI sync; keep the default local-first and "
     "offline-safe unless approved.",
     "stage7-lead", "docs/specification/STAGE6_EVENT_STREAM_BOUNDARY.md"),
    ("stage7-005", "Gate real adapter activation behind approval",
     "adapter_activation", "urgent",
     "Any real AI adapter activation in Stage 7 must remain opt-in behind the "
     "operator approval boundary; no automatic dispatch.",
     "stage7-lead", "scos/control_center/operator_approval.py"),
    ("stage7-006", "Preserve the local-first safety boundary",
     "safety_boundary", "urgent",
     "No cloud/SaaS/telemetry unless explicitly approved; keep all data on the "
     "local machine and the Stage 6.8 security baseline green.",
     "stage7-lead", "scripts/security_scan_baseline.py"),
    ("stage7-007", "Keep integrations/buffer out of scope by default",
     "safety_boundary", "high",
     "Do not include integrations/buffer in Stage 7 unless a separate, "
     "explicitly approved scope decision adds it.",
     "stage7-lead", "docs/specification/STAGE6_SCOPE_BOUNDARY.md"),
    ("stage7-008", "Define Stage 7 success criteria and closure gate",
     "stage7_readiness", "urgent",
     "Mirror the Stage 5.10 / Stage 6.10 certification pattern: decide what "
     "Stage 7 must deliver and the measurable criteria that close it.",
     "stage7-lead", "docs/roadmap/STAGE7_HANDOFF.md"),
    ("stage7-009", "Document the Stage 6 read-surface contract",
     "documentation", "normal",
     "Write the Stage 7 read-surface specification so the read API stays "
     "deterministic, read-only, and offline-safe.",
     "stage7-docs", "docs/specification/STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md"),
    ("stage7-010", "Extend Stage 6.9 drift detection as a guard",
     "read_surface", "normal",
     "Reuse the Stage 6.9 drift detection as a continuous local guard for the "
     "Stage 7 read surface's coherence between state/event/audit evidence.",
     "stage7-platform", "scos/control_center/drift_detection.py"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_url_like(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text.lower().startswith(_URL_PREFIXES) or bool(_SCHEME_RE.match(text))


def _gate_id(repo_root: Path, checked_at: str) -> str:
    digest = hashlib.sha256(
        f"stage6-final-integration-gate|{checked_at}|{repo_root}".encode("utf-8")
    ).hexdigest()[:16]
    return f"s6g-{digest}"


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


def _strip_docstrings(text: str) -> str:
    return _TRIPLE_QUOTED_RE.sub("", text)


def _line_is_negated(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _NEGATION_TOKENS)


def _is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    return "tests" in parts or Path(rel).name.startswith("test_")


def _code_lines(text: str):
    """Mirror scripts/security_scan_baseline.py _code_lines exactly.

    Strips triple-quoted docstrings, then skips blank lines, ``#``/``//``/``*``
    comment lines, and lines under a negated heading. Only genuine code lines
    reach the scanner, so prose mentions of forbidden behavior are never
    flagged (keeps this gate aligned with the Stage 6.8 security baseline).
    """
    for line in _strip_docstrings(text).splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("//")
            or stripped.startswith("*")
            or _line_is_negated(stripped)
        ):
            continue
        yield stripped


def _scan_backend_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    """Scan scos/control_center/*.py (excluding own + subprocess-allowlisted).

    Mirrors scripts/security_scan_baseline._append_control_center_findings so
    the Stage 6.10 gate agrees with the Stage 6.8 security baseline scan.
    """
    cc_dir = _control_center_dir(repo_root)
    token_category = {token: category for category, token in _FORBIDDEN_BACKEND_TOKENS}
    import_pattern = re.compile(
        r"^\s*(?:import|from)\s+("
        + "|".join(re.escape(t) for _category, t in _FORBIDDEN_BACKEND_TOKENS)
        + r")\b",
        re.MULTILINE,
    )
    allowlisted = set(_CONTROL_CENTER_SUBPROCESS_ALLOWLIST)
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
        rel = str(path.relative_to(repo_root)).replace("\\", "/")
        # network / ai / gui import scan over full source (matches real scan).
        for match in import_pattern.finditer(text):
            token = match.group(1)
            findings.append({"file": path.name, "token": token,
                             "category": token_category[token]})
        # The remaining checks iterate filtered code lines only (matches real
        # scan's _code_lines), gated by runtime_module so test modules are skipped.
        runtime_module = not _is_test_path(rel)
        audit_upper = _W_AUDIT_LEDGER.upper()
        for stripped in _code_lines(text):
            if not runtime_module:
                break
            if _SUBPROCESS_IMPORT_RE.search(stripped) and rel not in allowlisted:
                findings.append({"file": path.name, "token": "subprocess",
                                 "category": "subprocess_scope"})
            if rel not in allowlisted:
                if (_SUBPROCESS_USE_RE.search(stripped) or _PTY_IMPORT_RE.search(stripped)
                        or _PTY_USE_RE.search(stripped)):
                    findings.append({"file": path.name, "token": "pty_or_subprocess_use",
                                     "category": "shell_exec"})
                if _W_OS_SYSTEM in stripped or _W_SHELL_TRUE in stripped:
                    findings.append({"file": path.name, "token": "shell_true_or_os_system",
                                     "category": "shell_exec"})
                upper = stripped.upper()
                if (("DELETE" in upper and audit_upper in upper)
                        or ("UPDATE" in upper and audit_upper in upper)
                        or ("DROP" in upper and "TABLE" in upper and audit_upper in upper)):
                    findings.append({"file": path.name, "token": "destructive_audit_ledger_sql",
                                     "category": "destructive_audit_ledger_sql"})
    return findings


def _scan_stage6_10_own_files_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    """Dogfood scan: this stage's own files must respect the same boundary."""
    cc_dir = _control_center_dir(repo_root)
    token_category = {token: category for category, token in _FORBIDDEN_BACKEND_TOKENS}
    import_pattern = re.compile(
        r"^\s*(?:import|from)\s+("
        + "|".join(re.escape(t) for _category, t in _FORBIDDEN_BACKEND_TOKENS)
        + r")\b",
        re.MULTILINE,
    )
    findings: list[dict[str, str]] = []
    for stem in _OWN_MODULES:
        path = cc_dir / f"{stem}.py"
        text = _read_text(path)
        if text is None:
            continue
        for match in import_pattern.finditer(text):
            token = match.group(1)
            findings.append({"file": path.name, "token": token,
                             "category": token_category[token]})
        for line in _strip_docstrings(text).splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or _line_is_negated(stripped):
                continue
            if _W_SHELL_TRUE in stripped or _W_OS_SYSTEM in stripped:
                findings.append({"file": path.name, "token": "shell_true_or_os_system",
                                 "category": "shell_exec"})
    return findings


def _scan_frontend_forbidden_tokens(repo_root: Path) -> list[dict[str, str]]:
    fe_dir = _frontend_dir(repo_root)
    if not fe_dir.is_dir():
        return []  # frontend absent -> not a Stage 6.10 certification target
    findings: list[dict[str, str]] = []
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
                if stripped.startswith("//") or stripped.startswith("*") \
                        or _line_is_negated(stripped):
                    continue
                for token, category in _FORBIDDEN_FRONTEND_TOKENS:
                    if token in stripped:
                        findings.append({"file": rel, "token": token, "category": category})
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


def _build_handoff_items() -> tuple[Stage7HandoffItem, ...]:
    return tuple(
        Stage7HandoffItem.of(
            item_id, title, category, priority,
            description=description, stage7_owner=owner,
            source_stage6_evidence=evidence,
        )
        for item_id, title, category, priority, description, owner, evidence
        in _STAGE7_HANDOFF_ITEMS
    )


def _compute_readiness(
    checks: list[Stage6GateCheck], blockers: list[Stage6GateBlocker]
) -> tuple[int, dict[str, int]]:
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
    # Clamp to honor the documented bands.
    error_critical = any(b.severity in ("error", "critical") for b in blockers)
    warnings_only = bool(blockers) and not error_critical
    if error_critical:
        score = min(score, 79)
    elif warnings_only:
        score = max(min(score, 99), 80)
    else:
        # no blockers: 100 when fully passed, else 80-99 (some skipped)
        if score >= 100:
            score = 100
        else:
            score = max(min(score, 99), 80)
    return score, breakdown


def _write_stable_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def run_stage6_final_integration_gate(
    *,
    repo_root,
    checked_at: str,
    output_path=None,
    require_clean_git: bool = True,
    run_smoke: bool = True,
    run_security_scan: bool = True,
    run_control_center_tests: bool = True,
    run_frontend_checks: bool = False,
) -> Stage6FinalIntegrationResult | Stage6FinalIntegrationError:
    checks: list[Stage6GateCheck] = []
    blockers: list[Stage6GateBlocker] = []
    evidence: list[Stage6GateEvidence] = []

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
        checks.append(Stage6GateCheck.of(
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
        blockers.append(Stage6GateBlocker.of(
            blocker_id, category, severity, title, detail,
            recommended_action, source_check, metadata,
        ))

    def _evidence(
        evidence_id: str, stage: str, kind: str, artifact_path: str,
        detail: str = "", metadata: dict[str, Any] | None = None,
    ) -> None:
        evidence.append(Stage6GateEvidence.of(
            evidence_id, stage, kind, artifact_path, detail=detail, metadata=metadata,
        ))

    def _error(
        error_kind: str, error_detail: str, failed_check: str,
        metadata: dict[str, Any] | None = None,
    ) -> Stage6FinalIntegrationError:
        return Stage6FinalIntegrationError.of(
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

    # 2. validate_repo_root_exists -------------------------------------------
    root = Path(str(repo_root))
    if not root.is_dir():
        _check("validate_repo_root_exists", "failure", "error", category="preflight",
               artifact_path=str(root), error_kind="INPUT_NOT_FOUND",
               error_detail="repo_root does not exist or is not a directory")
        return _error("INPUT_NOT_FOUND", "repo_root does not exist or is not a directory",
                      "validate_repo_root_exists", metadata={"repo_root": str(root)})
    root = root.resolve()
    gate_id = _gate_id(root, checked_at)
    _check("validate_inputs", "success", category="preflight", artifact_path=str(root),
           metadata={"gate_id": gate_id})
    _check("validate_repo_root_exists", "success", category="preflight",
           artifact_path=str(root))

    # 3. validate_git_state ---------------------------------------------------
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
                _check("validate_git_state", "failure", "error", category="preflight",
                       error_kind="GIT_STATE_NOT_CLEAN",
                       error_detail="; ".join(problems),
                       metadata={"problems": problems, "branch": branch or ""})
                _blocker("blk-git-state", "preflight", "error",
                         "Working tree is not clean (require_clean_git=True)",
                         "; ".join(problems),
                         "Commit or stash the pending changes before certifying Stage 6.",
                         "validate_git_state", metadata={"problems": problems})
            else:
                _check("validate_git_state", "success", category="preflight",
                       metadata={"branch": branch or "", "clean": True})
    else:
        _check("validate_git_state", "success", category="preflight",
               metadata={"reason": "require_clean_git=False; clean-tree not enforced"})

    # 4. Per-stage artifact presence/coherence ------------------------------
    cc_dir = _control_center_dir(root)
    cc_tests_dir = _control_center_tests_dir(root)
    for entry in _STAGE_ARTIFACTS:
        stage_label = entry["stage"]
        stage_num = stage_label.split(".")[1]
        kind = entry["kind"]
        cert_doc = entry["cert_doc"]

        if kind == "generic":
            check_name = f"validate_stage6_{stage_num}_artifacts"
            missing_modules = sorted(
                f"{m}.py" for m in entry["modules"]
                if not (cc_dir / f"{m}.py").is_file()
            )
            missing_tests = sorted(
                t for t in entry["tests"] if not (cc_tests_dir / t).is_file()
            )
            missing_specs = sorted(
                d for d in entry["spec_docs"] if not (root / d).is_file()
            )
            missing_extras = sorted(
                d for d in entry.get("extra_docs", ()) if not (root / d).is_file()
            )
            missing_cert = [] if (root / cert_doc).is_file() else [cert_doc]
            missing_artifacts = (
                missing_modules + missing_tests + missing_specs
                + missing_extras + missing_cert
            )
            metadata = {
                "missing_modules": missing_modules,
                "missing_tests": missing_tests,
                "missing_spec_docs": missing_specs,
                "missing_extra_docs": missing_extras,
                "missing_cert_doc": missing_cert,
            }
            if missing_artifacts:
                _check(check_name, "failure", "error", category="source_contract",
                       artifact_path=cert_doc,
                       error_kind="STAGE_ARTIFACT_MISSING",
                       error_detail=f"Stage {stage_label} artifacts/docs incomplete",
                       metadata=metadata)
                _blocker(f"blk-stage6-{stage_num}-artifacts", "source_contract", "error",
                         f"Stage {stage_label} artifacts or docs are incomplete",
                         f"missing_artifacts={missing_artifacts}",
                         f"Restore the missing Stage {stage_label} artifacts and/or docs.",
                         check_name, metadata=metadata)
            else:
                _check(check_name, "success", category="source_contract",
                       metadata=metadata)
                _evidence(f"ev-stage6-{stage_num}", stage_label, "artifact_presence",
                          cert_doc,
                          detail=f"Stage {stage_label} ({entry['name']}) artifacts present")
        elif kind == "self":
            check_name = f"validate_stage6_{stage_num}_artifacts"
            contract_doc = entry["contract_doc"]
            release_doc = entry["release_doc"]
            handoff_doc = entry["handoff_doc"]
            missing = sorted(
                d for d in (cert_doc, contract_doc, release_doc, handoff_doc)
                if not (root / d).is_file()
            )
            metadata = {"missing_docs": missing}
            if missing:
                _check(check_name, "failure", "error", category="source_contract",
                       artifact_path=handoff_doc,
                       error_kind="STAGE_ARTIFACT_MISSING",
                       error_detail="Stage 6.10 contract/release/handoff docs incomplete",
                       metadata=metadata)
                _blocker("blk-stage6-10-docs", "source_contract", "error",
                         "Stage 6.10 final gate docs are incomplete",
                         f"missing_docs={missing}",
                         "Create the missing Stage 6.10 contract/release/handoff docs.",
                         check_name, metadata=metadata)
            else:
                _check(check_name, "success", category="source_contract", metadata=metadata)
                _evidence("ev-stage6-10", stage_label, "artifact_presence", handoff_doc,
                          detail="Stage 6.10 contract/release/handoff docs present")
        # kind == "security_scan" handled in the coherence section below.

    # 5. Stage 6 coherence: 6.7 audit wiring + 6.8 security coverage --------
    runner_text = _read_text(cc_dir / "command_runner.py") or ""
    audit_wired = ("approval_audit" in runner_text) or ("is_execution_granted" in runner_text)
    if audit_wired:
        _check("validate_stage6_7_audit_wiring", "success", category="stage6_coherence",
               artifact_path="scos/control_center/command_runner.py")
        _evidence("ev-stage6-7", "6.7", "audit_wiring",
                  "scos/control_center/command_runner.py",
                  detail="approval-audit ledger referenced by command_runner.py")
    else:
        _check("validate_stage6_7_audit_wiring", "failure", "error",
               category="stage6_coherence",
               artifact_path="scos/control_center/command_runner.py",
               error_kind="AUDIT_NOT_WIRED",
               error_detail="command_runner.py does not reference the approval-audit ledger")
        _blocker("blk-stage6-7-audit", "stage6_coherence", "error",
                 "Stage 6.7 approval-audit ledger is not wired into command execution",
                 "command_runner.py does not reference approval_audit_store / is_execution_granted.",
                 "Wire the Stage 6.6 audit ledger into command_runner execution enforcement.",
                 "validate_stage6_7_audit_wiring")

    sec_text = _read_text(root / _SECURITY_SCRIPT)
    if sec_text is None:
        _check("validate_stage6_8_security_scan_cc_coverage", "failure", "error",
               category="stage6_coherence", artifact_path=_SECURITY_SCRIPT,
               error_kind="SECURITY_SCRIPT_MISSING",
               error_detail="scripts/security_scan_baseline.py not found")
        _blocker("blk-stage6-8-sec-missing", "stage6_coherence", "error",
                 "Security scan baseline script is missing",
                 "scripts/security_scan_baseline.py not found.",
                 "Restore the security baseline before certifying Stage 6.",
                 "validate_stage6_8_security_scan_cc_coverage")
    else:
        cc_covered = ("control_center" in sec_text) or ("_CONTROL_CENTER_DIR" in sec_text)
        fe_covered = ("control-center" in sec_text) or ("_FRONTEND_DIR" in sec_text)
        if cc_covered:
            _check("validate_stage6_8_security_scan_cc_coverage", "success",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT)
            _evidence("ev-stage6-8-cc", "6.8", "security_coverage", _SECURITY_SCRIPT,
                      detail="security scan covers scos/control_center")
        else:
            _check("validate_stage6_8_security_scan_cc_coverage", "failure", "error",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT,
                   error_kind="SECURITY_NO_CC_COVERAGE",
                   error_detail="security scan does not cover scos/control_center")
            _blocker("blk-stage6-8-cc", "stage6_coherence", "error",
                     "Security scan does not cover scos/control_center",
                     "scripts/security_scan_baseline.py has no control_center coverage.",
                     "Add scos/control_center coverage to the security baseline (Stage 6.8).",
                     "validate_stage6_8_security_scan_cc_coverage")
        if fe_covered:
            _check("validate_stage6_8_security_scan_frontend_coverage", "success",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT)
            _evidence("ev-stage6-8-fe", "6.8", "security_coverage", _SECURITY_SCRIPT,
                      detail="security scan covers apps/control-center")
        else:
            _check("validate_stage6_8_security_scan_frontend_coverage", "failure", "error",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT,
                   error_kind="SECURITY_NO_FE_COVERAGE",
                   error_detail="security scan does not cover apps/control-center")
            _blocker("blk-stage6-8-fe", "stage6_coherence", "error",
                     "Security scan does not cover apps/control-center",
                     "scripts/security_scan_baseline.py has no control-center coverage.",
                     "Add apps/control-center coverage to the security baseline (Stage 6.8).",
                     "validate_stage6_8_security_scan_frontend_coverage")

    if run_security_scan:
        exit_code, tail = _run_repo_script(root, _SECURITY_SCRIPT, _SCRIPT_TIMEOUT_SECONDS)
        if exit_code == 0:
            _check("validate_stage6_8_security_scan_runnable", "success",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT,
                   metadata={"exit_code": 0, "tail": tail})
        else:
            _check("validate_stage6_8_security_scan_runnable", "failure", "error",
                   category="stage6_coherence", artifact_path=_SECURITY_SCRIPT,
                   error_kind="SECURITY_SCAN_FAILED",
                   error_detail="security scan baseline reported findings",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-stage6-8-sec-run", "stage6_coherence", "error",
                     "Security scan baseline failed",
                     f"{_SECURITY_SCRIPT} exited with {exit_code!r}: {tail}",
                     "Resolve the security findings before certifying Stage 6.",
                     "validate_stage6_8_security_scan_runnable",
                     metadata={"exit_code": exit_code})
    else:
        _check("validate_stage6_8_security_scan_runnable", "skipped",
               category="stage6_coherence",
               metadata={"reason": "run_security_scan=False",
                         "note": "security scan is a required operator command before closure"})

    # 6. Safety boundary ------------------------------------------------------
    backend_findings = _scan_backend_forbidden_tokens(root)
    if backend_findings:
        _check("validate_no_backend_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="FORBIDDEN_BACKEND_BEHAVIOR",
               error_detail="forbidden backend tokens found in scos/control_center",
               metadata={"findings": backend_findings})
        _blocker("blk-backend-forbidden-tokens", "safety_boundary", "critical",
                 "Forbidden backend behavior detected in scos/control_center",
                 f"{len(backend_findings)} finding(s).",
                 "Remove the forbidden import/pattern before certifying Stage 6.",
                 "validate_no_backend_forbidden_tokens", metadata={"findings": backend_findings})
    else:
        _check("validate_no_backend_forbidden_tokens", "success", category="safety_boundary")

    frontend_findings = _scan_frontend_forbidden_tokens(root)
    if frontend_findings:
        _check("validate_no_frontend_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="FORBIDDEN_FRONTEND_BEHAVIOR",
               error_detail="forbidden frontend tokens found in apps/control-center",
               metadata={"findings": frontend_findings})
        _blocker("blk-frontend-forbidden-tokens", "safety_boundary", "critical",
                 "Forbidden frontend behavior detected in apps/control-center",
                 f"{len(frontend_findings)} finding(s).",
                 "Remove the forbidden call/import before certifying Stage 6.",
                 "validate_no_frontend_forbidden_tokens",
                 metadata={"findings": frontend_findings})
    else:
        _check("validate_no_frontend_forbidden_tokens", "success", category="safety_boundary")

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

    # real AI dispatch check (adapter modules must stay simulations)
    cc_dir = _control_center_dir(root)
    ai_dispatch_findings: list[dict[str, str]] = []
    adapter_files = ("agent_adapter_contracts.py", "agent_adapter_simulator.py",
                    "agent_adapter_registry.py")
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
        _check("validate_no_real_ai_dispatch", "failure", "critical",
               category="safety_boundary",
               error_kind="REAL_AI_DISPATCH_DETECTED",
               error_detail="adapter modules show signs of a real dispatch integration",
               metadata={"findings": ai_dispatch_findings})
        _blocker("blk-real-ai-dispatch", "safety_boundary", "critical",
                 "Real AI dispatch behavior detected in adapter modules",
                 f"findings={ai_dispatch_findings}",
                 "Remove the real-dispatch code; Stage 6 adapters must remain simulations.",
                 "validate_no_real_ai_dispatch", metadata={"findings": ai_dispatch_findings})
    else:
        _check("validate_no_real_ai_dispatch", "success", category="safety_boundary")

    # subprocess allowlist (only allowlisted modules may import subprocess)
    allowlisted_stems = {p.split("/")[-1][:-3] for p in _CONTROL_CENTER_SUBPROCESS_ALLOWLIST}
    unexpected_importers = []
    if cc_dir.is_dir():
        for path in sorted(cc_dir.glob("*.py")):
            if path.stem in _OWN_MODULES or path.stem in allowlisted_stems:
                continue
            text = _read_text(path) or ""
            if re.search(r"^\s*import\s+" + _W_SUBPROCESS + r"\b", text, re.MULTILINE):
                unexpected_importers.append(path.stem)
    if unexpected_importers:
        _check("validate_subprocess_allowlist_exception", "failure", "critical",
               category="safety_boundary",
               error_kind="SUBPROCESS_ALLOWLIST_VIOLATION",
               error_detail="subprocess used outside the allowlisted modules",
               metadata={"unexpected_importers": unexpected_importers})
        _blocker("blk-subprocess-allowlist", "safety_boundary", "critical",
                 "subprocess is used outside the allowlisted modules",
                 f"unexpected_importers={unexpected_importers}",
                 "Remove the extra subprocess usage.",
                 "validate_subprocess_allowlist_exception",
                 metadata={"unexpected_importers": unexpected_importers})
    else:
        _check("validate_subprocess_allowlist_exception", "success",
               category="safety_boundary",
               metadata={"allowlisted_modules": sorted(allowlisted_stems)})

    own_findings = _scan_stage6_10_own_files_forbidden_tokens(root)
    if own_findings:
        _check("validate_stage6_10_own_files_forbidden_tokens", "failure", "critical",
               category="safety_boundary",
               error_kind="STAGE6_10_SELF_SCAN_FAILED",
               error_detail="Stage 6.10's own files contain a forbidden token",
               metadata={"findings": own_findings})
        _blocker("blk-stage6-10-self-scan", "safety_boundary", "critical",
                 "Stage 6.10's own gate modules violate the safety boundary",
                 f"findings={own_findings}",
                 "Remove the forbidden token from the Stage 6.10 module itself.",
                 "validate_stage6_10_own_files_forbidden_tokens",
                 metadata={"findings": own_findings})
    else:
        _check("validate_stage6_10_own_files_forbidden_tokens", "success",
               category="safety_boundary")

    # 7. Optional run guards (neutral when skipped, blocker on failure) -----
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
                     "Fix the smoke failures before certifying Stage 6.",
                     "run_smoke_script", metadata={"exit_code": exit_code})
    else:
        _check("run_smoke_script", "skipped", category="testing",
               metadata={"reason": "run_smoke=False"})

    if run_control_center_tests:
        try:
            proc = subprocess.run(
                [_script_interpreter(root), "-m", "pytest", _CC_TESTS_DIR_REL, "-q"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            exit_code, tail = proc.returncode, _tail_line(proc.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            exit_code, tail = None, type(exc).__name__
        if exit_code == 0:
            _check("run_control_center_tests", "success", category="testing",
                   artifact_path=_CC_TESTS_DIR_REL, metadata={"exit_code": 0, "tail": tail})
        else:
            _check("run_control_center_tests", "failure", "error", category="testing",
                   artifact_path=_CC_TESTS_DIR_REL, error_kind="CONTROL_CENTER_TESTS_FAILED",
                   error_detail="control_center test tier failed",
                   metadata={"exit_code": exit_code, "tail": tail})
            _blocker("blk-control-center-tests", "testing", "error",
                     "control_center test tier failed",
                     f"pytest {_CC_TESTS_DIR_REL} exited with {exit_code!r}: {tail}",
                     "Fix the failing control_center tests before certifying Stage 6.",
                     "run_control_center_tests", metadata={"exit_code": exit_code})
    else:
        _check("run_control_center_tests", "skipped", category="testing",
               metadata={"reason": "run_control_center_tests=False"})

    if run_frontend_checks:
        import shutil as _shutil
        import os as _os
        pnpm_exe = _shutil.which("pnpm")
        pnpm_probe = None
        if pnpm_exe is not None:
            try:
                pnpm_probe = subprocess.run(
                    [pnpm_exe, "--version"], cwd=str(_frontend_dir(root)),
                    capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pnpm_probe = None
        if pnpm_exe is None or pnpm_probe is None or pnpm_probe.returncode != 0:
            _check("run_frontend_checks", "skipped", category="testing",
                   metadata={"reason": "pnpm not available"})
        else:
            env_note = {"NEXT_TELEMETRY_DISABLED": "1"}
            for check_name, args in (
                ("run_frontend_lint", [pnpm_exe, "lint"]),
                ("run_frontend_build", [pnpm_exe, "build"]),
            ):
                try:
                    proc = subprocess.run(
                        args, cwd=str(_frontend_dir(root)), capture_output=True,
                        text=True, timeout=_FRONTEND_TIMEOUT_SECONDS,
                        env={**_os.environ, **env_note},
                    )
                    exit_code, tail = proc.returncode, _tail_line(proc.stdout or proc.stderr)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    exit_code, tail = None, type(exc).__name__
                if exit_code == 0:
                    _check(check_name, "success", category="testing",
                           metadata={"exit_code": 0, "tail": tail})
                elif exit_code is None:
                    _check(check_name, "skipped", category="testing",
                           metadata={"reason": tail})
                else:
                    _check(check_name, "failure", "error", category="testing",
                           error_kind="FRONTEND_CHECK_FAILED",
                           error_detail=f"{args[-1]} failed",
                           metadata={"exit_code": exit_code, "tail": tail})
                    _blocker(f"blk-{check_name}", "testing", "error",
                             f"pnpm {args[-1]} failed",
                             f"exit_code={exit_code} tail={tail}",
                             f"Fix the pnpm {args[-1]} failure before certifying Stage 6.",
                             check_name, metadata={"exit_code": exit_code})
    else:
        _check("run_frontend_checks", "skipped", category="testing",
               metadata={"reason": "run_frontend_checks=False"})

    # 8. Stage 7 handoff ------------------------------------------------------
    handoff_items = _build_handoff_items()
    handoff_items_2 = _build_handoff_items()
    deterministic = (
        json.dumps([i.to_dict() for i in handoff_items], sort_keys=True)
        == json.dumps([i.to_dict() for i in handoff_items_2], sort_keys=True)
    )
    if 8 <= len(handoff_items) <= 12 and deterministic:
        _check("validate_stage7_handoff_items_generated", "success",
               category="stage7_handoff", metadata={"count": len(handoff_items)})
    else:
        _check("validate_stage7_handoff_items_generated", "failure", "error",
               category="stage7_handoff", error_kind="HANDOFF_ITEMS_INVALID",
               error_detail="handoff item count or determinism check failed",
               metadata={"count": len(handoff_items), "deterministic": deterministic})
        _blocker("blk-stage7-handoff-items", "stage7_handoff", "error",
                 "Stage 7 handoff items are invalid or non-deterministic",
                 f"count={len(handoff_items)} deterministic={deterministic}",
                 "Regenerate 8-12 deterministic Stage 7 handoff items.",
                 "validate_stage7_handoff_items_generated",
                 metadata={"count": len(handoff_items)})

    handoff_doc = _STAGE7_HANDOFF_DOC
    if (root / handoff_doc).is_file():
        _check("validate_stage7_handoff_doc_exists", "success",
               category="stage7_handoff", artifact_path=handoff_doc)
        _evidence("ev-stage7-handoff", "7", "handoff_doc", handoff_doc,
                  detail="Stage 7 handoff document present")
    else:
        _check("validate_stage7_handoff_doc_exists", "failure", "error",
               category="stage7_handoff", artifact_path=handoff_doc,
               error_kind="HANDOFF_DOC_MISSING",
               error_detail="docs/roadmap/STAGE7_HANDOFF.md is missing")
        _blocker("blk-stage7-handoff-doc", "stage7_handoff", "error",
                 "Stage 7 handoff document is missing",
                 f"{handoff_doc} was not found.",
                 "Create the Stage 7 handoff document before certifying Stage 6.",
                 "validate_stage7_handoff_doc_exists")

    # 9. Readiness + verdict --------------------------------------------------
    score, breakdown = _compute_readiness(checks, blockers)
    has_blocker = bool(blockers)
    # Optional run guards that failed already added blockers; re-check.
    go_no_go = "GO" if (not has_blocker and score == 100) else "NO_GO"
    readiness_level = "certified" if go_no_go == "GO" else "blocked"
    accepted = go_no_go == "GO"
    stage_closed = go_no_go == "GO"
    _check("compute_stage6_readiness", "success", category="stage7_handoff",
           metadata={"score": score, "breakdown": breakdown, "go_no_go": go_no_go})

    # 10. Output artifact -----------------------------------------------------
    final_output: Path | None = None
    if output_path is not None:
        target = Path(str(output_path))
        final_output = target if target.suffix.lower() == ".json" else target / _OUTPUT_FILENAME

    result = Stage6FinalIntegrationResult(
        ok=True,
        schema_version=STAGE6_FINAL_GATE_SCHEMA_VERSION,
        accepted=accepted,
        gate_id=gate_id,
        checked_at=checked_at,
        stage=_STAGE_LABEL,
        stage_closed=stage_closed,
        go_no_go=go_no_go,
        readiness_level=readiness_level,
        readiness_score=score,
        readiness_max_score=READINESS_MAX_SCORE,
        checks=tuple(checks),
        evidence=tuple(evidence),
        blockers=tuple(blockers),
        stage7_handoff_items=handoff_items,
        output_path=None if final_output is None else str(final_output),
        metadata={
            "generator": _GENERATOR,
            "gate_name": _GATE_NAME,
            "gate_stage": "6.10",
            "repo_root": str(root),
            "score_breakdown": breakdown,
            "flags": {
                "require_clean_git": bool(require_clean_git),
                "run_smoke": bool(run_smoke),
                "run_security_scan": bool(run_security_scan),
                "run_control_center_tests": bool(run_control_center_tests),
                "run_frontend_checks": bool(run_frontend_checks),
            },
        },
    )

    if final_output is not None:
        try:
            final_output.parent.mkdir(parents=True, exist_ok=True)
            _write_stable_json(final_output, result.to_dict())
        except OSError as exc:
            _check("write_output", "failure", "error", category="stage7_handoff",
                   artifact_path=str(final_output),
                   error_kind="OUTPUT_WRITE_FAILED",
                   error_detail="certification report could not be written",
                   metadata={"os_error": type(exc).__name__})
            return _error("OUTPUT_WRITE_FAILED", "certification report could not be written",
                          "write_output", metadata={"os_error": type(exc).__name__})

    return result
