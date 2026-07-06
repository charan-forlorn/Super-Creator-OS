"""test_sqlite_state_schema.py - SCOS Stage 6.3 SQLite schema suite.

Plain executable script (no pytest). Covers schema/index/pragma statement
shape, stable JSON dumping, and database path safety validation.

Run: python scos/control_center/tests/test_sqlite_state_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from sqlite_state_schema import (  # noqa: E402
    DEFAULT_STATE_DB_RELATIVE_PATH,
    SQLITE_STATE_SCHEMA_VERSION,
    get_index_statements,
    get_pragmas,
    get_schema_statements,
    stable_json_dumps,
    validate_database_path,
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


def test_1_schema_version_constant() -> None:
    check("schema version is 1", SQLITE_STATE_SCHEMA_VERSION == 1)
    check(
        "default path under scos/work/control_center/state",
        DEFAULT_STATE_DB_RELATIVE_PATH.startswith(
            "scos/work/control_center/state/"
        ),
    )


def test_2_schema_statements_cover_all_tables() -> None:
    statements = get_schema_statements()
    joined = " ".join(statements)
    for table in ("state_schema", "commands", "sessions", "events", "approvals", "results"):
        check(f"schema defines table {table}", f"CREATE TABLE IF NOT EXISTS {table}" in joined)


def test_3_index_statements_cover_required_indexes() -> None:
    statements = get_index_statements()
    joined = " ".join(statements)
    for fragment in (
        "events(subject_type, subject_id, sequence)",
        "events(created_at)",
        "commands(status)",
        "commands(session_id)",
        "sessions(status)",
        "approvals(subject_type, subject_id)",
        "approvals(decision)",
        "results(subject_type, subject_id)",
        "results(verdict)",
    ):
        check(f"index covers {fragment}", fragment in joined)


def test_4_pragmas_include_wal() -> None:
    pragmas = get_pragmas()
    check("WAL pragma present", "PRAGMA journal_mode=WAL" in pragmas)
    check("synchronous pragma present", "PRAGMA synchronous=NORMAL" in pragmas)
    check("foreign_keys pragma present", "PRAGMA foreign_keys=ON" in pragmas)
    check("busy_timeout pragma present", "PRAGMA busy_timeout=5000" in pragmas)


def test_5_stable_json_dumps_deterministic() -> None:
    a = stable_json_dumps({"b": 2, "a": 1})
    b = stable_json_dumps({"a": 1, "b": 2})
    check("stable json is key-order independent", a == b)
    check("stable json is sorted", a == '{"a":1,"b":2}')


def test_6_validate_database_path_rejects_urls() -> None:
    root = Path("C:/repo") if sys.platform.startswith("win") else Path("/repo")
    error = validate_database_path(root, Path("https://example.com/db.sqlite3"))
    check("url path rejected", error is not None and error.error_kind == "invalid_path")


def test_7_validate_database_path_rejects_traversal() -> None:
    root = Path("C:/repo") if sys.platform.startswith("win") else Path("/repo")
    error = validate_database_path(root, Path("../outside/db.sqlite3"))
    check("traversal rejected", error is not None and error.error_kind == "invalid_path")


def test_8_validate_database_path_accepts_default_relative_path() -> None:
    root = Path("C:/repo") if sys.platform.startswith("win") else Path("/repo")
    error = validate_database_path(root, Path(DEFAULT_STATE_DB_RELATIVE_PATH))
    check("default relative path accepted", error is None)


def main() -> int:
    tests = [
        test_1_schema_version_constant,
        test_2_schema_statements_cover_all_tables,
        test_3_index_statements_cover_required_indexes,
        test_4_pragmas_include_wal,
        test_5_stable_json_dumps_deterministic,
        test_6_validate_database_path_rejects_urls,
        test_7_validate_database_path_rejects_traversal,
        test_8_validate_database_path_accepts_default_relative_path,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
