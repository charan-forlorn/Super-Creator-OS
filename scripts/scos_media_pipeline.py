from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
sys.stderr.reconfigure(encoding="utf-8",errors="replace")
REPO=Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path: sys.path.insert(0,str(REPO))
from scos.media_analysis.cache import analysis_key,file_sha256,load,store
from scos.media_analysis.pipeline import analyze_media,build_plan,write_json
from scos.media_analysis.temporal_quality import verify_temporal_quality
from scos.media_analysis.contracts import MediaEvidence,MediaSourceProbe,SilenceSpan,SceneBoundary,CadenceStats,SubtitleEvidence,AdBoundary

def _load_evidence(path:Path)->MediaEvidence:
    data=json.loads(path.read_text(encoding="utf-8")); src=MediaSourceProbe(**data["source"])
    ad=AdBoundary(**data["ad_boundary"]) if data.get("ad_boundary") else None
    return MediaEvidence(src,[SilenceSpan(**x) for x in data["silences"]],[SceneBoundary(**x) for x in data["scene_boundaries"]],
                         CadenceStats(**data["cadence"]) if data["cadence"] else None,
                         SubtitleEvidence(**data["subtitles"]),data.get("warnings",[]),ad,data.get("source_sha256"))

def main()->int:
    ap=argparse.ArgumentParser(description="SCOS deterministic media intelligence pipeline")
    sub=ap.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("analyze"); a.add_argument("source"); a.add_argument("--out"); a.add_argument("--srt"); a.add_argument("--cache-dir",default=str(REPO/"scos"/"work"/"media-analysis-cache")); a.add_argument("--no-cache",action="store_true")
    p=sub.add_parser("plan"); p.add_argument("evidence"); p.add_argument("--out"); p.add_argument("--speed",choices=["fast","balanced","quality"],default="balanced"); p.add_argument("--smoothness",choices=["preserve","adaptive"],default="preserve")
    v=sub.add_parser("verify"); v.add_argument("output"); v.add_argument("--source"); v.add_argument("--target-fps",type=float)
    r=sub.add_parser("render"); r.add_argument("source"); r.add_argument("plan"); r.add_argument("output"); r.add_argument("--interpolate-fps",type=int)
    s=sub.add_parser("smooth-plus"); s.add_argument("source"); s.add_argument("plan"); s.add_argument("evidence"); s.add_argument("output"); s.add_argument("--threshold",type=float,default=0.35)
    ad=sub.add_parser("adaptive-smooth-plus"); ad.add_argument("source"); ad.add_argument("plan"); ad.add_argument("evidence"); ad.add_argument("output"); ad.add_argument("--threshold",type=float,default=0.35); ad.add_argument("--threads",default="2:4:4")
    ns=ap.parse_args()
    if ns.cmd=="analyze":
        config={"silence_db":-45.0,"min_silence":0.5,"scene_threshold":0.30,"srt_sha256":file_sha256(ns.srt) if ns.srt and Path(ns.srt).is_file() else None}
        key=analysis_key(ns.source,config); payload=None
        if not ns.no_cache: payload=load(ns.cache_dir,key)
        if payload is None:
            payload=analyze_media(ns.source,srt=ns.srt).to_dict()
            if not ns.no_cache: store(ns.cache_dir,key,payload)
            cache_state="MISS"
        else: cache_state="HIT"
        if ns.out: write_json(payload,ns.out)
        print(json.dumps({"cache":cache_state,"key":key,"evidence":payload},ensure_ascii=False,indent=2)); return 0
    if ns.cmd=="plan":
        plan=build_plan(_load_evidence(Path(ns.evidence)),speed=ns.speed,smoothness=ns.smoothness).to_dict()
        if ns.out: write_json(plan,ns.out)
        print(json.dumps(plan,ensure_ascii=False,indent=2)); return 0
    if ns.cmd=="verify":
        result=verify_temporal_quality(ns.output,ns.source,target_fps=ns.target_fps)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0 if result["status"]=="PASS" else 2
    if ns.cmd=="render":
        plan=json.loads(Path(ns.plan).read_text(encoding="utf-8"))
        from scos.render.source_edit import render_source_edits
        result=render_source_edits(ns.source,[tuple(x) for x in plan["keep_ranges"]],ns.output,profile=plan["encoder_profile"],interpolate_fps=ns.interpolate_fps)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    ev=_load_evidence(Path(ns.evidence)); plan=json.loads(Path(ns.plan).read_text(encoding="utf-8")); keep_ranges=[tuple(x) for x in plan["keep_ranges"]]; cuts=[s.time for s in ev.scene_boundaries]
    if ns.cmd=="smooth-plus":
        from scos.render.smooth_plus import render_smooth_plus
        result=render_smooth_plus(ns.source,keep_ranges,cuts,ns.output,duplicate_ratio=ev.cadence.duplicate_ratio if ev.cadence else 0.0,threshold=ns.threshold)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    if ns.cmd=="adaptive-smooth-plus":
        from scos.render.smooth_plus import render_adaptive_smooth_plus
        result=render_adaptive_smooth_plus(ns.source,keep_ranges,cuts,ns.output,duplicate_ratio=ev.cadence.duplicate_ratio if ev.cadence else 0.0,threshold=ns.threshold,threads=ns.threads)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    return 2
if __name__=="__main__": raise SystemExit(main())
