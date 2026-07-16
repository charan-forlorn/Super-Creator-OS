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
