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
