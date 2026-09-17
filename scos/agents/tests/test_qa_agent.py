"""Regression tests for SCOS QA agent semantics.

Proves:
1. Valid real assets → QA PASS
2. Missing asset → QA FAIL (mandatory negative path)
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from scos.agents.qa_agent import QAAgent


def _make_asset(path: Path, content: bytes = b"FAKE_BYTES") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_qa_passes_with_valid_assets() -> None:
    """All assets present, sync ok, duration > 0 → passed = True."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset_a = tmp_path / "scene_00.png"
        asset_b = tmp_path / "scene_01.png"
        _make_asset(asset_a)
        _make_asset(asset_b)

        timeline = {
            "clips": [
                {"scene_id": "scene_00", "start": 0.0, "end": 2.0, "asset_path": str(asset_a)},
                {"scene_id": "scene_01", "start": 2.0, "end": 5.0, "asset_path": str(asset_b)},
            ],
            "total_duration": 5.0,
        }
        result = QAAgent().run({"edit_timeline": timeline})
        assert result["sync"] is True
        assert result["duration"] is True
        assert result["missing_assets"] == []
        assert result["passed"] is True


def test_qa_fails_with_missing_asset() -> None:
    """One asset missing → passed = False (mandatory negative path)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset_a = tmp_path / "scene_00.png"
        missing_b = tmp_path / "scene_01.png"  # NOT created
        _make_asset(asset_a)

        timeline = {
            "clips": [
                {"scene_id": "scene_00", "start": 0.0, "end": 2.0, "asset_path": str(asset_a)},
                {"scene_id": "scene_01", "start": 2.0, "end": 5.0, "asset_path": str(missing_b)},
            ],
            "total_duration": 5.0,
        }
        result = QAAgent().run({"edit_timeline": timeline})
        assert result["sync"] is True
        assert result["duration"] is True
        assert len(result["missing_assets"]) == 1
        assert str(missing_b) in result["missing_assets"]
        assert result["passed"] is False  # THE critical invariant


def test_qa_fails_with_all_assets_missing() -> None:
    """All assets missing → passed = False."""
    timeline = {
        "clips": [
            {"scene_id": "scene_00", "start": 0.0, "end": 2.0, "asset_path": "/nonexistent/a.png"},
            {"scene_id": "scene_01", "start": 2.0, "end": 5.0, "asset_path": "/nonexistent/b.png"},
        ],
        "total_duration": 5.0,
    }
    result = QAAgent().run({"edit_timeline": timeline})
    assert result["missing_assets"] == ["/nonexistent/a.png", "/nonexistent/b.png"]
    assert result["passed"] is False


def test_qa_fails_with_sync_error() -> None:
    """Clip start >= end → sync fails → passed = False."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset_a = tmp_path / "scene_00.png"
        _make_asset(asset_a)

        timeline = {
            "clips": [
                {"scene_id": "scene_00", "start": 5.0, "end": 2.0, "asset_path": str(asset_a)},
            ],
            "total_duration": 3.0,
        }
        result = QAAgent().run({"edit_timeline": timeline})
        assert result["sync"] is False
        assert result["passed"] is False


def test_qa_fails_with_zero_duration() -> None:
    """total_duration = 0 → duration fails → passed = False."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        asset_a = tmp_path / "scene_00.png"
        _make_asset(asset_a)

        timeline = {
            "clips": [
                {"scene_id": "scene_00", "start": 0.0, "end": 0.0, "asset_path": str(asset_a)},
            ],
            "total_duration": 0.0,
        }
        result = QAAgent().run({"edit_timeline": timeline})
        assert result["duration"] is False
        assert result["passed"] is False


if __name__ == "__main__":
    test_qa_passes_with_valid_assets()
    test_qa_fails_with_missing_asset()
    test_qa_fails_with_all_assets_missing()
    test_qa_fails_with_sync_error()
    test_qa_fails_with_zero_duration()
    print("ALL_QA_REGRESSION_TESTS_PASSED")
