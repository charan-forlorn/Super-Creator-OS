"""test_operator_packet_review_store.py - SCOS Stage 5.5 review store suite.

Run: python scos/control_center/tests/test_operator_packet_review_store.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_packet_review_models import (  # noqa: E402
    OperatorPacketDecision,
    OperatorPacketReviewResult,
    PacketReviewCheck,
)
from operator_packet_review_store import (  # noqa: E402
    append_operator_packet_decision,
    append_operator_packet_review_result,
    load_operator_packet_decisions,
    load_operator_packet_review_results,
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


def _check() -> PacketReviewCheck:
    return PacketReviewCheck.of("packet_id_present", "success", "info", packet_id="pp-1")


def _decision(reason: str = "Looks safe.") -> OperatorPacketDecision:
    return OperatorPacketDecision.of(
        packet_id="pp-1",
        routing_decision_id="rd-1",
        decision="approve",
        decided_by="operator",
        decided_at="2026-07-06T14:00:00Z",
        reason=reason,
        checks=(_check(),),
    )


def _result(decision: OperatorPacketDecision) -> OperatorPacketReviewResult:
    return OperatorPacketReviewResult.of(
        packet_id="pp-1",
        result_packet_id=None,
        routing_decision_id="rd-1",
        reviewed_at="2026-07-06T14:00:00Z",
        decision=decision,
        checks=(_check(),),
    )


def test_1_append_and_load_decisions() -> None:
    print("\n[1] append/load decisions")
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "decisions.jsonl"
        first = _decision("First.")
        second = _decision("Second.")
        append_operator_packet_decision(path, first)
        append_operator_packet_decision(path, second)
        loaded = load_operator_packet_decisions(path)
        check("two decisions loaded", len(loaded) == 2)
        check("append order preserved", [item.reason for item in loaded] == ["First.", "Second."])
        lines = path.read_text(encoding="utf-8").splitlines()
        check("compact JSONL line", all(" " not in line for line in lines))
        check("sort_keys places checks first", lines[0].startswith('{"checks"'))


def test_2_append_and_load_review_results() -> None:
    print("\n[2] append/load review results")
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "reviews.jsonl"
        decision = _decision()
        result = _result(decision)
        append_operator_packet_review_result(path, result)
        loaded = load_operator_packet_review_results(path)
        check("one result loaded", len(loaded) == 1)
        check("review_id round-trips", loaded[0].review_id == result.review_id)
        check("nested decision round-trips", loaded[0].decision.decision_id == decision.decision_id)


def test_3_missing_file_and_malformed_jsonl() -> None:
    print("\n[3] missing file + malformed JSONL")
    with tempfile.TemporaryDirectory() as temp_dir:
        missing = Path(temp_dir) / "missing.jsonl"
        check("missing decision file returns empty tuple", load_operator_packet_decisions(missing) == ())
        bad = Path(temp_dir) / "bad.jsonl"
        bad.write_text("{not json}\n", encoding="utf-8")
        try:
            load_operator_packet_decisions(bad)
            check("malformed JSONL raises", False)
        except ValueError as exc:
            check("malformed JSONL raises stable error", "INVALID_OPERATOR_PACKET_DECISION_LINE" in str(exc))


def test_4_reject_url_paths_and_wrong_types() -> None:
    print("\n[4] path/type validation")
    try:
        append_operator_packet_decision("https://example.com/out.jsonl", _decision())
        check("URL path rejected", False)
    except ValueError:
        check("URL path rejected", True)
    try:
        append_operator_packet_decision("x.jsonl", object())
        check("wrong decision type rejected", False)
    except ValueError:
        check("wrong decision type rejected", True)


def main() -> int:
    test_1_append_and_load_decisions()
    test_2_append_and_load_review_results()
    test_3_missing_file_and_malformed_jsonl()
    test_4_reject_url_paths_and_wrong_types()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
