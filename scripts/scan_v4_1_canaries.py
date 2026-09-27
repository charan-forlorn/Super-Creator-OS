from __future__ import annotations
import json
from pathlib import Path
from scos.media_analysis.adaptive_smooth_plus_v3 import run_quality_canary
from scos.media_analysis.source_probe import probe_source

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence"/"media-pipeline-adaptive-v4.1"/"scan2"
OUT.mkdir(parents=True,exist_ok=True)

SOURCES=[
("screen_main",r"C:\Users\chara\OneDrive\Videos\การบันทึกหน้าจอ\การบันทึกหน้าจอ 2026-09-27 091454.mp4"),
("screen_desktop",r"C:\Users\chara\Downloads\SCOS_single_screen_desktop.mp4"),
("portrait_phone",r"C:\Users\chara\Downloads\SCOS_single_screen_phone.mp4"),
("natural_elephantsdream",r"C:\Users\chara\Downloads\scos_calibration_sources\elephantsdream\elephantsdream_teaser.mp4"),
("natural_internal",r"C:\Users\chara\Downloads\scos_calibration_sources\internalpreview\internal-preview.mp4"),
]

def starts(duration:float)->list[float]:
    length=min(1.0,max(0.5,duration*0.05))
    latest=max(0.1,duration-length-0.75)
    return [round(min(latest,max(0.1,latest*f)),6) for f in (0.10,0.25,0.40,0.55,0.70,0.80)]

def main():
    summary={}
    for name,source in SOURCES:
        path=Path(source)
        if not path.exists():
            summary[name]={"status":"MISSING"}; continue
        probe=probe_source(path)
        if not probe.cfr:
            summary[name]={"status":"NON_CFR"}; continue
        rows=[]
        length=min(1.0,max(0.5,float(probe.duration_s)*0.05))
        for i,start in enumerate(starts(float(probe.duration_s)),1):
            end=min(float(probe.duration_s)-0.5,start+length)
            if end<=start+0.1:
                continue
            try:
                e=run_quality_canary(path,(start,end),temp_root=OUT/f"tmp-{name}-{i}")
                row={"start":start,"end":end,"status":"PASS","decision":e.decision,
                     "valid_triple_ratio":e.valid_triple_ratio,
                     "quality_score":e.quality_score,
                     "candidate_metrics":e.candidate_metrics,
                     "reasons":list(e.reasons)}
                rows.append(row)
            except Exception as exc:
                rows.append({"start":start,"end":end,"status":"ERROR",
                             "error_type":type(exc).__name__,"error":str(exc)})
        summary[name]={"status":"PASS","smooth_count":sum(r.get("decision")=="SMOOTH+" for r in rows),
                       "review_count":sum(r.get("decision")=="REVIEW" for r in rows),
                       "error_count":sum(r.get("status")=="ERROR" for r in rows),
                       "rows":rows}
    (OUT/"CANARY_SCAN_SUMMARY.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:{kk:v.get(kk) for kk in ("status","smooth_count","review_count","error_count")} for k,v in summary.items()},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
