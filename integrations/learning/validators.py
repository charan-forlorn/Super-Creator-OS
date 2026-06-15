"""validators.py — pure schema validation for the Super Creator OS learning layer.

No side effects. Every writer (memory_writer, archive_manager, anchor_library)
calls these before touching disk. Keeps the v1 memory contract inviolable.
"""

from __future__ import annotations

# The original v1 record contract — must never be broken or removed.
V1_REQUIRED = ["project_name", "product_niche", "hook_successful",
               "editing_specs", "retention_score", "lesson_learned", "created_at"]

VALID_EVENTS = {
    "PROJECT_RENDERED", "PROJECT_QA_PASSED", "PROJECT_QA_FAILED",
    "MEMORY_RECORD_CREATED", "HIGHLIGHT_PATTERN_DISCOVERED",
    "RENDER_FAILURE_DETECTED", "PROJECT_COMPLETE",
}


def validate_record(rec: dict) -> list[str]:
    errs = []
    if not isinstance(rec, dict):
        return ["record is not an object"]
    for k in V1_REQUIRED:
        if k not in rec:
            errs.append(f"missing v1 field: {k}")
    if not isinstance(rec.get("retention_score"), int):
        errs.append("retention_score must be int")
    elif not (0 <= rec["retention_score"] <= 100):
        errs.append("retention_score out of range 0-100")
    if not rec.get("project_name"):
        errs.append("project_name empty")
    if not rec.get("product_niche"):
        errs.append("product_niche empty")
    return errs


def validate_db(db) -> list[str]:
    """Existing records must remain a valid array, each keeping v1 fields."""
    if not isinstance(db, list):
        return ["database root is not a JSON array"]
    errs = []
    for i, r in enumerate(db):
        if not isinstance(r, dict):
            errs.append(f"record {i} is not an object")
            continue
        for k in V1_REQUIRED:
            if k not in r:
                errs.append(f"existing record {i} missing v1 field {k}")
    return errs


def validate_event(ev: dict) -> list[str]:
    errs = []
    for k in ("event_type", "project_id", "timestamp", "metadata"):
        if k not in ev:
            errs.append(f"event missing field: {k}")
    if ev.get("event_type") not in VALID_EVENTS:
        errs.append(f"unknown event_type: {ev.get('event_type')}")
    if "metadata" in ev and not isinstance(ev["metadata"], dict):
        errs.append("event.metadata must be an object")
    return errs


def validate_anchor_library(lib) -> list[str]:
    if not isinstance(lib, dict):
        return ["anchor library root must be an object {niche: {...}}"]
    errs = []
    for niche, payload in lib.items():
        if niche.startswith("_"):           # metadata keys (e.g. _schema) are not niches
            continue
        if not isinstance(payload, dict) or "anchors" not in payload:
            errs.append(f"niche '{niche}' missing 'anchors' list")
            continue
        if not isinstance(payload["anchors"], list):
            errs.append(f"niche '{niche}'.anchors must be a list")
    return errs
