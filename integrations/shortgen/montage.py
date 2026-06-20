"""montage.py — WF-2 Music Montage assembler (offline).

raw video + music -> a beat-synced, multi-shot vertical montage with the game audio
ducked under the music. Additive: reuses WF-1 v2 (narrative_engine.detect_episodes),
WF-2 (short_generator.build_video_chain), and the v1 signal engine
(highlight_engine.extract_audio_energy) — modifies none of them.

Pipeline:
  1. select N non-overlapping story episodes (ending on the strongest late climax)
  2. analyze the music: pick the hype section (max-energy window) + tempo (beat period)
  3. render each shot: fit 9:16 reframe + speed-up (video only) + punch grade + white
     flash-in; finale gets a slow punch-in zoom. Game audio kept (sped to match).
  4. concat shots (beat-synced durations)
  5. mix game audio (reduced) + music (NOT sped) -> loudnorm -> final mp4

ffmpeg + numpy only. Music is never time-stretched (tempo preserved).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "highlight"))
from short_generator import build_video_chain, _find_font, _esc_path, ShortOptions  # noqa: E402
from narrative_engine import detect_episodes, NarrativeConfig  # noqa: E402
from highlight_engine import HighlightConfig, extract_audio_energy, onset, _ffprobe_duration  # noqa: E402

GRADE_PUNCH = "eq=contrast=1.12:saturation=1.28:brightness=0.01"


@dataclass
class MontageConfig:
    n_shots: int = 4
    speed: float = 1.0              # 1.0 = full detail, no skipping; music untouched
    target_shot_s: float = 3.3      # snapped to a beat multiple
    game_volume: float = 0.5        # "เบาเสียงเกมลง 50%"
    music_volume: float = 1.0
    reframe: str = "fit"
    flash_s: float = 0.08           # white flash-in at each cut
    tw: int = 1080
    th: int = 1920
    fps: int = 30


# ---------------------------------------------------------------------------
# 1. shot selection (WF-1 v2)
# ---------------------------------------------------------------------------
def select_shots(source: Path, n: int) -> list[dict]:
    """N non-overlapping episodes, chronological, guaranteed to include the latest
    strong climax (the finale)."""
    eps = detect_episodes(source, NarrativeConfig())
    if not eps:
        return []
    finale = max(eps, key=lambda e: e["climax_t"])          # latest climax = payoff
    chosen = [finale]
    for e in sorted(eps, key=lambda e: -e["arc_score"]):
        if len(chosen) >= n:
            break
        if all(e["end"] <= c["start"] or e["start"] >= c["end"] for c in chosen):
            chosen.append(e)
    return sorted(chosen, key=lambda e: e["climax_t"])      # chronological


# ---------------------------------------------------------------------------
# 2. music analysis — hype section + beat period
# ---------------------------------------------------------------------------
def analyze_music(music: Path, want_s: float) -> tuple[float, float]:
    """Return (hype_start_s aligned to a beat, beat_period_s). Tempo-only analysis,
    onset-based (no librosa)."""
    hc = HighlightConfig(window_s=0.1)                      # fine resolution for beats
    times, energy = extract_audio_energy(music, hc)
    if len(energy) == 0:
        return 0.0, 0.5
    # hype window = contiguous want_s with max mean energy
    w = max(1, int(round(want_s / hc.window_s)))
    if len(energy) > w:
        csum = np.cumsum(np.insert(energy, 0, 0))
        means = (csum[w:] - csum[:-w]) / w
        hype_i = int(np.argmax(means))
    else:
        hype_i = 0
    # beats = onset peaks across the track; period = median spacing in 0.3..0.9s
    on = onset(energy)
    thr = on.mean() + 0.8 * on.std()
    beat_idx = [i for i in range(1, len(on) - 1)
                if on[i] >= thr and on[i] >= on[i - 1] and on[i] >= on[i + 1]]
    beat_times = [float(times[i]) for i in beat_idx]
    if len(beat_times) >= 3:
        diffs = np.diff(beat_times)
        diffs = diffs[(diffs >= 0.3) & (diffs <= 0.9)]
        period = float(np.median(diffs)) if len(diffs) else 0.5
    else:
        period = 0.5
    # snap hype start to the nearest beat onset (downbeat)
    hype_t = float(times[hype_i])
    if beat_times:
        hype_t = min(beat_times, key=lambda b: abs(b - hype_t))
    return hype_t, period


# ---------------------------------------------------------------------------
# 3. per-shot render
# ---------------------------------------------------------------------------
def _render_shot(source: Path, src_start: float, src_end: float, cfg: MontageConfig,
                 out: Path, is_finale: bool) -> bool:
    """Render ONE full-fight shot: the whole episode span (engagement -> kill ->
    brief resolution), sped up. Showing the full fight is what builds the
    win-or-lose suspense the viewer wants."""
    total = _ffprobe_duration(source)
    start = max(0.0, src_start)
    src_dur = max(0.5, min(src_end, total) - start)
    out_dur = src_dur / cfg.speed
    vchain = build_video_chain(cfg.reframe, cfg.tw, cfg.th, 0.5)   # ...[vr]
    post = f"setpts=PTS/{cfg.speed},{GRADE_PUNCH}"
    if is_finale:
        zinc = max(0.0003, 0.12 / max(1.0, out_dur * cfg.fps))    # push-in peaks at the kill
        post += (f",zoompan=z='min(pzoom+{zinc:.5f},1.12)':d=1:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={cfg.tw}x{cfg.th}:fps={cfg.fps}")
    post += f",fade=t=in:st=0:d={cfg.flash_s}:color=white"
    fc = f"{vchain};[vr]{post}[vout];[0:a]atempo={cfg.speed},afade=t=in:st=0:d=0.02,afade=t=out:st={max(0,out_dur-0.03):.3f}:d=0.03[aout]"
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{src_dur:.3f}", "-i", str(source),
           "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 and is_finale:                    # zoom can be finicky -> retry w/o it
        return _render_shot_noznoom(source, start, src_dur, out_dur, cfg, out)
    return p.returncode == 0


def _render_shot_noznoom(source, start, src_dur, out_dur, cfg, out) -> bool:
    vchain = build_video_chain(cfg.reframe, cfg.tw, cfg.th, 0.5)
    fc = (f"{vchain};[vr]setpts=PTS/{cfg.speed},{GRADE_PUNCH},"
          f"fade=t=in:st=0:d={cfg.flash_s}:color=white[vout];"
          f"[0:a]atempo={cfg.speed},afade=t=in:st=0:d=0.02,afade=t=out:st={max(0,out_dur-0.03):.3f}:d=0.03[aout]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{src_dur:.3f}", "-i", str(source),
           "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


# ---------------------------------------------------------------------------
# 4-5. assemble: concat + mix(game+music) + loudnorm
# ---------------------------------------------------------------------------
def render_montage(source: str | Path, music: str | Path, out: str | Path,
                   cfg: MontageConfig | None = None) -> dict:
    cfg = cfg or MontageConfig()
    source, music, out = Path(source), Path(music), Path(out)
    if not source.exists() or not music.exists():
        return {"ok": False, "info": "source or music not found"}
    shots = select_shots(source, cfg.n_shots)
    if not shots:
        return {"ok": False, "info": "no episodes detected"}

    src_total = _ffprobe_duration(source)
    out_durs = [round((min(e["end"], src_total) - max(0.0, e["start"])) / cfg.speed, 3) for e in shots]
    total = round(sum(out_durs), 3)
    hype_t, beat = analyze_music(music, total)             # music section to cover the montage

    tmp = Path(tempfile.mkdtemp(prefix="scos_montage_"))
    shot_files: list[Path] = []
    for i, ep in enumerate(shots):
        sf = tmp / f"shot_{i}.mp4"
        ok = _render_shot(source, ep["start"], ep["end"], cfg, sf, is_finale=(i == len(shots) - 1))
        if not ok:
            return {"ok": False, "info": f"shot {i} render failed", "tmp": str(tmp)}
        shot_files.append(sf)

    # concat shots (re-encode-safe via concat demuxer; uniform params so copy works)
    listf = tmp / "list.txt"
    listf.write_text("".join(f"file '{p.as_posix()}'\n" for p in shot_files), encoding="utf-8")
    base = tmp / "base.mp4"
    c1 = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                         "-f", "concat", "-safe", "0", "-i", str(listf),
                         "-c", "copy", str(base)], capture_output=True, text=True)
    if c1.returncode != 0:                                 # fallback: re-encode concat
        inputs = []
        for p in shot_files:
            inputs += ["-i", str(p)]
        n = len(shot_files)
        fc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
                        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(base)],
                       capture_output=True, text=True)

    # final: mix game(0.5) + music(from hype_t, NOT sped) -> loudnorm
    fade_out = max(0.0, total - 0.4)
    amix = (f"[0:a]volume={cfg.game_volume}[g];"
            f"[1:a]volume={cfg.music_volume},afade=t=out:st={fade_out:.3f}:d=0.4[m];"
            f"[g][m]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(base), "-ss", f"{hype_t:.3f}", "-t", f"{total:.3f}", "-i", str(music),
           "-filter_complex", amix, "-map", "0:v", "-map", "[aout]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return {"ok": False, "info": f"final mix failed: {p.stderr.strip()[-300:]}", "tmp": str(tmp)}

    return {"ok": True, "out": str(out), "shots": len(shots), "shot_durs_s": out_durs,
            "shot_spans": [[s["start"], s["end"]] for s in shots],
            "total_s": total, "music_hype_start_s": round(hype_t, 2), "speed": cfg.speed,
            "shot_climaxes": [s["climax_t"] for s in shots], "tmp": str(tmp)}


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-2 Music Montage")
    ap.add_argument("--video", required=True)
    ap.add_argument("--music", required=True)
    ap.add_argument("--out", default="work/video/montage_hgb_v1.mp4")
    ap.add_argument("--shots", type=int, default=4)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--game-volume", type=float, default=0.5)
    a = ap.parse_args()
    cfg = MontageConfig(n_shots=a.shots, speed=a.speed, game_volume=a.game_volume)
    res = render_montage(a.video, a.music, a.out, cfg)
    print(json.dumps({k: v for k, v in res.items() if k != "tmp"}, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
