from __future__ import annotations
import subprocess,time
from pathlib import Path
from scos.media_binaries import resolve_ffmpeg
from scos.media_analysis.source_probe import probe_source

PROFILES={
 "nvenc_p1_fast":("h264_nvenc",("-preset","p1","-cq","19")),
 "nvenc_p3_hq":("h264_nvenc",("-preset","p3","-tune","hq","-rc","vbr","-cq","19","-b:v","0","-bf","3","-b_ref_mode","middle","-temporal-aq","1","-rc-lookahead","16")),
 "nvenc_p4_hq":("h264_nvenc",("-preset","p4","-tune","hq","-rc","vbr","-cq","19","-b:v","0","-bf","3","-b_ref_mode","middle","-temporal-aq","1","-rc-lookahead","20")),
 "libx264_quality":("libx264",("-preset","medium","-crf","18")),
}

def render_source_edits(source: str|Path, keep_ranges: list[tuple[float,float]], output: str|Path,
                        profile: str="nvenc_p3_hq", interpolate_fps: int|None=None)->dict:
    src=Path(source).resolve(); out=Path(output).resolve()
    if not keep_ranges: raise ValueError("keep_ranges empty")
    probe=probe_source(src); ffmpeg=resolve_ffmpeg()
    if not probe.has_audio: raise ValueError("source_edit requires an audio stream")
    enc,args=PROFILES[profile]
    parts=[]; labels=[]
    for i,(start,end) in enumerate(keep_ranges):
        dur=max(0.001,end-start)
        parts.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]")
        fade_out=max(0.0,dur-0.03)
        parts.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out:.3f}:d=0.03[a{i}]")
        labels.extend([f"[v{i}]",f"[a{i}]"])
    parts.append("".join(labels)+f"concat=n={len(keep_ranges)}:v=1:a=1[v][a]")
    if interpolate_fps:
        parts.append(f"[v]minterpolate=fps={interpolate_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bilat:scd=fdiff:scd_threshold=8,fps={interpolate_fps},setpts=PTS-STARTPTS[vout]")
        vmap="vout"; fps_args=["-r",str(interpolate_fps)]
    else:
        vmap="v"; fps_args=["-fps_mode","passthrough"]
    cmd=[ffmpeg,"-hide_banner","-loglevel","error","-i",str(src),"-filter_complex",";".join(parts),
         "-map",f"[{vmap}]","-map","[a]","-c:v",enc,*args,*fps_args,
         "-profile:v","high","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar","48000",
         "-movflags","+faststart","-y",str(out)]
    t=time.perf_counter(); p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",check=False); elapsed=time.perf_counter()-t
    if p.returncode: raise RuntimeError((p.stderr or "")[-2000:])
    return {"output":str(out),"elapsed_s":elapsed,"source_fps":probe.fps,"profile":profile,"interpolate_fps":interpolate_fps}
