"""scos_video_mcp.py — Super Creator OS local MCP server (offline, ffmpeg-backed).

ADDITIVE: a self-contained stdio MCP server that exposes the video-analysis +
light-editing helpers this project already uses (ffprobe / ffmpeg) as MCP tools, so
any MCP client (Claude Code, Claude Desktop) can call them directly. Touches nothing
in the existing pipeline — pure new module.

Run standalone:  python integrations/mcp/scos_video_mcp.py
Registered for Claude Code via the project .mcp.json.
"""
from __future__ import annotations
import json, subprocess, shlex
from pathlib import Path
import numpy as np
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("scos-video")

def _run(cmd: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

@mcp.tool()
def probe(path: str) -> str:
    """Return video metadata as JSON: width, height, fps, duration, codecs, audio info."""
    rc, out, err = _run(["ffprobe","-v","error","-print_format","json",
        "-show_entries","stream=codec_type,codec_name,width,height,r_frame_rate,channels,sample_rate",
        "-show_entries","format=duration,size,bit_rate", path])
    if rc: return f"ERROR: {err.strip()}"
    data = json.loads(out)
    v = next((s for s in data.get("streams",[]) if s.get("codec_type")=="video"), {})
    a = next((s for s in data.get("streams",[]) if s.get("codec_type")=="audio"), {})
    fr = v.get("r_frame_rate","0/1")
    try:
        num, den = (fr.split("/") + ["1"])[:2]
        fps = round(float(num) / float(den)) if float(den) else None
    except Exception: fps = fr
    return json.dumps({
        "width": v.get("width"), "height": v.get("height"), "fps": fps,
        "video_codec": v.get("codec_name"),
        "duration_s": float(data.get("format",{}).get("duration",0) or 0),
        "size_bytes": int(data.get("format",{}).get("size",0) or 0),
        "has_audio": bool(a), "audio_codec": a.get("codec_name"),
        "audio_channels": a.get("channels"), "audio_sr": a.get("sample_rate"),
    }, ensure_ascii=False)

@mcp.tool()
def volume_stats(path: str) -> str:
    """Return mean/max loudness (dB) of the audio track via ffmpeg volumedetect."""
    rc, out, err = _run(["ffmpeg","-hide_banner","-nostats","-i",path,"-af","volumedetect","-f","null","-"])
    mean = next((l.split("mean_volume:")[1].strip() for l in err.splitlines() if "mean_volume:" in l), "n/a")
    mx   = next((l.split("max_volume:")[1].strip() for l in err.splitlines() if "max_volume:" in l), "n/a")
    return json.dumps({"mean_volume": mean, "max_volume": mx}, ensure_ascii=False)

@mcp.tool()
def scene_cuts(path: str, threshold: float = 0.4) -> str:
    """List scene-change timestamps (seconds) above `threshold` (0-1). Lower = more sensitive."""
    rc, out, err = _run(["ffmpeg","-hide_banner","-nostats","-i",path,
        "-vf",f"select='gt(scene,{threshold})',metadata=print","-an","-f","null","-"])
    ts = [l.split("pts_time:")[1].split()[0] for l in err.splitlines() if "pts_time:" in l]
    return json.dumps({"count": len(ts), "timestamps": [round(float(t),2) for t in ts]}, ensure_ascii=False)

@mcp.tool()
def extract_frames(path: str, times: str, out_dir: str, height: int = 760) -> str:
    """Extract still frames at comma-separated `times` (sec) to out_dir as JPGs. Returns written paths."""
    od = Path(out_dir); od.mkdir(parents=True, exist_ok=True); written=[]
    for t in [x.strip() for x in times.split(",") if x.strip()]:
        dest = od / f"frame_{t.replace('.','_')}.jpg"
        rc,_,err = _run(["ffmpeg","-hide_banner","-nostats","-ss",t,"-i",path,"-frames:v","1",
            "-q:v","4","-vf",f"scale=-1:{height}",str(dest),"-y"])
        if rc==0: written.append(str(dest))
    return json.dumps({"written": written}, ensure_ascii=False)

@mcp.tool()
def extract_audio(path: str, out_path: str, start: float = 0.0, duration: float | None = None) -> str:
    """Extract an audio segment to WAV (44.1k stereo). duration=None -> to end."""
    cmd = ["ffmpeg","-hide_banner","-nostats","-y","-ss",str(start),"-i",path]
    if duration is not None: cmd += ["-t",str(duration)]
    cmd += ["-ar","44100","-ac","2",out_path]
    rc,_,err = _run(cmd)
    return "OK -> "+out_path if rc==0 else f"ERROR: {err.strip()[-300:]}"

@mcp.tool()
def trim(path: str, out_path: str, start: float, duration: float) -> str:
    """Trim a clip [start, start+duration] (re-encoded h264/aac) to out_path."""
    rc,_,err = _run(["ffmpeg","-hide_banner","-nostats","-y","-ss",str(start),"-i",path,
        "-t",str(duration),"-c:v","libx264","-crf","19","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",out_path])
    return "OK -> "+out_path if rc==0 else f"ERROR: {err.strip()[-300:]}"

@mcp.tool()
def mux_audio(video_path: str, audio_path: str, out_path: str) -> str:
    """Replace/attach an audio track onto a video (copies video, encodes aac, -shortest)."""
    rc,_,err = _run(["ffmpeg","-hide_banner","-nostats","-y","-i",video_path,"-i",audio_path,
        "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k","-shortest",out_path])
    return "OK -> "+out_path if rc==0 else f"ERROR: {err.strip()[-300:]}"

_GRADES = {
    "punch":   "eq=contrast=1.12:saturation=1.28:brightness=0.01",
    "vibrant": "eq=saturation=1.45:contrast=1.05",
    "warm":    "eq=saturation=1.1,colorbalance=rs=0.10:gs=0.02:bs=-0.10",
    "cold":    "eq=saturation=1.05,colorbalance=rs=-0.08:bs=0.12",
    "cine":    "eq=contrast=1.1:saturation=1.05,colorbalance=rs=-0.05:bs=0.06:rh=0.08:bh=-0.06",
    "bw":      "hue=s=0,eq=contrast=1.1",
}

@mcp.tool()
def grade(path: str, out_path: str, preset: str = "punch") -> str:
    """Apply a color-grade preset to a video. presets: punch, vibrant, warm, cold, cine, bw."""
    vf = _GRADES.get(preset)
    if not vf:
        return f"ERROR: unknown preset '{preset}'. Choose from {list(_GRADES)}"
    rc,_,err = _run(["ffmpeg","-hide_banner","-nostats","-y","-i",path,"-vf",vf,
        "-c:v","libx264","-crf","19","-pix_fmt","yuv420p","-c:a","copy",out_path])
    return f"OK ({preset}) -> {out_path}" if rc==0 else f"ERROR: {err.strip()[-300:]}"

@mcp.tool()
def burn_subtitles(path: str, srt_path: str, out_path: str, font_size: int = 18, margin_v: int = 60) -> str:
    """Burn an .srt onto the video (centered, outlined, semi-transparent box). Hard-coded captions."""
    esc = srt_path.replace("\\", "/").replace(":", "\\:")
    style = (f"Fontname=Arial,FontSize={font_size},PrimaryColour=&H00FFFFFF,"
             f"BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV={margin_v}")
    rc,_,err = _run(["ffmpeg","-hide_banner","-nostats","-y","-i",path,
        "-vf",f"subtitles='{esc}':force_style='{style}'",
        "-c:v","libx264","-crf","19","-pix_fmt","yuv420p","-c:a","copy",out_path])
    return "OK -> "+out_path if rc==0 else f"ERROR: {err.strip()[-300:]}"

@mcp.tool()
def concat_list(paths: str, out_path: str, width: int = 1080, height: int = 1920) -> str:
    """Concatenate comma-separated video paths (re-encoded, scaled to width x height, video-only)."""
    items = [p.strip() for p in paths.split(",") if p.strip()]
    if len(items) < 2:
        return "ERROR: provide at least 2 comma-separated paths"
    cmd = ["ffmpeg","-hide_banner","-nostats","-y"]
    for p in items: cmd += ["-i", p]
    chains = "".join(f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                     f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];" for i in range(len(items)))
    concat = "".join(f"[v{i}]" for i in range(len(items))) + f"concat=n={len(items)}:v=1:a=0[outv]"
    cmd += ["-filter_complex", chains+concat, "-map","[outv]",
            "-c:v","libx264","-crf","19","-pix_fmt","yuv420p", out_path]
    rc,_,err = _run(cmd)
    return f"OK ({len(items)} clips) -> {out_path}" if rc==0 else f"ERROR: {err.strip()[-400:]}"

def _motion_profile(path: str, fps: int = 8, size: int = 128):
    """Per-frame visual motion energy (mean abs frame-diff, 0..1) at low res.
    Works for BOTH hard-cut edits and smooth-animation edits (no scene-cut needed)."""
    p = subprocess.run(["ffmpeg","-v","error","-i",path,
        "-vf",f"scale={size}:{size},fps={fps},format=gray","-f","rawvideo","-"],
        capture_output=True)
    buf = p.stdout; fr = size*size; n = len(buf)//fr
    if n < 2: return np.array([]), fps
    arr = np.frombuffer(buf[:n*fr], np.uint8).reshape(n, fr).astype(np.float32)
    diff = np.abs(np.diff(arr, axis=0)).mean(axis=1) / 255.0
    return diff, fps

@mcp.tool()
def analyze_virality(path: str) -> str:
    """Local, offline virality/retention heuristic (replaces paid predictors).
    Scores hook, pacing, energy, format & length. Pacing/hook use real MOTION ENERGY
    (frame-diff), so smooth-animation edits are scored fairly (not just hard cuts).
    Returns JSON with a 0-100 score, letter grade, breakdown, metrics, and tips."""
    meta = json.loads(probe(path))
    vol = json.loads(volume_stats(path))
    dur = meta.get("duration_s",0) or 0.001
    w,h = meta.get("width",0) or 1, meta.get("height",0) or 1
    def db(s):
        try: return float(str(s).split("dB")[0].strip())
        except Exception: return -99.0
    mean_db = db(vol.get("mean_volume","-99"))
    mp, fps_m = _motion_profile(path)
    avg_motion  = float(np.mean(mp)) if len(mp) else 0.0
    early_motion= float(np.mean(mp[:int(3*fps_m)])) if len(mp) else 0.0
    cuts = json.loads(scene_cuts(path, 0.2))            # reported only, not scored
    # --- factor scores (0-20 each) ---
    fmt = 20 if h > w*1.2 else (10 if abs(h-w) < w*0.2 else 4)
    if 7 <= dur <= 60: length = 20
    elif dur < 7: length = max(4, int(dur/7*20))
    else: length = max(6, int(20 - (dur-60)/30*6))
    pace = 20 if avg_motion>=0.035 else 14 if avg_motion>=0.02 else 9 if avg_motion>=0.01 else 4
    energy = 20 if -15 <= mean_db <= -8 else (12 if -20 <= mean_db < -15 else 6)
    hook = 20 if early_motion>=0.03 else 12 if early_motion>=0.015 else 6
    total = fmt+length+pace+energy+hook
    grade_letter = "S" if total>=90 else "A" if total>=80 else "B" if total>=68 else "C" if total>=55 else "D"
    tips = []
    if fmt < 20: tips.append("Use a vertical 9:16 frame for Shorts/Reels/TikTok.")
    if hook < 20: tips.append("Add a stronger visual hook in the first 1-3s (more motion/text/pop).")
    if pace < 20: tips.append("Keep visual motion lively throughout; avoid long static holds.")
    if energy < 20: tips.append("Raise/normalize audio energy (loud, punchy mix around -12 dB mean).")
    if length < 20: tips.append("Aim for ~7-45s; trim dead air.")
    if not tips: tips.append("Strong across the board — ship it and test the first frame/thumbnail.")
    return json.dumps({
        "score": total, "grade": grade_letter,
        "breakdown": {"format": fmt, "length": length, "pace": pace, "energy": energy, "hook": hook},
        "metrics": {"duration_s": round(dur,2), "resolution": f"{w}x{h}",
                     "avg_motion": round(avg_motion,4), "hook_motion_first3s": round(early_motion,4),
                     "hard_cuts": cuts.get("count",0), "mean_db": mean_db},
        "tips": tips,
    }, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run()
