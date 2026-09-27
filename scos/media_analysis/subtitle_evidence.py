from __future__ import annotations
from pathlib import Path
from .contracts import SubtitleEvidence

def resolve_subtitle_evidence(source: str|Path, srt: str|Path|None=None) -> SubtitleEvidence:
    if srt:
        p=Path(srt).resolve()
        if p.is_file() and p.stat().st_size>0:
            return SubtitleEvidence("srt","VERIFIED",1.0,str(p),"Caller supplied subtitle sidecar")
    candidate=Path(source).with_suffix(".srt")
    if candidate.is_file() and candidate.stat().st_size>0:
        return SubtitleEvidence("srt","VERIFIED",1.0,str(candidate),"Adjacent subtitle sidecar")
    # Local OCR/ASR providers remain optional; core runtime never fabricates captions.
    try:
        __import__("rapidocr_onnxruntime")
        ocr_available=True
    except Exception:
        ocr_available=False
    try:
        __import__("faster_whisper")
        asr_available=True
    except Exception:
        asr_available=False
    note=f"Providers available: ASR={asr_available}, OCR={ocr_available}; no verified cue source yet."
    return SubtitleEvidence("auto","UNKNOWN",None,None,note)
