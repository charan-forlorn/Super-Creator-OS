"""anchor_library.py — Highlight Anchor Intelligence.

Central, niche-agnostic store of "phrases that mark a beat" and how well they
perform. Learns from every passed project: which anchors actually appeared, what
retention the project scored, whether it succeeded. Lets storytelling/retention
skills ask: "for this niche, what hook has worked before?"

Library file: memory/highlight_anchor_library.json  (append/update, never destroyed)
Derived per anchor:  retention_avg = retention_sum/retention_count
                     success_rate  = success_count/use_count

Safe: validate -> backup -> atomic write. Same discipline as memory_writer.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path

from validators import validate_anchor_library

LIB_PATH = Path(__file__).resolve().parents[2] / "memory" / "highlight_anchor_library.json"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _norm(s: str) -> str:
    return s.lower().strip().strip(".,!?;:")


def suggest_hooks(niche: str, top_n: int = 3, path: Path | None = None) -> list[dict]:
    """Return best-performing anchors for a niche, ranked by (success_rate, retention_avg, frequency)."""
    lib = _load(Path(path) if path else LIB_PATH)
    payload = lib.get(niche)
    if not payload:
        return []
    scored = []
    for a in payload["anchors"]:
        if a.get("kind") == "audio_event":      # not a transferable verbal hook
            continue
        rc, uc = a.get("retention_count", 0), a.get("use_count", 0)
        ravg = (a.get("retention_sum", 0) / rc) if rc else 0
        srate = (a.get("success_count", 0) / uc) if uc else 0
        scored.append({**a, "retention_avg": round(ravg, 1), "success_rate": round(srate, 2)})
    scored.sort(key=lambda x: (x["success_rate"], x["retention_avg"], x["frequency"]), reverse=True)
    return scored[:top_n]


def record_project_anchors(niche: str, anchors: list[dict], retention_score: int,
                           success: bool, path: Path | None = None) -> tuple[bool, str, list[str]]:
    """Update the library from a finished project. Returns (ok, info, newly_discovered_phrases)."""
    p = Path(path) if path else LIB_PATH
    lib = _load(p)
    errs = validate_anchor_library(lib) if lib else []
    if errs:
        return False, "library invalid: " + "; ".join(errs), []

    meta = {k: v for k, v in lib.items() if k.startswith("_")}
    lib.setdefault(niche, {"anchors": []})
    existing = {_norm(a["phrase"]): a for a in lib[niche]["anchors"]}
    discovered: list[str] = []

    for anc in anchors:
        phrase = (anc.get("label") or anc.get("phrase") or "").strip()
        if not phrase:
            continue
        key = _norm(phrase)
        rec = existing.get(key)
        if rec is None:
            rec = {"phrase": phrase, "kind": anc.get("kind", "callout"),
                   "frequency": 0, "retention_sum": 0, "retention_count": 0,
                   "success_count": 0, "use_count": 0, "last_used": None}
            existing[key] = rec
            lib[niche]["anchors"].append(rec)
            discovered.append(phrase)
        rec["frequency"] += 1
        rec["use_count"] += 1
        rec["retention_sum"] += int(retention_score)
        rec["retention_count"] += 1
        if success:
            rec["success_count"] += 1
        rec["last_used"] = _now()

    # backup + atomic write
    if p.exists():
        bdir = p.parent / "_db_backups"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bdir / f"anchor_library.{_dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json")
    out = {**meta, **{k: v for k, v in lib.items() if not k.startswith("_")}}
    _atomic_write(p, out)
    return True, f"updated niche '{niche}' ({len(anchors)} anchors, {len(discovered)} new)", discovered
