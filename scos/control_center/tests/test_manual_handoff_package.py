"""test_manual_handoff_package.py - SCOS Stage 5.5 handoff package suite.

Run: python scos/control_center/tests/test_manual_handoff_package.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from manual_handoff_package import create_manual_handoff_package  # noqa: E402
from operator_packet_review_models import (  # noqa: E402
    ManualHandoffPackage,
    OperatorPacketReviewError,
)
from prompt_result_packet_builder import create_prompt_packet  # noqa: E402

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


def _packet():
    return create_prompt_packet(
        session_id="session-handoff",
        task_id="task-handoff",
        packet_type="implementation_prompt",
        source_agent="chatgpt",
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        title="Implement manual handoff package",
        objective="Create the deterministic handoff files.",
        prompt_body="Implement and test the manual handoff package.",
        created_at="2026-07-06T13:00:00Z",
        constraints=("local only", "no clipboard"),
        expected_artifacts=("implementation_report", "test_output"),
    )


def test_1_create_package_files_and_manifest() -> None:
    print("\n[1] create package files and manifest")
    packet = _packet()
    with tempfile.TemporaryDirectory() as temp_dir:
        package = create_manual_handoff_package(
            packet=packet,
            target_agent="claude_code",
            target_runtime_id="claude_code_cli",
            output_dir=temp_dir,
            created_at="2026-07-06T13:10:00Z",
        )
        check("returns ManualHandoffPackage", isinstance(package, ManualHandoffPackage))
        if not isinstance(package, ManualHandoffPackage):
            return
        for path_text in (
            package.prompt_path,
            package.context_summary_path,
            package.instruction_path,
            package.manifest_path,
        ):
            check(f"{Path(path_text).name} exists", Path(path_text).is_file())
        manifest = json.loads(Path(package.manifest_path).read_text(encoding="utf-8"))
        check("manifest handoff_id matches", manifest["handoff_id"] == package.handoff_id)
        check("manifest includes sha256 for generated files", all("sha256" in item for item in manifest["files"]))
        check("five deterministic instructions", len(package.instructions) == 5)
        check(
            "instructions include no commit/push approval bypass",
            "Do not let the AI commit/push" in Path(package.instruction_path).read_text(encoding="utf-8"),
        )


def test_2_deterministic_handoff_id() -> None:
    print("\n[2] deterministic handoff id")
    packet = _packet()
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = create_manual_handoff_package(
            packet=packet,
            target_agent="claude_code",
            target_runtime_id="claude_code_cli",
            output_dir=first_dir,
            created_at="2026-07-06T13:10:00Z",
        )
        second = create_manual_handoff_package(
            packet=packet,
            target_agent="claude_code",
            target_runtime_id="claude_code_cli",
            output_dir=second_dir,
            created_at="2026-07-06T13:10:00Z",
        )
        check("same stable fields yield same handoff_id", first.handoff_id == second.handoff_id)


def test_3_reject_url_output_dir_and_invalid_agent() -> None:
    print("\n[3] reject unsafe inputs")
    packet = _packet()
    url = create_manual_handoff_package(
        packet=packet,
        target_agent="claude_code",
        target_runtime_id="claude_code_cli",
        output_dir="https://example.com/out",
        created_at="2026-07-06T13:10:00Z",
    )
    check("URL output dir rejected", isinstance(url, OperatorPacketReviewError))
    bad_agent = create_manual_handoff_package(
        packet=packet,
        target_agent="not_an_agent",
        target_runtime_id="x",
        output_dir="scos/work/control_center/manual_handoffs",
        created_at="2026-07-06T13:10:00Z",
    )
    check("invalid agent rejected", isinstance(bad_agent, OperatorPacketReviewError))


def test_4_static_source_no_forbidden_automation() -> None:
    print("\n[4] static source check")
    source = (_PACKAGE / "manual_handoff_package.py").read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "os.system",
        "requests",
        "urllib.request",
        "webbrowser",
        "pyautogui",
        "pyperclip",
        "win32clipboard",
        "clipboard.copy",
        "clipboard.paste",
        "navigator.clipboard",
    )
    for marker in forbidden:
        check(f"source does not contain {marker!r}", marker not in source)


def main() -> int:
    test_1_create_package_files_and_manifest()
    test_2_deterministic_handoff_id()
    test_3_reject_url_output_dir_and_invalid_agent()
    test_4_static_source_no_forbidden_automation()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
