"""test_stage5_final_certification.py - SCOS Stage 5.10 final certification suite.

Plain executable script (no pytest). Exercises the Stage 5 final AI Command
Center certification gate against small synthetic fixture repos (never
against mutable real-repo state, except one read-only integration pass at
the end). Every fixture lives under a TemporaryDirectory; no committed
artifact is mutated.

Run: python scos/control_center/tests/test_stage5_final_certification.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
_ROOT = _HERE.parents[2]

sys.path.insert(0, str(_PACKAGE))

from stage5_certification_models import (  # noqa: E402
    Stage5FinalCertificationError,
    Stage5FinalCertificationResult,
)
from stage5_final_certification import (  # noqa: E402
    _ALLOWLISTED_SUBPROCESS_MODULE,
    _OWN_MODULES,
    _STAGE5_HANDOFF_DOC,
    _STAGE6_HANDOFF_DOC,
    _STAGE_ARTIFACTS,
    run_stage5_final_certification,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-06T00:00:00Z"
_OUTPUT_NAME = "stage5_final_certification.json"
_PASS_SCRIPT = "import sys\nprint('STUB: PASS')\nsys.exit(0)\n"


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _stub_module(stage_label: str, extra_body: str = "") -> str:
    return f'"""SCOS Stage {stage_label} stub module."""\n\n{extra_body}'


def _make_fixture_repo(root: Path) -> Path:
    """Build a synthetic repo that passes every Stage 5.1-5.9 artifact check."""
    lazy_exports: dict[str, str] = {}
    for entry in _STAGE_ARTIFACTS:
        stage = entry["stage"]
        for module_name in entry["modules"]:
            body = ""
            if module_name == _ALLOWLISTED_SUBPROCESS_MODULE:
                body = (
                    "import subprocess\n\n"
                    "def run_stub():\n"
                    "    return subprocess.run(['echo', 'hi'], capture_output=True, "
                    "text=True, timeout=5)\n"
                )
            _write(root / "scos" / "control_center" / f"{module_name}.py",
                   _stub_module(stage, body))
            marker = f"{module_name.upper()}_MARKER"
            lazy_exports[marker] = module_name
            _write(root / "scos" / "control_center" / f"{module_name}.py",
                   _stub_module(stage, body) + f"{marker} = 1\n")
        for test_file in entry["tests"]:
            _write(root / "scos" / "control_center" / "tests" / test_file,
                   _PASS_SCRIPT)
        _write(root / entry["cert_doc"],
               f"# Stage {stage} plan stub\n\nFollows Stage 5.{int(stage.split('.')[1]) - 1}.\n"
               if stage != "5.1" else f"# Stage {stage} plan stub\n")
        for spec_doc in entry["spec_docs"]:
            _write(root / spec_doc, "# stub contract doc\n")
        for component in entry["frontend_components"]:
            if component in ("app-shell.tsx", "sidebar.tsx"):
                continue
            _write(root / "apps" / "control-center" / "components" / component,
                   "// stub component\nexport function Stub() { return null }\n")
        for lib_file in entry["frontend_lib"]:
            _write(root / "apps" / "control-center" / "lib" / lib_file,
                   "// stub mock data\nexport const STUB = {}\n")

    init_lines = "\n".join(f'    "{k}": "{v}",' for k, v in lazy_exports.items())
    _write(root / "scos" / "control_center" / "__init__.py",
           f'"""stub package."""\n\n_LAZY_EXPORTS = {{\n{init_lines}\n}}\n')

    app_shell_imports = "\n".join(
        f'import "./{c[:-4]}"' for entry in _STAGE_ARTIFACTS
        for c in entry["frontend_components"] if c not in ("app-shell.tsx", "sidebar.tsx")
    )
    _write(root / "apps" / "control-center" / "components" / "app-shell.tsx",
           f"// stub app shell\n{app_shell_imports}\n")
    nav_entries = "\n".join(
        f'  {{ id: "{c.replace(".tsx", "").replace("-panel", "")}" }},'
        for entry in _STAGE_ARTIFACTS
        for c in entry["frontend_components"] if c not in ("app-shell.tsx", "sidebar.tsx")
    )
    _write(root / "apps" / "control-center" / "components" / "sidebar.tsx",
           f"// stub sidebar\nconst NAV_SECTIONS = [\n{nav_entries}\n]\n")
    _write(root / "apps" / "control-center" / "README.md",
           "# Control Center\n\n## Overview\n\nStub readme.\n")
    _write(root / "apps" / "control-center" / "package.json",
           json.dumps({"scripts": {"dev": "next dev", "build": "next build",
                                    "start": "next start", "lint": "eslint ."}}))

    _write(root / _STAGE5_HANDOFF_DOC, "# stub Stage 5 handoff\n\nEnds at Gate 5.E.\n")
    _write(root / _STAGE6_HANDOFF_DOC, "# stub Stage 6 handoff\n")
    _write(root / "scripts" / "test_smoke.py", _PASS_SCRIPT)
    _write(root / "scripts" / "security_scan_baseline.py", _PASS_SCRIPT)
    return root


def _run_gate(root, **kwargs):
    kwargs.setdefault("checked_at", _NOW)
    kwargs.setdefault("require_clean_git", False)
    kwargs.setdefault("run_smoke", False)
    kwargs.setdefault("run_security_scan", False)
    kwargs.setdefault("run_frontend_checks", False)
    return run_stage5_final_certification(repo_root=root, **kwargs)


def _check_by_name(result, name):
    return [c for c in result.checks if c.check_name == name]


def test_input_validation(tmp: Path):
    print("\n[01-05] input validation")
    r = _run_gate(tmp / "missing-repo")
    check("missing repo_root -> INPUT_NOT_FOUND",
          isinstance(r, Stage5FinalCertificationError) and r.error_kind == "INPUT_NOT_FOUND")
    r = _run_gate("")
    check("empty repo_root -> INVALID_ARGUMENTS",
          isinstance(r, Stage5FinalCertificationError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate("https://example.test/repo")
    check("URL repo_root rejected",
          isinstance(r, Stage5FinalCertificationError) and r.error_kind == "INVALID_ARGUMENTS")
    fixture = _make_fixture_repo(tmp / "fx-input")
    r = _run_gate(fixture, checked_at="")
    check("empty checked_at rejected",
          isinstance(r, Stage5FinalCertificationError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate(fixture, output_path="https://example.test/out.json")
    check("URL output_path rejected",
          isinstance(r, Stage5FinalCertificationError) and r.error_kind == "INVALID_ARGUMENTS")


def test_certification_id(tmp: Path):
    print("\n[06] certification_id derivation")
    fixture = _make_fixture_repo(tmp / "fx-id")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("id deterministic across runs", r1.certification_id == r2.certification_id)
    check("id has s5c- prefix", r1.certification_id.startswith("s5c-"))
    r3 = _run_gate(fixture, checked_at="2026-07-07T00:00:00Z")
    check("id changes with checked_at", r3.certification_id != r1.certification_id)


def test_go_on_complete_fixture(tmp: Path):
    print("\n[07] GO on complete fixture")
    fixture = _make_fixture_repo(tmp / "fx-go")
    r = _run_gate(fixture, run_smoke=True, run_security_scan=True)
    check("complete fixture -> GO", isinstance(r, Stage5FinalCertificationResult)
          and r.go_no_go == "GO")
    check("GO closes stage", r.stage_closed is True and r.accepted is True)
    check("GO has zero error/critical blockers",
          not any(b.severity in ("error", "critical") for b in r.blockers))


def test_no_go_on_missing_artifact(tmp: Path):
    print("\n[08] NO_GO on missing artifact")
    fixture = _make_fixture_repo(tmp / "fx-missing")
    (fixture / _STAGE_ARTIFACTS[6]["spec_docs"][0]).unlink()
    r = _run_gate(fixture)
    check("missing Stage 5.7 spec doc -> NO_GO", r.go_no_go == "NO_GO")
    check("specific check failed",
          _check_by_name(r, "validate_stage5_7_artifacts")[0].status == "failure")
    check("blocker recorded", any(b.blocker_id == "blk-stage5-7-artifacts" for b in r.blockers))


def test_fragmentation_negated_heading(tmp: Path):
    print("\n[08b] fragmentation scan respects negated headings")
    fixture = _make_fixture_repo(tmp / "fx-frag")
    boundary = fixture / "docs" / "specification" / "STAGE6_SCOPE_BOUNDARY.md"
    _write(boundary,
           "# Stage 6 Scope Boundary\n\n## Forbidden Scope\n\n"
           "- Stage 5.11+ or Stage 4.20+ markers; reopening closed stages.\n")
    r = _run_gate(fixture)
    check("prohibition bullet under forbidden heading is not a finding",
          _check_by_name(r, "validate_no_stage5_11_plus")[0].status == "success")
    _write(boundary,
           "# Stage 6 Scope Boundary\n\n## Upcoming Work\n\n"
           "- Stage 5.11 packet router plan.\n")
    r2 = _run_gate(fixture)
    check("planned Stage 5.11 work under neutral heading still flagged",
          _check_by_name(r2, "validate_no_stage5_11_plus")[0].status == "failure")


def test_stage5_6_gap_reproduction(tmp: Path):
    print("\n[09] Stage 5.6 known-gap fixture")
    fixture = _make_fixture_repo(tmp / "fx-56-gap")
    cc_dir = fixture / "scos" / "control_center"
    # Remove the Stage 5.6 lazy-export coverage and docstring convention.
    init_text = (cc_dir / "__init__.py").read_text(encoding="utf-8")
    lines = [
        line for line in init_text.splitlines()
        if not any(f'"{m}"' in line for m in _STAGE_ARTIFACTS[5]["modules"])
    ]
    (cc_dir / "__init__.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for module_name in _STAGE_ARTIFACTS[5]["modules"]:
        _write(cc_dir / f"{module_name}.py", "# no stage docstring here\nX = 1\n")
    # Introduce the real duplicate-key defect.
    init_text = (cc_dir / "__init__.py").read_text(encoding="utf-8")
    init_text = init_text.replace(
        "_LAZY_EXPORTS = {\n",
        '_LAZY_EXPORTS = {\n    "DUP_KEY": "command_models",\n    "DUP_KEY": "operator_execution_models",\n',
    )
    (cc_dir / "__init__.py").write_text(init_text, encoding="utf-8")
    r = _run_gate(fixture)
    check("Stage 5.6 artifact check fails", _check_by_name(r, "validate_stage5_6_artifacts")[0].status == "failure")
    check("duplicate key check fails",
          _check_by_name(r, "validate_init_no_duplicate_lazy_export_keys")[0].status == "failure")
    check("overall verdict NO_GO", r.go_no_go == "NO_GO")


def test_output_artifact(tmp: Path):
    print("\n[10-11] output artifact")
    fixture = _make_fixture_repo(tmp / "fx-out")
    out_file = tmp / "out" / "cert.json"
    r = _run_gate(fixture, output_path=out_file)
    check("output file written", out_file.is_file())
    check("result records output_path", r.output_path == str(out_file))
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    check("output JSON has required top-level keys",
          {"ok", "certification_id", "go_no_go", "readiness_score", "checks",
           "blockers", "stage6_handoff_items"}.issubset(payload.keys()))
    first_bytes = out_file.read_bytes()
    _run_gate(fixture, output_path=out_file)
    check("re-run output byte-identical", out_file.read_bytes() == first_bytes)
    check("LF only + trailing newline",
          b"\r\n" not in first_bytes and first_bytes.endswith(b"\n"))
    no_out = _make_fixture_repo(tmp / "fx-no-out")
    r = _run_gate(no_out)
    check("output_path=None writes nothing",
          r.output_path is None and list(no_out.rglob(_OUTPUT_NAME)) == [])


def test_safety_scan_catches_injections(tmp: Path):
    print("\n[12-13] safety scan catches injected forbidden tokens")
    fixture = _make_fixture_repo(tmp / "fx-inject")
    _write(fixture / "apps" / "control-center" / "components" / "evil.tsx",
           "export function Evil() { fetch('https://example.test'); return null }\n")
    _write(fixture / "scos" / "control_center" / "evil_module.py",
           "import requests\n")
    r = _run_gate(fixture)
    check("injected fetch( caught",
          any(f["token"] == "fetch(" for c in _check_by_name(r, "validate_frontend_forbidden_tokens")
              for f in c.metadata.to_dict().get("findings", [])))
    check("injected foreign subprocess/requests import caught",
          _check_by_name(r, "validate_backend_forbidden_tokens")[0].status == "failure")
    check("verdict NO_GO", r.go_no_go == "NO_GO")


def test_command_runner_subprocess_allowlist(tmp: Path):
    print("\n[14-15] command_runner subprocess allowlist")
    fixture = _make_fixture_repo(tmp / "fx-allowlist")
    r = _run_gate(fixture)
    check("legitimate shell=False subprocess usage passes",
          _check_by_name(r, "validate_subprocess_allowlist_exception")[0].status == "success")
    bad = _make_fixture_repo(tmp / "fx-allowlist-bad")
    _write(bad / "scos" / "control_center" / f"{_ALLOWLISTED_SUBPROCESS_MODULE}.py",
           _stub_module("5.1", "import subprocess\n\n"
                        "def run_stub():\n"
                        "    return subprocess.run(['echo'], shell=True)\n"))
    r = _run_gate(bad)
    check("shell=True usage fails the allowlist check",
          _check_by_name(r, "validate_subprocess_allowlist_exception")[0].status == "failure")
    check("shell=True -> critical blocker + NO_GO",
          any(b.blocker_id == "blk-subprocess-allowlist" and b.severity == "critical"
              for b in r.blockers) and r.go_no_go == "NO_GO")


def test_stage6_handoff_items(tmp: Path):
    print("\n[16] Stage 6 handoff items deterministic")
    fixture = _make_fixture_repo(tmp / "fx-handoff")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("8-12 handoff items generated", 8 <= len(r1.stage6_handoff_items) <= 12)
    check("handoff items deterministic across runs",
          [i.to_dict() for i in r1.stage6_handoff_items]
          == [i.to_dict() for i in r2.stage6_handoff_items])
    categories = {i.category for i in r1.stage6_handoff_items}
    check("handoff covers the known Stage 5.6 defects",
          {"technical_debt", "frontend", "control_center_backend"} <= categories)
    missing_doc = _make_fixture_repo(tmp / "fx-handoff-missing")
    (missing_doc / _STAGE6_HANDOFF_DOC).unlink()
    r = _run_gate(missing_doc)
    check("missing Stage 6 handoff doc -> failure + blocker",
          _check_by_name(r, "validate_stage6_handoff_doc_exists")[0].status == "failure"
          and any(b.blocker_id == "blk-stage6-handoff-doc" for b in r.blockers))


def test_no_mutation(tmp: Path):
    print("\n[17] no mutation of inspected files")
    import hashlib
    fixture = _make_fixture_repo(tmp / "fx-mutate")
    before = {
        str(p.relative_to(fixture)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(fixture.rglob("*")) if p.is_file()
    }
    _run_gate(fixture)
    after = {
        str(p.relative_to(fixture)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(fixture.rglob("*")) if p.is_file()
    }
    check("fixture tree unchanged after gate run", before == after)


def test_static_boundaries():
    print("\n[18-19] static boundary scan of the Stage 5.10 modules themselves")
    gate_src = (_PACKAGE / "stage5_final_certification.py").read_text(encoding="utf-8")
    models_src = (_PACKAGE / "stage5_certification_models.py").read_text(encoding="utf-8")
    combined = gate_src + models_src
    for token in ("uuid.uuid4", "random.", "datetime.now", "date.today", "time.time"):
        check(f"no non-determinism token '{token}'", token not in combined)
    check("models module stays subprocess-free", "subprocess" not in models_src)
    check("models module never imports scos.commercial",
          "import scos.commercial" not in models_src and "from scos.commercial" not in models_src
          and "from .commercial" not in models_src)
    check("gate module never imports scos.commercial",
          "import scos.commercial" not in gate_src and "from scos.commercial" not in gate_src
          and "from .commercial" not in gate_src)


def test_package_import_safe():
    print("\n[20] __init__ lazy export preserved")
    import subprocess
    code = (
        "import scos.control_center as c\n"
        "assert callable(c.run_stage5_final_certification)\n"
        "assert c.STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION == 1\n"
        "assert callable(c.approve_command)\n"
        "assert 'run_stage5_final_certification' in c.__all__\n"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(_ROOT))
    check("import scos.control_center exposes Stage 5.10 lazily",
          proc.returncode == 0)


def test_real_repo_readonly():
    print("\n[21] optional read-only integration pass over the real repo")
    r = run_stage5_final_certification(
        repo_root=_ROOT, checked_at=_NOW,
        require_clean_git=False, run_smoke=False, run_security_scan=False,
        run_frontend_checks=False)
    check("real repo run returns a result object",
          isinstance(r, Stage5FinalCertificationResult))
    check("real repo run is deterministic-shape (has checks + blockers)",
          len(r.checks) > 0)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_input_validation(tmp)
        test_certification_id(tmp)
        test_go_on_complete_fixture(tmp)
        test_no_go_on_missing_artifact(tmp)
        test_fragmentation_negated_heading(tmp)
        test_stage5_6_gap_reproduction(tmp)
        test_output_artifact(tmp)
        test_safety_scan_catches_injections(tmp)
        test_command_runner_subprocess_allowlist(tmp)
        test_stage6_handoff_items(tmp)
        test_no_mutation(tmp)
    test_static_boundaries()
    test_package_import_safe()
    test_real_repo_readonly()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
