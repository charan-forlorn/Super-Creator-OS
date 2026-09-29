from pathlib import Path
import json
from scos.media_analysis.adaptive_smooth_plus_v3 import run_quality_canary
src=r"C:/Users/chara/OneDrive/Videos/การบันทึกหน้าจอ/การบันทึกหน้าจอ 2026-09-27 091454.mp4"
root=Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/screen_recording_real")
for name,s,e in [("screen-main-1",38.166667,39.166667),("screen-main-2",43.166667,44.166667)]:
    ev=run_quality_canary(src,(s,e),temp_root=Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/tmp")/name)
    p=ev.to_dict()
    p["source_id"]="screen-main"; p["class_label"]="screen_recording_real"; p["selection"]="v3_known_good"
    (root/f"{name}.json").write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    print(name,ev.decision,ev.valid_triple_ratio,ev.quality_score)
