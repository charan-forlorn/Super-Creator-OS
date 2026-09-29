from pathlib import Path
import json
from scos.media_analysis.adaptive_smooth_plus_v3 import gate_smooth_spans_with_canaries
src=r"C:/Users/chara/OneDrive/Videos/การบันทึกหน้าจอ/การบันทึกหน้าจอ 2026-09-27 091454.mp4"
spans=[(32.166667,37.166667),(38.166667,39.166667),(43.166667,44.166667)]
accepted,evidence=gate_smooth_spans_with_canaries(src,spans,temp_root=r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/tmp/screen-main-gate")
root=Path(r"C:/Workspace/super-creator-os/evidence/media-pipeline-adaptive-v4.1/screen_recording_real")
for i,e in enumerate(evidence,1):
    p=e.to_dict(); p.update({"source_id":"screen-main","class_label":"screen_recording_real","selection":"v3_multi_window_gate","accepted":e.decision=="SMOOTH+"})
    (root/f"screen-main-gate-{i}.json").write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding="utf-8")
print({"accepted":accepted,"decisions":[e.decision for e in evidence]})
