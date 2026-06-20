"""short_generator.py — WF-2 Auto Short Generator (offline, single-pass ffmpeg).

highlight_candidates.json (+ source video) -> final_short.mp4, no human intervention.

Pipeline per clip (ONE ffmpeg encode — minimizes CPU, maximizes throughput):
  seek[start,end] -> 9:16 reframe -> loudnorm audio -> hook text overlay -> H.264 preset.

REFRAME MODES (challenged the spec's "face tracking" — wrong for gameplay):
  - fit       : scale-to-width + blurred-background pad. Preserves the FULL frame
                (best for gameplay where action spans the width). DEFAULT.
  - crop      : center crop to 9:16.
  - saliency  : crop biased toward the horizontal MOTION centroid (offline numpy,
                no ML) — the honest, buildable form of "action tracking" (static per clip;
                per-frame dynamic tracking is v2).

SCOPED TO v2 (with rationale, not faked): per-frame dynamic zoom (zoompan is slow);
ASR subtitle generation (N/A for speechless gameplay; whisper/Scribe path exists for
talking-head content).

ADDITIVE: new module + new output file. Touches no moat asset, no schema, no core.
ffmpeg + numpy only (declared deps).

CLI:
  python integrations/shortgen/short_generator.py \
      --video <src.mp4> --candidates highlight_candidates.json \
      --out final_short.mp4 [--peak-near 50] [--reframe fit|crop|saliency] \
      [--hook "WAIT FOR IT"] [--preset tiktok|reels|shorts]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Export presets — all vertical 9:16; differ only where platforms differ.
PRESETS = {
    "tiktok":  {"w": 1080, "h": 1920, "fps": 30, "vbr_crf": 20, "abr": "192k"},
    "reels":   {"w": 1080, "h": 1920, "fps": 30, "vbr_crf": 20, "abr": "192k"},
    "shorts":  {"w": 1080, "h": 1920, "fps": 30, "vbr_crf": 20, "abr": "192k"},
}

DEFAULT_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


@dataclass
class ShortOptions:
    reframe: str = "fit"            # fit | crop | saliency
    hook: str | None = None
    hook_seconds: float = 2.5
    preset: str = "tiktok"
    loudness_lufs: float = -14.0
    font: str | None = None
    x264_preset: str = "veryfast"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _probe(video: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_entries", "stream=codec_type,width,height", "-show_entries",
         "format=duration", str(video)], capture_output=True, text=True)
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {}
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in d.get("streams", []))
    return {"w": v.get("width"), "h": v.get("height"), "has_audio": has_audio,
            "duration": float(d.get("format", {}).get("duration", 0) or 0)}


def _find_font(opts: ShortOptions) -> str | None:
    for f in ([opts.font] if opts.font else []) + DEFAULT_FONTS:
        if f and Path(f).exists():
            return f
    return None


def _esc_path(p: str) -> str:
    """Escape a Windows path for use inside an ffmpeg filtergraph (drive colon)."""
    return p.replace("\\", "/").replace(":", "\\:")


def select_candidate(cands: list[dict], peak_near: float | None, rank: int) -> dict | None:
    if not cands:
        return None
    if peak_near is not None:
        return min(cands, key=lambda c: abs(c.get("peak", c["start"]) - peak_near))
    ordered = sorted(cands, key=lambda c: -c.get("score", 0))
    return ordered[rank] if 0 <= rank < len(ordered) else ordered[0]


def action_center_frac(video: Path, start: float, dur: float, size: int = 160) -> float:
    """Horizontal motion centroid (0..1) over the clip — the offline 'action track'.
    Returns 0.5 (centered) if motion is flat/unavailable. No ML, deterministic."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(start), "-i", str(video), "-t", str(dur),
         "-vf", f"scale={size}:{size},fps=6,format=gray", "-f", "rawvideo", "-"],
        capture_output=True)
    buf = p.stdout
    fr = size * size
    n = len(buf) // fr
    if n < 2:
        return 0.5
    arr = np.frombuffer(buf[:n * fr], np.uint8).reshape(n, size, size).astype(np.float32)
    motion = np.abs(np.diff(arr, axis=0)).sum(axis=0)          # size x size motion map
    col = motion.sum(axis=0)                                    # per-column motion
    if col.sum() < 1e-6:
        return 0.5
    centroid = float((np.arange(size) * col).sum() / col.sum())
    return min(1.0, max(0.0, centroid / (size - 1)))


# ---------------------------------------------------------------------------
# filtergraph
# ---------------------------------------------------------------------------
def build_video_chain(reframe: str, tw: int, th: int, frac: float) -> str:
    if reframe == "crop":
        return f"[0:v]crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={tw}:{th},setsar=1[vr]"
    if reframe == "saliency":
        return (f"[0:v]crop=ih*9/16:ih:(iw-ih*9/16)*{frac:.4f}:0,"
                f"scale={tw}:{th},setsar=1[vr]")
    # fit (blur-pad) — preserves full frame
    return (f"[0:v]split=2[bg][fg];"
            f"[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,"
            f"crop={tw}:{th},boxblur=20:1[bgb];"
            f"[fg]scale={tw}:-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[vr]")


def build_hook(label_in: str, label_out: str, hook: str, secs: float,
               font: str, txtfile: Path) -> str:
    txtfile.write_text(hook, encoding="utf-8")
    return (f"[{label_in}]drawtext=fontfile='{_esc_path(font)}':"
            f"textfile='{_esc_path(str(txtfile))}':fontcolor=white:fontsize=72:"
            f"borderw=6:bordercolor=black@0.9:x=(w-text_w)/2:y=h*0.10:"
            f"enable='between(t,0,{secs})'[{label_out}]")


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------
def render_story_short(video, episode: dict, out, opts: ShortOptions | None = None, *,
                       anticipation: str = "WAIT FOR IT", payoff: str = "DOUBLE KILL") -> dict:
    """WF-1 v2 path: render a NARRATIVE episode with an anticipation hook over the
    buildup and a payoff callout timed to the climax (climax_offset)."""
    opts = opts or ShortOptions()
    co = float(episode.get("climax_offset", max(0.0, episode["climax_t"] - episode["start"])))
    hook_events = [
        {"text": anticipation, "start": 0.0, "end": max(2.0, co - 0.4), "fontsize": 66},
        {"text": payoff, "start": max(0.0, co - 0.2), "end": co + 2.4, "fontsize": 88},
    ]
    cand = {"start": episode["start"], "end": episode["end"]}
    return render_short(video, cand, out, opts, hook_events=hook_events)


def render_short(video: str | Path, candidate: dict, out: str | Path,
                 opts: ShortOptions | None = None, *, hook_events: list[dict] | None = None) -> dict:
    """Render one candidate to a vertical short. Returns
    {ok, out, render_seconds, clip_seconds, reframe, hook_applied, info}.
    hook_events (optional): timed overlays [{text,start,end,fontsize?}] — used by the
    v2 story path; falls back to the single opts.hook when not provided."""
    opts = opts or ShortOptions()
    video, out = Path(video), Path(out)
    if not video.exists():
        return {"ok": False, "info": f"source not found: {video}"}
    pr = PRESETS.get(opts.preset)
    if not pr:
        return {"ok": False, "info": f"unknown preset {opts.preset}"}
    meta = _probe(video)
    start = float(candidate["start"])
    dur = max(0.1, float(candidate["end"]) - start)

    frac = (action_center_frac(video, start, dur)
            if opts.reframe == "saliency" else 0.5)
    chain = build_video_chain(opts.reframe, pr["w"], pr["h"], frac)

    font = _find_font(opts)
    hook_applied = False
    tmp_txts: list[Path] = []
    last = "vr"
    events = hook_events
    if events is None and opts.hook:
        events = [{"text": opts.hook, "start": 0.0, "end": opts.hook_seconds}]
    if events and font:
        for k, ev in enumerate(events):
            tf = Path(tempfile.gettempdir()) / f"_scos_hook_{os.getpid()}_{k}.txt"
            tf.write_text(str(ev["text"]), encoding="utf-8")
            tmp_txts.append(tf)
            out_lbl = "vout" if k == len(events) - 1 else f"vh{k}"
            chain += (f";[{last}]drawtext=fontfile='{_esc_path(font)}':"
                      f"textfile='{_esc_path(str(tf))}':fontcolor=white:fontsize={ev.get('fontsize', 72)}:"
                      f"borderw=6:bordercolor=black@0.9:x=(w-text_w)/2:y={ev.get('y', 'h*0.10')}:"
                      f"enable='between(t,{ev['start']},{ev['end']})'[{out_lbl}]")
            last = out_lbl
        hook_applied = True

    fc = chain
    amap = []
    if meta.get("has_audio"):
        fc += f";[0:a]loudnorm=I={opts.loudness_lufs}:TP=-1.5:LRA=11[aout]"
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", pr["abr"]]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", str(start), "-i", str(video), "-t", str(dur),
           "-filter_complex", fc, "-map", f"[{last}]", *amap,
           "-c:v", "libx264", "-crf", str(pr["vbr_crf"]), "-preset", opts.x264_preset,
           "-pix_fmt", "yuv420p", "-r", str(pr["fps"]), "-movflags", "+faststart",
           str(out)]

    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    for tf in tmp_txts:
        try: tf.unlink()
        except OSError: pass

    if p.returncode != 0:
        # graceful degradation: retry once without any hook overlay
        if hook_applied:
            opts2 = ShortOptions(**{**opts.__dict__, "hook": None})
            return render_short(video, candidate, out, opts2, hook_events=None)
        return {"ok": False, "info": f"ffmpeg failed: {p.stderr.strip()[-300:]}",
                "render_seconds": round(elapsed, 2)}

    return {"ok": True, "out": str(out), "render_seconds": round(elapsed, 2),
            "clip_seconds": round(dur, 2), "reframe": opts.reframe,
            "saliency_frac": round(frac, 3) if opts.reframe == "saliency" else None,
            "hook_applied": hook_applied, "preset": opts.preset,
            "info": f"rendered {dur:.1f}s clip in {elapsed:.2f}s"}


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-2 Auto Short Generator")
    ap.add_argument("--video", required=True)
    ap.add_argument("--candidates", required=True, help="highlight_candidates.json")
    ap.add_argument("--out", default="final_short.mp4")
    ap.add_argument("--peak-near", type=float, default=None,
                    help="select the candidate whose peak is nearest this time (s)")
    ap.add_argument("--rank", type=int, default=0, help="else: 0=highest score")
    ap.add_argument("--reframe", default="fit", choices=["fit", "crop", "saliency"])
    ap.add_argument("--hook", default=None)
    ap.add_argument("--preset", default="tiktok", choices=list(PRESETS))
    ap.add_argument("--font", default=None)
    a = ap.parse_args()

    cands = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
    cand = select_candidate(cands, a.peak_near, a.rank)
    if cand is None:
        print("no candidate to render"); return 1
    opts = ShortOptions(reframe=a.reframe, hook=a.hook, preset=a.preset, font=a.font)
    res = render_short(a.video, cand, a.out, opts)
    print(json.dumps({**res, "candidate": cand}, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
