"""test_system_qualification.py — SCOS Stage 2.4 certification gate test.

Runs the full System Qualification suite and asserts a deterministic 100/100 PASS
certification, a valid report, reproducibility across two runs, and that the suite is
read-only (production source unchanged).

Run: python scos/qualification/tests/test_system_qualification.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_HERE.parent))     # for `import system_qualification`

import system_qualification as SQ          # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _prod_sources():
    files = []
    for p in (_REPO_ROOT / "scos").rglob("*.py"):
        if "tests" in p.parts or "qualification" in p.parts or "__pycache__" in p.parts:
            continue
        files.append(p)
    return sorted(files)


def _snapshot(files):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 2.4 — SYSTEM QUALIFICATION — GATE TEST"); print("=" * 60)

    prod = _prod_sources()
    before = _snapshot(prod)

    with tempfile.TemporaryDirectory() as tmp:
        wd1 = Path(tmp) / "q1"
        report = SQ.SystemQualification(now_fn=lambda: 0, work_dir=wd1).run_all()

        print("\n[1] certification result")
        check("status PASS", report["status"] == "PASS")
        check("all 10 qualifications true", all(report["tests"].values()) and len(report["tests"]) == 10)
        score = sum(10 for v in report["tests"].values() if v)
        check("score 100/100", score == 100)
        check("qualified_stage Stage 2", report["qualified_stage"] == "Stage 2")
        check("qualification_time deterministic (0)", report["qualification_time"] == 0)

        print("\n[2] report persisted + valid")
        rp = wd1 / "certification_report.json"
        check("certification_report.json written", rp.exists())
        reloaded = json.loads(rp.read_text(encoding="utf-8"))
        check("report reload-recoverable", reloaded == report)

        print("\n[3] determinism — second full run is byte-identical")
        wd2 = Path(tmp) / "q2"
        report2 = SQ.SystemQualification(now_fn=lambda: 0, work_dir=wd2).run_all()
        check("identical status/score/tests", report2 == report)
        b1 = (wd1 / "certification_report.json").read_text(encoding="utf-8")
        b2 = (wd2 / "certification_report.json").read_text(encoding="utf-8")
        check("identical report bytes", b1 == b2)

    print("\n[4] read-only — production sources unchanged")
    after = _snapshot(prod)
    check("no production source modified", before == after)

    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
