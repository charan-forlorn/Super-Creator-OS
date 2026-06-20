"""test_montage.py — WF-2 music-montage tests.

UNIT/INTEGRATION on real assets when present (shot selection invariants + music
analysis sanity). A full render is slow (multi-shot encode) so it is NOT run here;
render verification is done manually via the CLI + frame review.

Run: python integrations/shortgen/tests/test_montage.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parents[1] / "highlight"))
import montage as MG  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def test_config():
    print("\n[1] config defaults match the approved plan")
    c = MG.MontageConfig()
    check("4 shots", c.n_shots == 4)
    check("speed 1.2x (video only)", c.speed == 1.2)
    check("game volume 0.5 (reduced 50%)", c.game_volume == 0.5)
    check("fit reframe", c.reframe == "fit")


def test_select_shots():
    print("\n[2] shot selection on the real clip — non-overlapping, ends on finale")
    raw = _HERE.parents[2] / "input" / "raw"
    vids = (list(raw.glob("*.mp4")) + list(raw.glob("*.MP4"))) if raw.exists() else []
    if not vids:
        print("        SKIP — no asset in input/raw/"); return
    shots = MG.select_shots(vids[0], 4)
    check("got up to 4 shots", 1 <= len(shots) <= 4)
    check("chronological by climax", shots == sorted(shots, key=lambda e: e["climax_t"]))
    # no overlap
    ok = all(shots[i]["end"] <= shots[i + 1]["start"] for i in range(len(shots) - 1))
    check("shots do not overlap", ok)
    check("finale = latest climax (payoff at the end)",
          shots[-1]["climax_t"] == max(s["climax_t"] for s in shots))
    print(f"        climaxes: {[s['climax_t'] for s in shots]}")


def test_analyze_music():
    print("\n[3] music analysis — hype section + beat period sane; music NOT sped")
    song = (_HERE.parents[2] / "input" / "song")
    m4a = list(song.glob("*.m4a")) + list(song.glob("*.mp3")) if song.exists() else []
    if not m4a:
        print("        SKIP — no music in input/song/"); return
    hype_t, period = MG.analyze_music(m4a[0], 14.0)
    check("hype_start within track", hype_t >= 0.0)
    check("beat period in a musical range (0.3..0.9s)", 0.3 <= period <= 0.9)
    print(f"        hype_start={hype_t:.1f}s  beat_period={period:.3f}s")


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" WF-2 MUSIC MONTAGE — TEST SUITE"); print("=" * 60)
    test_config(); test_select_shots(); test_analyze_music()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
