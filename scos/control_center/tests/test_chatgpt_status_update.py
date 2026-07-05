"""test_chatgpt_status_update.py - SCOS Stage 5.7 ChatGPT status update suite.

Plain executable script (no pytest). Covers deterministic Markdown
rendering, presence of constraints/evidence/action, and the absence of any
premature commit/push claims.

Run: python scos/control_center/tests/test_chatgpt_status_update.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from chatgpt_status_update import (  # noqa: E402
    prepare_chatgpt_status_update,
    render_chatgpt_status_update_markdown,
)
from result_intake_builder import build_result_intake_record  # noqa: E402
from result_intake_models import AIResultIntakeRecord, ChatGPTStatusUpdatePacket  # noqa: E402

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


def _make_record(**overrides) -> AIResultIntakeRecord:
    kwargs = dict(
        session_id="sess-1",
        task_id="task-1",
        source_agent="hermes",
        source_runtime_id="runtime-1",
        raw_result_text=(
            "Audit complete. Verdict: PASS\n"
            "Blocker: none\n"
            "Warning: coverage below target\n"
            "Tests: 100 passed\n"
            "Changed Files: 5 files audited\n"
        ),
        created_at="2026-07-06T00:00:00Z",
        title="Audit result",
    )
    kwargs.update(overrides)
    record = build_result_intake_record(**kwargs)
    assert isinstance(record, AIResultIntakeRecord), record
    return record


def _make_packet() -> ChatGPTStatusUpdatePacket:
    record = _make_record()
    packet = prepare_chatgpt_status_update(
        intake_record=record,
        target_runtime_id="chatgpt-web",
        created_at="2026-07-06T00:05:00Z",
        requested_chatgpt_action="mark_blocked",
    )
    assert isinstance(packet, ChatGPTStatusUpdatePacket), packet
    return packet


def test_1_deterministic_markdown() -> None:
    print("\n[1] deterministic markdown")
    packet = _make_packet()
    first = render_chatgpt_status_update_markdown(packet)
    second = render_chatgpt_status_update_markdown(packet)
    check("rendering is deterministic", first == second)
    check("rejects non-packet input", _raises(lambda: render_chatgpt_status_update_markdown({"not": "a packet"})))


def test_2_includes_required_content() -> None:
    print("\n[2] includes constraints/evidence/action")
    packet = _make_packet()
    markdown = render_chatgpt_status_update_markdown(packet)
    check("includes session id", packet.session_id in markdown)
    check("includes task id", packet.task_id in markdown)
    check("includes source agent", "hermes" in markdown)
    check("includes verdict", packet.result_verdict in markdown)
    check("includes requested action", packet.requested_chatgpt_action in markdown)
    check("includes evidence section header", "## Evidence" in markdown)
    check("includes constraints section", "Do not assume hidden files." in markdown)
    check(
        "includes commit/push constraint",
        "Do not claim work committed/pushed unless evidence says so." in markdown,
    )
    check(
        "includes evidence-only next-action constraint",
        "Produce next action only from provided evidence." in markdown,
    )
    check("includes manual handoff notice", "manual handoff artifact" in markdown)


def test_3_no_hidden_commit_push_claims() -> None:
    print("\n[3] no hidden commit/push claims")
    packet = _make_packet()
    markdown = render_chatgpt_status_update_markdown(packet)
    lowered = markdown.lower()
    check("does not assert 'committed'", "was committed" not in lowered)
    check("does not assert 'pushed to'", "pushed to" not in lowered)
    check("does not claim automatic sending", "sent to chatgpt" not in lowered)


def main() -> int:
    test_1_deterministic_markdown()
    test_2_includes_required_content()
    test_3_no_hidden_commit_push_claims()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
