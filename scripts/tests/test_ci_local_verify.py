"""Behavioral and CI-parity tests for ``scripts/ci_local_verify.py`` (Cohort 8C).

These tests exercise the local verifier WITHOUT running the real full smoke,
security, or pytest populations. The real child processes are replaced by an
injected fake runner, while command construction, ordering, marker selection,
warning filters, environment handling, isolation, and exit-code propagation are
verified against the actual implementation. Semantic parity with the committed
``.github/workflows/ci.yml`` is proven structurally.

Run:
    .venv\\Scripts\\python.exe -m pytest scripts/tests/test_ci_local_verify.py \\
        -W error::pytest.PytestConfigWarning \\
        -W error::pytest.PytestUnhandledThreadExceptionWarning -q
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import ci_local_verify as civ  # noqa: E402

CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Expected CI verification-gate order (GitHub-host setup steps are excluded).
EXPECTED_GATE_ORDER = [
    "smoke",
    "security_scan",
    "standard_population",
    "integration_population",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identify_gate(argv):
    """Map an argv list to a gate id for call-assertion purposes."""
    if any("test_smoke.py" in str(a) for a in argv):
        return "smoke"
    if any("security_scan_baseline.py" in str(a) for a in argv):
        return "security_scan"
    if "not integration" in argv:
        return "standard_population"
    if "integration" in argv and "-m" in argv:
        return "integration_population"
    return "unknown"


def _fake_runner_factory(record, rc_by_gate=None):
    """Return a runner that records calls and returns per-gate exit codes.

    ``rc_by_gate`` maps gate id -> exit code (default 0). When a gate id is not
    present, returns 0. A callable value is invoked with the gate id.
    """
    rc_by_gate = rc_by_gate or {}

    def runner(argv, cwd=None, env=None):
        gate = _identify_gate(argv)
        record.append({"gate": gate, "argv": list(argv), "cwd": cwd, "env": env})
        if gate in rc_by_gate:
            val = rc_by_gate[gate]
            return val() if callable(val) else val
        return 0

    return runner


def _parse_ci_gates():
    """Parse committed ci.yml and return ordered (name, run_text) verification gates."""
    assert CI_YML.is_file(), f"missing committed workflow: {CI_YML}"
    with CI_YML.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    steps = doc["jobs"]["test"]["steps"]
    gates = []
    for step in steps:
        run = step.get("run")
        if not run:
            continue
        if "test_smoke.py" in run:
            gates.append(("smoke", run))
        elif "security_scan_baseline.py" in run:
            gates.append(("security_scan", run))
        elif "-m" in run and "integration" in run:
            # Two pytest populations differ only by marker expression.
            if "not integration" in run:
                gates.append(("standard_population", run))
            else:
                gates.append(("integration_population", run))
    return gates


# ---------------------------------------------------------------------------
# Command contract
# ---------------------------------------------------------------------------

def test_gates_are_ordered_argv_lists():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, REPO_ROOT / "tmp-never")
    assert [g.gate_id for g in gates] == EXPECTED_GATE_ORDER
    for g in gates:
        assert isinstance(g.argv, list)
        assert all(isinstance(tok, str) for tok in g.argv)
        # first token is the canonical interpreter
        assert g.argv[0] == str(interp)


def test_canonical_venv_interpreter_is_used():
    interp = civ.detect_interpreter(REPO_ROOT)
    # The canonical interpreter must be the .venv interpreter, not global python.
    assert str(interp).endswith(str(civ._VENV_RELATIVE)) or "Scripts/python.exe" in str(interp)
    assert "python.exe" in str(interp)
    gates = civ.build_gates(REPO_ROOT, interp, REPO_ROOT / "tmp-never")
    for g in gates:
        assert g.argv[0] == str(interp)


def test_shell_true_never_used_and_cwd_correct(monkeypatch):
    """Exercise the REAL runner path; prove shell=False and cwd is repo root."""
    calls = []

    class _FakeProc:
        returncode = 0

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return _FakeProc()

    monkeypatch.setattr(civ.subprocess, "run", fake_run)
    rc = civ.run_all(REPO_ROOT, runner=civ._real_runner)
    assert rc == 0
    # Gate-execution calls (cwd == repo root) must never use shell=True.
    gate_calls = [k for k in calls if k.get("cwd") == str(REPO_ROOT)]
    assert gate_calls, "expected gate execution calls"
    for k in gate_calls:
        assert k.get("shell", False) is False
        assert k["cwd"] == str(REPO_ROOT)
    # Media-sensitive gate calls receive a child-local env.
    media_calls = [k for k in gate_calls if k.get("env") is not None]
    assert media_calls, "pytest gates must receive process-local media env"
    for k in media_calls:
        assert k["env"]["SCOS_FFMPEG_BIN"]
        assert k["env"]["SCOS_FFPROBE_BIN"]


def test_standard_marker_contract_is_correct():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-std")
    std = next(g for g in gates if g.gate_id == "standard_population")
    # find the *marker* -m (the one whose value is a marker expression)
    positions = [i for i, tok in enumerate(std.argv) if tok == "-m"]
    marker_vals = [std.argv[i + 1] for i in positions]
    assert "not integration" in marker_vals
    assert "integrations" in std.argv and "scos" in std.argv and "scripts" in std.argv


def test_integration_marker_contract_is_correct():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-int")
    integ = next(g for g in gates if g.gate_id == "integration_population")
    positions = [i for i, tok in enumerate(integ.argv) if tok == "-m"]
    marker_vals = [integ.argv[i + 1] for i in positions]
    assert "integration" in marker_vals
    assert "integrations" in integ.argv and "scos" in integ.argv and "scripts" in integ.argv


def test_both_warning_guards_present_and_not_blanket():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, REPO_ROOT / "tmp-never")
    for g in gates:
        if not g.is_pytest:
            continue  # smoke/security are not pytest gate
        # exactly the two required guards, no blanket -W error
        assert "-W" in g.argv
        assert "error::pytest.PytestConfigWarning" in g.argv
        assert "error::pytest.PytestUnhandledThreadExceptionWarning" in g.argv
        assert "error" not in [a for a in g.argv if a == "-W" or a.startswith("-W")]
        # no bare "-W error"
        joined = " ".join(g.argv)
        assert "-W error " not in joined
        assert "-W error::" in joined


def test_cacheprovider_not_disabled():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, REPO_ROOT / "tmp-never")
    for g in gates:
        assert "-p" not in g.argv
        assert "no:cacheprovider" not in g.argv


def test_unique_cache_and_basetemp_per_pytest_gate():
    interp = civ.detect_interpreter(REPO_ROOT)
    run_root = Path(tempfile.gettempdir()) / "scos-test-unique"
    gates = civ.build_gates(REPO_ROOT, interp, run_root)
    std = next(g for g in gates if g.gate_id == "standard_population")
    integ = next(g for g in gates if g.gate_id == "integration_population")
    # distinct per gate
    assert std.cache_dir != integ.cache_dir
    assert std.basetemp != integ.basetemp
    assert "standard" in std.cache_dir and "standard" in std.basetemp
    assert "integration" in integ.cache_dir and "integration" in integ.basetemp
    # outside the repository
    for path in (std.cache_dir, std.basetemp, integ.cache_dir, integ.basetemp):
        assert not path.startswith(str(REPO_ROOT))
    # unique OS-temp root (gettempdir-based) — run_root is unique
    assert str(run_root) not in (None, "")


# ---------------------------------------------------------------------------
# Failure behavior
# ---------------------------------------------------------------------------

def test_first_failure_stops_subsequent_gates():
    record = []
    # Fail at gate 2 (security_scan); gates 3 & 4 must never run.
    runner = _fake_runner_factory(record, rc_by_gate={"security_scan": 1})
    rc = civ.run_all(REPO_ROOT, runner=runner)
    assert rc == 1
    seen = [c["gate"] for c in record]
    assert "smoke" in seen
    assert "security_scan" in seen
    assert "standard_population" not in seen
    assert "integration_population" not in seen


def test_failing_exit_code_is_propagated():
    record = []
    runner = _fake_runner_factory(record, rc_by_gate={"standard_population": 7})
    rc = civ.run_all(REPO_ROOT, runner=runner)
    assert rc == 7  # exact child exit code, not a generic verifier code


def test_failing_gate_name_reported_and_no_false_pass(capsys):
    record = []
    runner = _fake_runner_factory(record, rc_by_gate={"integration_population": 3})
    rc = civ.run_all(REPO_ROOT, runner=runner)
    out = capsys.readouterr().out
    assert rc == 3
    # the failing gate is identified by name
    assert "GATE integration_population FAIL" in out
    assert "OVERALL FAIL" in out
    assert "OVERALL PASS" not in out
    # prior gates are reported (their gate ids appear in headers + commands)
    assert "smoke" in out
    assert "security_scan" in out
    assert "standard_population" in out


def test_keyboard_interrupt_returns_interrupted_code():
    def runner(argv, cwd=None, env=None):
        raise KeyboardInterrupt()

    rc = civ.run_all(REPO_ROOT, runner=runner)
    assert rc == civ.EXIT_INTERRUPTED


# ---------------------------------------------------------------------------
# Environment behavior
# ---------------------------------------------------------------------------

def test_existing_environment_copied_and_path_prepended():
    record = []
    runner = _fake_runner_factory(record)
    civ.run_all(REPO_ROOT, runner=runner)
    media_calls = [c for c in record if c["env"] is not None]
    assert media_calls
    for c in media_calls:
        env = c["env"]
        # copy of current environment (every original key present)
        for key in os.environ:
            assert key in env
        # PATH prepended, not replaced
        assert env["PATH"].startswith(str(civ._MEDIA_SHIM_DIR))
        assert os.environ.get("PATH", "") in env["PATH"]


def test_media_bins_child_local_and_not_permanent():
    record = []
    runner = _fake_runner_factory(record)
    # Snapshot the environment immediately before the verifier call and prove
    # the verifier does NOT mutate the real process environment (process-local
    # media env is passed only to child processes).
    before = dict(os.environ)
    civ.run_all(REPO_ROOT, runner=runner)
    after = dict(os.environ)
    media_calls = [c for c in record if c["env"] is not None]
    for c in media_calls:
        assert c["env"]["SCOS_FFMPEG_BIN"] == str(civ._MEDIA_FFMPEG)
        assert c["env"]["SCOS_FFPROBE_BIN"] == str(civ._MEDIA_FFPROBE)
    # verifier must not mutate the real os.environ
    assert set(before.keys()) == set(after.keys())
    for key in before:
        assert before[key] == after[key], f"verifier mutated env key {key}"


def test_media_preflight_failure_blocks_media_gates(monkeypatch):
    monkeypatch.setattr(civ, "_verify_media_binary", lambda p: False)
    record = []
    rc = civ.run_all(REPO_ROOT, runner=_fake_runner_factory(record))
    assert rc == civ.EXIT_VERIFIER_ERROR
    # no pytest gate should have run (blocked at preflight)
    assert not any(c["gate"] in ("standard_population", "integration_population")
                   for c in record)


# ---------------------------------------------------------------------------
# Isolation behavior
# ---------------------------------------------------------------------------

def test_repository_paths_not_used_for_cache_or_basetemp():
    interp = civ.detect_interpreter(REPO_ROOT)
    gates = civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-iso")
    for g in gates:
        if not g.is_pytest:
            continue
        assert not g.cache_dir.startswith(str(REPO_ROOT))
        assert not g.basetemp.startswith(str(REPO_ROOT))
        assert g.cache_dir != g.basetemp


def test_verifier_owned_run_root_is_identifiable_and_not_deleted():
    import tempfile
    interp = civ.detect_interpreter(REPO_ROOT)
    record = []
    rc, run_root = civ.run_all(
        REPO_ROOT, runner=_fake_runner_factory(record), return_run_root=True,
    )
    assert rc == 0
    assert run_root is not None
    # run root lives under the OS temp dir, outside the repo
    assert str(run_root).startswith(tempfile.gettempdir())
    assert not str(run_root).startswith(str(REPO_ROOT))
    # verifier does NOT delete the run root by default (evidence persists)
    assert Path(run_root).exists()


# ---------------------------------------------------------------------------
# CI parity (semantic, not brittle full-text equality)
# ---------------------------------------------------------------------------

def test_ci_workflow_contains_both_warning_guards_on_both_populations():
    ci_gates = _parse_ci_gates()
    pytest_gates = [run for _id, run in ci_gates if "pytest" in run or "-m" in run]
    assert len(pytest_gates) == 2, "expected exactly two pytest populations in CI"
    for run in pytest_gates:
        assert "-W error::pytest.PytestConfigWarning" in run
        assert "-W error::pytest.PytestUnhandledThreadExceptionWarning" in run
        assert "no:cacheprovider" not in run


def test_ci_verification_gate_order_matches_local():
    ci_gates = [gid for gid, _ in _parse_ci_gates()]
    interp = civ.detect_interpreter(REPO_ROOT)
    local_gates = [g.gate_id for g in civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-parity")]
    assert ci_gates == local_gates == EXPECTED_GATE_ORDER


def test_ci_and_local_markers_and_targets_correspond():
    ci_gates = dict(_parse_ci_gates())
    interp = civ.detect_interpreter(REPO_ROOT)
    local = {g.gate_id: g for g in civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-parity")}

    ci_std = ci_gates["standard_population"]
    assert '-m "not integration"' in ci_std or "-m not integration" in ci_std
    assert local["standard_population"].marker == "not integration"

    ci_int = ci_gates["integration_population"]
    assert "-m integration" in ci_int
    assert local["integration_population"].marker == "integration"

    for gid in ("standard_population", "integration_population"):
        ci_run = ci_gates[gid]
        for target in ("integrations", "scos", "scripts"):
            assert target in ci_run
            assert target in local[gid].argv


def test_ci_and_local_warning_guards_are_identical():
    ci_gates = dict(_parse_ci_gates())
    interp = civ.detect_interpreter(REPO_ROOT)
    local = {g.gate_id: g for g in civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-parity")}
    for gid in ("standard_population", "integration_population"):
        ci_run = ci_gates[gid]
        for guard in civ.WARNING_GUARDS:
            assert guard in ci_run
            assert guard in local[gid].argv


def test_ci_uses_python_interpreter_local_uses_venv(monkeypatch):
    ci_gates = dict(_parse_ci_gates())
    # CI uses `python` (setup-python provides 3.11); local uses canonical .venv.
    assert "python" in ci_gates["smoke"]
    assert "python" in ci_gates["security_scan"]
    interp = civ.detect_interpreter(REPO_ROOT)
    local = {g.gate_id: g for g in civ.build_gates(REPO_ROOT, interp, Path(tempfile.gettempdir()) / "scos-test-parity")}
    assert str(interp) in local["smoke"].argv[0]
    assert str(interp) in local["security_scan"].argv[0]


# ---------------------------------------------------------------------------
# Negative: wrong repository / missing interpreter / missing binaries
# ---------------------------------------------------------------------------

def test_refuses_wrong_repository_root(monkeypatch, capsys):
    fake_root = REPO_ROOT / "nonexistent-repo-root-xyz"
    monkeypatch.setattr(civ, "find_repo_root", lambda: fake_root)
    rc = civ.main([])
    assert rc == civ.EXIT_VERIFIER_ERROR
    assert "REFUSAL" in capsys.readouterr().err


def test_missing_interpreter_returns_verifier_error(monkeypatch):
    def boom(_root):
        raise FileNotFoundError("no interpreter")

    monkeypatch.setattr(civ, "detect_interpreter", boom)
    rc = civ.run_all(REPO_ROOT, runner=_fake_runner_factory([]))
    assert rc == civ.EXIT_VERIFIER_ERROR


def test_missing_ffmpeg_or_ffprobe_blocks(monkeypatch):
    def one_missing(path):
        # ffmpeg present, ffprobe missing -> preflight must fail
        return "ffprobe" not in str(path)

    monkeypatch.setattr(civ, "_verify_media_binary", one_missing)
    record = []
    rc = civ.run_all(REPO_ROOT, runner=_fake_runner_factory(record))
    assert rc == civ.EXIT_VERIFIER_ERROR
    assert not any(c["gate"] in ("standard_population", "integration_population")
                   for c in record)


def test_plan_mode_prints_contract_without_executing(capsys):
    rc = civ.main(["--plan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PLAN OK" in out
    assert "standard_population" in out
    assert "integration_population" in out
    assert "PytestConfigWarning" in out


def test_verifier_creates_per_gate_cache_and_basetemp_dirs():
    """Anti-false-green: the verifier must create each pytest gate's unique
    OS-temp cache_dir and basetemp on disk (Windows basetemp startup race)."""
    record = []
    rc, run_root = civ.run_all(
        REPO_ROOT, runner=_fake_runner_factory(record), return_run_root=True,
    )
    assert rc == 0
    # The per-gate cache/basetemp dirs must now exist outside the repo.
    for gate_id in ("standard_population", "integration_population"):
        gate = next(g for g in civ.build_gates(
            REPO_ROOT, civ.detect_interpreter(REPO_ROOT), run_root) if g.gate_id == gate_id)
        cache = Path(gate.cache_dir)
        base = Path(gate.basetemp)
        assert cache.is_dir(), f"cache_dir not created: {cache}"
        assert base.is_dir(), f"basetemp not created: {base}"
        assert not str(cache).startswith(str(REPO_ROOT))
        assert not str(base).startswith(str(REPO_ROOT))
