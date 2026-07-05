"""test_command_queue.py - SCOS Stage 5.1 local command queue suite.

Plain executable script (no pytest). Covers JSONL append/read round-trips,
append-only behavior, stable line sha256 digests, blank-line skipping,
invalid-line errors, and URL path rejection. Uses a temporary directory for
every queue file.

Run: python scos/control_center/tests/test_command_queue.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from command_models import ApprovedCommand  # noqa: E402
from command_queue import (  # noqa: E402
    CONTROL_CENTER_COMMAND_QUEUE_SCHEMA_VERSION,
    append_approved_command,
    read_command_queue,
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


def _approved(command_id: str = "cmd-001") -> ApprovedCommand:
    return ApprovedCommand.of(
        command_id=command_id,
        command_type="RUN_SMOKE_CHECK",
        approved_by="operator-a",
        approved_at="2026-07-05T10:05:00Z",
        metadata=(("origin", "control-center"),),
    )


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", CONTROL_CENTER_COMMAND_QUEUE_SCHEMA_VERSION == 1)


def test_append_and_read(tmp: Path) -> None:
    print("\n[2] append + read round-trip")
    queue = tmp / "queue" / "commands.jsonl"
    digest = append_approved_command(queue_path=queue, approved_command=_approved())
    check("parent directory created", queue.is_file())
    check("digest is sha256 hex", len(digest) == 64 and all(c in "0123456789abcdef" for c in digest))
    commands = read_command_queue(queue_path=queue)
    check("one command read back", len(commands) == 1)
    check("round-trip equality", commands[0] == _approved())
    check("str path accepted", read_command_queue(queue_path=str(queue)) == commands)


def test_append_only(tmp: Path) -> None:
    print("\n[3] append-only behavior")
    queue = tmp / "commands.jsonl"
    append_approved_command(queue_path=queue, approved_command=_approved("cmd-001"))
    first_text = queue.read_text(encoding="utf-8")
    append_approved_command(queue_path=queue, approved_command=_approved("cmd-002"))
    second_text = queue.read_text(encoding="utf-8")
    check("existing content preserved", second_text.startswith(first_text))
    check("one line per command", second_text.count("\n") == 2)
    commands = read_command_queue(queue_path=queue)
    check("append order preserved", [c.command_id for c in commands] == ["cmd-001", "cmd-002"])
    check("LF line endings only", "\r" not in second_text)


def test_stable_line_sha256(tmp: Path) -> None:
    print("\n[4] line sha256 stability")
    queue_a = tmp / "a.jsonl"
    queue_b = tmp / "b.jsonl"
    digest_a = append_approved_command(queue_path=queue_a, approved_command=_approved())
    digest_b = append_approved_command(queue_path=queue_b, approved_command=_approved())
    check("same command -> same digest", digest_a == digest_b)
    line = queue_a.read_text(encoding="utf-8").splitlines()[0]
    check(
        "digest matches written line",
        digest_a == hashlib.sha256(line.encode("utf-8")).hexdigest(),
    )
    payload = json.loads(line)
    check(
        "line key order is model order",
        list(payload.keys())
        == ["command_id", "command_type", "approved_by", "approved_at", "args", "metadata"],
    )


def test_blank_and_invalid_lines(tmp: Path) -> None:
    print("\n[5] blank-line skipping + invalid line error")
    queue = tmp / "mixed.jsonl"
    append_approved_command(queue_path=queue, approved_command=_approved())
    with open(queue, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n   \n")
    append_approved_command(queue_path=queue, approved_command=_approved("cmd-002"))
    check("blank lines skipped", len(read_command_queue(queue_path=queue)) == 2)

    broken = tmp / "broken.jsonl"
    broken.write_text('{"command_id": "cmd-001"}\n{not json\n', encoding="utf-8")
    try:
        read_command_queue(queue_path=broken)
        check("invalid line raises controlled error", False)
    except ValueError as exc:
        check(
            "invalid line raises controlled error",
            str(exc) == "INVALID_QUEUE_LINE: line 2 is not valid JSON",
        )
    check("missing file reads as empty queue", read_command_queue(queue_path=tmp / "nope.jsonl") == ())


def test_url_path_rejected(tmp: Path) -> None:
    print("\n[6] URL path rejection")
    for bad in ("http://example.com/q.jsonl", "https://example.com/q.jsonl", "ftp://host/q.jsonl"):
        try:
            append_approved_command(queue_path=bad, approved_command=_approved())
            check(f"append rejects {bad.split(':', 1)[0]} path", False)
        except ValueError as exc:
            check(
                f"append rejects {bad.split(':', 1)[0]} path",
                str(exc).startswith("URL_PATH_REJECTED:"),
            )
    try:
        read_command_queue(queue_path="https://example.com/q.jsonl")
        check("read rejects URL path", False)
    except ValueError as exc:
        check("read rejects URL path", str(exc).startswith("URL_PATH_REJECTED:"))
    try:
        append_approved_command(queue_path=tmp / "q.jsonl", approved_command="not-a-command")
        check("non-ApprovedCommand rejected", False)
    except ValueError as exc:
        check("non-ApprovedCommand rejected", str(exc).startswith("NOT_AN_APPROVED_COMMAND:"))


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_schema_version()
        test_append_and_read(tmp)
        test_append_only(tmp)
        test_stable_line_sha256(tmp)
        test_blank_and_invalid_lines(tmp)
        test_url_path_rejected(tmp)
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
