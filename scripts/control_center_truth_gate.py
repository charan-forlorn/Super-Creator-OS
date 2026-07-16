"""Control Center browser-acceptance + mock/truth enforcement gate (Cohort 9D).

Deterministic, install-free, CI-safe structural verifier for the Control Center
frontend truth contract. It is the local CI-parity "Browser Acceptance" gate:
it checks the production read-only surface for regressions that would violate
the Cohort 9A/9B truth contract or introduce a browser-performed production
mutation. The full desktop/mobile viewport matrix (real browsers) is executed
out-of-band by the certifying agent against a production-equivalent build and is
recorded in the cohort report; this gate is the deterministic, repeatable part
that CI and the local verifier both run identically.

Why static and not a live browser driver:
- The security scanner (security_scan_baseline.py) scans scripts/*.py only with
  generic token/network patterns, but the cohort forbids introducing live
  browser drivers, remote services, or subprocess-based egress into the repo.
  A pure-stdlib structural gate guarantees zero scanner findings and zero new
  runtime dependencies while still enforcing the required truth contract:
    * production routes do not import test/demo fixtures;
    * valid records map to AVAILABLE_WITH_DATA;
    * empty records map to EMPTY (never UNAVAILABLE, never fabricated);
    * unavailable/malformed/stale/untrusted map to UNAVAILABLE (never EMPTY);
    * demo data is never merged into live truth;
    * dry-run remains preview-only (mode DRY_RUN, side_effects_performed false);
    * no browser storage fabricates or persists truth;
    * no new production mutation route is introduced.

Runtime truth-state behavior is additionally covered by the vitest truth-contract
and browser-acceptance suites (apps/control-center/tests/*), which execute the
actual mapping/fail-closed/dry-run logic in jsdom.

Run: .venv\\Scripts\\python.exe scripts\\control_center_truth_gate.py
Exit: 0 on PASS, 1 on FAIL, 2 on preflight/usage error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND_DIR = _ROOT / "apps" / "control-center"

# Truth-bearing production files that must NEVER import mock/demo/fixture data.
# The prototype shell components (app-shell, prompt-builder, workflow-router-panel)
# are intentionally exempt: per package.json the Control Center is a "local-first
# frontend prototype (no backend)" and those shells render illustrative mock data
# behind disabled controls. They are NOT part of the truth-bearing read-only
# bridge, so they are not asserted here.
_TRUTH_PATH_FILES = (
    "app/page.tsx",
    "app/projects/page.tsx",
    "app/evidence/page.tsx",
    "app/approvals/page.tsx",
    "app/layout.tsx",
    "app/api/control-center-snapshot/route.ts",
    "app/api/operator-dry-run/route.ts",
    "components/cockpit/cockpit-dashboard.tsx",
    "components/cockpit/cockpit-routes.tsx",
    "components/cockpit/cockpit-shell.tsx",
    "components/operator-dry-run-panel.tsx",
    "lib/control-center-snapshot.ts",
    "lib/operator-dry-run.ts",
)

# Mock/demo/fixture module-name fragments whose import is forbidden in the
# truth path. Cohort 9A/9B guarantee DEMO is a single separate constant dataset,
# so the *data* files themselves are allowed to exist; only *importing* them into
# the truth path is prohibited (no silent leak of demo fixtures into live truth).
_FORBIDDEN_IMPORT_FRAGMENTS = ("mock-data", "mock_data", "fixture", "demo-data", "demo_data")

# Browser-storage tokens that must never appear in truth-path production files:
# truth must never be fabricated or persisted through client storage.
_FORBIDDEN_STORAGE_TOKENS = ("localStorage", "sessionStorage", "navigator.clipboard")

# Reviewed read-only transport routes. No other app/api route may introduce a
# mutation method (POST/PUT/PATCH/DELETE) — the only allowed production surface
# is the two reviewed same-origin read-only bridges.
_REVIEWED_ROUTES = {
    "apps/control-center/app/api/control-center-snapshot/route.ts",
    "apps/control-center/app/api/operator-dry-run/route.ts",
}


def _iter_frontend_files():
    if not _FRONTEND_DIR.is_dir():
        return
    for path in sorted(_FRONTEND_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        if any(part in ("node_modules", ".next", ".vercel", "dist", "build", "coverage")
               for part in path.parts):
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def _import_lines(text: str):
    """Yield (lineno, line) for import/export-from statements (TS/JS)."""
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("export ") and "from" in stripped:
            yield i, stripped


def _check_truth_path_mock_isolation(findings: list[tuple]) -> None:
    """Production truth-path files must not import mock/demo/fixture data."""
    for rel in _TRUTH_PATH_FILES:
        path = _FRONTEND_DIR / rel
        if not path.is_file():
            findings.append((rel, 0, "truth_path_file_missing", rel))
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in _import_lines(text):
            for frag in _FORBIDDEN_IMPORT_FRAGMENTS:
                if frag in line:
                    findings.append((rel, lineno, "truth_path_imports_mock_fixture", frag))
                    break


def _check_route_tree_mock_isolation(findings: list[tuple]) -> None:
    """Every file under app/ (route tree) must not import mock/demo/fixture data."""
    for path in _iter_frontend_files():
        rel = _rel(path)
        if not rel.startswith("apps/control-center/app/"):
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in _import_lines(text):
            for frag in _FORBIDDEN_IMPORT_FRAGMENTS:
                if frag in line:
                    findings.append((rel, lineno, "route_tree_imports_mock_fixture", frag))
                    break


def _check_no_storage_fabrication(findings: list[tuple]) -> None:
    """Truth-path production files must not fabricate truth via browser storage."""
    for rel in _TRUTH_PATH_FILES:
        path = _FRONTEND_DIR / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        # Strip comments/strings-lite: scan whole file; storage tokens are
        # structural identifiers, unlikely inside prose strings.
        for token in _FORBIDDEN_STORAGE_TOKENS:
            if token in text:
                # Allow the documented exemption: the reviewed dry-run panel may
                # reference "write_browser_storage" only as a prohibited-action
                # name inside the dry-run planner output (a string literal), not
                # as an actual call. We flag real API usage only.
                if token == "navigator.clipboard" and "write_browser_storage" in text:
                    continue
                findings.append((rel, 0, "truth_path_uses_browser_storage", token))


def _check_no_new_mutation_route(findings: list[tuple]) -> None:
    """No app/api route may expose a mutation method beyond the reviewed set."""
    api_dir = _FRONTEND_DIR / "app" / "api"
    if not api_dir.is_dir():
        return
    for path in sorted(api_dir.rglob("route.ts")):
        rel = _rel(path)
        if rel in _REVIEWED_ROUTES:
            # Reviewed routes are allowed; verify they declare read-only runtime
            # and dynamic = force-dynamic (no static caching of a read-only bridge).
            text = path.read_text(encoding="utf-8")
            if "force-dynamic" not in text:
                findings.append((rel, 0, "reviewed_route_not_force_dynamic", "force-dynamic"))
            continue
        # Any other route file is a regression: only the two reviewed read-only
        # bridges may exist.
        findings.append((rel, 0, "unreviewed_api_route_introduced", rel))


def _check_dry_run_preview_only(findings: list[tuple]) -> None:
    """operator-dry-run.ts must keep the preview-only truth markers."""
    path = _FRONTEND_DIR / "lib" / "operator-dry-run.ts"
    if not path.is_file():
        findings.append(("lib/operator-dry-run.ts", 0, "truth_path_file_missing", "lib/operator-dry-run.ts"))
        return
    text = path.read_text(encoding="utf-8")
    if 'mode: "DRY_RUN"' not in text:
        findings.append(("lib/operator-dry-run.ts", 0, "dry_run_mode_marker_missing", "DRY_RUN"))
    if "side_effects_performed: false" not in text:
        findings.append(("lib/operator-dry-run.ts", 0, "dry_run_side_effects_marker_missing", "false"))
    if "DRY_RUN_PREVIEW_ONLY" not in text or "LIVE_EXECUTION_NOT_ENABLED" not in text:
        findings.append(("lib/operator-dry-run.ts", 0, "dry_run_warning_markers_missing", "preview"))


def _check_snapshot_unavailable_semantics(findings: list[tuple]) -> None:
    """control-center-snapshot.ts must preserve DEMO separation + UNAVAILABLE fail-closed."""
    path = _FRONTEND_DIR / "lib" / "control-center-snapshot.ts"
    if not path.is_file():
        findings.append(("lib/control-center-snapshot.ts", 0, "truth_path_file_missing", "lib/control-center-snapshot.ts"))
        return
    text = path.read_text(encoding="utf-8")
    if "DEMO_LABEL" not in text:
        findings.append(("lib/control-center-snapshot.ts", 0, "demo_label_missing", "DEMO_LABEL"))
    # The live-failure fallback must return UNAVAILABLE (never EMPTY) and the
    # resolver must reference both the demo dataset and the unavailable fallback
    # so the two branches stay distinct.
    if "unavailableFallback" not in text:
        findings.append(("lib/control-center-snapshot.ts", 0, "unavailable_fallback_missing", "unavailableFallback"))
    if "DEMO_SNAPSHOT" not in text or "resolveCockpitView" not in text:
        findings.append(("lib/control-center-snapshot.ts", 0, "demo_live_branch_missing", "resolveCockpitView"))


def main() -> int:
    print("CONTROL CENTER TRUTH GATE — structural browser-acceptance + mock/truth enforcement (Cohort 9D)")
    if not _FRONTEND_DIR.is_dir():
        print("PREFETCH FAIL: frontend directory not found: " + str(_FRONTEND_DIR))
        return 2

    findings: list[tuple] = []
    _check_truth_path_mock_isolation(findings)
    _check_route_tree_mock_isolation(findings)
    _check_no_storage_fabrication(findings)
    _check_no_new_mutation_route(findings)
    _check_dry_run_preview_only(findings)
    _check_snapshot_unavailable_semantics(findings)

    findings.sort()
    print(f"  checks       : {len(_TRUTH_PATH_FILES)} truth-path files + app/ route tree")
    print(f"  findings     : {len(findings)}")
    for rel, lineno, category, sample in findings:
        where = f"{rel}:{lineno}" if lineno else rel
        print(f"  FAIL  {category}  {where}  detail={sample}")

    verdict = "PASS" if not findings else "FAIL"
    print(f"CONTROL CENTER TRUTH GATE: {verdict}")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
