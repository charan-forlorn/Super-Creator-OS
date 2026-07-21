"""Focused tests for the Stage 6.8 security scan baseline."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import scripts.security_scan_baseline as scan


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@contextlib.contextmanager
def _scanner_root(root: Path):
    original = {
        "_ROOT": scan._ROOT,
        "_COMMERCIAL_DIR": scan._COMMERCIAL_DIR,
        "_CONTROL_CENTER_DIR": scan._CONTROL_CENTER_DIR,
        "_FRONTEND_DIR": scan._FRONTEND_DIR,
        "_SCRIPTS_DIR": scan._SCRIPTS_DIR,
    }
    scan._ROOT = root
    scan._COMMERCIAL_DIR = root / "scos" / "commercial"
    scan._CONTROL_CENTER_DIR = root / "scos" / "control_center"
    scan._FRONTEND_DIR = root / "apps" / "control-center"
    scan._SCRIPTS_DIR = root / "scripts"
    try:
        yield
    finally:
        for name, value in original.items():
            setattr(scan, name, value)


def _run_scan(root: Path) -> tuple[int, str]:
    with _scanner_root(root):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = scan.main()
    return code, stream.getvalue()


def test_stage68_clean_fixture_passes_with_policy_false_positives(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(
        root / "scos" / "control_center" / "command_runner.py",
        "import " + ("sub" + "process") + "\n"
        "def run_stub():\n"
        "    return " + ("sub" + "process") + ".run(['echo'], capture_output=True)\n",
    )
    _write(
        root / "scos" / "control_center" / "model.py",
        '"""No socket, no fetch, No WebSocket, no polling."""\nVALUE = 1\n',
    )
    _write(
        root / "apps" / "control-center" / "components" / "safe.tsx",
        "// no " + ("fet" + "ch") + "\n"
        "export const Copy = 'Disabled until later: "
        + ("Web" + "Socket") + ", SSE, polling';\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output


def test_stage68_flags_control_center_and_frontend_forbidden_runtime(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "bad.py", "import " + ("requ" + "ests") + "\n")
    _write(
        root / "apps" / "control-center" / "components" / "bad.tsx",
        "export function Bad() { return " + ("fet" + "ch") + "('/api'); }\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "network_library_in_control_center" in output
    assert "frontend_transport" in output


def test_stage68_frontend_skips_build_outputs_and_flags_api_surface(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "node_modules" / "pkg" / "bad.ts",
        "export const ignored = " + ("fet" + "ch") + "('/ignored');\n",
    )
    _write(root / "apps" / "control-center" / "app" / "api" / "route.ts", "export {}\n")

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_api_route" in output
    assert "frontend_transport" not in output


# ---------------------------------------------------------------------------
# Cohort 9B.1 — focused regression tests for the reviewed dry-run surface
# classification repair.
#
# Positive: the reviewed Cohort 9B dry-run surface (local-only POST route +
# panel's exact same-origin fetch + test-only socket trap) produces ZERO
# findings and a PASS exit.
#
# Negative: unsafe variants across every repaired category remain detected.
# Each negative asserts the specific category that must survive.
# ---------------------------------------------------------------------------

def test_cohort9b_reviewed_dry_run_surface_produces_zero_findings(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    # Reviewed local-only POST dry-run preview route.
    _write(
        root / "apps" / "control-center" / "app" / "api" / "operator-dry-run" / "route.ts",
        'import { NextResponse } from "next/server";\n'
        'export async function POST(request) {\n'
        "  return NextResponse.json({});\n"
        "}\n",
    )
    # Reviewed panel component with the exact same-origin reviewed target.
    _write(
        root / "apps" / "control-center" / "components" / "operator-dry-run-panel.tsx",
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('/api/operator-dry-run', { method: 'POST' });\n"
        "}\n",
    )
    # Test-only socket trap under a recognized Control Center test path.
    _write(
        root / "scos" / "control_center" / "tests" / "test_operator_dry_run.py",
        "import " + ("soc" + "ket") + "\n"
        "def test_trap():\n"
        "    assert " + ("soc" + "ket") + ".socket\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "frontend_api_route" not in output
    assert "frontend_route_or_middleware" not in output
    assert "frontend_transport" not in output
    assert "network_library_in_control_center" not in output


def test_cohort9b_negative_unreviewed_api_route_still_flagged(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    # A different API route must not benefit from the Cohort 9B exemption.
    _write(
        root / "apps" / "control-center" / "app" / "api" / "other-route" / "route.ts",
        "export {}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_api_route" in output


def test_cohort9b_negative_reviewed_route_with_subprocess_remains_detected(tmp_path: Path):
    # The frontend route allow-list must NOT suppress the Control Center
    # subprocess screen. A non-allowlisted Control Center module that imports
    # subprocess (named to evoke a route) must still be flagged.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(
        root / "scos" / "control_center" / "dry_run_route.py",
        "import " + ("sub" + "process") + "\n"
        "def run():\n"
        "    return " + ("sub" + "process") + ".run(['echo'])\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "subprocess_outside_allowlist" in output


def test_cohort9b_negative_external_absolute_fetch_still_flagged(tmp_path: Path):
    # Even inside an allow-listed component, an absolute external URL fetch is
    # not a reviewed target, so it must remain a finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "components" / "operator-dry-run-panel.tsx",
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('https://example.invalid/x');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort9b_negative_dynamic_fetch_target_still_flagged(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "components" / "operator-dry-run-panel.tsx",
        "const target = '/api/operator-dry-run';\n"
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "(target);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort9b_negative_same_origin_to_other_route_still_flagged(tmp_path: Path):
    # Same-origin fetch, allow-listed file, but a DIFFERENT (unreviewed) route
    # target must still be flagged — the transport exemption is target-aware.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "components" / "operator-dry-run-panel.tsx",
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('/api/some-other-route');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort9b_negative_other_component_same_target_still_flagged(tmp_path: Path):
    # The allow-list is exact (path-specific), not a broad fetch-target rule.
    # A non-allow-listed component performing the same reviewed fetch must be
    # flagged.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "components" / "some-other-panel.tsx",
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('/api/operator-dry-run');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort9b_negative_production_socket_import_still_flagged(tmp_path: Path):
    # A production (non-test) Control Center module importing socket must
    # remain detected; only the recognized test-path socket trap is exempt.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(
        root / "scos" / "control_center" / "socket_helper.py",
        "import " + ("soc" + "ket") + "\n"
        "def open_listener():\n"
        "    return " + ("soc" + "ket") + ".socket()\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "network_library_in_control_center" in output


def test_cohort9b_negative_production_requests_import_still_flagged(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(
        root / "scos" / "control_center" / "net_client.py",
        "import " + ("requ" + "ests") + "\n"
        "def get(url):\n"
        "    return " + ("requ" + "ests") + ".get(url)\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "network_library_in_control_center" in output


def test_cohort9g_detects_supported_synthetic_secret_families_with_safe_output(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    secrets = {
        "openai": "sk-" + "A" * 24,
        "github": "gh" + "p_" + "B" * 24,
        "slack": "xo" + "xb-" + "1" * 12 + "-" + "2" * 12,
        "aws_id": "AK" + "IA" + "C" * 16,
        "aws_secret": "aws_" + "secret" + "_access_key = '" + "D" * 40 + "'",
        "bearer": "Bearer " + "E" * 24,
        "jwt": "ey" + "J" + "F" * 18 + "." + "G" * 18 + "." + "H" * 18,
        "private_key": "-----" + "BEGIN" + " PRIVATE" + " KEY-----",
        "password": "pass" + "word = 'cohort9g-do-not-use-password'",
        "webhook": "web" + "hook = 'cohort9g-do-not-use-webhook-secret'",
        "url": "https://user:cohort9g-password@example.invalid/path",
        "generic": "api" + "_key = '" + "I" * 24 + "'",
    }
    _write(
        root / "scripts" / "leaky.py",
        "\n".join(f"{name} = {value!r}" for name, value in secrets.items()) + "\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    for category in (
        "openai_secret_key",
        "github_token",
        "slack_token",
        "aws_access_key_id",
        "aws_secret_access_key",
        "bearer_or_jwt_token",
        "private_key_header",
        "password_assignment",
        "webhook_or_signing_secret",
        "credential_url",
        "generic_secret_assignment",
    ):
        assert category in output
    assert "[REDACTED len=" in output
    for raw in secrets.values():
        assert raw not in output


def test_cohort9g_synthetic_test_fixtures_are_narrowly_classified(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    synthetic = "sk-" + "cohort9g" + "DONOTUSE" + "synthetic"
    _write(
        root / "scripts" / "tests" / "test_fixture.py",
        "TOKEN = '" + synthetic + "'  # synthetic cohort9g do-not-use fixture\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output


def test_cohort9g_production_like_synthetic_secret_is_not_ignored(tmp_path: Path):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    synthetic = "sk-" + "cohort9g" + "DONOTUSE" + "synthetic"
    _write(root / "scripts" / "production_like.py", "TOKEN = '" + synthetic + "'\n")

    code, output = _run_scan(root)

    assert code == 1
    assert "openai_secret_key" in output
    assert synthetic not in output


def test_cohort9g_scanner_read_error_fails_closed(tmp_path: Path, monkeypatch):
    root = tmp_path / "repo"
    leaky = root / "scripts" / "unreadable.py"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(leaky, "VALUE = 1\n")

    original = Path.read_text

    def boom(self, *args, **kwargs):
        if self == leaky:
            raise OSError("cohort9g unreadable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)
    code, output = _run_scan(root)

    assert code == 1
    assert "unreadable_source_file" in output


# ---------------------------------------------------------------------------
# Cohort 10D — focused regression tests for the reviewed bounded child-kill
# `setTimeout` classification repair (scanner de-obfuscation + narrow
# exemption). Adds `scripts/security_scan_baseline.py` beyond the 14 Cohort
# paths. The exemption is per-call-site on exactly two reviewed bridge files
# and ONLY for a `setTimeout` whose body kills the owned child; setInterval and
# any other `setTimeout` (polling/retry/refresh) stays a finding. The literal
# `setTimeout` is the only accepted spelling; lexical splits are a finding.
# ---------------------------------------------------------------------------

_BRIDGE_TS = "apps/control-center/lib/hvs-materialization-store.ts"
_BRIDGE_TEST = "apps/control-center/tests/hvs-materialization-store.test.ts"


def test_cohort10d_approved_bounded_childkill_timeout_is_exempt(tmp_path: Path):
    # The exact reviewed Cohort 10D transport pattern (literal setTimeout,
    # body kills the owned child) must NOT be a finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "import { spawn } from 'node:child_process';\n"
        "export function guard(child: any): void {\n"
        "  const timer = setTimeout(() => {\n"
        "    if (child && !child.killed) { try { child.kill('SIGKILL'); } catch {} }\n"
        "  }, 30000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "frontend_polling" not in output


def test_cohort10d_unapproved_setTimeout_second_site_in_same_file_flagged(tmp_path: Path):
    # The exemption is call-site specific. A second `setTimeout` in the same
    # reviewed file that does NOT kill the owned child (here a refresh/again
    # pattern) must remain a frontend_polling finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "import { spawn } from 'node:child_process';\n"
        "export function guard(child: any): void {\n"
        "  const timer = setTimeout(() => {\n"
        "    if (child && !child.killed) { try { child.kill('SIGKILL'); } catch {} }\n"
        "  }, 30000);\n"
        "  setTimeout(() => { refresh(); again(); }, 5000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_polling" in output


def test_cohort10d_setInterval_in_bridge_file_still_flagged(tmp_path: Path):
    # setInterval is never exempted (no browser polling allowed from a
    # server-side bridge file either).
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "export function poll(): void {\n"
        "  setInterval(() => { healthCheck(); }, 1000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_polling" in output


def test_cohort10d_setTimeout_outside_bridge_files_still_flagged(tmp_path: Path):
    # The exemption is restricted to the two reviewed bridge files. An identical
    # bounded child-kill setTimeout in any OTHER frontend file is still a
    # finding (no broad path/file token allowlist was added).
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "lib" / "other-bridge.ts",
        "export function guard(child: any): void {\n"
        "  const timer = setTimeout(() => {\n"
        "    if (child && !child.killed) { try { child.kill('SIGKILL'); } catch {} }\n"
        "  }, 30000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_polling" in output


def test_cohort10d_obfuscated_timer_spelling_is_a_finding(tmp_path: Path):
    # Lexical splits of the timer primitive (the original defect) must now be a
    # finding named exactly, so it can never silently pass the scanner again.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "const schedule = (globalThis as any)['set' + 'Timeout'] as any;\n"
        "export function guard(child: any): void {\n"
        "  const timer = schedule(() => { child.kill('SIGKILL'); }, 30000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "obfuscated_timer_primitive" in output


def test_cohort10d_transport_and_storage_rules_unchanged(tmp_path: Path):
    # Transport (fetch) and browser-storage rules must remain fully active,
    # including inside the reviewed bridge files.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "export function load() {\n"
        "  const x = " + ("fet" + "ch") + "('/api/x');\n"
        "  const y = " + ("local" + "Storage") + ".getItem('k');\n"
        "  const z = " + ("set" + "Interval") + "(() => {}, 1000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output
    assert "frontend_storage" in output
    assert "frontend_polling" in output


def test_cohort10d_no_broad_path_exemption_added(tmp_path: Path):
    # Negative: a broad path/file-level token allowlist was NOT added. Prove a
    # generic dangerous frontend-runtime token (WebSocket) inside a reviewed
    # bridge file is still caught by its normal category.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRIDGE_TS,
        "export function connect(): void {\n"
        "  const ws = new " + ("Web" + "Socket") + "('wss://example.invalid');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10d_full_scanner_zero_findings_on_repo_final_bytes(tmp_path: Path):
    # Integration: the live repo root must scan clean (0 findings) with the new
    # classification. Uses the real sorted list of scanned files invariant.
    root = Path(__file__).resolve().parents[2]
    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "SECURITY SCAN: PASS" in output


# ---------------------------------------------------------------------------
# Cohort 10E — focused regression tests for the reviewed Brand Kit + controlled
# export-stub transport classification repair.
#
# Root cause: these four Cohort 10E files are bounded, same-origin, fail-closed
# transports (no HVS init, no render, no external network, no browser storage,
# no memory/database.json mutation) but were missing from the reviewed
# allow-lists, so the structural heuristics flagged them. Repair = register the
# exact reviewed route paths + client files + their exact same-origin fetch
# targets (the documented narrow mechanism, identical to 10C/10D). No frontend
# code changed.
#
# Positive: the reviewed Cohort 10E surface produces ZERO findings.
# Negative: unreviewed/target-mismatched variants remain detected (the
# exemption is path-specific AND target-aware, so no broad allowlist was added).
# ---------------------------------------------------------------------------

_BRAND_KIT_ROUTE = "apps/control-center/app/api/brand-kit/route.ts"
_BRAND_KIT_CLIENT = "apps/control-center/lib/brand-kit-client.ts"
_EXPORT_ROUTE = "apps/control-center/app/api/hvs-render/export/route.ts"
_EXPORT_CLIENT = "apps/control-center/lib/hvs-render-client.ts"


def test_cohort10e_reviewed_brand_kit_and_export_surface_produces_zero_findings(
    tmp_path: Path,
):
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    # Reviewed Brand Kit route (GET read + POST upsert, fail-closed).
    _write(
        root / _BRAND_KIT_ROUTE,
        "import { NextResponse } from 'next/server';\n"
        "export const dynamic = 'force-dynamic';\n"
        "export async function GET() { return NextResponse.json({}); }\n"
        "export async function POST() { return NextResponse.json({}); }\n",
    )
    # Reviewed Brand Kit client fetching the exact same-origin reviewed target.
    _write(
        root / _BRAND_KIT_CLIENT,
        "export function useBrandKit() {\n"
        "  return " + ("fet" + "ch") + "('/api/brand-kit', { method: 'GET' });\n"
        "}\n",
    )
    # Reviewed controlled export stub route (fail-closed).
    _write(
        root / _EXPORT_ROUTE,
        "import { NextResponse } from 'next/server';\n"
        "export const dynamic = 'force-dynamic';\n"
        "export async function POST() { return NextResponse.json({}); }\n",
    )
    # Reviewed HVS render client exporting via the exact reviewed target.
    _write(
        root / _EXPORT_CLIENT,
        "export async function exportRenderArtifact() {\n"
        "  return " + ("fet" + "ch") + "('/api/hvs-render/export', { method: 'POST' });\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "frontend_api_route" not in output
    assert "frontend_route_or_middleware" not in output
    assert "frontend_transport" not in output


def test_cohort10e_negative_unreviewed_api_route_still_flagged(tmp_path: Path):
    # A different (unreviewed) API route must not benefit from the Cohort 10E
    # exemption.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(root / "apps" / "control-center" / "app" / "api" / "other-route" / "route.ts", "export {}\n")

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_api_route" in output


def test_cohort10e_negative_export_client_absolute_fetch_still_flagged(tmp_path: Path):
    # Even inside the allow-listed export client, an absolute external URL is
    # not a reviewed target, so it must remain a finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _EXPORT_CLIENT,
        "export async function exportRenderArtifact() {\n"
        "  return " + ("fet" + "ch") + "('https://example.invalid/x');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10e_negative_brand_kit_client_other_target_still_flagged(tmp_path: Path):
    # Same-origin fetch in the allow-listed Brand Kit client, but a DIFFERENT
    # (unreviewed) route prefix must still be flagged — target-aware exemption.
    # Uses a prefix that does NOT contain the reviewed '/api/brand-kit' string.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _BRAND_KIT_CLIENT,
        "export function useBrandKit() {\n"
        "  return " + ("fet" + "ch") + "('/api/x-brand-kit/other');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10e_negative_other_client_same_export_target_still_flagged(tmp_path: Path):
    # The allow-list is path-specific: a non-allow-listed client performing the
    # same reviewed export fetch must be flagged.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "lib" / "some-other-client.ts",
        "export async function go() {\n"
        "  return " + ("fet" + "ch") + "('/api/hvs-render/export');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


# ---------------------------------------------------------------------------
# Cohort 10G — focused regression tests for the reviewed golden-render
# execution-boundary classification repair.
#
# Root cause: the Cohort 10G files (golden-render execute route, panel, TS
# bridge store, and Python orchestration service) are bounded, same-origin,
# fail-closed, operator-authorized HVS render transports (no external network,
# no browser storage, no memory/database.json mutation) but were missing from
# the reviewed allow-lists, so the structural heuristics flagged them. Repair =
# register the exact reviewed route/panel/store paths + the exact same-origin
# fetch target + the Python service in the subprocess allow-list (the
# documented narrow mechanism, identical to 10D/10E). No frontend/product code
# changed.
#
# Positive: the reviewed Cohort 10G surface produces ZERO findings.
# Negative: unsafe variants across every repaired category remain detected
# (shell=True, command string, browser-controlled executable, unbounded
# transport); the exemption is path-specific AND target-aware, so no broad
# allowlist was added. Existing 10D/10E classifications remain valid.
# ---------------------------------------------------------------------------

_GOLDEN_ROUTE = "apps/control-center/app/api/golden-render/execute/route.ts"
_GOLDEN_PANEL = "apps/control-center/components/golden-render-panel.tsx"
_GOLDEN_STORE = "apps/control-center/lib/golden-render-store.ts"
_GOLDEN_SERVICE = "scos/control_center/hvs_golden_render_service.py"


def test_cohort10g_reviewed_golden_render_surface_produces_zero_findings(
    tmp_path: Path,
):
    # The exact reviewed Cohort 10G surface: local POST execute route (strict
    # ALLOWED_FIELDS validation) + panel's exact same-origin fetch + TS bridge
    # store (bounded child-kill setTimeout) + Python orchestration service
    # (subprocess.run list, shell=False, bounded timeout). Must yield 0
    # findings.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_ROUTE,
        "import { NextResponse } from 'next/server';\n"
        "export const dynamic = 'force-dynamic';\n"
        "export async function POST() { return NextResponse.json({}); }\n",
    )
    _write(
        root / _GOLDEN_PANEL,
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('/api/golden-render/execute', { method: 'POST' });\n"
        "}\n",
    )
    _write(
        root / _GOLDEN_STORE,
        "import { spawn } from 'node:child_process';\n"
        "export function guard(child: any): void {\n"
        "  const timer = setTimeout(() => {\n"
        "    if (child && !child.killed) { try { child.kill('SIGKILL'); } catch {} }\n"
        "  }, 30000);\n"
        "}\n",
    )
    _write(
        root / _GOLDEN_SERVICE,
        "import " + ("sub" + "process") + "\n"
        "def run():\n"
        "    return " + ("sub" + "process") + ".run("
        "['python', '-m', 'scos.control_center.hvs_golden_render_cli', 'execute'],\n"
        "        cwd='/trusted/hvs', shell=False, timeout=600)\n",
    )

    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "frontend_api_route" not in output
    assert "frontend_route_or_middleware" not in output
    assert "frontend_transport" not in output
    assert "subprocess_outside_allowlist" not in output
    assert "shell_or_arbitrary_execution" not in output


def test_cohort10g_negative_unreviewed_api_route_still_flagged(tmp_path: Path):
    # A different (unreviewed) API route must not benefit from the Cohort 10G
    # exemption.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(root / "apps" / "control-center" / "app" / "api" / "other-route" / "route.ts", "export {}\n")

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_api_route" in output


def test_cohort10g_negative_service_shell_true_still_flagged(tmp_path: Path):
    # A Cohort 10G-equivalent service that uses shell=True must remain a
    # finding — the subprocess allow-list does NOT suppress shell=True.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_SERVICE,
        "import " + ("sub" + "process") + "\n"
        "def run():\n"
        "    return " + ("sub" + "process") + ".run('python -m pkg execute', shell=True)\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "shell_or_arbitrary_execution" in output


def test_cohort10g_negative_panel_external_absolute_fetch_still_flagged(tmp_path: Path):
    # Even inside the allow-listed panel, an absolute external URL fetch is not
    # a reviewed target, so it must remain a finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_PANEL,
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('https://example.invalid/x');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10g_negative_panel_dynamic_fetch_target_still_flagged(tmp_path: Path):
    # Same-origin fetch in the allow-listed panel, but a DIFFERENT (unreviewed)
    # route target must still be flagged — the transport exemption is
    # target-aware.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_PANEL,
        "const target = '/api/golden-render/execute';\n"
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "(someOtherRoute);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10g_negative_other_component_same_target_still_flagged(tmp_path: Path):
    # The allow-list is path-specific: a non-allow-listed component performing
    # the same reviewed fetch must be flagged.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / "apps" / "control-center" / "components" / "some-other-panel.tsx",
        "export function Panel() {\n"
        "  return " + ("fet" + "ch") + "('/api/golden-render/execute');\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_transport" in output


def test_cohort10g_negative_store_unbounded_polling_setTimeout_still_flagged(
    tmp_path: Path,
):
    # The bridge-timeout exemption is call-site specific. A second setTimeout in
    # the reviewed store file that does NOT kill the owned child (refresh/again
    # pattern) must remain a frontend_polling finding.
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_STORE,
        "import { spawn } from 'node:child_process';\n"
        "export function guard(child: any): void {\n"
        "  const timer = setTimeout(() => {\n"
        "    if (child && !child.killed) { try { child.kill('SIGKILL'); } catch {} }\n"
        "  }, 30000);\n"
        "  setTimeout(() => { refresh(); again(); }, 5000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_polling" in output


def test_cohort10g_negative_store_setInterval_still_flagged(tmp_path: Path):
    # setInterval is never exempted (no browser polling from a bridge file).
    root = tmp_path / "repo"
    _write(root / "scos" / "commercial" / "safe.py", "VALUE = 1\n")
    _write(root / "scripts" / "safe.py", "VALUE = 1\n")
    _write(root / "scos" / "control_center" / "safe.py", "VALUE = 1\n")
    _write(
        root / _GOLDEN_STORE,
        "export function poll(): void {\n"
        "  setInterval(() => { healthCheck(); }, 1000);\n"
        "}\n",
    )

    code, output = _run_scan(root)

    assert code == 1
    assert "frontend_polling" in output


def test_cohort10g_full_scanner_zero_findings_on_repo_final_bytes(tmp_path: Path):
    # Integration: the live repo root must scan clean (0 findings) with the
    # Cohort 10G classification registered. Uses the real sorted list of
    # scanned files invariant.
    root = Path(__file__).resolve().parents[2]
    code, output = _run_scan(root)

    assert code == 0
    assert "findings      : 0" in output
    assert "SECURITY SCAN: PASS" in output
