"""test_state_snapshot.py - SCOS Stage 6.3 durable state snapshot suite.

Plain executable script (no pytest). Covers snapshot shape, deterministic
JSON serialization, and disabled-capability flags.

Run: python scos/control_center/tests/test_state_snapshot.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from sqlite_state_store import SQLiteStateStore  # noqa: E402
from state_snapshot import build_state_snapshot, stable_state_snapshot_json  # noqa: E402

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


def test_1_snapshot_shape() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_snapshot_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        snapshot = build_state_snapshot(store, checked_at="t1")
        check("schema_version present", snapshot["schema_version"] == 1)
        check("checked_at present", snapshot["checked_at"] == "t1")
        check("wal_enabled true", snapshot["wal_enabled"] is True)
        for key in ("commands", "sessions", "events", "approvals", "results"):
            check(f"counts has {key}", key in snapshot["counts"])
            check(f"latest_records has {key}", key in snapshot["latest_records"])
        for capability in (
            "websocket",
            "sse",
            "polling",
            "real_adapter_dispatch",
            "arbitrary_command_execution",
            "nextjs_api_routes",
        ):
            check(
                f"{capability} is disabled",
                snapshot["disabled_capabilities"].get(capability) == "disabled",
            )
        check(
            "next stage points to 6.4",
            "Stage 6.4" in snapshot["next_stage"],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_stable_json_is_deterministic() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_snapshot_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        snapshot = build_state_snapshot(store, checked_at="t1")
        first = stable_state_snapshot_json(snapshot)
        second = stable_state_snapshot_json(snapshot)
        check("same snapshot serializes identically", first == second)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    tests = [
        test_1_snapshot_shape,
        test_2_stable_json_is_deterministic,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
