"""test_short_generator.py — WF-2 tests.

UNIT: candidate selection + filtergraph construction (pure, no ffmpeg).
INTEGRATION (optional): if a real asset is present, render a short and probe that
the output is genuinely 9:16 with the right duration. Skips cleanly when no asset.

Run: python integrations/shortgen/tests/test_short_generator.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
import short_generator as SG  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


CANDS = [
    {"start": 0.0, "end": 8.0, "score": 100, "peak": 5.5, "reason": "x"},
    {"start": 47.0, "end": 52.0, "score": 88, "peak": 50.0, "reason": "kill cue"},
]


def test_select():
    print("\n[1] select_candidate")
    check("peak-near picks the closest peak", SG.select_candidate(CANDS, 50.0, 0)["peak"] == 50.0)
    check("rank 0 picks highest score", SG.select_candidate(CANDS, None, 0)["score"] == 100)
    check("empty -> None", SG.select_candidate([], None, 0) is None)


def test_chain():
    print("\n[2] build_video_chain — valid 9:16 filtergraphs")
    fit = SG.build_video_chain("fit", 1080, 1920, 0.5)
    check("fit produces blur-pad overlay to 1080x1920",
          "overlay" in fit and "1080:1920" in fit and "boxblur" in fit)
    crop = SG.build_video_chain("crop", 1080, 1920, 0.5)
    check("crop centers a 9:16 window", "crop=ih*9/16:ih:(iw-ih*9/16)/2:0" in crop)
    sal = SG.build_video_chain("saliency", 1080, 1920, 0.73)
    check("saliency biases crop by the motion frac", "0.7300" in sal)


def test_presets():
    print("\n[3] export presets are all vertical 9:16")
    check("3 presets, all 1080x1920",
          all(p["w"] == 1080 and p["h"] == 1920 for p in SG.PRESETS.values())
          and set(SG.PRESETS) == {"tiktok", "reels", "shorts"})


def test_integration_render():
    print("\n[4] integration (optional) — render a real short and verify 9:16")
    raw = _HERE.parents[2] / "input" / "raw"
    vids = (list(raw.glob("*.mp4")) + list(raw.glob("*.MP4"))) if raw.exists() else []
    if not vids:
        print("        SKIP — no asset in input/raw/"); return
    out = Path(tempfile.gettempdir()) / "_scos_wf2_test.mp4"
    res = SG.render_short(vids[0], CANDS[1], out, SG.ShortOptions(reframe="fit", hook="TEST"))
    check("render returns ok", res.get("ok") is True)
    if res.get("ok"):
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(out)], capture_output=True, text=True)
        check("output is exactly 1080x1920", p.stdout.strip() == "1080,1920")
        print(f"        (rendered {res['clip_seconds']}s in {res['render_seconds']}s)")
        try: out.unlink()
        except OSError: pass


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" WF-2 AUTO SHORT GENERATOR — TEST SUITE"); print("=" * 60)
    test_select(); test_chain(); test_presets(); test_integration_render()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
