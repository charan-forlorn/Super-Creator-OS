"""test_asset_builder_v2.py — Stage 2 AssetBuilder v2 (style-aware) suite.

Validates: style influence, determinism, downstream compatibility (EditComposer +
FFmpeg engine), and manifest correctness. Uses a temp StyleMemoryEngine store.

Run: python scos/assets/tests/test_asset_builder_v2.py
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from scos.assets.asset_builder import _derive_run_id            # noqa: E402
from scos.assets.asset_builder_v2 import AssetBuilderV2          # noqa: E402
from scos.agents.edit_composer import EditComposer              # noqa: E402
from scos.memory.style_memory import StyleMemoryEngine          # noqa: E402
from scos.render import ffmpeg_engine                            # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "gaming", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "gaming", "start": 2.0, "end": 3.5},
    ],
    "total_duration": 3.5,
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _png_dims(p: Path) -> tuple[int, int]:
    d = p.read_bytes()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", d[16:24])


def _ffprobe_dims(p: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(p)],
        capture_output=True, text=True).stdout
    st = json.loads(out)["streams"][0]
    return st["width"], st["height"]


def _style(style_id, content_type, palette, freq, pacing, retention=0.9):
    return {
        "style_id": style_id, "content_type": content_type,
        "avg_color_palette": palette, "audio_frequency_bias": freq,
        "scene_pacing_profile": pacing, "retention_score": retention,
        "created_at": 1000,
    }


def _engine(tmp, profile):
    e = StyleMemoryEngine(Path(tmp) / f"sm_{os.urandom(4).hex()}.json")
    e.record_video_metrics(profile)
    return e


def _capture(res):
    """sha256 of every asset file, keyed by scene_id -> (png, wav)."""
    return {a["scene_id"]: (_sha(_REPO_ROOT / a["image_path"]),
                            _sha(_REPO_ROOT / a["audio_path"])) for a in res["assets"]}


def test_style_influence(tmp):
    print("\n[1] style influence — different styles -> different assets")
    eng_a = _engine(tmp, _style("warm", "gaming", [200, 60, 40], 300.0, 1.0))
    eng_b = _engine(tmp, _style("cool", "gaming", [40, 60, 200], 520.0, 2.0))
    cap_a = _capture(AssetBuilderV2(eng_a).run(SCENE_PLAN))   # writes run dir
    cap_b = _capture(AssetBuilderV2(eng_b).run(SCENE_PLAN))   # overwrites same paths
    check("PNG differs by style", cap_a["scene_00"][0] != cap_b["scene_00"][0])
    check("WAV differs by style", cap_a["scene_00"][1] != cap_b["scene_00"][1])


def test_determinism(tmp):
    print("\n[2] determinism — same plan + style -> identical bytes")
    eng = _engine(tmp, _style("warm", "gaming", [200, 60, 40], 300.0, 1.0))
    r1 = AssetBuilderV2(eng).run(SCENE_PLAN)
    cap1 = _capture(r1)
    man1 = _sha(_REPO_ROOT / r1["manifest_path"])
    r2 = AssetBuilderV2(eng).run(SCENE_PLAN)
    cap2 = _capture(r2)
    man2 = _sha(_REPO_ROOT / r2["manifest_path"])
    check("run_id stable + matches v1 rule",
          r1["run_id"] == r2["run_id"] == _derive_run_id(SCENE_PLAN))
    check("png+wav byte-identical across runs", cap1 == cap2)
    check("manifest byte-identical across runs", man1 == man2)


def test_manifest(tmp):
    print("\n[3] manifest correctness")
    eng = _engine(tmp, _style("warm", "gaming", [200, 60, 40], 300.0, 1.0))
    res = AssetBuilderV2(eng).run(SCENE_PLAN)
    man = json.loads((_REPO_ROOT / res["manifest_path"]).read_text(encoding="utf-8"))
    check("engine tag", man.get("engine") == "asset_builder_v2")
    check("style_enabled true", man.get("style_enabled") is True)
    check("run_id matches", man["run_id"] == res["run_id"])
    ids = [a["scene_id"] for a in man["assets"]]
    check("assets sorted by scene_id", ids == sorted(ids) == ["scene_00", "scene_01"])
    paths = [a["image_path"] for a in man["assets"]] + [a["audio_path"] for a in man["assets"]]
    check("all paths relative", all(not Path(p).is_absolute() and ":" not in p for p in paths))
    a0 = res["assets"][0]
    check("asset contract (image/audio/asset_path alias/duration)",
          a0["asset_path"] == a0["image_path"]
          and {"scene_id", "image_path", "audio_path", "duration"} <= set(a0))
    img = _REPO_ROOT / a0["image_path"]
    check("png is 1080x1920", _png_dims(img) == (1080, 1920))


def test_compatibility(tmp):
    print("\n[4] downstream compatibility — EditComposer + FFmpeg -> 1080x1920 mp4")
    eng = _engine(tmp, _style("warm", "gaming", [200, 60, 40], 300.0, 1.0))
    res = AssetBuilderV2(eng).run(SCENE_PLAN)
    edit_timeline = EditComposer().run({"scene_plan": SCENE_PLAN, "asset_bundle": res})
    check("composer produced one clip per scene",
          len(edit_timeline["clips"]) == len(SCENE_PLAN["scenes"]))
    render = ffmpeg_engine.render({"run_id": res["run_id"], "edit_timeline": edit_timeline})
    mp4 = Path(render["video_path"])
    check("mp4 exists & non-empty", mp4.exists() and mp4.stat().st_size > 0)
    check("mp4 is 1080x1920", _ffprobe_dims(mp4) == (1080, 1920))


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 2 — ASSET BUILDER v2 — TEST SUITE"); print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_style_influence(tmp)
        test_determinism(tmp)
        test_manifest(tmp)
        test_compatibility(tmp)
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
