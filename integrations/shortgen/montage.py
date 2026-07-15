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
from short_generator import (build_video_chain, _find_font, _esc_path, ShortOptions,  # noqa: E402
                             action_center_frac)
from narrative_engine import detect_episodes, NarrativeConfig  # noqa: E402
from highlight_engine import HighlightConfig, extract_audio_energy, onset, _ffprobe_duration  # noqa: E402

GRADE_PUNCH = "eq=contrast=1.12:saturation=1.28:brightness=0.01"

# --- Central media-binary resolver ------------------------------------------
# Keep montage.py runnable as a standalone script (``python montage.py``)
# while routing ffmpeg through the shared, hermetic resolver. Repo root
# is added to sys.path so the in-package resolver is importable without a
# hardcoded path or a changed CLI. Resolution is lazy (module import time)
# and fails closed with an actionable error if ffmpeg is unavailable.
_REPO_ROOT = _HERE.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from scos.media_binaries import resolve_ffmpeg  # noqa: E402

FFMPEG = resolve_ffmpeg()


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
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
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
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
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
    c1 = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                         "-f", "concat", "-safe", "0", "-i", str(listf),
                         "-c", "copy", str(base)], capture_output=True, text=True)
    if c1.returncode != 0:                                 # fallback: re-encode concat
        inputs = []
        for p in shot_files:
            inputs += ["-i", str(p)]
        n = len(shot_files)
        fc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *inputs,
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
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
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


# ===========================================================================
# DIRECTOR MODE — 60s hype highlight (cold-open peak + effects + bass-drop finale)
# ===========================================================================
def _music_drop(music: Path) -> float:
    """Time of the biggest energy jump in the track (the drop) — for the finale sync."""
    hc = HighlightConfig(window_s=0.25)
    times, energy = extract_audio_energy(music, hc)
    if len(energy) < 4:
        return 0.0
    rise = onset(energy)
    # smooth-ish: pick the strongest sustained rise in the back 2/3 (drops rarely at the very start)
    lo = len(rise) // 5
    idx = lo + int(np.argmax(rise[lo:]))
    return float(times[idx])


def select_highlight_shots(source: Path, target_s: float, coldopen_s: float,
                           window_s: float) -> tuple[dict | None, list[dict]]:
    """finale = best-arc COMBAT moment (teased at open, shown last). mids = other top
    combat moments whose climaxes are >= window_s apart (zoomed windows don't repeat)."""
    eps = detect_episodes(source, NarrativeConfig())
    if not eps:
        return None, []
    finale = max(eps, key=lambda e: (e["arc_score"], e["climax_t"]))
    n_needed = max(2, int((target_s - coldopen_s) / window_s))
    chosen = [finale]
    for e in sorted(eps, key=lambda x: -x["arc_score"]):
        if e is finale:
            continue
        if all(abs(e["climax_t"] - c["climax_t"]) >= window_s for c in chosen):
            chosen.append(e)
        if len(chosen) >= n_needed:
            break
    mids = sorted([c for c in chosen if c is not finale], key=lambda x: x["climax_t"])
    return finale, mids


def _zoom_chain(frac: float, tw: int, th: int, bottom_cut: float = 0.11) -> str:
    """ZOOM into the action: crop a 9:16 strip from the source (excluding the bottom
    replay-scrubber strip), centered on the motion `frac`, then upscale + light sharpen.
    Makes the combat BIG and removes the replay UI."""
    keep = 1.0 - bottom_cut
    return (f"[0:v]crop=w='ih*{keep:.3f}*9/16':h='ih*{keep:.3f}':"
            f"x='(iw-ih*{keep:.3f}*9/16)*{frac:.4f}':y=0,"
            f"scale={tw}:{th},unsharp=5:5:0.7,setsar=1[vr]")


def _fx_chain(in_lbl: str, out_lbl: str, cfg: MontageConfig, climax_rel: float,
              text: str | None, font: str | None) -> str:
    """grade -> shake(around kill) -> white flash(at kill) -> timed text. (No zoompan:
    keeps the time base intact so flash/text land exactly on the kill.)"""
    c0, c1 = max(0.0, climax_rel - 0.15), climax_rel + 0.20
    parts = [f"[{in_lbl}]{GRADE_PUNCH}[g0]"]
    # subtle shake via crop oscillation, active only around the kill
    parts.append(
        f"[g0]crop=w=iw-6:h=ih-6:"
        f"x='3+3*sin(2*PI*18*t)*between(t,{c0:.2f},{c1:.2f})':"
        f"y='3+3*sin(2*PI*15*t)*between(t,{c0:.2f},{c1:.2f})',scale={cfg.tw}:{cfg.th}[g1]")
    # quick white flash at the kill
    parts.append(f"[g1]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.6:t=fill:"
                 f"enable='between(t,{climax_rel:.2f},{climax_rel + 0.05:.2f})'[g2]")
    if text and font:
        parts.append(f"[g2]drawtext=fontfile='{_esc_path(font)}':text='{text}':"
                     f"fontcolor=white:fontsize=86:borderw=7:bordercolor=black@0.9:"
                     f"x=(w-text_w)/2:y=h*0.10:enable='between(t,{climax_rel - 0.05:.2f},{climax_rel + 1.5:.2f})'[{out_lbl}]")
    else:
        parts.append(f"[g2]null[{out_lbl}]")
    return ";".join(parts)


def _render_fight(source: Path, ep: dict, cfg: MontageConfig, out: Path,
                  is_finale: bool, text: str | None, pre: float = 4.5, post: float = 1.5) -> bool:
    """One COMBAT shot: the action window around the kill, ZOOMED into the fight (replay
    bar cropped out). Finale gets slow-mo into the kill."""
    font = _thai_font()
    total = _ffprobe_duration(source)
    climax = ep["climax_t"]
    start = max(0.0, climax - pre); end = min(total, climax + post)
    frac = action_center_frac(source, start, end - start)
    zc = _zoom_chain(frac, cfg.tw, cfg.th)

    if not is_finale:
        climax_rel = climax - start
        fc = (f"{zc};{_fx_chain('vr', 'vout', cfg, climax_rel, text, font)};"
              f"[0:a]afade=t=in:st=0:d=0.02[aout]")
        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
               "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(source),
               "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(out)]
        return subprocess.run(cmd, capture_output=True, text=True).returncode == 0

    # FINALE: slow-mo into the kill, then zoom+fx on the assembled clip
    sm = max(start, climax - 0.5); slow = 0.6
    raw = out.parent / (out.stem + "_raw.mp4")
    fcr = (f"[0:v]trim={start:.3f}:{sm:.3f},setpts=PTS-STARTPTS[v0];"
           f"[0:v]trim={sm:.3f}:{end:.3f},setpts=(PTS-STARTPTS)/{slow}[v1];"
           f"[0:a]atrim={start:.3f}:{sm:.3f},asetpts=PTS-STARTPTS[a0];"
           f"[0:a]atrim={sm:.3f}:{end:.3f},asetpts=PTS-STARTPTS,atempo={slow}[a1];"
           f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[vc][ac]")
    if subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                       "-filter_complex", fcr, "-map", "[vc]", "-map", "[ac]",
                       "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                       "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(raw)],
                      capture_output=True, text=True).returncode != 0:
        return False
    climax_rel = (sm - start) + 0.5 / slow
    fc2 = f"{zc};{_fx_chain('vr', 'vout', cfg, climax_rel, text, font)}"
    return subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                           "-filter_complex", fc2, "-map", "[vout]", "-map", "0:a",
                           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                           "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(out)],
                          capture_output=True, text=True).returncode == 0


def _render_coldopen(source: Path, ep: dict, cfg: MontageConfig, out: Path, text: str) -> bool:
    """Cold-open: ZOOM into the finale kill, play it, then FREEZE on the win frame and
    pop a cheeky caption ('ฟอนต์ข้อความกวนๆ')."""
    font = _thai_font()
    total = _ffprobe_duration(source)
    climax = ep["climax_t"]
    start = max(0.0, climax - 1.7); end = min(total, climax + 0.4)
    dur = end - start
    frac = action_center_frac(source, start, dur)
    zc = _zoom_chain(frac, cfg.tw, cfg.th)
    kill_rel = climax - start
    freeze = 1.4
    tx = (f",drawtext=fontfile='{_esc_path(font)}':text='{text}':fontcolor=white:fontsize=98:"
          f"borderw=10:bordercolor=black:x=(w-text_w)/2:y=h*0.13:"
          f"enable='gte(t,{dur + 0.05:.2f})'") if font else ""
    fc = (f"{zc};[vr]{GRADE_PUNCH},"
          f"drawbox=w=iw:h=ih:color=white@0.6:t=fill:enable='between(t,{kill_rel:.2f},{kill_rel + 0.05:.2f})',"
          f"tpad=stop_mode=clone:stop_duration={freeze}{tx}[vout];"
          f"[0:a]afade=t=out:st={max(0.0, dur - 0.1):.2f}:d=0.1,apad=pad_dur={freeze}[aout]")
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(source),
           "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-r", str(cfg.fps), "-c:a", "aac", "-ar", "48000", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def cfg_opts() -> ShortOptions:
    return ShortOptions()


# Thai-capable fonts (Arial has no Thai glyphs -> tofu boxes). Tahoma ships with Windows.
THAI_FONTS = ["C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/tahoma.ttf",
              "C:/Windows/Fonts/leelawadeebold.ttf", "C:/Windows/Fonts/LeelaUIb.ttf",
              "C:/Windows/Fonts/Leelawadee.ttf", "C:/Windows/Fonts/angsab.ttf"]


def _thai_font() -> str | None:
    for f in THAI_FONTS:
        if Path(f).exists():
            return f
    return _find_font(cfg_opts())


def render_highlight_60s(source: str | Path, music: str | Path, out: str | Path,
                         target_s: float = 56.0, cfg: MontageConfig | None = None,
                         kill_text: str = "เอาอยู่!", finale_text: str = "จบเกม",
                         coldopen_text: str = "ง่ายไป๊", window_s: float = 6.0) -> dict:
    cfg = cfg or MontageConfig(speed=1.0)
    source, music, out = Path(source), Path(music), Path(out)
    if not source.exists() or not music.exists():
        return {"ok": False, "info": "source or music not found"}
    coldopen_s = 3.5
    finale, mids = select_highlight_shots(source, target_s, coldopen_s, window_s)
    if finale is None:
        return {"ok": False, "info": "no fights detected"}

    tmp = Path(tempfile.mkdtemp(prefix="scos_hl60_"))
    parts: list[Path] = []
    # 1) cold-open teaser of the finale kill
    co = tmp / "coldopen.mp4"
    if not _render_coldopen(source, finale, cfg, co, coldopen_text):
        return {"ok": False, "info": "cold-open failed", "tmp": str(tmp)}
    parts.append(co)
    # 2) mid fights (chronological)
    for i, ep in enumerate(mids):
        f = tmp / f"fight_{i}.mp4"
        if not _render_fight(source, ep, cfg, f, is_finale=False, text=kill_text):
            return {"ok": False, "info": f"fight {i} failed", "tmp": str(tmp)}
        parts.append(f)
    # 3) finale (full, slow-mo into kill)
    fin = tmp / "finale.mp4"
    if not _render_fight(source, finale, cfg, fin, is_finale=True, text=finale_text):
        return {"ok": False, "info": "finale failed", "tmp": str(tmp)}
    parts.append(fin)

    # concat all
    listf = tmp / "list.txt"
    listf.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    base = tmp / "base.mp4"
    if subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat",
                       "-safe", "0", "-i", str(listf), "-c", "copy", str(base)],
                      capture_output=True, text=True).returncode != 0:
        inp = []
        for p in parts:
            inp += ["-i", str(p)]
        n = len(parts)
        fc = "".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *inp,
                        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", str(base)], capture_output=True, text=True)

    total = _ffprobe_duration(base)
    # music: align so the DROP lands on the finale kill; game 0.5 under music
    drop = _music_drop(music)
    fin_kill_in_montage = max(0.0, total - 2.0)               # finale kill ~2s before the end
    m_start = max(0.0, drop - fin_kill_in_montage)
    fade_out = max(0.0, total - 0.5)
    amix = (f"[0:a]volume={cfg.game_volume}[g];"
            f"[1:a]volume={cfg.music_volume},afade=t=out:st={fade_out:.3f}:d=0.5[m];"
            f"[g][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(base), "-ss", f"{m_start:.3f}", "-t", f"{total:.3f}", "-i", str(music),
                        "-filter_complex", amix, "-map", "0:v", "-map", "[aout]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"ok": False, "info": f"final mix failed: {r.stderr.strip()[-300:]}", "tmp": str(tmp)}
    return {"ok": True, "out": str(out), "total_s": round(total, 2), "mid_fights": len(mids),
            "finale_climax": finale["climax_t"], "music_drop_s": round(drop, 2),
            "music_start_s": round(m_start, 2), "tmp": str(tmp)}


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-2 Music Montage / Highlight Director")
    ap.add_argument("--video", required=True)
    ap.add_argument("--music", required=True)
    ap.add_argument("--out", default="work/video/montage_hgb_v1.mp4")
    ap.add_argument("--mode", choices=["montage", "director"], default="montage")
    ap.add_argument("--target", type=float, default=60.0)
    ap.add_argument("--shots", type=int, default=4)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--game-volume", type=float, default=0.5)
    a = ap.parse_args()
    cfg = MontageConfig(n_shots=a.shots, speed=a.speed, game_volume=a.game_volume)
    if a.mode == "director":
        res = render_highlight_60s(a.video, a.music, a.out, a.target, cfg)
    else:
        res = render_montage(a.video, a.music, a.out, cfg)
    print(json.dumps({k: v for k, v in res.items() if k != "tmp"}, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
