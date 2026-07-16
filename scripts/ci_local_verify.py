"""SCOS local CI-parity verifier (Cohort 8C).

Deterministic local reproduction of the committed GitHub Actions quality gates
in ``.github/workflows/ci.yml``. The verifier runs the SAME verification gates,
in the SAME order, with the SAME interpreter, test targets, marker selection,
warning filters, cache/basetemp isolation, media environment, and exit-code
semantics as CI.

Authoritative CI gate contract (verification gates only; first 4 CI steps are
GitHub-host setup: checkout / setup-python / apt ffmpeg / pip install):

    1. Smoke                       ``python scripts/test_smoke.py``
    2. Security scan baseline      ``python scripts/security_scan_baseline.py``
    3. Control Center typecheck    ``node ./node_modules/typescript/bin/tsc
                                       --noEmit --incremental false``
                                     (cwd apps/control-center)
    4. Control Center lint         ``npm run lint`` (cwd apps/control-center)
    5. Control Center frontend     ``npx vitest run --no-file-parallelism``
       tests                        (cwd apps/control-center)
    6. Control Center production   ``npm run build`` (cwd apps/control-center)
       build
    7. Browser acceptance          ``python scripts/control_center_truth_gate.py``
       (structural truth gate)
    8. Certified Standard pop.     ``python -m pytest integrations scos scripts
                                       -m "not integration"
                                       -o cache_dir=<temp>/.../cache
                                       --basetemp <temp>/.../basetemp
                                       -W error::pytest.PytestConfigWarning
                                       -W error::pytest.PytestUnhandledThreadExceptionWarning
                                       -q``
    9. Certified Explicit Integration pop.  (same, ``-m integration``)

Cohort 9D: gates 3-7 are the Control Center frontend gate set, added to BOTH
ci.yml and this verifier in the SAME order and with SAME semantics. The browser
acceptance gate (7) is the structural, install-free, CI-safe truth-contract
enforcer; the full desktop/mobile viewport matrix is executed out-of-band by the
certifying agent and is not a subprocess here (no new browser driver, no egress).

Design contract (Cohort 8C):
- Repository root is located deterministically (this file lives in ``scripts/``).
- Refuses to run from/against the wrong repository.
- Uses ``.venv/Scripts/python.exe`` (Windows) — canonical interpreter.
- Builds every child command as an argv list; never ``shell=True``.
- Creates a unique OS-temp run root; per-pytest-gate unique cache_dir and basetemp.
- cacheprovider stays enabled (NO ``-p no:cacheprovider``).
- Applies both warning-as-error guards on every pytest population.
- Standard and Integration remain SEPARATE gates.
- Stops on the first non-zero gate exit; returns that exit code.
- Stable non-zero verifier error code for preflight failures.
- Performs NO repository mutation; cleans only verifier-owned temp paths.
- Media binaries (ffmpeg/ffprobe) are resolved and required; their env is
  process-local (PATH prepend, never replace), no permanent machine change.

Usage:
    .venv/Scripts\\python.exe scripts\\ci_local_verify.py
    .venv/Scripts\\python.exe scripts\\ci_local_verify.py --plan   # read-only inspection
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Canonical constants (the shared SCOS/HVS contract, Cohort 8C §6)
# ---------------------------------------------------------------------------

# Canonical interpreter relative form resolved against the detected repo root.
_VENV_RELATIVE = Path(".venv") / "Scripts" / "python.exe"
_VENV_RELATIVE_POSIX = Path(".venv") / "bin" / "python"  # non-Windows fallback

# Control Center frontend (Cohort 9D). Node/npm/npx are resolved on PATH with
# the SAME command semantics as CI (which runs `npm run lint`, `npx vitest run`,
# `node tsc` directly). On Windows the bare names (`npm`) are `.cmd` shims that
# CreateProcess cannot launch without the extension, so resolve the real
# executable via shutil.which; the launched program and arguments are identical
# to CI, preserving gate parity.
_CONTROL_CENTER_DIR = Path("apps") / "control-center"
_NPM_BIN = shutil.which("npm") or "npm"
_NPX_BIN = shutil.which("npx") or "npx"
_NODE_BIN = shutil.which("node") or "node"
if os.name == "nt":
    _TSC_BIN = "node_modules\\typescript\\bin\\tsc"
else:
    _TSC_BIN = "node_modules/.bin/tsc"

# Process-local media contract (Cohort 8C §6).
_MEDIA_SHIM_DIR = Path("C:/Users/chara/scoop/shims")
_MEDIA_FFMPEG = _MEDIA_SHIM_DIR / "ffmpeg.exe"
_MEDIA_FFPROBE = _MEDIA_SHIM_DIR / "ffprobe.exe"

# Required warning-as-error guards (Cohort 8C §7). Never blanket ``-W error``.
WARNING_GUARDS: tuple[str, str] = (
    "error::pytest.PytestConfigWarning",
    "error::pytest.PytestUnhandledThreadExceptionWarning",
)

# Pytest test targets collected in CI (integrations/scos/scripts).
PYTEST_TARGETS: tuple[str, ...] = ("integrations", "scos", "scripts")

# Cohort 8C stable verifier exit codes.
EXIT_VERIFIER_ERROR = 2  # preflight / internal verifier failure
EXIT_GATE_FAILURE = None  # replaced per gate by the child's own exit code
EXIT_INTERRUPTED = 130  # keyboard interruption

_VERIFIER_NAME = "SCOS local CI-parity verifier (Cohort 8C)"


@dataclass
class Gate:
    """A single CI-parity gate: command construction + execution metadata."""

    order: int
    gate_id: str
    argv: List[str]
    extra_env: Optional[dict] = None
    media_sensitive: bool = False
    is_pytest: bool = False
    marker: Optional[str] = None
    cache_dir: Optional[str] = None
    basetemp: Optional[str] = None


# ---------------------------------------------------------------------------
# Repository resolution
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Return the SCOS repository root (two levels above this file)."""
    return Path(__file__).resolve().parents[1]


def detect_interpreter(repo_root: Path) -> Path:
    """Return the canonical ``.venv`` interpreter, preferring the Windows form."""
    win = repo_root / _VENV_RELATIVE
    posix = repo_root / _VENV_RELATIVE_POSIX
    if win.is_file():
        return win
    if posix.is_file():
        return posix
    raise FileNotFoundError(
        f"canonical interpreter not found: neither {win} nor {posix} exists"
    )


# ---------------------------------------------------------------------------
# Media precondition (process-local; never mutate the machine)
# ---------------------------------------------------------------------------

def _verify_media_binary(path: Path) -> bool:
    """True iff the binary resolves and ``-version`` exits 0 (case-insensitive)."""
    if not path.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(path), "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError:
        return False
    return proc.returncode == 0


def build_media_env(base_env: dict) -> dict:
    """Return a COPY of ``base_env`` with PATH prepended and ffmpeg bins set.

    The current environment is copied; PATH is prepended (never replaced); no
    permanent machine mutation occurs. Raises RuntimeError if the required
    binaries cannot be resolved.
    """
    env = dict(base_env)
    ffmpeg = _MEDIA_FFMPEG
    ffprobe = _MEDIA_FFPROBE
    if not _verify_media_binary(ffmpeg):
        raise RuntimeError(
            f"required media binary not resolvable: {ffmpeg} "
            f"(install via scoop: scoop install ffmpeg)"
        )
    if not _verify_media_binary(ffprobe):
        raise RuntimeError(
            f"required media binary not resolvable: {ffprobe} "
            f"(install via scoop: scoop install ffmpeg)"
        )
    existing_path = env.get("PATH", "")
    # Prepend the shim dir; keep the rest untouched.
    env["PATH"] = (
        str(_MEDIA_SHIM_DIR)
        + (os.pathsep + existing_path if existing_path else "")
    )
    env["SCOS_FFMPEG_BIN"] = str(ffmpeg)
    env["SCOS_FFPROBE_BIN"] = str(ffprobe)
    return env


# ---------------------------------------------------------------------------
# Gate construction
# ---------------------------------------------------------------------------

def _pytest_population_args(
    interpreter: Path,
    marker: str,
    cache_dir: str,
    basetemp: str,
) -> List[str]:
    argv = [
        str(interpreter),
        "-m", "pytest",
        *PYTEST_TARGETS,
        "-m", marker,
        "-o", f"cache_dir={cache_dir}",
        "--basetemp", basetemp,
    ]
    for guard in WARNING_GUARDS:
        argv += ["-W", guard]
    argv += ["-q"]
    return argv


def build_gates(
    repo_root: Path,
    interpreter: Path,
    run_root: Path,
) -> List[Gate]:
    """Construct the ordered CI-parity gates.

    run_root is a unique OS-temp directory created by the caller (one run root
    per invocation). Each pytest gate receives its own unique cache_dir and
    basetemp under run_root, all OUTSIDE the repository.
    """
    gates: List[Gate] = []

    # 1. Smoke gate.
    gates.append(Gate(
        order=1,
        gate_id="smoke",
        argv=[str(interpreter), str(repo_root / "scripts" / "test_smoke.py")],
    ))

    # 2. Security scan baseline.
    gates.append(Gate(
        order=2,
        gate_id="security_scan",
        argv=[str(interpreter),
              str(repo_root / "scripts" / "security_scan_baseline.py")],
    ))

    # 3. Control Center typecheck (frontend, Cohort 9D).
    gates.append(Gate(
        order=3,
        gate_id="cc_typecheck",
        argv=[_NODE_BIN,
              _TSC_BIN,
              "--noEmit", "--incremental", "false"],
        extra_env={"CHANGE_DIR": str(repo_root / _CONTROL_CENTER_DIR)},
    ))

    # 4. Control Center lint (frontend, Cohort 9D).
    gates.append(Gate(
        order=4,
        gate_id="cc_lint",
        argv=[_NPM_BIN, "run", "lint"],
        extra_env={"CHANGE_DIR": str(repo_root / _CONTROL_CENTER_DIR)},
    ))

    # 5. Control Center frontend tests (frontend, Cohort 9D).
    gates.append(Gate(
        order=5,
        gate_id="cc_frontend_tests",
        argv=[_NPX_BIN, "vitest", "run", "--no-file-parallelism"],
        extra_env={"CHANGE_DIR": str(repo_root / _CONTROL_CENTER_DIR)},
    ))

    # 6. Control Center production build (frontend, Cohort 9D).
    gates.append(Gate(
        order=6,
        gate_id="cc_build",
        argv=[_NPM_BIN, "run", "build"],
        extra_env={"CHANGE_DIR": str(repo_root / _CONTROL_CENTER_DIR)},
    ))

    # 7. Browser acceptance (structural truth gate, Cohort 9D). Install-free,
    #    CI-safe, no subprocess egress. Mirrors the repo-supported command.
    gates.append(Gate(
        order=7,
        gate_id="cc_browser_acceptance",
        argv=[str(interpreter),
              str(repo_root / "scripts" / "control_center_truth_gate.py")],
    ))

    # 8. Certified Standard population.
    std_cache = str(run_root / "standard" / "cache")
    std_base = str(run_root / "standard" / "basetemp")
    gates.append(Gate(
        order=8,
        gate_id="standard_population",
        argv=_pytest_population_args(interpreter, "not integration", std_cache, std_base),
        media_sensitive=True,
        is_pytest=True,
        marker="not integration",
        cache_dir=std_cache,
        basetemp=std_base,
    ))

    # 9. Certified Explicit Integration population.
    int_cache = str(run_root / "integration" / "cache")
    int_base = str(run_root / "integration" / "basetemp")
    gates.append(Gate(
        order=9,
        gate_id="integration_population",
        argv=_pytest_population_args(interpreter, "integration", int_cache, int_base),
        media_sensitive=True,
        is_pytest=True,
        marker="integration",
        cache_dir=int_cache,
        basetemp=int_base,
    ))

    return gates


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _quote(argv: Sequence[str]) -> str:
    """Safely quote an argv list for display (no shell execution)."""
    out = []
    for tok in argv:
        if " " in tok or any(c in tok for c in "\"'\\"):
            out.append('"' + tok.replace('"', '\\"') + '"')
        else:
            out.append(tok)
    return " ".join(out)


def run_gate(
    gate: Gate,
    repo_root: Path,
    runner: Callable[..., int],
) -> int:
    """Execute one gate and return its exit code.

    ``runner`` mirrors ``subprocess.run(argv, cwd=..., env=...).returncode`` and
    is injectable for testing. The real runner applies the process-local media
    environment for media-sensitive gates. Cohort 9D: a gate may request a
    different working directory via ``extra_env["CHANGE_DIR"]`` (used by the
    Control Center frontend gates, which run in apps/control-center).
    """
    cwd = repo_root
    if gate.extra_env and "CHANGE_DIR" in gate.extra_env:
        cwd = Path(gate.extra_env["CHANGE_DIR"])
    print(f"\n=== GATE {gate.order}: {gate.gate_id} ===")
    print(f"  cwd : {cwd}")
    print(f"  cmd : {_quote(gate.argv)}")
    if gate.is_pytest:
        print(f"  marker     : {gate.marker}")
        print(f"  cache_dir  : {gate.cache_dir}")
        print(f"  basetemp   : {gate.basetemp}")
        print(f"  warning    : {', '.join(WARNING_GUARDS)}")
    if gate.media_sensitive:
        print(f"  media env  : PATH prepended with scoop shims; "
              f"SCOS_FFMPEG_BIN / SCOS_FFPROBE_BIN process-local")

    # Ensure unique OS-temp cache/basetemp paths exist before launching pytest.
    # On Windows pytest creates only the basetemp LEAF (mkdir without parents),
    # so the parent chain must already exist — mirroring the GitHub Actions
    # ``mkdir`` setup step that provisions ``${{ runner.temp }}/...``.
    if gate.is_pytest:
        for p in (gate.cache_dir, gate.basetemp):
            if p:
                Path(p).mkdir(parents=True, exist_ok=True)

    env = None
    if gate.media_sensitive:
        env = build_media_env(dict(os.environ))
    rc = runner(gate.argv, cwd=str(cwd), env=env)
    return rc


def _real_runner(argv: Sequence[str], cwd: str, env: Optional[dict]) -> int:
    proc = subprocess.run(list(argv), cwd=cwd, env=env, shell=False)
    return proc.returncode


def run_all(
    repo_root: Path,
    interpreter: Optional[Path] = None,
    run_root: Optional[Path] = None,
    runner: Callable[..., int] = _real_runner,
    log: Optional[list] = None,
    return_run_root: bool = False,
) -> int | tuple[int, Optional[Path]]:
    """Run all gates in order; stop on first failure.

    Returns:
        - the failing gate's exit code (propagated) on first gate failure;
        - 0 if all gates pass;
        - EXIT_VERIFIER_ERROR on preflight failure.
    ``log`` (optional) collects per-gate result dicts for callers/tests.
    """
    # Preflight: locate the canonical interpreter (fail closed if absent).
    try:
        if interpreter is None:
            interpreter = detect_interpreter(repo_root)
    except (FileNotFoundError, OSError) as exc:
        print(f"PREFLIGHT FAIL: cannot locate canonical interpreter: {exc}",
              file=sys.stderr)
        if return_run_root:
            return EXIT_VERIFIER_ERROR, run_root
        return EXIT_VERIFIER_ERROR

    if not interpreter.is_file():
        print(f"PREFIGHT FAIL: canonical interpreter missing: {interpreter}",
              file=sys.stderr)
        if return_run_root:
            return EXIT_VERIFIER_ERROR, run_root
        return EXIT_VERIFIER_ERROR

    # Unique OS-temp run root (one per invocation).
    if run_root is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_root = Path(tempfile.gettempdir()) / f"scos-ci-local-{stamp}-{os.getpid()}"

    run_root.mkdir(parents=True, exist_ok=True)
    print(f"\n{_VERIFIER_NAME}")
    print(f"repo root : {repo_root}")
    print(f"interp    : {interpreter}")
    print(f"run root  : {run_root}")

    # Preflight: media binaries (media-sensitive gates depend on them).
    try:
        build_media_env(dict(os.environ))
    except RuntimeError as exc:
        print(f"PREFLIGHT FAIL: {exc}", file=sys.stderr)
        print("RESULT: GATE preflight FAIL (media precondition)")
        if return_run_root:
            return EXIT_VERIFIER_ERROR, run_root
        return EXIT_VERIFIER_ERROR

    gates = build_gates(repo_root, interpreter, run_root)

    results = []
    for gate in gates:
        try:
            rc = run_gate(gate, repo_root, runner)
        except KeyboardInterrupt:
            print(f"\nINTERRUPTED at gate {gate.order} ({gate.gate_id})",
                  file=sys.stderr)
            if log is not None:
                results.append({"gate": gate.gate_id, "exit": EXIT_INTERRUPTED,
                                "interrupted": True})
            if return_run_root:
                return EXIT_INTERRUPTED, run_root
            return EXIT_INTERRUPTED
        except RuntimeError as exc:
            # media precondition failure surfaces here for media gates
            print(f"GATE {gate.gate_id} BLOCKED: {exc}", file=sys.stderr)
            if log is not None:
                results.append({"gate": gate.gate_id, "exit": EXIT_VERIFIER_ERROR,
                                "blocked": True})
            if return_run_root:
                return EXIT_VERIFIER_ERROR, run_root
            return EXIT_VERIFIER_ERROR

        if log is not None:
            results.append({"gate": gate.gate_id, "exit": rc})
        if rc != 0:
            print(f"\nRESULT: GATE {gate.gate_id} FAIL (exit {rc})")
            print("RESULT: OVERALL FAIL")
            if return_run_root:
                return rc, run_root
            return rc  # propagate exact failing exit code

    print("\nRESULT: ALL GATES PASS")
    print("RESULT: OVERALL PASS")
    if return_run_root:
        return 0, run_root
    return 0


# ---------------------------------------------------------------------------
# Read-only inspection (Cohort 8C §20)
# ---------------------------------------------------------------------------

def plan(repo_root: Path, interpreter: Optional[Path] = None) -> int:
    """Print the constructed contract without executing any gate."""
    if interpreter is None:
        try:
            interpreter = detect_interpreter(repo_root)
        except FileNotFoundError as exc:
            print(f"PLAN FAIL: {exc}", file=sys.stderr)
            return EXIT_VERIFIER_ERROR

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root = Path(tempfile.gettempdir()) / f"scos-ci-local-{stamp}-{os.getpid()}"
    gates = build_gates(repo_root, interpreter, run_root)

    print(f"\n{_VERIFIER_NAME} — PLAN (read-only, no execution)")
    print(f"repo root : {repo_root}")
    print(f"interp    : {interpreter}")
    print(f"run root  : {run_root}  (unique OS-temp; not created in --plan)")
    print("media precond : PATH prepend C:/Users/chara/scoop/shims; "
          "SCOS_FFMPEG_BIN / SCOS_FFPROBE_BIN process-local")
    print("warning guards: " + ", ".join(WARNING_GUARDS))
    print("cacheprovider : enabled (no -p no:cacheprovider)")
    print("gate order:")
    for gate in gates:
        print(f"  {gate.order}. {gate.gate_id}")
        print(f"       {_quote(gate.argv)}")
        if gate.is_pytest:
            print(f"       marker={gate.marker} cache_dir={gate.cache_dir} "
                  f"basetemp={gate.basetemp}")
    print(f"\nPLAN OK — {len(gates)} gates; CI parity order preserved")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=_VERIFIER_NAME)
    parser.add_argument(
        "--plan", action="store_true",
        help="read-only inspection: print gate contract, do not execute",
    )
    parser.add_argument(
        "--repo-root", default=None,
        help="override repository root (advanced; normally auto-detected)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="remove the verifier-owned OS-temp run root after a successful run "
             "(off by default so evidence persists for audit)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root()

    # Refuse to run against the wrong repository: this file must live in
    # <root>/scripts/ci_local_verify.py and the root must contain the CI workflow.
    if not (repo_root / ".github" / "workflows" / "ci.yml").is_file():
        print(f"REFUSAL: {repo_root} is not the SCOS repository "
              f"(missing .github/workflows/ci.yml)", file=sys.stderr)
        return EXIT_VERIFIER_ERROR
    if not (repo_root / "scripts" / "ci_local_verify.py").samefile(Path(__file__)):
        print("REFUSAL: invoked against a different repository layout",
              file=sys.stderr)
        return EXIT_VERIFIER_ERROR

    if args.plan:
        return plan(repo_root)

    try:
        rc, used_run_root = run_all(repo_root, return_run_root=True)
    except KeyboardInterrupt:
        print("\nINTERRUPTED", file=sys.stderr)
        return EXIT_INTERRUPTED

    if args.clean and used_run_root is not None and rc == 0:
        import shutil
        shutil.rmtree(used_run_root, ignore_errors=True)
        print(f"cleaned verifier-owned run root: {used_run_root}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
