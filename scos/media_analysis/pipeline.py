from __future__ import annotations
import json
from pathlib import Path
from .ad_boundary import infer_final_ad_boundary
from .cache import file_sha256
from .cadence import estimate_cadence
from .contracts import EditPlan,MediaEvidence,SilenceSpan
from .scene_boundaries import detect_scene_boundaries
from .silence import complement_ranges,detect_silence
from .source_probe import probe_source
from .subtitle_evidence import resolve_subtitle_evidence

def analyze_media(source: str|Path, *, silence_db: float=-45.0, min_silence: float=0.5,
                  scene_threshold: float=0.30, srt: str|Path|None=None)->MediaEvidence:
    source_path=Path(source).resolve()
    probe=probe_source(source_path)
    strict=detect_silence(source_path,silence_db,min_silence)
    broad=detect_silence(source_path,-35.0,max(0.8,min_silence))
    merged=list(strict)
    for span in broad:
        if not any(abs(span.start-x.start)<0.05 and abs(span.end-x.end)<0.05 for x in merged):
            merged.append(SilenceSpan(span.start,span.end,span.duration,"broad_silence"))
    scenes=detect_scene_boundaries(source_path,scene_threshold)
    cadence=estimate_cadence(source_path,probe)
    subtitles=resolve_subtitle_evidence(source_path,srt)
    ad=infer_final_ad_boundary(probe.duration_s,scenes,broad)
    warnings=[]
    if cadence.duplicate_ratio>0.45: warnings.append("High duplicate-frame cadence detected; preserve source cadence or consider bounded interpolation.")
    if not cadence.cfr: warnings.append("Source is not clean CFR; adaptive interpolation is disabled until source cadence is repaired.")
    if ad: warnings.append(f"Potential advert boundary at {ad.content_end:.3f}s with scene trigger {ad.trigger_scene_time:.3f}s.")
    return MediaEvidence(probe,merged,scenes,cadence,subtitles,warnings,ad,file_sha256(source_path))

def build_plan(evidence: MediaEvidence, *, target_srt: str|Path|None=None,
               speed: str="balanced", smoothness: str="preserve")->EditPlan:
    base_ranges=complement_ranges(evidence.source.duration_s,[s for s in evidence.silences if s.kind=="silence"])
    ranges=base_ranges
    if evidence.ad_boundary:
        cut=evidence.ad_boundary.content_end
        ranges=[(a,min(b,cut)) for a,b in base_ranges if a<cut and min(b,cut)-a>=0.05]
    encoder="nvenc_p3_hq" if speed=="balanced" else ("nvenc_p1_fast" if speed=="fast" else "libx264_quality")
    interpolation="disabled"
    if smoothness=="adaptive" and evidence.cadence and evidence.cadence.duplicate_ratio>0.45:
        interpolation="adaptive_smooth_plus_v2_candidate"
    subtitle_policy="srt" if evidence.subtitles.status=="VERIFIED" else "evidence_required"
    return EditPlan(tuple(ranges),-45.0,0.5,"preserve_source_fps",encoder,interpolation,subtitle_policy,
                    ad_boundary_s=evidence.ad_boundary.content_end if evidence.ad_boundary else None)

def write_json(value: dict,path: str|Path)->None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True),encoding="utf-8")
