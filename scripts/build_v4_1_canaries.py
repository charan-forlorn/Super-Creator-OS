from pathlib import Path
import json
from scos.media_analysis.adaptive_smooth_plus_v3 import run_quality_canary

root=Path(r"C:/Workspace/super-creator-os")
ev=root/"evidence/media-pipeline-adaptive-v4.1"
motion=json.loads((ev/"motion_candidates.json").read_text(encoding="utf-8"))
sources={
"screen-main":{"class":"screen_recording_real","path":r"C:/Users/chara/OneDrive/Videos/การบันทึกหน้าจอ/การบันทึกหน้าจอ 2026-09-27 091454.mp4"},
"screen-desktop":{"class":"screen_recording_real","path":r"C:/Users/chara/Downloads/SCOS_single_screen_desktop.mp4"},
"screen-download":{"class":"screen_recording_real","path":r"C:/Users/chara/Downloads/Download.mp4"},
"portrait-phone":{"class":"portrait_screen_real","path":r"C:/Users/chara/Downloads/SCOS_single_screen_phone.mp4"},
"portrait-remix":{"class":"portrait_screen_real","path":r"C:/Users/chara/Downloads/Download_single_screen_remix.mp4"},
"portrait-remaster":{"class":"portrait_screen_real","path":r"C:/Users/chara/Downloads/Download_single_screen_remix_REMASTERED_1080x1920.mp4"},
"caminandes":{"class":"natural_motion_real","path":r"C:/Users/chara/Downloads/scos_calibration_sources/caminandes/caminandes_gran_dillama.mp4"},
"elephantsdream":{"class":"natural_motion_real","path":r"C:/Users/chara/Downloads/scos_calibration_sources/elephantsdream/elephantsdream_teaser.mp4"},
"internal-preview":{"class":"natural_motion_real","path":r"C:/Users/chara/Downloads/scos_calibration_sources/internalpreview/internal-preview.mp4"},
}
results=[]
for sid,meta in sources.items():
    outdir=ev/meta["class"]; outdir.mkdir(parents=True,exist_ok=True)
    for idx,w in enumerate(motion[sid]["top_windows"][:2],1):
        name=f"{sid}-{idx}"
        tmp=ev/"tmp"/name
        e=run_quality_canary(meta["path"],(w["start"],w["end"]),temp_root=tmp)
        payload=e.to_dict()
        payload["source_id"]=sid
        payload["class_label"]=meta["class"]
        payload["motion_score"]=w["score"]
        outdir.joinpath(f"{name}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        results.append({"sample_id":name,"class":meta["class"],"decision":e.decision,"valid_triple_ratio":e.valid_triple_ratio,"quality_score":e.quality_score,"motion_score":w["score"]})
(ev/"V4_1_CANARY_RESULTS.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(results,ensure_ascii=False,indent=2))
