"""test_narrative_engine.py — WF-1 v2 tests.

UNIT: the Buildup Sufficiency Gate + Arc Score + schema on synthetic signals.
INTEGRATION (optional): on a real asset, assert episodes carry buildup before climax.

Run: python integrations/highlight/tests/test_narrative_engine.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
import narrative_engine as NE  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def test_arc_score_rewards_ramp():
    print("\n[1] Arc Score rewards a rising ramp into the peak")
    cfg = NE.NarrativeConfig()
    ramp_up = np.linspace(0.1, 1.0, 10)              # clean rise
    flat_spike = np.concatenate([np.full(9, 0.1), [1.0]])  # no build, sudden spike
    s_up, _ = NE._arc_score(ramp_up, 1.0, 6.0, cfg)
    s_spike, _ = NE._arc_score(flat_spike, 1.0, 6.0, cfg)
    check("ramp scores higher than a bare spike", s_up > s_spike)
    check("scores are 0..100", 0 <= s_up <= 100 and 0 <= s_spike <= 100)


def test_buildup_gate_and_schema():
    print("\n[2] Buildup Sufficiency Gate + v2 schema (synthetic curve)")
    # synthetic: quiet, then a rising fight to a climax at ~30s
    n = 80  # 40s @ 0.5
    f = np.full(n, 0.1)
    f[40:61] = np.linspace(0.2, 1.0, 21)             # ramp 20s..30s into climax at idx 60 (=30s)
    # monkey-patch the signal stage to feed our synthetic curve
    import highlight_engine as HE
    orig_a, orig_m, orig_fuse, orig_dur = (HE.extract_audio_energy, HE.extract_motion_energy,
                                           HE.fuse, HE._ffprobe_duration)
    NE.extract_audio_energy = lambda p, c: (None, f)
    NE.extract_motion_energy = lambda p, c: (None, f)
    NE.fuse = lambda a, m, c: f
    NE._ffprobe_duration = lambda p: 40.0
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
            tf.write(b"x"); fake = tf.name
        eps = NE.detect_episodes(fake, NE.NarrativeConfig(min_buildup_s=4.0))
        check("at least one episode", len(eps) >= 1)
        e = eps[0]
        check("schema keys present",
              all(k in e for k in ("start", "end", "climax_t", "climax_offset",
                                   "hook_window", "arc_score", "buildup_start")))
        check("buildup precedes climax (gate honored)", e["climax_t"] - e["start"] >= 4.0)
        check("climax_offset = climax_t - start", abs(e["climax_offset"] - (e["climax_t"] - e["start"])) < 0.6)
        os.unlink(fake)
    finally:
        NE.extract_audio_energy, NE.extract_motion_energy = orig_a, orig_m
        NE.fuse, NE._ffprobe_duration = orig_fuse, orig_dur


def test_integration_real():
    print("\n[3] integration (optional) — real asset, episodes have buildup")
    raw = _HERE.parents[2] / "input" / "raw"
    vids = (list(raw.glob("*.mp4")) + list(raw.glob("*.MP4"))) if raw.exists() else []
    if not vids:
        print("        SKIP — no asset in input/raw/"); return
    eps = NE.detect_episodes(vids[0])
    check("episodes detected", len(eps) >= 1)
    check("every episode has buildup before its climax",
          all(e["climax_t"] - e["start"] >= 3.5 for e in eps))
    dk = min(eps, key=lambda e: abs(e["climax_t"] - 50.0))
    check("a Double-Kill-region climax (~50s) is selectable", abs(dk["climax_t"] - 50.0) <= 6.0)
    print(f"        (DK episode: {dk['start']}-{dk['end']}s climax@{dk['climax_t']})")


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" WF-1 v2 NARRATIVE ENGINE — TEST SUITE"); print("=" * 60)
    test_arc_score_rewards_ramp(); test_buildup_gate_and_schema(); test_integration_real()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
