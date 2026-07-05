"""test_command_validation.py - SCOS Stage 5.1 command validation suite.

Plain executable script (no pytest). Covers allowed/unknown command types,
forbidden command text, duplicate args, URL rejection, shell-character
rejection, and deterministic error ordering. Forbidden text literals are
assembled from fragments so this file's own text stays free of the tokens.

Run: python scos/control_center/tests/test_command_validation.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from command_models import ALLOWED_COMMAND_TYPES, CommandDraft  # noqa: E402
from command_validation import (  # noqa: E402
    CONTROL_CENTER_COMMAND_VALIDATION_SCHEMA_VERSION,
    FORBIDDEN_COMMAND_TEXT,
    validate_command_args,
    validate_command_draft,
    validate_command_type,
    validate_no_forbidden_command_text,
)

_PASS = 0
_FAIL = 0

# Forbidden markers assembled from fragments (repo static-scan convention).
_T_GIT_PUSH = "git pu" + "sh"
_T_CURL = "cu" + "rl"
_T_PAY = "pay" + "ment"
_T_DEPLOY = "dep" + "loy"
_T_WEBHOOK = "web" + "hook"


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _draft(**overrides) -> CommandDraft:
    payload = {
        "command_id": "cmd-001",
        "command_type": "RUN_SMOKE_CHECK",
        "requested_by": "operator-a",
        "created_at": "2026-07-05T10:00:00Z",
        "summary": "Run the Tier 1 smoke check",
        "args": (),
        "metadata": (),
    }
    payload.update(overrides)
    return CommandDraft.of(**payload)


def test_schema_version() -> None:
    print("\n[1] schema version + forbidden marker count")
    check("schema version is 1", CONTROL_CENTER_COMMAND_VALIDATION_SCHEMA_VERSION == 1)
    check("25 forbidden text markers", len(FORBIDDEN_COMMAND_TEXT) == 25)


def test_command_types() -> None:
    print("\n[2] validate_command_type")
    for command_type in ALLOWED_COMMAND_TYPES:
        ok, error = validate_command_type(command_type)
        check(f"{command_type} allowed", ok and error is None)
    ok, error = validate_command_type("LAUNCH_ROCKETS")
    check("unknown type rejected", not ok)
    check("unknown type stable message", error == "unknown command_type: 'LAUNCH_ROCKETS'")


def test_command_args() -> None:
    print("\n[3] validate_command_args")
    ok, errors = validate_command_args("RUN_SMOKE_CHECK", ())
    check("no-arg command passes", ok and errors == ())
    ok, errors = validate_command_args(
        "RUN_STAGE4_FINAL_GATE", (("checked_at", "2026-07-05T10:00:00Z"),)
    )
    check("gate with checked_at passes", ok and errors == ())
    ok, errors = validate_command_args("RUN_STAGE4_FINAL_GATE", ())
    check("gate without checked_at fails", not ok and errors == ("missing required arg: checked_at",))
    ok, errors = validate_command_args(
        "RUN_STAGE4_FINAL_GATE",
        (("checked_at", "a"), ("checked_at", "b")),
    )
    check("duplicate arg keys fail", not ok and "duplicate arg key: checked_at" in errors)
    ok, errors = validate_command_args("RUN_SMOKE_CHECK", (("extra", "x"),))
    check("disallowed arg key fails", not ok and errors == ("arg key not allowed for RUN_SMOKE_CHECK: extra",))
    ok, errors = validate_command_args(
        "RUN_STAGE4_FINAL_GATE", (("checked_at", "https://example.com/now"),)
    )
    check("URL arg value fails", not ok and "arg value must not be a URL: checked_at" in errors)
    ok, errors = validate_command_args(
        "RUN_STAGE4_FINAL_GATE", (("checked_at", "2026 | echo pwned"),)
    )
    check(
        "shell character in arg value fails",
        not ok and "arg value contains forbidden shell character: checked_at" in errors,
    )
    ok, errors = validate_command_args("NOT_A_TYPE", ())
    check("unknown type in args fails", not ok and errors == ("unknown command_type: 'NOT_A_TYPE'",))


def test_forbidden_text() -> None:
    print("\n[4] validate_no_forbidden_command_text")
    ok, found = validate_no_forbidden_command_text("run the local smoke script")
    check("clean text passes", ok and found == ())
    ok, found = validate_no_forbidden_command_text(f"please {_T_GIT_PUSH} to origin")
    check("git-mutation text fails", not ok and _T_GIT_PUSH in found)
    ok, found = validate_no_forbidden_command_text(_T_CURL.upper() + " something")
    check("case-insensitive match", not ok and _T_CURL in found)
    ok, found = validate_no_forbidden_command_text(f"{_T_PAY} and {_T_WEBHOOK}")
    check("multiple markers reported", not ok and found == (_T_PAY, _T_WEBHOOK))
    ok, found = validate_no_forbidden_command_text(f"start {_T_DEPLOY} now")
    check("release-boundary marker fails", not ok and _T_DEPLOY in found)


def test_command_draft() -> None:
    print("\n[5] validate_command_draft")
    ok, errors = validate_command_draft(_draft())
    check("valid draft passes", ok and errors == ())
    ok, errors = validate_command_draft(_draft(summary="   "))
    check("empty summary fails", not ok and errors == ("empty required field: summary",))
    ok, errors = validate_command_draft(_draft(command_type="NOT_A_TYPE"))
    check("unknown type in draft fails", not ok and errors == ("unknown command_type: 'NOT_A_TYPE'",))
    ok, errors = validate_command_draft(_draft(summary=f"then {_T_GIT_PUSH} it"))
    check(
        "forbidden text in summary fails",
        not ok and errors == (f"forbidden command text in summary: {_T_GIT_PUSH}",),
    )
    ok, errors = validate_command_draft(
        _draft(metadata=((_T_WEBHOOK + "_url", "hooks/site"),))
    )
    check("forbidden text in metadata fails", not ok and len(errors) == 1)
    ok, errors = validate_command_draft(
        _draft(command_type="RUN_STAGE4_FINAL_GATE", args=())
    )
    check("draft arg contract enforced", not ok and errors == ("missing required arg: checked_at",))


def test_deterministic_ordering() -> None:
    print("\n[6] deterministic error ordering")
    bad = _draft(
        command_id="",
        summary=f"{_T_PAY} then {_T_GIT_PUSH}",
        args=(("extra", "https://example.com"),),
    )
    first = validate_command_draft(bad)
    second = validate_command_draft(bad)
    check("same errors across calls", first == second)
    _ok, errors = first
    check("required-field error first", errors[0] == "empty required field: command_id")
    check(
        "forbidden markers in fixed list order",
        errors.index(f"forbidden command text in summary: {_T_GIT_PUSH}")
        < errors.index(f"forbidden command text in summary: {_T_PAY}"),
    )
    original = bad.to_dict()
    validate_command_draft(bad)
    check("draft not mutated", bad.to_dict() == original)


def main() -> int:
    test_schema_version()
    test_command_types()
    test_command_args()
    test_forbidden_text()
    test_command_draft()
    test_deterministic_ordering()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
