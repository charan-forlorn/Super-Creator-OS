"""validators.py — pure schema validation for the Super Creator OS learning layer.

No side effects. Every writer (memory_writer, archive_manager, anchor_library)
calls these before touching disk. Keeps the v1 memory contract inviolable.
"""

from __future__ import annotations

# The original v1 record contract — must never be broken or removed.
V1_REQUIRED = ["project_name", "product_niche", "hook_successful",
               "editing_specs", "retention_score", "lesson_learned", "created_at"]

VALID_EVENTS = {
    # --- backward loop (render -> memory) ---
    "PROJECT_RENDERED", "PROJECT_QA_PASSED", "PROJECT_QA_FAILED",
    "MEMORY_RECORD_CREATED", "HIGHLIGHT_PATTERN_DISCOVERED",
    "RENDER_FAILURE_DETECTED", "PROJECT_COMPLETE",
    # --- forward loop (memory -> next decision), emitted by recommendation_service ---
    "BRIEF_RECEIVED", "REFERENCE_MATCHED", "HOOKS_RECOMMENDED",
    "CREATIVE_SEED_READY",
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


# --- provenance/v3 (OPTIONAL block on a record) ---------------------------
# Validated ONLY when present. Never added to V1_REQUIRED; a record without a
# provenance block stays fully valid (backward compatible).
PROVENANCE_MATCH_QUALITY = {"exact", "near", "cold_start"}
PROVENANCE_ADOPTION = {"adopted", "partial", "rejected", "none_suggested", "unrecorded"}


def validate_provenance(prov) -> list[str]:
    """Validate a record's optional `provenance` block. Empty list if prov is None."""
    if prov is None:
        return []
    if not isinstance(prov, dict):
        return ["provenance must be an object"]
    errs: list[str] = []
    rec = prov.get("recommended")
    dec = prov.get("decided")
    if rec is not None and not isinstance(rec, dict):
        errs.append("provenance.recommended must be an object")
        rec = None
    if dec is not None and not isinstance(dec, dict):
        errs.append("provenance.decided must be an object")
        dec = None

    if isinstance(rec, dict):
        mq = rec.get("match_quality")
        if mq is not None and mq not in PROVENANCE_MATCH_QUALITY:
            errs.append(f"provenance.recommended.match_quality invalid: {mq}")
        if mq == "cold_start" and rec.get("reference_project"):
            errs.append("cold_start provenance must not carry a reference_project")
        sh = rec.get("suggested_hooks")
        if sh is not None and not isinstance(sh, list):
            errs.append("provenance.recommended.suggested_hooks must be a list")

    if isinstance(dec, dict):
        ad = dec.get("hook_adoption")
        if ad is not None and ad not in PROVENANCE_ADOPTION:
            errs.append(f"provenance.decided.hook_adoption invalid: {ad}")
        hu = dec.get("hooks_actually_used")
        if hu is not None and not isinstance(hu, list):
            errs.append("provenance.decided.hooks_actually_used must be a list")
    return errs


# --- telemetry sidecar (memory/telemetry.json) -----------------------------
# Observed outcome rows, joined to records/provenance by loop_run_id. A SEPARATE
# store — database.json contract is never touched by telemetry.
TELEMETRY_REQUIRED = ["loop_run_id", "project_name", "platform", "collected_at"]
TELEMETRY_PLATFORMS = {"tiktok", "youtube_shorts", "instagram_reels"}
# fields that are percentages (0..100) when present
TELEMETRY_PCT_FIELDS = ("avg_watch_pct", "completion_rate", "rewatch_rate_pct", "ctr_pct")
# fields that are non-negative counts/seconds when present
TELEMETRY_NONNEG_FIELDS = ("views", "likes", "comments", "shares", "saves",
                           "avg_watch_time_s", "output_duration_s")


def validate_telemetry(entry) -> list[str]:
    """Validate one telemetry row. Numeric fields are optional but, when present,
    must be in range. loop_run_id is the join key and is required."""
    if not isinstance(entry, dict):
        return ["telemetry entry is not an object"]
    errs: list[str] = []
    for k in TELEMETRY_REQUIRED:
        if not entry.get(k):
            errs.append(f"telemetry missing/empty required field: {k}")
    plat = entry.get("platform")
    if plat is not None and plat not in TELEMETRY_PLATFORMS:
        errs.append(f"telemetry.platform invalid: {plat} (allowed: {sorted(TELEMETRY_PLATFORMS)})")
    for f in TELEMETRY_PCT_FIELDS:
        v = entry.get(f)
        if v is not None and not (isinstance(v, (int, float)) and 0 <= v <= 100):
            errs.append(f"telemetry.{f} must be a number in 0..100")
    for f in TELEMETRY_NONNEG_FIELDS:
        v = entry.get(f)
        if v is not None and not (isinstance(v, (int, float)) and v >= 0):
            errs.append(f"telemetry.{f} must be a non-negative number")
    return errs


def validate_telemetry_store(store) -> list[str]:
    """The telemetry file must be a JSON array of rows that each validate."""
    if not isinstance(store, list):
        return ["telemetry store root is not a JSON array"]
    errs = []
    for i, row in enumerate(store):
        for e in validate_telemetry(row):
            errs.append(f"row {i}: {e}")
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
