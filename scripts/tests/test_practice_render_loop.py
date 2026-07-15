"""Tests for SCOS x HVS daily practice-render loop (item #2).

All tests inject a fake `renderer` so no real HVS render or file deletion
touches the workspace. We verify: learn-only mode records patterns without
real render; real mode records patterns with render_success=True; the learned
records land in the SCOS database.json with the practice schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.practice_render_loop import (
    PLATFORM_FORMATS,
    _DEFAULT_OUTPUT,
    append_learned_pattern,
    practice_one,
    run_daily,
)


def _fake_renderer(success: bool):
    def _r(format_id: str, out_path: str) -> tuple[bool, str]:
        return success, f"fake-rendered {format_id} -> {out_path}"
    return _r


def test_learn_only_records_patterns_no_real(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    result = run_daily(memory_db=db, allow_real=False, renderer=_fake_renderer(True))
    assert result["simulated"] is True
    assert result["learned_patterns"] == len(PLATFORM_FORMATS)
    rows = json.loads(db.read_text(encoding="utf-8"))
    assert len(rows) == len(PLATFORM_FORMATS)
    assert all(r["is_practice"] for r in rows)
    assert all(r["render_success"] is False for r in rows)  # simulated


def test_real_mode_records_render_success(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    result = run_daily(memory_db=db, allow_real=True, renderer=_fake_renderer(True))
    assert result["real_renders"] == len(PLATFORM_FORMATS)
    rows = json.loads(db.read_text(encoding="utf-8"))
    assert all(r["render_success"] is True for r in rows)
    # real practice renders are QA-passed by the renderer contract
    assert all(r["qa_pass"] is True for r in rows)


def test_real_mode_render_failure_still_learns(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    result = run_daily(memory_db=db, allow_real=True, renderer=_fake_renderer(False))
    # even on failure we record the attempt (so the loop never silently loses signal)
    rows = json.loads(db.read_text(encoding="utf-8"))
    assert len(rows) == len(PLATFORM_FORMATS)
    assert all(r["render_success"] is False for r in rows)


def test_practice_one_real_deletes_video_via_hook(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one("tiktok_ig_yt_shorts", memory_db=db, allow_real=True,
                       renderer=_fake_renderer(True), delete_fn=_del)
    assert rep["render_ok"] is True
    assert rep["simulated"] is False
    assert rep["deleted_videos"] == [str(_DEFAULT_OUTPUT / "tiktok_ig_yt_shorts.mp4")]
    assert deleted_log  # deletion hook was invoked


def test_practice_one_real_no_delete_on_render_fail(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one("tiktok_ig_yt_shorts", memory_db=db, allow_real=True,
                       renderer=_fake_renderer(False), delete_fn=_del)
    assert rep["render_ok"] is False
    assert rep["deleted_videos"] == []  # failure → no deletion
    assert not deleted_log


def test_practice_one_real_hvs_blocked_records_failure(tmp_path: Path):
    """Simulate HVS returning BLOCKED (uncertified project / missing approval).

    We inject a renderer that returns False to stand in for the HVS BLOCKED
    path, and assert we never claim render_success and never delete.
    """
    db = tmp_path / "memory" / "database.json"
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one("youtube_website", memory_db=db, allow_real=True,
                       renderer=_fake_renderer(False), delete_fn=_del)
    assert rep["render_ok"] is False
    assert rep["simulated"] is False  # it did attempt a REAL (blocked) run
    rows = json.loads(db.read_text(encoding="utf-8"))
    assert rows[-1]["render_success"] is False
    assert rows[-1]["qa_pass"] is False
    assert not deleted_log  # blocked → keep evidence, never delete


def test_practice_one_uses_correct_format(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    rep = practice_one("tiktok_ig_yt_shorts", memory_db=db,
                       allow_real=False, renderer=_fake_renderer(True))
    assert rep["format_id"] == "vertical_9_16"
    assert rep["simulated"] is True
    assert rep["learned_record"]


def test_append_learned_pattern_schema(tmp_path: Path):
    db = tmp_path / "memory" / "database.json"
    rec = append_learned_pattern(db, "ig_fb_feed", "square_1_1",
                                 "1080x1080", 30, "lesson", simulated=False)
    assert rec["schema_version"] == "v4"
    assert rec["engine"] == "practice-loop"
    assert rec["render_specs"]["format_id"] == "square_1_1"
    rows = json.loads(db.read_text(encoding="utf-8"))
    assert rows[0]["project_name"] == rec["project_name"]
