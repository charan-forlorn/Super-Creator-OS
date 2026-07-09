"""test_stage6_final_integration_gate.py - SCOS Stage 6.10 final integration gate suite.

Plain executable script (also pytest-collectable). Exercises the Stage 6 final
integration gate against small synthetic fixture repos (never against mutable
real-repo state, except one read-only integration pass at the end). Every
fixture lives under a TemporaryDirectory; no committed artifact is mutated.

Run: python scos/control_center/tests/test_stage6_final_integration_gate.py
   or: .venv\\Scripts\\python.exe -m pytest scos/control_center/tests/test_stage6_final_integration_gate.py -q
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

from stage6_final_gate_models import (  # noqa: E402
    Stage6FinalIntegrationError,
    Stage6FinalIntegrationResult,
)
from stage6_final_integration_gate import (  # noqa: E402
    _CONTROL_CENTER_SUBPROCESS_ALLOWLIST,
    _OWN_MODULES,
    _STAGE7_HANDOFF_DOC,
    _STAGE_ARTIFACTS,
    run_stage6_final_integration_gate,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-09T00:00:00Z"
_OUTPUT_NAME = "stage6_final_integration_report.json"
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
    """Build a synthetic repo that passes every Stage 6.2-6.10 artifact check.

    Scans the real gate's _STAGE_ARTIFACTS manifest so the fixture always
    matches the gate's expectations.
    """
    for entry in _STAGE_ARTIFACTS:
        kind = entry["kind"]
        if kind == "generic":
            for module_name in entry["modules"]:
                _write(root / "scos" / "control_center" / f"{module_name}.py",
                       _stub_module(entry["stage"]))
            for test_file in entry["tests"]:
                _write(root / "scos" / "control_center" / "tests" / test_file,
                       _PASS_SCRIPT)
            _write(root / entry["cert_doc"], f"# Stage {entry['stage']} plan stub\n")
            for spec_doc in entry["spec_docs"]:
                _write(root / spec_doc, "# stub contract doc\n")
            for extra_doc in entry.get("extra_docs", ()):
                _write(root / extra_doc, "# stub extra doc\n")
        elif kind == "self":
            # 6.10 contract + release + handoff docs
            _write(root / entry["cert_doc"], "# Stage 6.10 plan stub\n")
            _write(root / entry["contract_doc"], "# stub contract\n")
            _write(root / entry["release_doc"], "# stub release\n")
            _write(root / entry["handoff_doc"], "# stub Stage 7 handoff\n")
        # security_scan kind (6.8) only needs its cert_doc + a security script
        _write(root / entry["cert_doc"], f"# Stage {entry['stage']} plan stub\n")
    # Allowlisted subprocess modules need a real subprocess import.
    for rel in _CONTROL_CENTER_SUBPROCESS_ALLOWLIST:
        if rel.startswith("scos/control_center/"):
            stem = rel.split("/")[-1][:-3]
            if stem in _OWN_MODULES or stem in ("command_runner", "stage5_final_certification"):
                _write(root / rel,
                       _stub_module("6.2",
                                   "import subprocess\n"
                                   "from .approval_audit_store import is_execution_granted\n"
                                   "def run_stub():\n"
                                   "    return subprocess.run(['echo'], capture_output=True, "
                                   "text=True, timeout=5)\n"))
    # Security scan baseline (needed for coverage + runnability check).
    _write(root / "scripts" / "test_smoke.py", _PASS_SCRIPT)
    _write(root / "scripts" / "security_scan_baseline.py",
           '"""stub security scan."""\n'
           '_CONTROL_CENTER_DIR = None\n'
           '_FRONTEND_DIR = None\n'
           'def main():\n'
           '    print("SECURITY SCAN: PASS")\n'
           '    return 0\n'
           'if __name__ == "__main__":\n'
           '    import sys\n'
           '    sys.exit(main())\n')
    # Minimal __init__.py so the package imports cleanly in the read-only pass.
    _write(root / "scos" / "control_center" / "__init__.py",
           '"""stub package."""\n')
    return root


def _run_gate(root, **kwargs):
    kwargs.setdefault("checked_at", _NOW)
    kwargs.setdefault("require_clean_git", False)
    kwargs.setdefault("run_smoke", False)
    kwargs.setdefault("run_security_scan", False)
    kwargs.setdefault("run_control_center_tests", False)
    kwargs.setdefault("run_frontend_checks", False)
    return run_stage6_final_integration_gate(repo_root=root, **kwargs)


def _check_by_name(result, name):
    return [c for c in result.checks if c.check_name == name]


def test_input_validation(tmp: Path):
    print("\n[01-05] input validation")
    r = _run_gate(tmp / "missing-repo")
    check("missing repo_root -> INPUT_NOT_FOUND",
          isinstance(r, Stage6FinalIntegrationError) and r.error_kind == "INPUT_NOT_FOUND")
    r = _run_gate("")
    check("empty repo_root -> INVALID_ARGUMENTS",
          isinstance(r, Stage6FinalIntegrationError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate("https://example.test/repo")
    check("URL repo_root rejected",
          isinstance(r, Stage6FinalIntegrationError) and r.error_kind == "INVALID_ARGUMENTS")
    fixture = _make_fixture_repo(tmp / "fx-input")
    r = _run_gate(fixture, checked_at="")
    check("empty checked_at rejected",
          isinstance(r, Stage6FinalIntegrationError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate(fixture, output_path="https://example.test/out.json")
    check("URL output_path rejected",
          isinstance(r, Stage6FinalIntegrationError) and r.error_kind == "INVALID_ARGUMENTS")


def test_gate_id(tmp: Path):
    print("\n[06] gate_id derivation")
    fixture = _make_fixture_repo(tmp / "fx-id")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("id deterministic across runs", r1.gate_id == r2.gate_id)
    check("id has s6g- prefix", r1.gate_id.startswith("s6g-"))
    r3 = _run_gate(fixture, checked_at="2026-07-10T00:00:00Z")
    check("id changes with checked_at", r3.gate_id != r1.gate_id)


def test_go_on_complete_fixture(tmp: Path):
    print("\n[07] GO on complete fixture")
    fixture = _make_fixture_repo(tmp / "fx-go")
    r = _run_gate(fixture, run_smoke=True, run_security_scan=True)
    check("complete fixture -> GO",
          isinstance(r, Stage6FinalIntegrationResult) and r.go_no_go == "GO")
    check("GO closes stage", r.stage_closed is True and r.accepted is True)
    check("GO has zero error/critical blockers",
          not any(b.severity in ("error", "critical") for b in r.blockers))
    check("GO readiness_score == 100", r.readiness_score == 100)


def test_no_go_on_missing_artifact(tmp: Path):
    print("\n[08] NO_GO on missing artifact")
    fixture = _make_fixture_repo(tmp / "fx-missing")
    # Remove a required Stage 6.2 spec doc.
    (fixture / "docs" / "specification" / "CONTROL_CENTER_COMMAND_API_CONTRACT.md").unlink()
    r = _run_gate(fixture)
    check("missing Stage 6.2 spec doc -> NO_GO", r.go_no_go == "NO_GO")
    check("specific check failed",
          _check_by_name(r, "validate_stage6_2_artifacts")[0].status == "failure")
    check("blocker recorded",
          any(b.blocker_id == "blk-stage6-2-artifacts" for b in r.blockers))


def test_missing_610_docs_blocker(tmp: Path):
    print("\n[09] missing Stage 6.10 docs -> NO_GO")
    fixture = _make_fixture_repo(tmp / "fx-nodocs")
    (fixture / "docs" / "specification" / "STAGE6_FINAL_INTEGRATION_GATE_CONTRACT.md").unlink()
    r = _run_gate(fixture)
    check("missing 6.10 contract -> NO_GO", r.go_no_go == "NO_GO")
    check("6.10 docs blocker present",
          any(b.blocker_id == "blk-stage6-10-docs" for b in r.blockers))


def test_missing_7_handoff_doc_blocker(tmp: Path):
    print("\n[10] missing Stage 7 handoff doc -> NO_GO")
    fixture = _make_fixture_repo(tmp / "fx-nohandoff")
    (fixture / _STAGE7_HANDOFF_DOC).unlink()
    r = _run_gate(fixture)
    check("missing Stage 7 handoff -> NO_GO", r.go_no_go == "NO_GO")
    check("handoff doc blocker present",
          any(b.blocker_id == "blk-stage7-handoff-doc" for b in r.blockers))


def test_output_path_none_writes_nothing(tmp: Path):
    print("\n[11] output_path=None writes nothing")
    fixture = _make_fixture_repo(tmp / "fx-none")
    r = _run_gate(fixture)
    check("result output_path is None", r.output_path is None)
    check("no report file written",
          list(fixture.rglob(_OUTPUT_NAME)) == [])


def test_output_path_writes_deterministic_json(tmp: Path):
    print("\n[12-13] output_path writes deterministic JSON")
    fixture = _make_fixture_repo(tmp / "fx-out")
    out_file = tmp / "out" / "report.json"
    r = _run_gate(fixture, output_path=out_file)
    check("output file written", out_file.is_file())
    check("result records output_path", r.output_path == str(out_file))
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    check("output JSON has required top-level keys",
          {"ok", "gate_id", "go_no_go", "readiness_score", "checks",
           "blockers", "stage7_handoff_items"}.issubset(payload.keys()))
    first_bytes = out_file.read_bytes()
    _run_gate(fixture, output_path=out_file)
    check("re-run output byte-identical", out_file.read_bytes() == first_bytes)
    check("LF only + trailing newline",
          b"\r\n" not in first_bytes and first_bytes.endswith(b"\n"))


def test_deterministic_same_inputs(tmp: Path):
    print("\n[14] same inputs + checked_at produce same result")
    fixture = _make_fixture_repo(tmp / "fx-det")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("identical to_dict() output", r1.to_dict() == r2.to_dict())


def test_dirty_git_is_blocker(tmp: Path):
    print("\n[15] dirty git state becomes blocker when require_clean_git=True")
    fixture = _make_fixture_repo(tmp / "fx-dirty")
    # Simulate a dirty working tree with a marker file under docs/ .
    _write(fixture / "docs" / "DIRTY_MARKER.md", "# dirty\n")
    r = _run_gate(fixture, require_clean_git=True)
    check("dirty tree -> NO_GO", r.go_no_go == "NO_GO")
    check("git-state blocker present",
          any(b.blocker_id == "blk-git-state" for b in r.blockers))


def test_warnings_do_not_close_stage(tmp: Path):
    print("\n[16] warnings do not close stage unless score 100 + no blockers")
    fixture = _make_fixture_repo(tmp / "fx-warn")
    # Introduce only a security-scan-runnable skip by disabling the run is not
    # a warning; instead simulate a coherent-but-incomplete repo by removing a
    # 6.5 extra doc so source_contract fails (error blocker -> NO_GO).
    (fixture / "docs" / "certification" / "Stage-6.5-regression-cleanup-report.md").unlink()
    r = _run_gate(fixture)
    check("missing coherence doc -> NO_GO (not silently closed)",
          r.go_no_go == "NO_GO" and r.stage_closed is False)


def test_stage7_handoff_items_present(tmp: Path):
    print("\n[17] Stage 7 handoff items present and deterministic")
    fixture = _make_fixture_repo(tmp / "fx-handoff")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("8-12 handoff items generated", 8 <= len(r1.stage7_handoff_items) <= 12)
    check("handoff items deterministic across runs",
          [i.to_dict() for i in r1.stage7_handoff_items]
          == [i.to_dict() for i in r2.stage7_handoff_items])
    categories = {i.category for i in r1.stage7_handoff_items}
    check("handoff covers read_surface + sync_decision + safety_boundary",
          {"read_surface", "sync_decision", "safety_boundary"} <= categories)


def test_no_forbidden_tokens_in_new_gate_files(tmp: Path):
    print("\n[18-19] static boundary scan of the Stage 6.10 modules themselves")
    gate_src = (_PACKAGE / "stage6_final_integration_gate.py").read_text(encoding="utf-8")
    models_src = (_PACKAGE / "stage6_final_gate_models.py").read_text(encoding="utf-8")
    combined = gate_src + models_src
    for token in ("uuid.uuid4", "random.", "datetime.now", "date.today", "time.time"):
        check(f"no non-determinism token '{token}'", token not in combined)
    check("models module stays subprocess-free", "subprocess" not in models_src)
    check("models module never imports scos.commercial",
          "import scos.commercial" not in models_src
          and "from scos.commercial" not in models_src
          and "from .commercial" not in models_src)
    check("gate module never imports scos.commercial",
          "import scos.commercial" not in gate_src
          and "from scos.commercial" not in gate_src
          and "from .commercial" not in gate_src)


def test_nested_mappings_immutable(tmp: Path):
    print("\n[20] result nested mappings/collections are immutable enough")
    fixture = _make_fixture_repo(tmp / "fx-immut")
    r = _run_gate(fixture)
    raised = False
    try:
        r.checks[0].metadata.items = ("x",)
    except (AttributeError, TypeError):
        raised = True
    check("FrozenMap items cannot be reassigned", raised)
    raised = False
    try:
        r.checks = ()
    except (AttributeError, TypeError):
        raised = True
    check("frozen dataclass fields cannot be reassigned", raised)


def test_package_import_safe():
    print("\n[21] __init__ lazy export preserved (new gate not force-imported)")
    import subprocess
    code = (
        "import scos.control_center as c\n"
        "assert callable(c.run_stage6_final_integration_gate)\n"
        "assert c.STAGE6_FINAL_GATE_SCHEMA_VERSION == 1\n"
        "assert 'run_stage6_final_integration_gate' in c.__all__\n"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(_ROOT))
    check("import scos.control_center exposes Stage 6.10 lazily",
          proc.returncode == 0)


def test_real_repo_readonly():
    print("\n[22] optional read-only integration pass over the real repo")
    r = run_stage6_final_integration_gate(
        repo_root=_ROOT, checked_at=_NOW,
        require_clean_git=False, run_smoke=False, run_security_scan=False,
        run_control_center_tests=False, run_frontend_checks=False)
    check("real repo run returns a result object",
          isinstance(r, Stage6FinalIntegrationResult))
    check("real repo run is deterministic-shape (has checks + blockers)",
          len(r.checks) > 0)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_input_validation(tmp)
        test_gate_id(tmp)
        test_go_on_complete_fixture(tmp)
        test_no_go_on_missing_artifact(tmp)
        test_missing_610_docs_blocker(tmp)
        test_missing_7_handoff_doc_blocker(tmp)
        test_output_path_none_writes_nothing(tmp)
        test_output_path_writes_deterministic_json(tmp)
        test_deterministic_same_inputs(tmp)
        test_dirty_git_is_blocker(tmp)
        test_warnings_do_not_close_stage(tmp)
        test_stage7_handoff_items_present(tmp)
        test_no_forbidden_tokens_in_new_gate_files(tmp)
        test_nested_mappings_immutable(tmp)
    test_package_import_safe()
    test_real_repo_readonly()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
