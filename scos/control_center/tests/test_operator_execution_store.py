"""test_operator_execution_store.py - SCOS Stage 5.9 JSONL store suite.

Plain executable script (no pytest). Covers append/load round-trips, order
preservation, deterministic line bytes, URL rejection, and malformed-JSONL
failure.

Run: python scos/control_center/tests/test_operator_execution_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_execution_runbook import (  # noqa: E402
    capture_manual_command_result,
    classify_operator_execution_outcome,
    create_git_commit_runbook,
)
from operator_execution_store import (  # noqa: E402
    append_command_execution_capture,
    append_manual_command_runbook,
    append_operator_execution_outcome,
    load_command_execution_captures,
    load_manual_command_runbooks,
    load_operator_execution_outcomes,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _raises(fn, exc_type=ValueError) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True


def _lifecycle():
    rb = create_git_commit_runbook(
        session_id="sess-59", task_id="task-59",
        commit_message="feat(control-center): add Stage 5.9 local operator execution console",
        staged_paths=["scos/control_center/operator_execution_models.py"],
        created_at="2026-07-06T00:00:00Z")
    cap = capture_manual_command_result(
        runbook=rb, operator_reported_command="git commit",
        pasted_output_summary="committed",
        raw_output_excerpt="[main a1b2c3] working tree clean",
        exit_status_text="exit 0", captured_at="2026-07-06T01:00:00Z")
    outcome = classify_operator_execution_outcome(
        runbook=rb, capture=cap, created_at="2026-07-06T02:00:00Z")
    return rb, cap, outcome


def test_1_runbook_roundtrip():
    tmp = tempfile.mkdtemp()
    try:
        rb, _, _ = _lifecycle()
        path = Path(tmp) / "runbooks.jsonl"
        append_manual_command_runbook(path, rb)
        append_manual_command_runbook(path, rb)
        loaded = load_manual_command_runbooks(path)
        check("two records appended", len(loaded) == 2)
        check("round-trip preserves to_dict", loaded[0].to_dict() == rb.to_dict())
        check("returns a tuple", isinstance(loaded, tuple))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_capture_and_outcome_roundtrip():
    tmp = tempfile.mkdtemp()
    try:
        _, cap, outcome = _lifecycle()
        cpath = Path(tmp) / "captures.jsonl"
        opath = Path(tmp) / "outcomes.jsonl"
        append_command_execution_capture(cpath, cap)
        append_operator_execution_outcome(opath, outcome)
        check("capture round-trip", load_command_execution_captures(cpath)[0].to_dict() == cap.to_dict())
        check("outcome round-trip", load_operator_execution_outcomes(opath)[0].to_dict() == outcome.to_dict())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_deterministic_line_and_order():
    tmp = tempfile.mkdtemp()
    try:
        rb, _, _ = _lifecycle()
        path = Path(tmp) / "sub" / "dir" / "runbooks.jsonl"
        append_manual_command_runbook(path, rb)
        text = path.read_text(encoding="utf-8")
        check("parent dirs auto-created", path.is_file())
        check("single LF-terminated line", text.count("\n") == 1 and text.endswith("\n"))
        check("sorted keys deterministic", text.index('"created_at"') < text.index('"task_id"'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_4_missing_file_and_malformed():
    tmp = tempfile.mkdtemp()
    try:
        missing = Path(tmp) / "nope.jsonl"
        check("missing file -> empty tuple", load_manual_command_runbooks(missing) == ())
        check("list does not create file", not missing.exists())
        bad = Path(tmp) / "bad.jsonl"
        bad.write_text("{not json}\n", encoding="utf-8")
        check("malformed JSONL raises", _raises(lambda: load_manual_command_runbooks(bad)))
        notobj = Path(tmp) / "arr.jsonl"
        notobj.write_text("[1,2,3]\n", encoding="utf-8")
        check("non-object line raises", _raises(lambda: load_manual_command_runbooks(notobj)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_5_url_path_rejected():
    rb, _, _ = _lifecycle()
    check("http path rejected", _raises(lambda: append_manual_command_runbook("http://x/y.jsonl", rb)))
    check("https load rejected", _raises(lambda: load_manual_command_runbooks("https://x/y.jsonl")))
    check("wrong type rejected", _raises(lambda: append_manual_command_runbook(
        Path(tempfile.mkdtemp()) / "r.jsonl", "not-a-runbook")))


def main() -> int:
    tests = [
        test_1_runbook_roundtrip,
        test_2_capture_and_outcome_roundtrip,
        test_3_deterministic_line_and_order,
        test_4_missing_file_and_malformed,
        test_5_url_path_rejected,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
