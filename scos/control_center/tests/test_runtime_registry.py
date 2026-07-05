"""test_runtime_registry.py - SCOS Stage 5.2 runtime registry suite.

Plain executable script (no pytest). Covers the built-in registry contents,
lookup helpers, and the manual_clipboard-always-present guarantee.

Run: python scos/control_center/tests/test_runtime_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from runtime_registry import (  # noqa: E402
    RUNTIME_REGISTRY_SCHEMA_VERSION,
    find_runtimes_for_task,
    get_runtime,
    list_runtimes,
)
from work_session_models import ALLOWED_TASK_TYPES  # noqa: E402

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


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", RUNTIME_REGISTRY_SCHEMA_VERSION == 1)


def test_list_runtimes() -> None:
    print("\n[2] list_runtimes")
    runtimes = list_runtimes()
    check("returns a tuple", isinstance(runtimes, tuple))
    check("eight built-in runtimes", len(runtimes) == 8)
    check("deterministic across calls", list_runtimes() == runtimes)
    ids = [runtime.runtime_id for runtime in runtimes]
    check("no duplicate runtime ids", len(ids) == len(set(ids)))


def test_manual_clipboard_always_present() -> None:
    print("\n[3] manual_clipboard fallback guarantee")
    runtime = get_runtime("manual-clipboard")
    check("manual-clipboard is registered", runtime is not None)
    check("manual-clipboard is enabled", bool(runtime and runtime.enabled))
    check(
        "manual-clipboard supports every allowed task type",
        bool(runtime)
        and set(runtime.supported_task_types) == set(ALLOWED_TASK_TYPES),
    )
    for task_type in ALLOWED_TASK_TYPES:
        matches = find_runtimes_for_task(task_type)
        ids = [r.runtime_id for r in matches]
        check(
            f"manual-clipboard covers task_type={task_type}",
            "manual-clipboard" in ids,
        )


def test_get_runtime() -> None:
    print("\n[4] get_runtime")
    runtime = get_runtime("claude-code-cli")
    check("known runtime found", runtime is not None)
    check("known runtime has expected agent_name", bool(runtime) and runtime.agent_name == "claude_code")
    check("unknown runtime returns None", get_runtime("does-not-exist") is None)


def test_find_runtimes_for_task() -> None:
    print("\n[5] find_runtimes_for_task")
    implementation_runtimes = find_runtimes_for_task("implementation")
    ids = {runtime.runtime_id for runtime in implementation_runtimes}
    check("claude-code-cli supports implementation", "claude-code-cli" in ids)
    check("codex-cli supports implementation", "codex-cli" in ids)
    check("hermes-cli does not support implementation", "hermes-cli" not in ids)
    check(
        "unknown task_type yields empty tuple",
        find_runtimes_for_task("not_a_real_task_type") == (),
    )
    check(
        "all returned runtimes are enabled",
        all(runtime.enabled for runtime in implementation_runtimes),
    )


def main() -> int:
    test_schema_version()
    test_list_runtimes()
    test_manual_clipboard_always_present()
    test_get_runtime()
    test_find_runtimes_for_task()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
