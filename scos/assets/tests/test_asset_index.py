from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from scos.assets.asset_index import (
    STATE_CHANGED,
    STATE_MISSING,
    STATE_READY,
    build_asset_index,
)


def _png(path: Path, color: str = "blue") -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={color}:s=320x180",
         "-frames:v", "1", str(path)],
        check=True,
    )


def _wav(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-ar", "48000", "-ac", "1", str(path)],
        check=True,
    )


def test_asset_index_is_deterministic_and_deduplicates_content() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _png(root / "one.png", "blue")
        (root / "two.png").write_bytes((root / "one.png").read_bytes())
        _wav(root / "voice.wav")

        first = build_asset_index([root])
        second = build_asset_index([root])

        assert first.index_hash == second.index_hash
        assert first.unique_sha256_count == 2
        assert first.duplicate_group_count == 1
        duplicate = next(item for item in first.entries if item.name == "two.png")
        assert duplicate.duplicate_of is not None
        assert all(item.state == STATE_READY for item in first.entries)


def test_changed_bytes_are_detected_against_previous_index() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _png(root / "asset.png", "blue")
        previous = build_asset_index([root])
        _png(root / "asset.png", "red")
        current = build_asset_index([root], previous=previous)

        assert current.entries[0].state == STATE_CHANGED
        assert current.entries[0].sha256 != previous.entries[0].sha256


def test_missing_root_is_explicit_and_does_not_fabricate_assets() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "missing"
        index = build_asset_index([root])
        assert len(index.entries) == 1
        assert index.entries[0].state == STATE_MISSING
        assert index.unique_sha256_count == 0


def test_scan_budget_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _png(root / "a.png")
        try:
            build_asset_index([root], max_total_bytes=1)
        except RuntimeError as exc:
            assert "byte budget exceeded" in str(exc)
        else:
            raise AssertionError("expected byte budget failure")
