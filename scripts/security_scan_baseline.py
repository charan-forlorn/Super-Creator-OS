"""SCOS security scan baseline — local static scan only (Stage 6.8).

Scans commercial executable source, Control Center backend source, Control
Center frontend source, the scripts directory, and root config files for
suspicious patterns: credential/token indicators, money-provider imports,
network libraries, external-service behavior indicators, forbidden frontend
runtime transport/state APIs, committed environment files, and private key
headers.

Design notes:
- stdlib only; no network, no dependency installation, no external scanners,
  no mutation.
- Docs are deliberately NOT scanned — mentioning forbidden capabilities as
  non-goals is expected there.
- Every scan pattern below is assembled from string fragments so this file's
  own source never contains the literal tokens it hunts for.
- Findings are printed with redacted samples only, never full matches.
- Output ordering is fully deterministic (sorted paths, then line numbers).

Run: .venv\\Scripts\\python.exe scripts\\security_scan_baseline.py
Exit: 0 on PASS (no findings), 1 on FAIL.
"""

from __future__ import annotations

import re
import sys
import hashlib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_COMMERCIAL_DIR = _ROOT / "scos" / "commercial"
_CONTROL_CENTER_DIR = _ROOT / "scos" / "control_center"
_FRONTEND_DIR = _ROOT / "apps" / "control-center"
_SCRIPTS_DIR = _ROOT / "scripts"
_ROOT_CONFIG_FILES = ("requirements.txt", "conftest.py")

_SKIP_DIR_NAMES = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}
_FRONTEND_SKIP_DIR_NAMES = {
    "node_modules", ".next", ".vercel", "dist", "build", "coverage",
}
_FRONTEND_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}

# ---------------------------------------------------------------------------
# Pattern table. Literal tokens are assembled from fragments (repo convention)
# so this scanner never flags itself. scope "commercial" restricts a category
# to scos/commercial executable source; "all" covers every scanned file.
# ---------------------------------------------------------------------------

_W_STRIPE = "stri" + "pe"
_W_PAYPAL = "pay" + "pal"
_W_BRAINTREE = "brain" + "tree"
_W_OMISE = "omi" + "se"
_W_SQUAREUP = "square" + "up"
_W_HUBSPOT = "hub" + "spot"
_W_SALESFORCE = "sales" + "force"
_W_ZOHO = "zo" + "ho"
_W_PIPEDRIVE = "pipe" + "drive"
_W_SENDGRID = "send" + "grid"
_W_TWILIO = "twi" + "lio"
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
_W_DELETE = "DELETE"
_W_UPDATE = "UPDATE"
_W_DROP = "DROP"
_W_AUDIT_LEDGER = "audit" + "_ledger"
_W_BIND_ADDR = "0." + "0." + "0." + "0"
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
_W_AKIA = "AK" + "IA"
_W_ASIA = "AS" + "IA"
_W_GHP = "gh" + "p_"
_W_XOX = "xo" + "x"
_W_SK = "sk" + "-"
_W_API_KEY = "api" + "_key"
_W_TOKEN = "tok" + "en"
_W_SECRET = "sec" + "ret"
_W_PASSWORD = "pass" + "word"
_W_WEBHOOK = "web" + "hook"
_W_SIGNING_SECRET = "signing" + "_secret"
_W_BEGIN = "-----" + "BEGIN"
_W_PRIVATE_KEY = "PRIVATE" + " KEY"
_W_EYJ = "ey" + "J"

_PATTERNS = (
    # (category, scope, compiled regex)
    ("openai_secret_key", "all", re.compile(r"\b" + _W_SK + r"[A-Za-z0-9]{20,}\b")),
    ("github_token", "all", re.compile(_W_GHP + r"[A-Za-z0-9]{20,}")),
    ("slack_token", "all", re.compile(_W_XOX + r"[baprs]-[A-Za-z0-9-]{10,}")),
    ("aws_access_key_id", "all", re.compile(r"\b(?:" + _W_AKIA + "|" + _W_ASIA + r")[0-9A-Z]{16}\b")),
    ("aws_secret_access_key", "all", re.compile(
        r"\baws_" + _W_SECRET + r"_access_key\b\s*[:=]\s*[\"'][A-Za-z0-9/+=]{32,}[\"']",
        re.IGNORECASE)),
    ("bearer_or_jwt_token", "all", re.compile(r"\b[Bb]earer\s+[A-Za-z0-9._\-]{16,}\b")),
    ("bearer_or_jwt_token", "all", re.compile(
        r"\b" + _W_EYJ + r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("password_assignment", "all", re.compile(
        r"\b" + _W_PASSWORD + r"\b\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']",
        re.IGNORECASE)),
    ("webhook_or_signing_secret", "all", re.compile(
        r"\b(?:" + _W_WEBHOOK + "|" + _W_SIGNING_SECRET + r")\b\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']",
        re.IGNORECASE)),
    ("credential_url", "all", re.compile(
        r"\b[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@[^/\s]+[^\s\"']*")),
    ("generic_secret_assignment", "all", re.compile(
        r"\b(?:" + _W_API_KEY + "|" + _W_TOKEN + "|" + _W_SECRET
        + r")\b\s*[:=]\s*[\"'][A-Za-z0-9_\-/+]{16,}[\"']", re.IGNORECASE)),
    ("money_provider_import", "all", re.compile(
        r"^\s*(?:import|from)\s+(?:" + "|".join(
            (_W_STRIPE, _W_PAYPAL, _W_BRAINTREE, _W_OMISE, _W_SQUAREUP)
        ) + r")\b", re.MULTILINE)),
    ("network_library_in_commercial", "commercial", re.compile(
        r"^\s*(?:import|from)\s+(?:" + "|".join(
            (_W_REQUESTS, re.escape(_W_URLLIB_REQ), re.escape(_W_HTTP_CLIENT),
             _W_SOCKET, _W_AIOHTTP, _W_HTTPX, _W_SMTPLIB, _W_WEBSOCKET + "s?")
        ) + r")\b", re.MULTILINE)),
    ("external_service_indicator", "all", re.compile(
        r"^\s*(?:import|from)\s+(?:" + "|".join(
            (_W_HUBSPOT, _W_SALESFORCE, _W_ZOHO, _W_PIPEDRIVE, _W_SENDGRID, _W_TWILIO)
        ) + r")\b", re.MULTILINE)),
    ("private_key_header", "all", re.compile(
        _W_BEGIN + r"[A-Z ]*" + _W_PRIVATE_KEY + "-----")),
)

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
    r"^\s*(?:import|from)\s+("
    + "|".join((_W_OPENAI, _W_ANTHROPIC))
    + r")\b",
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
_REMOTE_HOST_ASSIGN_RE = re.compile(
    r"\b(?:HOST|host)\s*=\s*[\"']" + re.escape(_W_BIND_ADDR) + r"[\"']"
)
_REMOTE_BIND_RE = re.compile(r"\.bind\(\s*\(\s*[\"'](?!127\.0\.0\.1|localhost)[^\"']+[\"']")
_TRIPLE_QUOTED_RE = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'')
_NEGATION_TOKENS = (
    "no ", "not ", "never", "forbid", "refus", "do not", "must not", "non-goal",
    "disabled",
)
_CONTROL_CENTER_SUBPROCESS_ALLOWLIST = {
    "scos/control_center/command_runner.py",
    "scos/control_center/stage5_final_certification.py",
    "scos/control_center/stage6_final_integration_gate.py",
    # Stage 0 cross-project integration: the HVS adapter drives HVS only
    # through `subprocess.run(list, shell=False, cwd=hvs_root, ...)` read-only
    # capability probes. Same safe pattern as command_runner.py.
    "scos/control_center/hvs_adapter.py",
    # Stage 5 approval-gated render dispatch: invokes ONLY the existing HVS
    # public render boundary via subprocess.run(list, shell=False, fixed
    # executable, fixed cwd, bounded timeout, no caller-controlled fragments).
    # Pre-existing Stage 5 production code; not introduced by Stage 6.
    "scos/control_center/hvs_render_dispatch.py",
    # Stage 8M approval-gated production-asset materialization: drives the
    # EXISTING HVS `import-media` boundary ONLY via
    # subprocess.run(list, shell=False, fixed executable, fixed cwd,
    # bounded timeout, no caller-controlled fragments). Same safe pattern as
    # hvs_adapter.py / hvs_render_dispatch.py; no render, no network, no
    # shell interpolation. Added alongside Stage 8M implementation.
    "scos/control_center/hvs_production_asset_service.py",
    # Stage 8N approval-gated render dispatch + artifact verification: drives
    # the EXISTING HVS `render-hyperframes` boundary ONLY via
    # subprocess.run(list, shell=False, fixed executable, fixed cwd,
    # bounded timeout, no caller-controlled fragments). FFprobe is also argv
    # list + shell=False + JSON output. Same safe pattern as
    # hvs_adapter.py / hvs_render_dispatch.py / hvs_production_asset_service.py;
    # no render inference from exit code, no network, no shell interpolation.
    # Added alongside the Stage 8N implementation.
    "scos/control_center/hvs_render_completion_service.py",
    "scripts/security_scan_baseline.py",
}
_FRONTEND_FORBIDDEN_TOKENS = (
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
_FRONTEND_PATH_MARKERS = ("route.ts", "middleware.ts")

# Cohort 9A reviewed-safe read-only transport allow-list.
# These specific files implement the ONLY authorized local read-only bridge
# (cohort §8 option 4): a GET-only, same-origin Next.js route handler that
# performs a single fs.readFileSync on a pre-generated committed snapshot
# artifact, plus the frontend adapter that fetches that same-origin route.
# No mutation method, no subprocess, no secret exposure, no external egress.
# The scanner's structural heuristics (frontend_api_route /
# frontend_route_or_middleware / frontend_transport) still flag ANY other new
# transport; only these reviewed paths are exempt.
# Cohort 9A + 9B reviewed same-origin transport allow-list.
# These specific files implement the ONLY authorized local read-only bridges:
#   * Cohort 9A: a GET-only, same-origin Next.js route handler that performs a
#     single fs.readFileSync on a pre-generated committed snapshot artifact,
#     plus the frontend adapter that fetches that same-origin route.
#   * Cohort 9B: a POST-only, same-origin dry-run preview route that returns a
#     deterministic preview produced by the dry-run planner (no subprocess, no
#     HVS, no fs/db write, no external URL), plus the panel component that
#     fetches that exact same-origin route.
# No mutation method, no subprocess, no secret exposure, no external egress.
# The scanner's structural heuristics (frontend_api_route /
# frontend_route_or_middleware / frontend_transport) still flag ANY other new
# transport; only these reviewed paths are exempt, and the transport exemption
# is target-aware (see _FRONTEND_REVIEWED_FETCH_TARGETS below) so an absolute
# or dynamic fetch inside an allowed file is still a finding.
_FRONTEND_READ_ONLY_TRANSPORT_ALLOWLIST = {
    "apps/control-center/app/api/control-center-snapshot/route.ts",
    "apps/control-center/lib/control-center-snapshot.ts",
    "apps/control-center/app/api/operator-dry-run/route.ts",
    "apps/control-center/components/operator-dry-run-panel.tsx",
}

# Exact reviewed same-origin fetch target(s) permitted for each allow-listed
# frontend file. The structural frontend_transport heuristic is exempted ONLY
# when the fetch line references one of these exact fixed relative targets.
# Any other fetch (absolute URL, dynamic host, different route) in the same
# file remains a finding — so a future regression cannot silently open egress.
_FRONTEND_REVIEWED_FETCH_TARGETS = {
    "apps/control-center/lib/control-center-snapshot.ts": ("/api/control-center-snapshot",),
    "apps/control-center/components/operator-dry-run-panel.tsx": ("/api/operator-dry-run",),
}


def _iter_scan_files():
    seen = set()
    roots = []
    if _COMMERCIAL_DIR.is_dir():
        roots.append(("commercial", _COMMERCIAL_DIR))
    if _CONTROL_CENTER_DIR.is_dir():
        roots.append(("control_center", _CONTROL_CENTER_DIR))
    if _SCRIPTS_DIR.is_dir():
        roots.append(("scripts", _SCRIPTS_DIR))
    for scope, root in roots:
        for path in sorted(root.rglob("*.py")):
            if any(part in _SKIP_DIR_NAMES for part in path.parts):
                continue
            if path not in seen:
                seen.add(path)
                yield scope, path
    for name in _ROOT_CONFIG_FILES:
        path = _ROOT / name
        if path.is_file() and path not in seen:
            seen.add(path)
            yield "config", path


def _iter_frontend_files():
    if not _FRONTEND_DIR.is_dir():
        return
    for path in sorted(_FRONTEND_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in _FRONTEND_SUFFIXES:
            continue
        if any(part in _FRONTEND_SKIP_DIR_NAMES for part in path.parts):
            continue
        yield "frontend", path


def _strip_docstrings(text: str) -> str:
    """Mirror the Stage 5 gate's triple-quoted prose filter."""
    return _TRIPLE_QUOTED_RE.sub("", text)


def _line_is_negated(line: str) -> bool:
    lowered = line.lower()
    return any(token in lowered for token in _NEGATION_TOKENS)


def _redact(text: str) -> str:
    flat = " ".join(text.split())
    digest = hashlib.sha256(flat.encode("utf-8")).hexdigest()[:12]
    return f"[REDACTED len={len(flat)} sha256={digest}]"


def _line_no(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _code_lines(text: str):
    for line_no, line in enumerate(_strip_docstrings(text).splitlines(), start=1):
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith("//")
            or stripped.startswith("*")
            or _line_is_negated(stripped)
        ):
            continue
        yield line_no, stripped


def _is_test_path(rel: str) -> bool:
    """Path-based classification of recognized test files.

    Covers tests/, __tests__/, *.test.*, *.spec.*, and the existing test_*
    Python convention. Classification is path-based ONLY — production files
    are never exempted because their contents resemble a test.
    """
    parts = rel.split("/")
    name = Path(rel).name
    if "tests" in parts or "__tests__" in parts:
        return True
    if name.startswith("test_") or name.startswith("test."):
        return True
    if ".test." in name or ".spec." in name:
        return True
    return False


def _is_narrow_synthetic_fixture(rel: str, category: str, text: str) -> bool:
    """Classify exact synthetic test fixtures without broad test exclusions."""
    if not _is_test_path(rel):
        return False
    if (
        rel == "scos/control_center/tests/test_adapter_activation_authorization_validation.py"
        and category == "bearer_or_jwt_token"
        and text == "Bearer " + "abcdefghijklmnop"
    ):
        return True
    lowered = text.lower()
    markers = (
        "cohort9g",
        "do-not-use",
        "synthetic",
        "example.invalid",
        "fake_" + "secret" + "_do_not_use",
    )
    covered = {
        "openai_secret_key",
        "github_token",
        "slack_token",
        "aws_access_key_id",
        "aws_secret_access_key",
        "bearer_or_jwt_token",
        "password_assignment",
        "webhook_or_signing_secret",
        "credential_url",
        "generic_secret_assignment",
        "private_key_header",
    }
    return category in covered and sum(1 for marker in markers if marker in lowered) >= 2


def _append_control_center_findings(findings, rel: str, text: str) -> None:
    runtime_module = not _is_test_path(rel)

    if runtime_module:
        # Only production Control Center modules are subject to the network /
        # AI-dispatch / GUI-automation import screen. Recognized test paths are
        # exempt: their imports (e.g. `socket` used solely to monkeypatch and
        # trap network creation inside a side-effect containment test) are not
        # production execution surfaces. A production socket/requests/urllib/
        # aiohttp/etc. import remains detected because `runtime_module` is True
        # for non-test paths.
        for category, pattern in (
            ("network_library_in_control_center", _CC_NETWORK_IMPORT_RE),
            ("real_ai_dispatch_import", _CC_AI_IMPORT_RE),
            ("browser_gui_clipboard_automation", _CC_GUI_IMPORT_RE),
        ):
            for match in pattern.finditer(text):
                findings.append((rel, _line_no(text, match.start()), category, _redact(match.group(0))))


    for line_no, stripped in _code_lines(text):
        if not runtime_module:
            continue
        if _SUBPROCESS_IMPORT_RE.search(stripped) and rel not in _CONTROL_CENTER_SUBPROCESS_ALLOWLIST:
            findings.append((rel, line_no, "subprocess_outside_allowlist", _redact(stripped)))
        if rel not in _CONTROL_CENTER_SUBPROCESS_ALLOWLIST:
            if (
                _SUBPROCESS_USE_RE.search(stripped)
                or _PTY_IMPORT_RE.search(stripped)
                or _PTY_USE_RE.search(stripped)
            ):
                findings.append((rel, line_no, "shell_or_arbitrary_execution", _redact(stripped)))
        if _W_OS_SYSTEM in stripped or _W_SHELL_TRUE in stripped:
            findings.append((rel, line_no, "shell_or_arbitrary_execution", _redact(stripped)))

        upper = stripped.upper()
        audit_upper = _W_AUDIT_LEDGER.upper()
        if (
            (_W_DELETE in upper and audit_upper in upper)
            or (_W_UPDATE in upper and audit_upper in upper)
            or (_W_DROP in upper and "TABLE" in upper and audit_upper in upper)
        ):
            findings.append((rel, line_no, "destructive_audit_ledger_sql", _redact(stripped)))

        if _W_BIND_ADDR in stripped or _REMOTE_HOST_ASSIGN_RE.search(stripped) or _REMOTE_BIND_RE.search(stripped):
            findings.append((rel, line_no, "remote_bind", _redact(stripped)))


def _append_frontend_findings(findings, rel: str, text: str, path: Path) -> None:
    read_only_transport = rel in _FRONTEND_READ_ONLY_TRANSPORT_ALLOWLIST
    if not read_only_transport:
        if path.name in _FRONTEND_PATH_MARKERS:
            findings.append((rel, 0, "frontend_route_or_middleware", _redact(path.name)))
        if "/app/" in f"/{rel}" and "/api/" in f"{rel}/":
            findings.append((rel, 0, "frontend_api_route", _redact("app/api")))

    for line_no, stripped in _code_lines(text):
        for category, token in _FRONTEND_FORBIDDEN_TOKENS:
            if token not in stripped:
                continue
            # The reviewed same-origin transport is exempt from the structural
            # frontend_transport heuristic ONLY when this file is allow-listed
            # AND the fetch line references its exact reviewed relative target
            # (see _FRONTEND_REVIEWED_FETCH_TARGETS). Every other forbidden-token
            # category (storage, clipboard, polling, nondeterminism,
            # server-action) remains fully active even on the allowed paths, and
            # an absolute URL, dynamic host, or different route in the same file
            # is never exempted — so real regressions are still caught.
            if (
                read_only_transport
                and category == "frontend_transport"
                and rel in _FRONTEND_REVIEWED_FETCH_TARGETS
                and any(t in stripped for t in _FRONTEND_REVIEWED_FETCH_TARGETS[rel])
            ):
                continue
            # Nondeterminism tokens: exempt in recognized test paths only when
            # the test actually mocks the API (existing behavior, unchanged).
            if _is_test_path(rel) and token in (
                _W_DATE_NOW, _W_MATH_RANDOM, _W_CRYPTO_RANDOM_UUID,
            ) and "monkeypatch" in stripped.lower():
                continue
            # Browser-storage tokens: exempt when located in a recognized test
            # path. Test fixtures exercise storage APIs legitimately; production
            # files are never exempted on content resemblance.
            if _is_test_path(rel) and token in (
                _W_LOCAL_STORAGE, _W_SESSION_STORAGE,
            ):
                continue
            findings.append((rel, line_no, category, _redact(stripped)))


def main() -> int:
    print("SECURITY SCAN BASELINE - local static scan (Stage 6.8)")

    findings = []  # (relpath, line_no, category, redacted_sample)
    files_scanned = 0

    for scope, path in list(_iter_scan_files()) + list(_iter_frontend_files() or ()):
        files_scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            rel = path.relative_to(_ROOT).as_posix()
            findings.append((rel, 0, "unreadable_source_file", _redact(str(path.name))))
            continue
        rel = path.relative_to(_ROOT).as_posix()
        for category, pattern_scope, pattern in _PATTERNS:
            if pattern_scope == "commercial" and scope != "commercial":
                continue
            for match in pattern.finditer(text):
                if _is_narrow_synthetic_fixture(rel, category, match.group(0)):
                    continue
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append((rel, line_no, category, _redact(match.group(0))))
        if scope == "control_center":
            _append_control_center_findings(findings, rel, text)
        elif scope == "frontend":
            _append_frontend_findings(findings, rel, text, path)

    # Committed environment-file indicator.
    for env_candidate in sorted(_ROOT.glob(".env*")):
        if env_candidate.is_file() and env_candidate.name != ".env.example":
            findings.append(
                (env_candidate.name, 0, "env_file_present", _redact(env_candidate.name)))

    findings.sort()
    categories = sorted({category for _, _, category, _ in findings})

    print(f"  files scanned : {files_scanned}")
    print(f"  findings      : {len(findings)}")
    print(f"  categories    : {categories if categories else '[]'}")
    for rel, line_no, category, sample in findings:
        print(f"  FINDING  {category}  {rel}:{line_no}  sample={sample}")

    verdict = "PASS" if not findings else "FAIL"
    print(f"SECURITY SCAN: {verdict}")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
