"""test_prompt_result_packet_store.py - SCOS Stage 5.4 JSONL packet store suite.

Plain executable script (no pytest). Covers append/load round-tripping,
append-only no-dedup semantics, missing-file behavior, URL path rejection,
malformed-line error handling, and non-dataclass argument rejection.

Run: python scos/control_center/tests/test_prompt_result_packet_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from prompt_result_packet_builder import (  # noqa: E402
    create_prompt_packet,
    create_result_packet,
    create_routing_decision,
)
from prompt_result_packet_store import (  # noqa: E402
    PROMPT_RESULT_PACKET_STORE_SCHEMA_VERSION,
    append_packet_routing_decision,
    append_prompt_packet,
    append_result_packet,
    load_packet_routing_decisions,
    load_prompt_packets,
    load_result_packets,
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


def _prompt(**overrides):
    kwargs = dict(
        session_id="session-1",
        task_id="task-1",
        packet_type="planning_prompt",
        source_agent="chatgpt",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        title="Implement Stage 5.4",
        objective="Build the packet layer",
        prompt_body="Implement the packet models per spec.",
        created_at="2026-07-06T10:00:00Z",
    )
    kwargs.update(overrides)
    return create_prompt_packet(**kwargs)


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", PROMPT_RESULT_PACKET_STORE_SCHEMA_VERSION == 1)


def test_append_and_load_prompt_packets_roundtrip(tmp_dir: Path) -> None:
    print("\n[2] append_prompt_packet / load_prompt_packets round trip")
    path = tmp_dir / "prompt_packets.jsonl"
    first = _prompt()
    second = _prompt(created_at="2026-07-06T11:00:00Z")
    digest_one = append_prompt_packet(path=path, packet=first)
    check("append returns a hex digest", isinstance(digest_one, str) and len(digest_one) == 64)
    append_prompt_packet(path=path, packet=second)

    loaded = load_prompt_packets(path=path)
    check("two packets loaded", len(loaded) == 2)
    check("first packet matches", loaded[0] == first)
    check("second packet matches", loaded[1] == second)


def test_append_and_load_result_packets_roundtrip(tmp_dir: Path) -> None:
    print("\n[3] append_result_packet / load_result_packets round trip")
    path = tmp_dir / "result_packets.jsonl"
    prompt = _prompt()
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    append_result_packet(path=path, packet=result)
    loaded = load_result_packets(path=path)
    check("one result loaded", len(loaded) == 1)
    check("loaded result matches appended result", loaded[0] == result)


def test_append_and_load_routing_decisions_roundtrip(tmp_dir: Path) -> None:
    print("\n[4] append_packet_routing_decision / load_packet_routing_decisions round trip")
    path = tmp_dir / "routing_decisions.jsonl"
    prompt = _prompt()
    result = create_result_packet(
        prompt_packet=prompt,
        result_type="planning_result",
        verdict="PASS",
        summary="Plan drafted.",
        created_at="2026-07-06T10:05:00Z",
    )
    decision = create_routing_decision(
        result_packet=result,
        next_agent="claude_code",
        next_packet_type="implementation_prompt",
        reason="Plan approved.",
    )
    append_packet_routing_decision(path=path, decision=decision)
    loaded = load_packet_routing_decisions(path=path)
    check("one decision loaded", len(loaded) == 1)
    check("loaded decision matches appended decision", loaded[0] == decision)


def test_missing_file_returns_empty_tuple(tmp_dir: Path) -> None:
    print("\n[5] missing file reads as empty store")
    missing_path = tmp_dir / "does_not_exist.jsonl"
    check("load_prompt_packets on missing file is empty", load_prompt_packets(path=missing_path) == ())
    check("load_result_packets on missing file is empty", load_result_packets(path=missing_path) == ())
    check(
        "load_packet_routing_decisions on missing file is empty",
        load_packet_routing_decisions(path=missing_path) == (),
    )


def test_rejects_http_and_https_paths() -> None:
    print("\n[6] rejects http:// and https:// paths")
    prompt = _prompt()
    try:
        append_prompt_packet(path="https://example.com/x.jsonl", packet=prompt)
        check("https path rejected", False)
    except ValueError as exc:
        check("https path rejected", "URL_PATH_REJECTED" in str(exc))
    try:
        append_prompt_packet(path="http://example.com/x.jsonl", packet=prompt)
        check("http path rejected", False)
    except ValueError as exc:
        check("http path rejected", "URL_PATH_REJECTED" in str(exc))


def test_malformed_line_raises_deterministic_error(tmp_dir: Path) -> None:
    print("\n[7] malformed JSONL line raises a stable error")
    bad_prompts = tmp_dir / "bad_prompts.jsonl"
    bad_prompts.write_text("not-json\n", encoding="utf-8", newline="\n")
    try:
        load_prompt_packets(path=bad_prompts)
        check("invalid prompt line raises ValueError", False)
    except ValueError as exc:
        check("invalid prompt line raises ValueError", "INVALID_PROMPT_PACKET_LINE" in str(exc))

    bad_results = tmp_dir / "bad_results.jsonl"
    bad_results.write_text("not-json\n", encoding="utf-8", newline="\n")
    try:
        load_result_packets(path=bad_results)
        check("invalid result line raises ValueError", False)
    except ValueError as exc:
        check("invalid result line raises ValueError", "INVALID_RESULT_PACKET_LINE" in str(exc))

    bad_decisions = tmp_dir / "bad_decisions.jsonl"
    bad_decisions.write_text("not-json\n", encoding="utf-8", newline="\n")
    try:
        load_packet_routing_decisions(path=bad_decisions)
        check("invalid decision line raises ValueError", False)
    except ValueError as exc:
        check("invalid decision line raises ValueError", "INVALID_ROUTING_DECISION_LINE" in str(exc))


def test_append_only_no_dedup(tmp_dir: Path) -> None:
    print("\n[8] append-only: no de-dup across distinct packets")
    path = tmp_dir / "no_dedup_prompts.jsonl"
    packets = [
        _prompt(created_at="2026-07-06T10:00:00Z"),
        _prompt(created_at="2026-07-06T11:00:00Z"),
        _prompt(created_at="2026-07-06T12:00:00Z"),
    ]
    for packet in packets:
        append_prompt_packet(path=path, packet=packet)
    loaded = load_prompt_packets(path=path)
    check("three distinct packet_ids", len({p.packet_id for p in packets}) == 3)
    check("three entries loaded in append order", len(loaded) == 3)
    check("append order preserved", [p.packet_id for p in loaded] == [p.packet_id for p in packets])


def test_reject_non_dataclass_instance(tmp_dir: Path) -> None:
    print("\n[9] rejects non-dataclass instances")
    path = tmp_dir / "type_check.jsonl"
    try:
        append_prompt_packet(path=path, packet="not a packet")
        check("non-PromptPacket rejected", False)
    except ValueError as exc:
        check("non-PromptPacket rejected", "NOT_A_PROMPT_PACKET" in str(exc))
    try:
        append_result_packet(path=path, packet="not a result")
        check("non-ResultPacket rejected", False)
    except ValueError as exc:
        check("non-ResultPacket rejected", "NOT_A_RESULT_PACKET" in str(exc))
    try:
        append_packet_routing_decision(path=path, decision="not a decision")
        check("non-PacketRoutingDecision rejected", False)
    except ValueError as exc:
        check("non-PacketRoutingDecision rejected", "NOT_A_ROUTING_DECISION" in str(exc))


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="scos_stage54_store_"))
    try:
        test_schema_version()
        test_append_and_load_prompt_packets_roundtrip(tmp_dir)
        test_append_and_load_result_packets_roundtrip(tmp_dir)
        test_append_and_load_routing_decisions_roundtrip(tmp_dir)
        test_missing_file_returns_empty_tuple(tmp_dir)
        test_rejects_http_and_https_paths()
        test_malformed_line_raises_deterministic_error(tmp_dir)
        test_append_only_no_dedup(tmp_dir)
        test_reject_non_dataclass_instance(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
