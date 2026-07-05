"""SCOS security scan baseline — local static scan only (Stage 4.18).

Scans commercial executable source, the scripts directory, and root config
files for suspicious patterns: credential/token indicators, money-provider
imports, network libraries inside commercial source, external-service
behavior indicators, committed environment files, and private key headers.

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
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_COMMERCIAL_DIR = _ROOT / "scos" / "commercial"
_SCRIPTS_DIR = _ROOT / "scripts"
_ROOT_CONFIG_FILES = ("requirements.txt", "conftest.py")

_SKIP_DIR_NAMES = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

_REDACT_KEEP = 12

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
_W_AKIA = "AK" + "IA"
_W_GHP = "gh" + "p_"
_W_XOX = "xo" + "x"
_W_SK = "sk" + "-"
_W_API_KEY = "api" + "_key"
_W_TOKEN = "tok" + "en"
_W_SECRET = "sec" + "ret"
_W_BEGIN = "-----" + "BEGIN"
_W_PRIVATE_KEY = "PRIVATE" + " KEY"

_PATTERNS = (
    # (category, scope, compiled regex)
    ("token_indicator", "all", re.compile(_W_AKIA + r"[0-9A-Z]{16}")),
    ("token_indicator", "all", re.compile(_W_GHP + r"[A-Za-z0-9]{20,}")),
    ("token_indicator", "all", re.compile(_W_XOX + r"[baprs]-[A-Za-z0-9-]{10,}")),
    ("token_indicator", "all", re.compile(r"\b" + _W_SK + r"[A-Za-z0-9]{20,}\b")),
    ("token_indicator", "all", re.compile(
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


def _iter_scan_files():
    seen = set()
    roots = []
    if _COMMERCIAL_DIR.is_dir():
        roots.append(("commercial", _COMMERCIAL_DIR))
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


def _redact(text: str) -> str:
    flat = " ".join(text.split())
    if len(flat) <= _REDACT_KEEP:
        return flat + "***"
    return flat[:_REDACT_KEEP] + "***"


def main() -> int:
    print("SECURITY SCAN BASELINE - local static scan (Stage 4.18)")

    findings = []  # (relpath, line_no, category, redacted_sample)
    files_scanned = 0

    for scope, path in _iter_scan_files():
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
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append((rel, line_no, category, _redact(match.group(0))))

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
