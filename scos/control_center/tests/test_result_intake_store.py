"""test_result_intake_store.py - SCOS Stage 5.7 result intake JSONL store suite.

Plain executable script (no pytest). Covers append/load round trips for all
four record types, deterministic JSONL formatting, malformed-line handling,
URL root rejection, and "list-only creates nothing" behavior.

Run: python scos/control_center/tests/test_result_intake_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from result_intake_builder import (  # noqa: E402
    build_chatgpt_status_update_packet,
    build_next_action_decision,
    build_project_state_update,
    build_result_intake_record,
)
from result_intake_models import AIResultIntakeRecord  # noqa: E402
from result_intake_store import ResultIntakeStore  # noqa: E402

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


def _make_record() -> AIResultIntakeRecord:
    record = build_result_intake_record(
        session_id="sess-1",
        task_id="task-1",
        source_agent="claude_code",
        source_runtime_id="runtime-1",
        raw_result_text="All tests passed. Verdict: PASS",
        created_at="2026-07-06T00:00:00Z",
        title="Implementation result",
    )
    assert isinstance(record, AIResultIntakeRecord), record
    return record


def test_1_append_and_load_all_record_types() -> None:
    print("\n[1] append/load all record types")
    tmp = Path(tempfile.mkdtemp(prefix="scos-result-intake-"))
    try:
        store = ResultIntakeStore(tmp)
        record = _make_record()
        packet = build_chatgpt_status_update_packet(
            intake_record=record,
            target_runtime_id="chatgpt-web",
            created_at="2026-07-06T00:05:00Z",
            requested_chatgpt_action="summarize_status",
        )
        state_update = build_project_state_update(
            intake_record=record,
            previous_stage="5.6",
            current_stage="5.7",
            updated_at="2026-07-06T00:10:00Z",
        )
        decision = build_next_action_decision(intake_record=record, created_at="2026-07-06T00:15:00Z")

        store.append_intake(record)
        store.append_chatgpt_status_update(packet)
        store.append_project_state_update(state_update)
        store.append_next_action_decision(decision)

        loaded_intakes = store.list_intakes()
        loaded_updates = store.list_chatgpt_status_updates()
        loaded_states = store.list_project_state_updates()
        loaded_decisions = store.list_next_action_decisions()

        check("one intake loaded", len(loaded_intakes) == 1)
        check("intake round-trips", loaded_intakes[0].to_dict() == record.to_dict())
        check("one chatgpt update loaded", len(loaded_updates) == 1)
        check("chatgpt update round-trips", loaded_updates[0].to_dict() == packet.to_dict())
        check("one state update loaded", len(loaded_states) == 1)
        check("state update round-trips", loaded_states[0].to_dict() == state_update.to_dict())
        check("one next action loaded", len(loaded_decisions) == 1)
        check("next action round-trips", loaded_decisions[0].to_dict() == decision.to_dict())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_deterministic_jsonl_format() -> None:
    print("\n[2] deterministic JSONL format")
    tmp = Path(tempfile.mkdtemp(prefix="scos-result-intake-"))
    try:
        store = ResultIntakeStore(tmp)
        record = _make_record()
        store.append_intake(record)
        import json

        line = (tmp / "result_intake.jsonl").read_text(encoding="utf-8").splitlines()[0]
        check("no trailing whitespace before newline", not line.endswith(" "))
        reencoded = json.dumps(
            json.loads(line), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        check("compact sorted separators round-trip exactly", line == reencoded)
        check("keys sorted", line.index('"artifacts"') < line.index('"blockers"'))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_malformed_jsonl_handling() -> None:
    print("\n[3] malformed JSONL handling")
    tmp = Path(tempfile.mkdtemp(prefix="scos-result-intake-"))
    try:
        store = ResultIntakeStore(tmp)
        target = tmp / "result_intake.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{not valid json}\n", encoding="utf-8")
        check("malformed line raises ValueError", _raises(lambda: store.list_intakes()))

        target.write_text("[1, 2, 3]\n", encoding="utf-8")
        check("non-object JSON line raises ValueError", _raises(lambda: store.list_intakes()))

        target.write_text("\n\n", encoding="utf-8")
        check("blank lines are skipped, no error", store.list_intakes() == ())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_4_url_root_rejection() -> None:
    print("\n[4] URL root rejection")
    check("http root rejected", _raises(lambda: ResultIntakeStore("http://example.com/data")))
    check("https root rejected", _raises(lambda: ResultIntakeStore("https://example.com/data")))
    check("generic scheme root rejected", _raises(lambda: ResultIntakeStore("ftp://example.com/data")))
    check("invalid path type rejected", _raises(lambda: ResultIntakeStore(12345)))


def test_5_list_only_creates_nothing() -> None:
    print("\n[5] list-only does not create dirs/files")
    tmp = Path(tempfile.mkdtemp(prefix="scos-result-intake-"))
    nested_root = tmp / "nested" / "does-not-exist-yet"
    try:
        store = ResultIntakeStore(nested_root)
        check("list_intakes returns empty tuple", store.list_intakes() == ())
        check("list_chatgpt_status_updates returns empty tuple", store.list_chatgpt_status_updates() == ())
        check("list_project_state_updates returns empty tuple", store.list_project_state_updates() == ())
        check("list_next_action_decisions returns empty tuple", store.list_next_action_decisions() == ())
        check("root_dir was never created", not nested_root.exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_1_append_and_load_all_record_types()
    test_2_deterministic_jsonl_format()
    test_3_malformed_jsonl_handling()
    test_4_url_root_rejection()
    test_5_list_only_creates_nothing()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
