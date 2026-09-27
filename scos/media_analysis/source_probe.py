from __future__ import annotations
import json, subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any
from scos.media_binaries import resolve_ffprobe
from .contracts import MediaSourceProbe

def _run_probe(path: Path) -> dict[str, Any]:
    ffprobe=resolve_ffprobe()
    cmd=[ffprobe,"-v","error","-show_streams","-show_format","-of","json",str(path)]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,check=False)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {(p.stderr or '').strip()[-500:]}")
    try: return json.loads(p.stdout or "{}")
    except json.JSONDecodeError as exc: raise RuntimeError("ffprobe returned malformed JSON") from exc

def _fps(value: str | None) -> float:
    if not value or value in {"0/0","N/A"}: return 0.0
    try: return float(Fraction(value))
    except (ValueError, ZeroDivisionError): return 0.0

def probe_source(path: str | Path) -> MediaSourceProbe:
    p=Path(path).resolve()
    if not p.is_file() or p.stat().st_size <= 0: raise FileNotFoundError(p)
    data=_run_probe(p); streams=data.get("streams",[])
    video=next((s for s in streams if s.get("codec_type")=="video"),None)
    if not video: raise RuntimeError(f"no video stream: {p}")
    audio=next((s for s in streams if s.get("codec_type")=="audio"),None)
    duration=float(data.get("format",{}).get("duration") or video.get("duration") or 0.0)
    fps=_fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    r_fps=_fps(video.get("r_frame_rate")); avg_fps=_fps(video.get("avg_frame_rate"))
    frames=int(video.get("nb_frames") or 0)
    if frames<=0 and duration>0 and fps>0: frames=round(duration*fps)
    count_duration_ok=frames<=0 or fps<=0 or abs(frames/max(fps,0.001)-duration)<=max(0.050,1.5/max(fps,0.001))
    rate_ok=r_fps<=0 or avg_fps<=0 or abs(r_fps-avg_fps)<=0.001
    cfr=bool(fps>0 and rate_ok and count_duration_ok)
    return MediaSourceProbe(
        path=str(p),duration_s=duration,width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),fps=fps,frames=frames,
        video_codec=str(video.get("codec_name") or ""),pixel_format=str(video.get("pix_fmt") or ""),
        color_transfer=str(video.get("color_transfer") or ""),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        audio_sample_rate=int(audio.get("sample_rate")) if audio and str(audio.get("sample_rate","")).isdigit() else None,
        audio_channels=int(audio.get("channels")) if audio and str(audio.get("channels","")).isdigit() else None,
        has_audio=audio is not None,
        cfr=cfr,
    )
