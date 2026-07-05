"""SCOS release tier — conservative local pre-release check (Stage 4.18).

Orchestrates the local release gate: git working-tree state (report-only),
smoke tier, Stage 4.18 unit suites, representative commercial regression
suites, and the security scan baseline. Subprocess use is limited to local
python test commands and a read-only git status; nothing is committed,
pushed, tagged, or mutated.

Run: .venv\\Scripts\\python.exe scripts\\test_release.py
Exit: 0 when every step passes, 1 otherwise. Output is deterministic
(fixed step order, no timestamps, no durations).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_TEST_STEPS = (
    ("smoke", "scripts/test_smoke.py"),
    ("unit: domain models", "scos/commercial/tests/test_domain_models.py"),
    ("unit: validation", "scos/commercial/tests/test_validation.py"),
    ("unit: manifest tools", "scos/commercial/tests/test_manifest_tools.py"),
    ("regression: report builder", "scos/commercial/tests/test_report_builder.py"),
    ("regression: delivery package", "scos/commercial/tests/test_delivery_package.py"),
    ("regression: cli", "scos/commercial/tests/test_cli.py"),
    ("regression: conversion handoff",
     "scos/commercial/tests/test_first_customer_conversion_handoff.py"),
    ("security scan baseline", "scripts/security_scan_baseline.py"),
)

# TODO(Stage 4.19): extend this gate for final commercial certification:
#   - run the FULL scos/commercial/tests suite, not the representative subset
#   - add the certification tier (determinism / artifact-integrity suites)
#   - verify HEAD == origin/main and current branch policy before release
#   - run the release-provenance checklist from
#     docs/security/SECURITY_HARDENING_BASELINE.md and record the evidence
#   - emit a machine-readable release report artifact for the Stage 5 handoff


def _run(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        args,
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def main() -> int:
    print("RELEASE TIER - conservative local release check (Stage 4.18)")
    results = []

    code, output = _run(["git", "status", "--porcelain"])
    if code != 0:
        results.append(("git working tree state", "FAIL"))
        print("  FAIL  git working tree state (git status unavailable)")
    else:
        dirty = sorted(line for line in output.splitlines() if line.strip())
        status = "PASS" if not dirty else "WARN"
        results.append(("git working tree state", status))
        print(f"  {status:4}  git working tree state ({len(dirty)} dirty path(s); report-only)")
        for line in dirty:
            print(f"          {line}")

    for name, rel_path in _TEST_STEPS:
        script = _ROOT / rel_path
        if not script.is_file():
            results.append((name, "FAIL"))
            print(f"  FAIL  {name} (missing: {rel_path})")
            continue
        code, _output = _run([sys.executable, str(script)])
        status = "PASS" if code == 0 else "FAIL"
        results.append((name, status))
        print(f"  {status:4}  {name} ({rel_path})")

    failed = [name for name, status in results if status == "FAIL"]
    warned = [name for name, status in results if status == "WARN"]
    print(f"\n RESULT: {len(results) - len(failed) - len(warned)} passed, "
          f"{len(warned)} warned, {len(failed)} failed")
    print("RELEASE CHECK: " + ("PASS" if not failed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
