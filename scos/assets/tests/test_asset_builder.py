"""test_asset_builder.py — Module 3 unit suite.

Deterministic-generation, file-format, and manifest checks. Pure stdlib + numpy;
no ffmpeg, no network. Run: python scos/assets/tests/test_asset_builder.py
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import wave
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from scos.assets import AssetBuilder, AssetConfig  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


SCENE_PLAN = {
    "scenes": [
        {"scene_id": "scene_00", "topic": "intro hook", "start": 0.0, "end": 2.0},
        {"scene_id": "scene_01", "topic": "main point", "start": 2.0, "end": 3.5},
    ],
    "total_duration": 3.5,
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _png_dims(p: Path) -> tuple[int, int]:
    data = p.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "bad PNG signature"
    # IHDR width/height are the first two big-endian uint32 of the IHDR data,
    # which begins at byte 16 (8 sig + 4 len + 4 'IHDR').
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def test_build_and_formats():
    print("\n[1] build + asset formats")
    res = AssetBuilder().run(SCENE_PLAN)
    check("run_id present", bool(res.get("run_id")))
    check("two assets", len(res["assets"]) == 2)
    for a in res["assets"]:
        img = _REPO_ROOT / a["image_path"]
        aud = _REPO_ROOT / a["audio_path"]
        check(f"{a['scene_id']} png exists & non-empty", img.exists() and img.stat().st_size > 0)
        check(f"{a['scene_id']} png is 1080x1920", _png_dims(img) == (1080, 1920))
        with wave.open(str(aud), "rb") as w:
            ok = (w.getframerate() == 48000 and w.getnchannels() == 1)
            wav_dur = w.getnframes() / w.getframerate()
        check(f"{a['scene_id']} wav 48000/mono", ok)
        check(f"{a['scene_id']} wav duration matches", abs(wav_dur - a["duration"]) < 0.02)


def test_contract_and_manifest():
    print("\n[2] output contract + manifest")
    res = AssetBuilder().run(SCENE_PLAN)
    a0 = res["assets"][0]
    check("asset has scene_id/image_path/audio_path/duration",
          {"scene_id", "image_path", "audio_path", "duration"} <= set(a0))
    check("asset_path alias == image_path", a0.get("asset_path") == a0["image_path"])
    manifest = json.loads((_REPO_ROOT / res["manifest_path"]).read_text(encoding="utf-8"))
    check("manifest run_id matches", manifest["run_id"] == res["run_id"])
    check("manifest 1:1 scene mapping",
          [m["scene_id"] for m in manifest["assets"]] == ["scene_00", "scene_01"])
    all_paths = [m["image_path"] for m in manifest["assets"]] + \
                [m["audio_path"] for m in manifest["assets"]]
    check("all manifest paths are relative (no absolute / no drive)",
          all(not Path(p).is_absolute() and ":" not in p for p in all_paths))


def test_determinism():
    print("\n[3] determinism — same input -> byte-identical files")
    r1 = AssetBuilder().run(SCENE_PLAN)
    sha_a = {a["scene_id"]: (_sha(_REPO_ROOT / a["image_path"]),
                             _sha(_REPO_ROOT / a["audio_path"])) for a in r1["assets"]}
    man_a = _sha(_REPO_ROOT / r1["manifest_path"])
    r2 = AssetBuilder().run(SCENE_PLAN)
    sha_b = {a["scene_id"]: (_sha(_REPO_ROOT / a["image_path"]),
                             _sha(_REPO_ROOT / a["audio_path"])) for a in r2["assets"]}
    man_b = _sha(_REPO_ROOT / r2["manifest_path"])
    check("run_id stable across runs", r1["run_id"] == r2["run_id"])
    check("png+wav sha256 identical across runs", sha_a == sha_b)
    check("manifest sha256 identical across runs", man_a == man_b)


def test_distinct_per_scene():
    print("\n[4] scenes are visually/audibly distinct")
    res = AssetBuilder().run(SCENE_PLAN)
    img0 = _sha(_REPO_ROOT / res["assets"][0]["image_path"])
    img1 = _sha(_REPO_ROOT / res["assets"][1]["image_path"])
    aud0 = _sha(_REPO_ROOT / res["assets"][0]["audio_path"])
    aud1 = _sha(_REPO_ROOT / res["assets"][1]["audio_path"])
    check("distinct images per scene", img0 != img1)
    check("distinct audio per scene", aud0 != aud1)


def test_honest_failure():
    print("\n[5] honest failure")
    raised = False
    try:
        AssetBuilder().run({"scenes": [], "total_duration": 0})
    except ValueError:
        raised = True
    check("empty scenes -> ValueError", raised)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" MODULE 3 — ASSET BUILDER — TEST SUITE"); print("=" * 60)
    test_build_and_formats()
    test_contract_and_manifest()
    test_determinism()
    test_distinct_per_scene()
    test_honest_failure()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
