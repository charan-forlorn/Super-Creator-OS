"""Tests for SCOS x HVS daily practice-render loop runtime memory routing.

All tests use temporary canonical/runtime paths. No real HVS render, production
memory/database.json, production memory/runtime, or source cleanup is touched.
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


def _runtime_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _seed_canonical(path: Path, payload: bytes = b"[]") -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path.read_bytes()


def _file_tree_bytes(path: Path) -> dict[str, bytes]:
    if not path.exists():
        return {}
    return {
        str(p.relative_to(path)): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _seed_runtime_sentinel(path: Path) -> None:
    record = append_learned_pattern(
        path.parent / "canonical-equivalent.json",
        "ig_fb_feed",
        "square_1_1",
        "1080x1080",
        30,
        "sentinel",
        simulated=True,
        runtime_journal=path,
        attempt_id="sentinel-default-state",
    )
    ok = record.get("learning_persisted")
    info = record.get("learning_info")
    assert ok, info


def test_learn_only_records_patterns_to_runtime_no_real(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical)

    result = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=False,
        renderer=_fake_renderer(True),
    )

    assert result["simulated"] is True
    assert result["learned_patterns"] == len(PLATFORM_FORMATS)
    assert canonical.read_bytes() == canonical_before
    rows = _runtime_rows(runtime)
    assert len(rows) == len(PLATFORM_FORMATS)
    assert all(r["is_practice"] for r in rows)
    assert all(r["engine"] == "practice-loop" for r in rows)
    assert all(r["record_type"] == "practice_render" for r in rows)
    assert all(r["render_success"] is False for r in rows)  # simulated


def test_real_mode_records_render_success_to_runtime(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical)

    result = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(True),
    )

    assert result["real_renders"] == len(PLATFORM_FORMATS)
    assert canonical.read_bytes() == canonical_before
    rows = _runtime_rows(runtime)
    assert all(r["render_success"] is True for r in rows)
    assert all(r["qa_pass"] is True for r in rows)


def test_real_mode_render_failure_still_learns_to_runtime(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)

    result = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(False),
    )

    rows = _runtime_rows(runtime)
    assert len(rows) == len(PLATFORM_FORMATS)
    assert all(r["render_success"] is False for r in rows)
    assert result["learned_patterns"] == len(PLATFORM_FORMATS)


def test_practice_one_real_deletes_video_via_hook_after_persistence(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one(
        "tiktok_ig_yt_shorts",
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(True),
        delete_fn=_del,
    )

    assert rep["render_ok"] is True
    assert rep["learning_persisted"] is True
    assert rep["simulated"] is False
    assert rep["deleted_videos"] == [str(_DEFAULT_OUTPUT / "tiktok_ig_yt_shorts.mp4")]
    assert deleted_log


def test_practice_one_real_no_delete_on_render_fail(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one(
        "tiktok_ig_yt_shorts",
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(False),
        delete_fn=_del,
    )

    assert rep["render_ok"] is False
    assert rep["deleted_videos"] == []
    assert not deleted_log


def test_cleanup_not_executed_after_persistence_failure(monkeypatch, tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    deleted_log = []

    def _fail_append(record, *, runtime_path=None):
        return False, "forced runtime append failure"

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    monkeypatch.setattr("scripts.practice_render_loop.memory_store.append_runtime_record", _fail_append)
    rep = practice_one(
        "tiktok_ig_yt_shorts",
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(True),
        delete_fn=_del,
    )

    assert rep["render_ok"] is True
    assert rep["learning_persisted"] is False
    assert "forced runtime append failure" in rep["learning_error"]
    assert rep["learned_record"] is None
    assert rep["deleted_videos"] == []
    assert not deleted_log
    assert not runtime.exists()


def test_practice_one_real_hvs_blocked_records_failure(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    deleted_log = []

    def _del(path: str) -> list[str]:
        deleted_log.append(path)
        return [path]

    rep = practice_one(
        "youtube_website",
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=True,
        renderer=_fake_renderer(False),
        delete_fn=_del,
    )

    assert rep["render_ok"] is False
    assert rep["simulated"] is False
    rows = _runtime_rows(runtime)
    assert rows[-1]["render_success"] is False
    assert rows[-1]["qa_pass"] is False
    assert not deleted_log


def test_practice_one_uses_correct_format(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)

    rep = practice_one(
        "tiktok_ig_yt_shorts",
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=False,
        renderer=_fake_renderer(True),
    )

    assert rep["format_id"] == "vertical_9_16"
    assert rep["simulated"] is True
    assert rep["learned_record"]


def test_append_learned_pattern_schema(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)

    rec = append_learned_pattern(
        canonical,
        "ig_fb_feed",
        "square_1_1",
        "1080x1080",
        30,
        "lesson",
        simulated=False,
        runtime_journal=runtime,
    )

    assert rec["schema_version"] == "v4"
    assert rec["engine"] == "practice-loop"
    assert rec["record_type"] == "practice_render"
    assert rec["render_specs"]["format_id"] == "square_1_1"
    rows = _runtime_rows(runtime)
    assert rows[0]["project_name"] == rec["project_name"]


def test_dry_run_writes_neither_canonical_nor_runtime(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical)

    result = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        allow_real=False,
        persist_learning=False,
        renderer=_fake_renderer(True),
    )

    assert result["learned_patterns"] == 0
    assert canonical.read_bytes() == canonical_before
    assert not runtime.exists()
    assert not runtime.parent.exists()


def test_identical_replay_is_idempotent(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)

    first = run_daily(memory_db=canonical, runtime_journal=runtime, renderer=_fake_renderer(True))
    second = run_daily(memory_db=canonical, runtime_journal=runtime, renderer=_fake_renderer(True))

    assert first["learned_patterns"] == len(PLATFORM_FORMATS)
    assert second["learned_patterns"] == 0
    assert len(_runtime_rows(runtime)) == len(PLATFORM_FORMATS)


def test_distinct_attempt_is_retained(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)

    first = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        attempt_id="attempt-one",
        renderer=_fake_renderer(True),
    )
    second = run_daily(
        memory_db=canonical,
        runtime_journal=runtime,
        attempt_id="attempt-two",
        renderer=_fake_renderer(True),
    )

    assert first["learned_patterns"] == len(PLATFORM_FORMATS)
    assert second["learned_patterns"] == len(PLATFORM_FORMATS)
    assert len(_runtime_rows(runtime)) == len(PLATFORM_FORMATS) * 2


def test_malformed_runtime_journal_fails_closed(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    runtime.parent.mkdir(parents=True)
    runtime.write_text("{broken\n", encoding="utf-8")
    before = runtime.read_bytes()

    result = run_daily(memory_db=canonical, runtime_journal=runtime, renderer=_fake_renderer(True))

    assert result["learned_patterns"] == 0
    assert all(r["learning_persisted"] is False for r in result["reports"])
    assert runtime.read_bytes() == before


def test_missing_runtime_directory_created_only_during_write(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    _seed_canonical(canonical)
    assert not runtime.parent.exists()

    append_learned_pattern(
        canonical,
        "ig_fb_feed",
        "square_1_1",
        "1080x1080",
        30,
        "lesson",
        simulated=True,
        runtime_journal=runtime,
        persist=False,
    )
    assert not runtime.parent.exists()

    append_learned_pattern(
        canonical,
        "ig_fb_feed",
        "square_1_1",
        "1080x1080",
        30,
        "lesson",
        simulated=True,
        runtime_journal=runtime,
    )
    assert runtime.parent.exists()
    assert runtime.exists()


def test_malformed_canonical_db_is_not_overwritten(tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    runtime = tmp_path / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical, b"{bad canonical")

    result = run_daily(memory_db=canonical, runtime_journal=runtime, renderer=_fake_renderer(True))

    assert result["learned_patterns"] == len(PLATFORM_FORMATS)
    assert canonical.read_bytes() == canonical_before
    assert len(_runtime_rows(runtime)) == len(PLATFORM_FORMATS)


def test_default_runtime_path_absent_when_temp_paths_are_injected(monkeypatch, tmp_path: Path):
    canonical = tmp_path / "memory" / "database.json"
    injected_runtime = tmp_path / "runtime" / "practice-render.jsonl"
    default_runtime = tmp_path / "production-equivalent" / "memory" / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical)

    monkeypatch.setattr(
        "scripts.practice_render_loop.memory_store.DEFAULT_RUNTIME_JOURNAL",
        default_runtime,
    )
    monkeypatch.setattr("scripts.practice_render_loop._DEFAULT_RUNTIME_JOURNAL", default_runtime)

    run_daily(memory_db=canonical, runtime_journal=injected_runtime, renderer=_fake_renderer(True))

    assert canonical.read_bytes() == canonical_before
    assert len(_runtime_rows(injected_runtime)) == len(PLATFORM_FORMATS)
    assert not default_runtime.exists()
    assert not default_runtime.parent.exists()


def test_preexisting_default_runtime_state_preserved_when_temp_paths_are_injected(
    monkeypatch, tmp_path: Path
):
    canonical = tmp_path / "memory" / "database.json"
    injected_runtime = tmp_path / "runtime" / "practice-render.jsonl"
    default_runtime = tmp_path / "production-equivalent" / "memory" / "runtime" / "practice-render.jsonl"
    canonical_before = _seed_canonical(canonical)
    _seed_runtime_sentinel(default_runtime)
    default_before = _file_tree_bytes(default_runtime.parent)

    monkeypatch.setattr(
        "scripts.practice_render_loop.memory_store.DEFAULT_RUNTIME_JOURNAL",
        default_runtime,
    )
    monkeypatch.setattr("scripts.practice_render_loop._DEFAULT_RUNTIME_JOURNAL", default_runtime)

    run_daily(memory_db=canonical, runtime_journal=injected_runtime, renderer=_fake_renderer(True))

    assert canonical.read_bytes() == canonical_before
    assert len(_runtime_rows(injected_runtime)) == len(PLATFORM_FORMATS)
    assert _file_tree_bytes(default_runtime.parent) == default_before


def test_daily_report_wrapper_remains_compatible(monkeypatch):
    import scripts.daily_practice_report as DPR

    def fake_run_daily(allow_real: bool = False):
        return {
            "date": "2026-07-15",
            "platforms": 1,
            "learned_patterns": 1,
            "real_renders": 0,
            "reports": [
                {
                    "simulated": True,
                    "render_ok": True,
                    "platform_key": "ig_fb_feed",
                    "format_id": "square_1_1",
                    "learned_record": "Practice ig_fb_feed",
                }
            ],
        }

    monkeypatch.setattr(DPR, "run_daily", fake_run_daily)
    report = DPR.build_report(allow_real=False)
    assert "Practice Render Loop" in report
    assert "ig_fb_feed" in report
    assert "Practice ig_fb_feed" in report
