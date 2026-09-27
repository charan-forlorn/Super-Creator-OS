from __future__ import annotations
import subprocess
from pathlib import Path
from scos.media_binaries import resolve_ffprobe
from .cadence import estimate_cadence_normalized
from .source_probe import probe_source

def _pts(path: Path)->list[float]:
    p=subprocess.run([resolve_ffprobe(),"-v","error","-select_streams","v:0",
                      "-show_entries","frame=best_effort_timestamp_time","-of","csv=p=0",str(path)],
                     capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=120,check=False)
    values=[]
    for line in p.stdout.splitlines():
        try: values.append(float(line.strip()))
        except ValueError: pass
    return values

def _stream_duration(path: Path,kind: str)->float|None:
    p=subprocess.run([resolve_ffprobe(),"-v","error","-select_streams",f"{kind}:0",
                      "-show_entries","stream=duration","-of","default=nw=1:nk=1",str(path)],
                     capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,check=False)
    try: return float((p.stdout or "").strip().splitlines()[0])
    except (ValueError,IndexError): return None

def _timeline_ok(spans:list[list[float]]|list[tuple[float,float]],keep_ranges:list[tuple[float,float]],cuts:list[float])->bool:
    for a,b in spans:
        if not any(a >= ka-1e-6 and b <= kb+1e-6 for ka,kb in keep_ranges): return False
        if any(a < cut < b for cut in cuts): return False
    return True

def verify_temporal_quality(output: str|Path,source: str|Path|None=None,
                            duplicate_ratio_tolerance: float=0.20,cfr_tolerance_s: float=0.100,
                            target_fps: float|None=None,keep_ranges:list[tuple[float,float]]|None=None,
                            smooth_spans:list[tuple[float,float]]|None=None,scene_cuts:list[float]|None=None)->dict:
    out_path=Path(output).resolve(); out=probe_source(out_path)
    result={"status":"PASS","checks":{},"warnings":[]}
    video_duration=_stream_duration(out_path,"v") or out.duration_s
    expected_frames=round(video_duration*out.fps) if out.fps>0 else out.frames
    cfr_ok=out.cfr and out.fps>0 and abs(out.frames-expected_frames)<=1 and abs(video_duration-out.frames/out.fps)<=cfr_tolerance_s
    result["checks"]["output_fps"]={"pass":out.fps>0,"value":out.fps,"target":target_fps}
    result["checks"]["cfr"]={"pass":cfr_ok,"frames":out.frames,"video_duration":video_duration,"source_probe_cfr":out.cfr}
    if target_fps is not None and abs(out.fps-target_fps)>0.01:
        result["status"]="FAIL"; result["checks"]["target_fps"]={"pass":False,"actual":out.fps,"expected":target_fps}
    else:
        result["checks"]["target_fps"]={"pass":True,"actual":out.fps,"expected":target_fps}
    pts=_pts(out_path); monotonic=all(b>a for a,b in zip(pts,pts[1:])) if len(pts)>1 else True
    result["checks"]["pts_monotonic"]={"pass":monotonic,"frames_checked":len(pts)}
    if not (cfr_ok and monotonic): result["status"]="FAIL"
    av_video=video_duration; av_audio=_stream_duration(out_path,"a")
    if av_video is not None and av_audio is not None:
        delta=abs(av_video-av_audio)
        result["checks"]["av_duration_delta"]={"pass":delta<=0.100,"video":av_video,"audio":av_audio,"delta":delta}
        if delta>0.100: result["status"]="FAIL"
    if keep_ranges is not None:
        expected_timeline=sum(b-a for a,b in keep_ranges)
        timeline_delta=abs(video_duration-expected_timeline)
        result["checks"]["edited_timeline_duration"]={"pass":timeline_delta<=0.100,"expected":expected_timeline,"actual":video_duration,"delta":timeline_delta}
        if timeline_delta>0.100: result["status"]="FAIL"
    if smooth_spans is not None and keep_ranges is not None:
        cuts=sorted(scene_cuts or [])
        ordered=sorted((float(a),float(b)) for a,b in smooth_spans)
        non_overlapping=all(b <= next_a + 1e-6 for (_,b),(next_a,_) in zip(ordered,ordered[1:]))
        route_ok=non_overlapping and _timeline_ok(ordered,keep_ranges,cuts)
        selected=sum(b-a for a,b in ordered)
        kept=sum(b-a for a,b in keep_ranges)
        route_ok = route_ok and selected <= kept + 1e-6
        result["checks"]["adaptive_route_integrity"]={
            "pass":route_ok,
            "smooth_seconds":selected,
            "keep_seconds":kept,
            "smooth_fraction":selected/kept if kept else 0.0,
            "non_overlapping":non_overlapping,
            "scene_cuts":cuts,
        }
        if not route_ok: result["status"]="FAIL"
    if source:
        src=probe_source(source)
        src_cad=estimate_cadence_normalized(source,src,src.fps)
        out_cad=estimate_cadence_normalized(output,out,src.fps)
        delta=abs(out_cad.duplicate_ratio-src_cad.duplicate_ratio)
        result["checks"]["duplicate_ratio_drift_normalized"]={"pass":delta<=duplicate_ratio_tolerance,"target_fps":src.fps,"source":src_cad.duplicate_ratio,"output_at_source_fps":out_cad.duplicate_ratio,"delta":delta}
        if delta>duplicate_ratio_tolerance: result["status"]="FAIL"
    result["encoder_contract"]={"fps":out.fps,"frames":out.frames,"duration_s":video_duration,"codec":out.video_codec,"size":[out.width,out.height]}
    return result
