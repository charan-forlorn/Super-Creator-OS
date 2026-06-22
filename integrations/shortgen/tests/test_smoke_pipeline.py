"""test_smoke_pipeline.py — P0-4 end-to-end smoke test: detect_highlights -> render_short.

The per-module integration tests (test_highlight_engine.py, test_short_generator.py)
only exercise real video against input/raw/, which is intentionally emptied by the
project's Raw Input Cleanup automation after every edit job — so on a clean checkout
those real-asset branches always SKIP and the pipeline as a WHOLE has never actually
been run against a real file in this environment.

This test uses input/reference/ instead (untouched by that cleanup) to prove the two
new WF-1/WF-2 modules actually chain together end-to-end: a real video in, a non-empty
9:16 short out. It is a does-it-crash check, not a correctness/quality test.

Run: python integrations/shortgen/tests/test_smoke_pipeline.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
sys.path.insert(0, str(_ROOT / "integrations" / "highlight"))
sys.path.insert(0, str(_ROOT / "integrations" / "shortgen"))
import highlight_engine as H   # noqa: E402
import short_generator as SG   # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def test_smoke_real_clip():
    print("\n[1] smoke (real asset) — detect_highlights -> render_short, end to end")
    ref_dir = _ROOT / "input" / "reference"
    vids = sorted(ref_dir.glob("*.mp4")) if ref_dir.exists() else []
    if not vids:
        print("        SKIP — no .mp4 asset in input/reference/")
        return
    video = vids[0]
    for v in vids:
        if v.stat().st_size < video.stat().st_size:
            video = v
    print(f"        using {video.name} ({video.stat().st_size / 1e6:.1f} MB)")

    cands = H.detect_highlights(video, H.HighlightConfig(max_candidates=3))
    check("detect_highlights returns a list", isinstance(cands, list))
    check("at least one candidate found on a real clip", len(cands) > 0)
    if not cands:
        return
    check("candidates are well-formed",
          all(0 <= c["score"] <= 100 and c["start"] < c["end"] for c in cands))

    best = max(cands, key=lambda c: c["score"])
    out = _ROOT / "work" / "video" / "_smoke_test_short.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = SG.render_short(video, best, out, SG.ShortOptions(reframe="fit", hook="SMOKE TEST"))
    check("render_short reports ok", res.get("ok") is True)
    check("output file exists", out.exists())
    if out.exists():
        check("output file is non-empty", out.stat().st_size > 0)
        print(f"        (rendered {res.get('clip_seconds')}s short -> {out})")


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60)
    print(" P0-4 SMOKE TEST — detect_highlights -> render_short (real clip)")
    print("=" * 60)
    test_smoke_real_clip()
    print("\n" + "=" * 60)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
