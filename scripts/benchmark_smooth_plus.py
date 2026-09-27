from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scos.media_analysis.source_probe import probe_source
from scos.media_analysis.temporal_quality import verify_temporal_quality
from scos.media_binaries import resolve_ffmpeg


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest().upper()


def _run_filter(source: Path,candidate: Path,filter_text: str,source_start: float,duration: float) -> tuple[int,str]:
    ff=resolve_ffmpeg()
    p=subprocess.run([ff,'-hide_banner','-ss',f'{source_start:.9f}','-t',f'{duration:.9f}','-i',str(source),'-i',str(candidate),'-filter_complex',filter_text,'-f','null','-'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1200,check=False)
    return p.returncode,(p.stdout or '')+'\n'+(p.stderr or '')


def quality_metric(source: Path,candidate: Path,source_fps: float,source_start: float,duration: float,roi: bool=False)->float|None:
    crop='' if not roi else ',crop=iw:ih*0.35:0:ih*0.65'
    filt=f'[0:v]fps={source_fps:.9f}{crop},format=yuv420p[ref];[1:v]fps={source_fps:.9f}{crop},format=yuv420p[dist];[dist][ref]ssim=shortest=1'
    rc,text=_run_filter(source,candidate,filt,source_start,duration)
    if rc: return None
    m=re.findall(r'All:([0-9.]+)',text)
    return float(m[-1]) if m else None


def vmaf_metric(source: Path,candidate: Path,source_fps: float,source_start: float,duration: float)->dict[str,Any]:
    filt=f'[0:v]fps={source_fps:.9f},format=yuv420p[ref];[1:v]fps={source_fps:.9f},format=yuv420p[dist];[dist][ref]libvmaf=shortest=1'
    rc,text=_run_filter(source,candidate,filt,source_start,duration)
    m=re.findall(r'VMAF score:\s*([0-9.]+)',text)
    return {'available':True,'value':float(m[-1]) if m else None,'filter_rc':rc}


def motion_metrics(candidate: Path)->dict[str,float]:
    ff=resolve_ffmpeg(); p=probe_source(candidate); width=320; height=max(2,round(width*p.height/max(1,p.width)/2)*2)
    q=subprocess.run([ff,'-hide_banner','-loglevel','error','-i',str(candidate),'-vf',f'scale={width}:{height},format=gray','-f','rawvideo','-pix_fmt','gray','pipe:1'],capture_output=True,timeout=900,check=False)
    if q.returncode or not q.stdout: return {'motion_mean':0.0,'motion_std':0.0,'motion_jerk':0.0,'artifact_spike_rate_proxy':0.0,'temporal_motion_continuity_proxy':0.0}
    size=width*height; frames=np.frombuffer(q.stdout[:len(q.stdout)//size*size],dtype=np.uint8).reshape((-1,height,width))
    if len(frames)<3: return {'motion_mean':0.0,'motion_std':0.0,'motion_jerk':0.0,'artifact_spike_rate_proxy':0.0,'temporal_motion_continuity_proxy':0.0}
    d=np.abs(frames[1:].astype(np.int16)-frames[:-1].astype(np.int16)).mean(axis=(1,2))/255.0; jerk=np.abs(np.diff(d)); med=float(np.median(jerk)); mad=float(np.median(np.abs(jerk-med)))+1e-9; spikes=float(np.mean(jerk>med+4.0*mad)); continuity=float(1.0/(1.0+float(jerk.mean())/(float(d.mean())+1e-6)))
    return {'motion_mean':float(d.mean()),'motion_std':float(d.std()),'motion_jerk':float(jerk.mean()),'artifact_spike_rate_proxy':spikes,'temporal_motion_continuity_proxy':continuity}


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--preserve',required=True); ap.add_argument('--full',required=True); ap.add_argument('--adaptive',required=True); ap.add_argument('--adaptive-run-json',required=True); ap.add_argument('--preserve-time',type=float,required=True); ap.add_argument('--full-time',type=float,required=True); ap.add_argument('--source-start',type=float,required=True); ap.add_argument('--keep-duration',type=float,required=True); ap.add_argument('--out',required=True)
    ns=ap.parse_args(); source=Path(ns.source).resolve(); artifacts={'PRESERVE':Path(ns.preserve).resolve(),'FULL_SMOOTH+':Path(ns.full).resolve(),'ADAPTIVE_SMOOTH+':Path(ns.adaptive).resolve()}; src=probe_source(source); result={'source':{'path':str(source),'sha256':sha256(source),'fps':src.fps,'duration_s':src.duration_s,'reference_start_s':ns.source_start,'reference_duration_s':ns.keep_duration},'modes':{}}
    run=json.loads(Path(ns.adaptive_run_json).read_text(encoding='utf-8')); adaptive_time=float(run.get('composition',{}).get('elapsed_s',0.0))+sum(float(x.get('elapsed_s',0.0)) for x in run.get('rife_reports',[]) if 'elapsed_s' in x)
    for name,path in artifacts.items():
        target=src.fps if name=='PRESERVE' else 60.0; qa=verify_temporal_quality(path,source,target_fps=target); ssim=quality_metric(source,path,src.fps,ns.source_start,ns.keep_duration,False); roi=quality_metric(source,path,src.fps,ns.source_start,ns.keep_duration,True); vmaf=vmaf_metric(source,path,src.fps,ns.source_start,ns.keep_duration); result['modes'][name]={'path':str(path),'sha256':sha256(path),'probe':probe_source(path).to_dict(),'temporal_qa':qa,'ssim_all_vs_kept_source':ssim,'ssim_subtitle_roi_proxy':roi,'vmaf':vmaf,'motion':motion_metrics(path)}
    result['modes']['PRESERVE']['processing_time_s']=ns.preserve_time; result['modes']['FULL_SMOOTH+']['processing_time_s']=ns.full_time; result['modes']['ADAPTIVE_SMOOTH+']['processing_time_s']=adaptive_time
    a=result['modes']['ADAPTIVE_SMOOTH+']; f=result['modes']['FULL_SMOOTH+']; result['comparison']={'rife_workload_reduction':1.0-float(run.get('interpolation_fraction',1.0)),'full_to_adaptive_speedup':ns.full_time/adaptive_time if adaptive_time else None,'adaptive_time_s':adaptive_time,'full_time_s':ns.full_time,'quality_ssim_delta_adaptive_minus_full':None if a['ssim_all_vs_kept_source'] is None or f['ssim_all_vs_kept_source'] is None else a['ssim_all_vs_kept_source']-f['ssim_all_vs_kept_source'],'quality_ssim_retention_vs_preserve':None if a['ssim_all_vs_kept_source'] is None or result['modes']['PRESERVE']['ssim_all_vs_kept_source'] is None else a['ssim_all_vs_kept_source']-result['modes']['PRESERVE']['ssim_all_vs_kept_source'],'automatic_promotion':False}
    Path(ns.out).parent.mkdir(parents=True,exist_ok=True); Path(ns.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result['comparison'],ensure_ascii=False,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())
