from __future__ import annotations
import json, os
from dataclasses import dataclass
from urllib import request
from urllib.error import HTTPError, URLError
from typing import Any

@dataclass(frozen=True)
class JevDecision:
    status: str
    model: str | None
    answers: dict[str, Any]
    confidence: float | None
    error: str | None = None

def _post(payload: dict[str, Any], api_key: str, timeout: float = 8.0) -> dict[str, Any]:
    body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
    req=request.Request("https://api.typesafe.ai/v1/systemone",data=body,method="POST",
                        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"})
    try:
        with request.urlopen(req,timeout=timeout) as response:
            raw=response.read().decode("utf-8",errors="replace")
            return json.loads(raw)
    except HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[-1000:]
        if exc.code in {429,529}: raise RuntimeError(f"typesafe retryable {exc.code}: {detail}") from exc
        raise RuntimeError(f"typesafe http {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"typesafe transport failure: {exc}") from exc

def advise_smooth_plus(state: dict[str, Any], *, min_confidence: float = 0.85) -> JevDecision:
    api_key=os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        return JevDecision("UNAVAILABLE",None,{},None,"TYPESAFE_API_KEY not configured")
    payload={
        "model": os.getenv("TYPESAFE_MODEL","jev-1.13.0"),
        "state": state,
        "questions":{
            "render_lane":{
                "type":"choice",
                "instructions":"Choose the safest useful local video render lane from the provided evidence.",
                "criteria":{
                    "preserve":"Preserve source FPS and avoid interpolation.",
                    "smooth_plus":"Use bounded RIFE-based interpolation when cadence evidence supports it and QA can verify it.",
                    "quality":"Prefer slower high-quality encoding without changing motion cadence."
                }
            },
            "smoothness_need":{
                "type":"score",
                "instructions":"Score how strongly the evidence supports creating a smoother-than-source motion candidate.",
                "criteria":{
                    "0":"No evidence of cadence problems or smoothness need.",
                    "1":"Weak evidence; preserve cadence.",
                    "2":"Material duplicate cadence; candidate is useful.",
                    "3":"Strong duplicate cadence; a bounded candidate is justified."
                }
            }
        }
    }
    try:
        result=_post(payload,api_key)
        answers=result.get("answers") or {}
        confs=[]
        for value in answers.values():
            if isinstance(value,dict) and isinstance(value.get("confidence"),(int,float)):
                confs.append(float(value["confidence"]))
        conf=min(confs) if confs else None
        status="PASS" if conf is not None and conf>=min_confidence else "REVIEW"
        return JevDecision(status,result.get("model"),answers,conf)
    except Exception as exc:
        return JevDecision("ERROR",payload["model"],{},None,str(exc))

def should_promote_smooth_plus(decision: JevDecision, deterministic_gate: bool)->bool:
    if not deterministic_gate or decision.status!="PASS":
        return False
    lane=decision.answers.get("render_lane",{})
    return lane.get("choice")=="smooth_plus"
