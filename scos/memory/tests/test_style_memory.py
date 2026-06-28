"""test_style_memory.py — SCOS Stage 2 Style Memory Engine suite.

Pure stdlib. Uses a temp store path so the real scos/work/memory file is untouched.
Run: python scos/memory/tests/test_style_memory.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from scos.memory.style_memory import StyleMemoryEngine  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _profile(style_id, content_type, retention, freq=300.0):
    return {
        "style_id": style_id,
        "content_type": content_type,
        "avg_color_palette": [10, 20, 30],
        "audio_frequency_bias": freq,
        "scene_pacing_profile": 1.2,
        "retention_score": retention,
        "created_at": 1000,
    }


def test_record_and_list(path):
    print("\n[1] record + list")
    e = StyleMemoryEngine(path)
    e.record_video_metrics(_profile("s_b", "gaming", 0.7))
    e.record_video_metrics(_profile("s_a", "gaming", 0.9))
    ids = [s["style_id"] for s in e.list_styles()]
    check("both recorded", set(ids) == {"s_a", "s_b"})
    check("listed sorted by style_id", ids == ["s_a", "s_b"])


def test_retrieve_best(path):
    print("\n[2] retrieve best by content_type")
    e = StyleMemoryEngine(path)
    e.record_video_metrics(_profile("g_low", "gaming", 0.6))
    e.record_video_metrics(_profile("g_high", "gaming", 0.95))
    e.record_video_metrics(_profile("v_one", "vlog", 0.8))
    got = e.get_style("gaming")
    check("highest retention wins", got["style_id"] == "g_high")
    check("right content_type", got["content_type"] == "gaming")


def test_default(path):
    print("\n[3] default style when no match")
    e = StyleMemoryEngine(path)
    d = e.get_style("unseen_type")
    check("style_id default", d["style_id"] == "default")
    check("content_type echoed", d["content_type"] == "unseen_type")
    check("default palette", d["avg_color_palette"] == [128, 128, 128])
    check("default freq 440.0", d["audio_frequency_bias"] == 440.0)
    check("created_at is int", isinstance(d["created_at"], int))


def test_update(path):
    print("\n[4] partial update preserves other fields")
    e = StyleMemoryEngine(path)
    e.record_video_metrics(_profile("u1", "ads", 0.5, freq=250.0))
    e.update_style("u1", {"retention_score": 0.88})
    s = e.list_styles()[0]
    check("retention updated", s["retention_score"] == 0.88)
    check("freq preserved", s["audio_frequency_bias"] == 250.0)
    check("palette preserved", s["avg_color_palette"] == [10, 20, 30])
    raised = False
    try:
        e.update_style("nope", {"retention_score": 1.0})
    except ValueError:
        raised = True
    check("unknown style_id -> ValueError", raised)


def test_persistence(path):
    print("\n[5] persistence across engine instances")
    e1 = StyleMemoryEngine(path)
    e1.record_video_metrics(_profile("p1", "gaming", 0.7))
    e2 = StyleMemoryEngine(path)
    check("reloaded from disk", [s["style_id"] for s in e2.list_styles()] == ["p1"])
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    check("on-disk JSON is a valid list", isinstance(raw, list) and raw[0]["style_id"] == "p1")


def test_deterministic_ordering(path):
    print("\n[6] deterministic ordering / stable serialization")
    e = StyleMemoryEngine(path)
    for sid in ["z", "m", "a", "d"]:
        e.record_video_metrics(_profile(sid, "gaming", 0.5))
    check("list sorted regardless of insert order",
          [s["style_id"] for s in e.list_styles()] == ["a", "d", "m", "z"])
    blob1 = Path(path).read_text(encoding="utf-8")
    StyleMemoryEngine(path)._save()  # re-serialize
    blob2 = Path(path).read_text(encoding="utf-8")
    check("re-serialization is byte-stable", blob1 == blob2)


def test_no_duplicates(path):
    print("\n[7] no duplicate style_id")
    e = StyleMemoryEngine(path)
    e.record_video_metrics(_profile("dup", "gaming", 0.5))
    raised = False
    try:
        e.record_video_metrics(_profile("dup", "gaming", 0.9))
    except ValueError:
        raised = True
    check("duplicate -> ValueError", raised)
    check("store count unchanged", len(e.list_styles()) == 1)


def _fresh_path(tmp):
    # Unique empty store path per test (file created on first save).
    p = Path(tmp) / f"store_{os.urandom(4).hex()}.json"
    return str(p)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 2 — STYLE MEMORY ENGINE — TEST SUITE"); print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_record_and_list(_fresh_path(tmp))
        test_retrieve_best(_fresh_path(tmp))
        test_default(_fresh_path(tmp))
        test_update(_fresh_path(tmp))
        test_persistence(_fresh_path(tmp))
        test_deterministic_ordering(_fresh_path(tmp))
        test_no_duplicates(_fresh_path(tmp))
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
