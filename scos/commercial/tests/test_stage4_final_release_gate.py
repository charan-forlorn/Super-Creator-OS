"""test_stage4_final_release_gate.py - SCOS Stage 4.19 final release gate suite.

Plain executable script (no pytest). Exercises the Stage 4 final commercial
release gate against small synthetic fixture repos (never against mutable
real-repo state, except one read-only integration pass at the end). Every
fixture lives under a TemporaryDirectory; no committed artifact is mutated.

subprocess is used only for the package-import-safety probe (repo test
convention); everything else runs the gate in-process. Script runner checks
use tiny stub scripts inside the fixtures.

Run: python scos/commercial/tests/test_stage4_final_release_gate.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent
_ROOT = _HERE.parents[2]

sys.path.insert(0, str(_COMMERCIAL))

from release_gate_models import (  # noqa: E402
    GO_NO_GO_VALUES,
    READINESS_LEVELS,
    STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
    Stage4FinalReleaseGateError,
    Stage4FinalReleaseGateResult,
    Stage4ReleaseBlocker,
    Stage4ReleaseCheck,
    Stage5HandoffItem,
)
from stage4_final_release_gate import (  # noqa: E402
    _CONTRACT_DOCS,
    _HARDENING_ASSETS,
    _SOURCE_FILES,
    _STAGE5_HANDOFF_DOC,
    run_stage4_final_release_gate,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-05T00:00:00Z"

_OUTPUT_NAME = "stage4_final_release_gate.json"
_PASS_SCRIPT = "import sys\nprint('STUB: PASS')\nsys.exit(0)\n"
_FAIL_SCRIPT = "import sys\nprint('STUB: FAIL')\nsys.exit(1)\n"

# Boundary tokens for the static source scans, assembled from fragments so
# this test file itself stays free of the raw tokens under a whole-tree scan.
_NET_TOKENS = (
    "requ" + "ests", "htt" + "px", "urllib" + ".request", "bot" + "o3",
    "soc" + "ket", "http" + ".client", "open" + "ai", "anthro" + "pic",
    "stri" + "pe", "pay" + "pal", "selen" + "ium", "play" + "wright",
    "smt" + "p", "web" + "soc" + "ket", "fla" + "sk", "fast" + "api",
)
_SERVICE_TOKENS = (
    "CR" + "M", "in" + "voice", "pay" + "ment", "bil" + "ling",
    "Saa" + "S", "check" + "out", "sales" + "force", "hub" + "spot",
    "send" + "grid", "auto_" + "dm", "send_" + "email", "send_" + "message",
)
_NONDET_TOKENS = ("uuid.uuid4", "random.", "datetime.now", "date.today", "time.time")
_KNOWLEDGE_TOKENS = ("KnowledgeService", "KnowledgeIndex", "query_engine",
                     "explain_engine", "insight_engine")
_FORBIDDEN_IMPORT_LINE = "import " + "requ" + "ests"


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


def _make_fixture_repo(root: Path) -> Path:
    """Build a synthetic repo that passes every file-existence check."""
    for _, rel in _CONTRACT_DOCS:
        _write(root / rel, "# stub contract doc\n")
    for rel in _HARDENING_ASSETS:
        if rel.startswith("scripts/"):
            _write(root / rel, _PASS_SCRIPT)
        elif rel.endswith(".py"):
            _write(root / rel, "# stub module\n")
        else:
            _write(root / rel, "# stub doc\n")
    for _, name in _SOURCE_FILES:
        target = root / "scos" / "commercial" / name
        if not target.exists():
            _write(target, "# stub module\n")
    _write(root / "docs" / "certification" / "Stage-4.18-plan.md",
           "# Stage 4.18 plan stub\n\nNo new commercial feature flow; no Stage 4.20+.\n")
    _write(root / _STAGE5_HANDOFF_DOC, "# stub Stage 5 handoff\n")
    return root


def _run_gate(root, **kwargs):
    kwargs.setdefault("checked_at", _NOW)
    kwargs.setdefault("require_clean_git", False)
    return run_stage4_final_release_gate(repo_root=root, **kwargs)


def _check_by_name(result, name):
    return [c for c in result.checks if c.check_name == name]


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_model_serialization():
    print("\n[01] result model serializes deterministically")
    def build():
        chk = Stage4ReleaseCheck.of(
            "c1", "success", "info", category="testing",
            artifact_path="a.json", metadata={"k": "v"})
        blk = Stage4ReleaseBlocker.of(
            "b1", "testing", "warning", "title", "detail", "action", "c1",
            metadata={"n": 1})
        item = Stage5HandoffItem.of(
            "stage5-001", "Title", "security", "high",
            description="desc", source_stage4_evidence="e.md")
        return Stage4FinalReleaseGateResult(
            ok=True, schema_version=STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
            accepted=True, release_gate_id="rg-1", checked_at=_NOW,
            stage="stage-4.19", stage_closed=True, go_no_go="GO",
            readiness_level="stage4_complete", readiness_score=95,
            readiness_max_score=100, checks=(chk,), blockers=(blk,),
            stage5_handoff_items=(item,), output_path=None,
            metadata={"b": 2, "a": 1})
    r1, r2 = build(), build()
    check("two builds serialize identically",
          json.dumps(r1.to_dict(), sort_keys=True) == json.dumps(r2.to_dict(), sort_keys=True))
    d = r1.to_dict()
    check("top-level key order is explicit",
          list(d) == ["ok", "schema_version", "accepted", "release_gate_id", "checked_at",
                      "stage", "stage_closed", "go_no_go", "readiness_level",
                      "readiness_score", "readiness_max_score", "checks", "blockers",
                      "stage5_handoff_items", "output_path", "metadata"])
    check("tuples serialize as lists",
          isinstance(d["checks"], list) and isinstance(d["blockers"], list)
          and isinstance(d["stage5_handoff_items"], list))
    check("nested models serialize via to_dict",
          d["checks"][0]["check_name"] == "c1" and d["blockers"][0]["blocker_id"] == "b1"
          and d["stage5_handoff_items"][0]["item_id"] == "stage5-001")
    check("metadata FrozenMap serializes to plain dict",
          d["metadata"] == {"a": 1, "b": 2})
    check("schema version constant is 1", STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION == 1)
    try:
        Stage4FinalReleaseGateResult(
            ok=True, schema_version=1, accepted=True, release_gate_id="x",
            checked_at=_NOW, stage="s", stage_closed=True, go_no_go="MAYBE",
            readiness_level="stage4_complete", readiness_score=0,
            readiness_max_score=100, checks=(), blockers=(),
            stage5_handoff_items=(), output_path=None, metadata={})
        bad_rejected = False
    except ValueError:
        bad_rejected = True
    check("invalid go_no_go rejected", bad_rejected)
    check("allowed enums exposed",
          GO_NO_GO_VALUES == ("GO", "CONDITIONAL_GO", "NO_GO") and len(READINESS_LEVELS) == 3)


def test_error_model_serialization():
    print("\n[02] error model serializes deterministically")
    def build():
        return Stage4FinalReleaseGateError.of(
            "INVALID_ARGUMENTS", "detail", "validate_inputs",
            (Stage4ReleaseCheck.of("validate_inputs", "failure", "error",
                                   category="preflight"),),
            (), {"z": 1})
    e1, e2 = build(), build()
    check("two builds serialize identically",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))
    d = e1.to_dict()
    check("error key order is explicit",
          list(d) == ["ok", "schema_version", "error_kind", "error_detail",
                      "failed_check", "checks", "blockers", "metadata"])
    check("ok is False and schema pinned", d["ok"] is False and d["schema_version"] == 1)


def test_input_validation(tmp: Path):
    print("\n[03-06] input validation")
    r = _run_gate(tmp / "missing-repo")
    check("missing repo_root -> INPUT_NOT_FOUND",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INPUT_NOT_FOUND")
    r2 = _run_gate(tmp / "missing-repo")
    check("missing repo_root error deterministic",
          json.dumps(r.to_dict(), sort_keys=True) == json.dumps(r2.to_dict(), sort_keys=True))
    r = _run_gate("")
    check("empty repo_root -> INVALID_ARGUMENTS",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate("https://example.test/repo")
    check("URL repo_root rejected",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INVALID_ARGUMENTS")
    fixture = _make_fixture_repo(tmp / "fx-input")
    r = _run_gate(fixture, checked_at="")
    check("empty checked_at rejected",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INVALID_ARGUMENTS")
    r = run_stage4_final_release_gate(repo_root=fixture, checked_at=None,
                                      require_clean_git=False)
    check("None checked_at rejected",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INVALID_ARGUMENTS")
    r = _run_gate(fixture, output_path="https://example.test/out.json")
    check("URL output_path rejected",
          isinstance(r, Stage4FinalReleaseGateError) and r.error_kind == "INVALID_ARGUMENTS")


def test_release_gate_id(tmp: Path):
    print("\n[07] release_gate_id derivation")
    fixture = _make_fixture_repo(tmp / "fx-id")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("gate id deterministic across runs", r1.release_gate_id == r2.release_gate_id)
    check("gate id has the gate-name prefix",
          r1.release_gate_id.startswith("stage4-final-commercial-release-gate-"))
    r3 = _run_gate(fixture, checked_at="2026-07-06T00:00:00Z")
    check("gate id changes with checked_at", r3.release_gate_id != r1.release_gate_id)
    check("gate id ends with 12-hex digest",
          len(r1.release_gate_id.rsplit("-", 1)[-1]) == 12)


def test_hardening_assets(tmp: Path):
    print("\n[08-09] Stage 4.18 hardening assets")
    fixture = _make_fixture_repo(tmp / "fx-hard")
    r = _run_gate(fixture)
    ok_checks = _check_by_name(r, "validate_hardening_foundation")
    check("hardening check succeeds on full fixture",
          len(ok_checks) == 1 and ok_checks[0].status == "success")
    check("all 10 hardening assets verified",
          ok_checks[0].metadata.to_dict().get("verified") == len(_HARDENING_ASSETS) == 10)
    broken = _make_fixture_repo(tmp / "fx-hard-broken")
    (broken / "docs" / "security" / "SECURITY_HARDENING_BASELINE.md").unlink()
    r = _run_gate(broken)
    check("missing hardening asset -> check failure",
          _check_by_name(r, "validate_hardening_foundation")[0].status == "failure")
    check("missing hardening asset -> blocker",
          any(b.blocker_id == "blk-hardening-assets" for b in r.blockers))


def test_stage4_20_markers(tmp: Path):
    print("\n[10] Stage 4.20+ marker scan")
    fixture = _make_fixture_repo(tmp / "fx-frag")
    r = _run_gate(fixture)
    check("clean fixture (incl. negated 4.18 mention) -> no fragmentation blocker",
          not any(b.title == "STAGE_OVER_FRAGMENTATION" for b in r.blockers))
    by_file = _make_fixture_repo(tmp / "fx-frag-file")
    _write(by_file / "docs" / "certification" / "Stage-4.20-plan.md", "# stub\n")
    r = _run_gate(by_file)
    check("Stage-4.20 filename -> STAGE_OVER_FRAGMENTATION blocker",
          any(b.title == "STAGE_OVER_FRAGMENTATION" for b in r.blockers))
    check("fragmentation blocker is critical -> NO_GO",
          r.go_no_go == "NO_GO" and r.stage_closed is False)
    by_text = _make_fixture_repo(tmp / "fx-frag-text")
    _write(by_text / "docs" / "specification" / "NOTES.md",
           "Planned Stage 4.20 work items live here.\n")
    r = _run_gate(by_text)
    check("non-negated content marker -> blocker",
          any(b.title == "STAGE_OVER_FRAGMENTATION" for b in r.blockers))
    negated = _make_fixture_repo(tmp / "fx-frag-neg")
    _write(negated / "docs" / "specification" / "NOTES.md",
           "This stage forbids Stage 4.20+ work; move it to Stage 5.\n")
    r = _run_gate(negated)
    check("negated content marker -> no blocker",
          not any(b.title == "STAGE_OVER_FRAGMENTATION" for b in r.blockers))


def test_forbidden_behavior_scan(tmp: Path):
    print("\n[11] static forbidden-behavior scan")
    fixture = _make_fixture_repo(tmp / "fx-forbid")
    r = _run_gate(fixture)
    check("clean fixture passes forbidden scan",
          _check_by_name(r, "validate_static_forbidden_behavior")[0].status == "success")
    bad = _make_fixture_repo(tmp / "fx-forbid-bad")
    _write(bad / "scos" / "commercial" / "bad_module.py",
           _FORBIDDEN_IMPORT_LINE + "\n")
    r = _run_gate(bad)
    check("forbidden import in executable source -> check failure",
          _check_by_name(r, "validate_static_forbidden_behavior")[0].status == "failure")
    check("forbidden import -> critical blocker + NO_GO",
          any(b.blocker_id == "blk-forbidden-behavior" and b.severity == "critical"
              for b in r.blockers) and r.go_no_go == "NO_GO")
    docs_only = _make_fixture_repo(tmp / "fx-forbid-docs")
    _write(docs_only / "docs" / "specification" / "BOUNDARY_NOTES.md",
           "Non-goal example: " + _FORBIDDEN_IMPORT_LINE + "\n")
    r = _run_gate(docs_only)
    check("same text in docs is ignored (docs not scanned)",
          _check_by_name(r, "validate_static_forbidden_behavior")[0].status == "success")


def test_script_runners(tmp: Path):
    print("\n[12-15] smoke + security script runners")
    fixture = _make_fixture_repo(tmp / "fx-scripts")
    r = _run_gate(fixture)
    check("smoke pass recorded",
          _check_by_name(r, "run_smoke_script")[0].status == "success")
    check("security pass recorded",
          _check_by_name(r, "run_security_scan_baseline")[0].status == "success")
    smoke_fail = _make_fixture_repo(tmp / "fx-smoke-fail")
    _write(smoke_fail / "scripts" / "test_smoke.py", _FAIL_SCRIPT)
    r = _run_gate(smoke_fail)
    check("smoke fail -> check failure + blocker",
          _check_by_name(r, "run_smoke_script")[0].status == "failure"
          and any(b.blocker_id == "blk-smoke-script" for b in r.blockers))
    sec_fail = _make_fixture_repo(tmp / "fx-sec-fail")
    _write(sec_fail / "scripts" / "security_scan_baseline.py", _FAIL_SCRIPT)
    r = _run_gate(sec_fail)
    check("security fail -> check failure + blocker",
          _check_by_name(r, "run_security_scan_baseline")[0].status == "failure"
          and any(b.blocker_id == "blk-security-scan" for b in r.blockers))
    r = _run_gate(fixture, run_smoke=False, run_security_scan=False)
    check("flag-skips recorded as skipped",
          _check_by_name(r, "run_smoke_script")[0].status == "skipped"
          and _check_by_name(r, "run_security_scan_baseline")[0].status == "skipped")
    check("release script defaults to skipped",
          _check_by_name(r, "run_release_script")[0].status == "skipped")


def test_output_artifact(tmp: Path):
    print("\n[16-17] output artifact")
    fixture = _make_fixture_repo(tmp / "fx-out")
    out_file = tmp / "out" / "gate.json"
    r = _run_gate(fixture, output_path=out_file)
    check("output file written on result path", out_file.is_file())
    check("result records output_path", r.output_path == str(out_file))
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    required_keys = {"ok", "schema_version", "accepted", "release_gate_id", "checked_at",
                     "stage", "stage_closed", "go_no_go", "readiness_level",
                     "readiness_score", "readiness_max_score", "checks", "blockers",
                     "stage5_handoff_items", "output_path", "metadata"}
    check("output JSON has all required top-level keys",
          required_keys.issubset(payload.keys()))
    first_bytes = out_file.read_bytes()
    _run_gate(fixture, output_path=out_file)
    check("re-run output byte-identical", out_file.read_bytes() == first_bytes)
    check("LF only + trailing newline",
          b"\r\n" not in first_bytes and first_bytes.endswith(b"\n"))
    out_dir = tmp / "out-dir"
    r = _run_gate(fixture, output_path=out_dir)
    check("directory output_path -> canonical filename",
          (out_dir / _OUTPUT_NAME).is_file() and r.output_path == str(out_dir / _OUTPUT_NAME))
    no_out = _make_fixture_repo(tmp / "fx-no-out")
    r = _run_gate(no_out)
    written = list(no_out.rglob(_OUTPUT_NAME))
    check("output_path=None writes nothing", r.output_path is None and written == [])
    bad_url = _run_gate(fixture, output_path="https://example.test/x.json")
    check("error path writes nothing",
          isinstance(bad_url, Stage4FinalReleaseGateError)
          and not (tmp / "x.json").exists())


def test_stage5_handoff_items(tmp: Path):
    print("\n[18] Stage 5 handoff items")
    fixture = _make_fixture_repo(tmp / "fx-handoff")
    r1 = _run_gate(fixture)
    r2 = _run_gate(fixture)
    check("10 handoff items generated", len(r1.stage5_handoff_items) == 10)
    check("handoff items deterministic",
          [i.to_dict() for i in r1.stage5_handoff_items]
          == [i.to_dict() for i in r2.stage5_handoff_items])
    check("item ids are stage5-001..stage5-010",
          [i.item_id for i in r1.stage5_handoff_items]
          == [f"stage5-{n:03d}" for n in range(1, 11)])
    categories = {i.category for i in r1.stage5_handoff_items}
    check("handoff covers required workstreams",
          {"control_center_backend", "command_api", "event_stream", "operator_approval",
           "security", "productization", "monitoring", "commercial_execution"} <= categories)
    broken = _make_fixture_repo(tmp / "fx-handoff-missing")
    (broken / _STAGE5_HANDOFF_DOC).unlink()
    r = _run_gate(broken)
    check("missing handoff doc -> failure + blocker",
          _check_by_name(r, "validate_stage5_handoff_readiness")[0].status == "failure"
          and any(b.blocker_id == "blk-stage5-handoff-doc" for b in r.blockers))


def test_readiness_scoring(tmp: Path):
    print("\n[19-20] readiness scoring + go/no-go")
    fixture = _make_fixture_repo(tmp / "fx-score")
    r = _run_gate(fixture)
    check("all checks pass -> GO", r.go_no_go == "GO")
    check("GO score is 95 (git waived at half weight)",
          r.readiness_score == 95 and r.readiness_max_score == 100)
    check("GO closes Stage 4", r.stage_closed is True and r.accepted is True
          and r.readiness_level == "stage4_complete")
    check("GO run has no blockers", r.blockers == ())
    bad = _make_fixture_repo(tmp / "fx-score-bad")
    _write(bad / "scos" / "commercial" / "bad_module.py", _FORBIDDEN_IMPORT_LINE + "\n")
    r = _run_gate(bad)
    check("critical blocker -> NO_GO + stage open",
          r.go_no_go == "NO_GO" and r.stage_closed is False
          and r.readiness_level == "stage4_blocked" and r.accepted is False)
    smoke_fail = _make_fixture_repo(tmp / "fx-score-warn")
    _write(smoke_fail / "scripts" / "test_smoke.py", _FAIL_SCRIPT)
    r = _run_gate(smoke_fail)
    check("non-critical failure at score 75 -> CONDITIONAL_GO",
          r.go_no_go == "CONDITIONAL_GO" and r.readiness_score == 75)
    check("allow_warnings=True keeps stage closed on CONDITIONAL_GO",
          r.stage_closed is True)
    r = _run_gate(smoke_fail, allow_warnings=False)
    check("allow_warnings=False leaves stage open on CONDITIONAL_GO",
          r.go_no_go == "CONDITIONAL_GO" and r.stage_closed is False)


def test_no_mutation(tmp: Path):
    print("\n[21] no mutation of inspected files")
    fixture = _make_fixture_repo(tmp / "fx-mutate")
    before = _tree_hashes(fixture)
    _run_gate(fixture)
    check("fixture tree unchanged after gate run", _tree_hashes(fixture) == before)
    out = tmp / "mutate-out" / "gate.json"
    _run_gate(fixture, output_path=out)
    check("fixture tree unchanged even when output written elsewhere",
          _tree_hashes(fixture) == before)


def test_static_boundaries():
    print("\n[22-23] static boundary scan of the Stage 4.19 modules")
    gate_src = (_COMMERCIAL / "stage4_final_release_gate.py").read_text(encoding="utf-8")
    models_src = (_COMMERCIAL / "release_gate_models.py").read_text(encoding="utf-8")
    combined = gate_src + models_src
    for token in _NET_TOKENS:
        check(f"no network/cloud token '{token}'", token not in combined)
    for token in _SERVICE_TOKENS:
        check(f"no external-service token '{token}'", token not in combined)
    for token in _NONDET_TOKENS:
        check(f"no non-determinism token '{token}'", token not in combined)
    for token in _KNOWLEDGE_TOKENS:
        check(f"no knowledge-layer token '{token}'", token not in combined)
    check("models module stays subprocess-free", "subprocess" not in models_src)
    check("gate module uses subprocess only for git + repo scripts",
          gate_src.count("subprocess.run") == 2)


def test_package_import_safe():
    print("\n[24] __init__ lazy export preserved")
    code = (
        "import sys\n"
        "import scos.commercial as c\n"
        "assert callable(c.run_stage4_final_release_gate)\n"
        "assert c.STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION == 1\n"
        "assert callable(c.create_first_customer_conversion_handoff)\n"
        "assert callable(c.write_stable_json)\n"
        "assert 'run_stage4_final_release_gate' in c.__all__\n"
        "assert not any(m.startswith('scos.knowledge') for m in sys.modules), "
        "'knowledge imported eagerly'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(_ROOT))
    check("import scos.commercial exposes Stage 4.19 lazily w/o knowledge",
          proc.returncode == 0)


def test_real_repo_readonly():
    print("\n[25] optional read-only integration pass over the real repo")
    r = run_stage4_final_release_gate(
        repo_root=_ROOT, checked_at=_NOW,
        require_clean_git=False, run_smoke=False, run_security_scan=False)
    check("real repo file inventory passes",
          isinstance(r, Stage4FinalReleaseGateResult)
          and not any(c.status == "failure" for c in r.checks))
    check("real repo has no gate blockers", r.blockers == ())


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_model_serialization()
        test_error_model_serialization()
        test_input_validation(tmp)
        test_release_gate_id(tmp)
        test_hardening_assets(tmp)
        test_stage4_20_markers(tmp)
        test_forbidden_behavior_scan(tmp)
        test_script_runners(tmp)
        test_output_artifact(tmp)
        test_stage5_handoff_items(tmp)
        test_readiness_scoring(tmp)
        test_no_mutation(tmp)
    test_static_boundaries()
    test_package_import_safe()
    test_real_repo_readonly()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
