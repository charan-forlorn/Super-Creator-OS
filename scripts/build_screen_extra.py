from pathlib import Path
import json
from scos.media_analysis.adaptive_smooth_plus_v3 import run_quality_canary
src=r"C:/Users/chara/OneDrive/Videos/Screen Recordings/Screen Recording 2026-09-04 152518.mp4"
root=Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/screen_recording_real")
wins=[(0.0,1.0),(3.4,4.4)]
for i,(s,e) in enumerate(wins,1):
    ev=run_quality_canary(src,(s,e),temp_root=Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/tmp")/f"screen-extra-{i}")
    p=ev.to_dict(); p.update({"source_id":"screen-extra","class_label":"screen_recording_real","selection":"motion_scan"})
    (root/f"screen-extra-{i}.json").write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
    print(i,ev.decision,ev.valid_triple_ratio,ev.quality_score)
