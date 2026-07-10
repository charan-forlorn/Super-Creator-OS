from __future__ import annotations

import configparser
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTEST_CONFIG = REPO_ROOT / "pytest.ini"


def _tracked_pytest_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    tracked: list[str] = []
    for raw_path in result.stdout.splitlines():
        path = raw_path.replace("\\", "/")
        name = Path(path).name
        if name.startswith("test_") or name.endswith("_test.py"):
            tracked.append(path)
    return sorted(tracked)


def _pytest_config_values(key: str) -> set[str]:
    parser = configparser.ConfigParser()
    parser.read(PYTEST_CONFIG)
    raw = parser["pytest"].get(key, "")
    return {line.strip() for line in raw.splitlines() if line.strip()}


def test_pytest_collection_roots_cover_all_tracked_pytest_files() -> None:
    testpaths = _pytest_config_values("testpaths")
    tracked_tests = _tracked_pytest_files()

    assert tracked_tests, "expected tracked pytest files in this repository"
    assert testpaths == {"integrations", "scos", "scripts"}

    outside_configured_roots = [
        path
        for path in tracked_tests
        if not any(path == root or path.startswith(f"{root}/") for root in testpaths)
    ]
    assert outside_configured_roots == []


def test_generated_work_storage_is_not_a_tracked_pytest_root() -> None:
    norecursedirs = _pytest_config_values("norecursedirs")
    tracked_tests = _tracked_pytest_files()

    assert "work" in norecursedirs
    assert [path for path in tracked_tests if path.startswith("work/")] == []
    assert [path for path in tracked_tests if path.startswith("scos/work/")] == []
