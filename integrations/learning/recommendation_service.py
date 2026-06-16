"""recommendation_service.py — the Orchestrator Learning Bridge (forward loop).

Closes the learning loop in the OTHER direction. learning_manager.py runs AFTER a
render (render -> memory). This runs BEFORE the timeline is built (memory -> next
decision): given a fresh brief it pulls everything the system already learned and
hands the Orchestrator a single "creative seed" to feed Storytelling / Retention /
Timeline.

Pipeline (mirrors the learning_manager discipline — stdlib only, UTF-8 forced,
event-driven, ADDITIVE, never edits a core file):

  1. emit BRIEF_RECEIVED
  2. find the nearest prior project in memory/database.json by product_niche
     (exact match -> token-overlap near match -> none) and emit REFERENCE_MATCHED
  3. ask anchor_library for the best-performing hooks for the niche
     -> emit HOOKS_RECOMMENDED
  4. assemble the seed: suggested hooks + retention benchmark + retention_signals
     + highlight patterns + editing_specs/lesson to reuse -> emit CREATIVE_SEED_READY
  5. return the seed dict to the Orchestrator

The seed is purely advisory. It writes NOTHING to memory (that stays the
Orchestrator's STEP 15 job) and reuses anchor_library read-only.

CLI:
  python integrations/learning/recommendation_service.py \
      --product-niche "Gaming (MOBA)" --project-name "<name>" [--db ...] [--top-n 3]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# --- make sibling modules importable regardless of cwd (same trick as learning_manager) ---
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from event_bus import EventBus            # noqa: E402
import anchor_library                     # noqa: E402
import seed_store                         # noqa: E402

DB_PATH = _HERE.parents[1] / "memory" / "database.json"

_STOP = {"the", "a", "an", "of", "and", "for", "to", "in", "on"}


def _force_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _tokens(niche: str) -> set[str]:
    """Lowercased word tokens, parens/punct stripped — 'Gaming (MOBA)' -> {gaming, moba}."""
    words = re.split(r"[^a-z0-9]+", niche.lower())
    return {w for w in words if w and w not in _STOP}


def _load_db(db: str | os.PathLike | None) -> list[dict]:
    p = Path(db) if db else DB_PATH
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _match_reference(niche: str, db: list[dict]) -> tuple[dict | None, str, float]:
    """Return (record, quality, score). quality in {exact, near, none}.

    exact = case-insensitive equality of product_niche; among ties the latest
    created_at wins. near = highest Jaccard token overlap (> 0). none otherwise.
    """
    if not db:
        return None, "none", 0.0
    want = niche.strip().lower()
    exact = [r for r in db if str(r.get("product_niche", "")).strip().lower() == want]
    if exact:
        exact.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return exact[0], "exact", 1.0

    want_tok = _tokens(niche)
    best, best_score = None, 0.0
    for r in db:
        rt = _tokens(str(r.get("product_niche", "")))
        if not (want_tok and rt):
            continue
        score = len(want_tok & rt) / len(want_tok | rt)
        # tie-break on recency so a fresher near-match wins over an older equal one
        if score > best_score or (
            score == best_score and best is not None
            and str(r.get("created_at", "")) > str(best.get("created_at", ""))
        ):
            best, best_score = r, score
    if best is not None and best_score > 0:
        return best, "near", round(best_score, 2)
    return None, "none", 0.0


def _library_key_for(niche: str, lib_path: Path | None = None) -> str | None:
    """Map a brief's product_niche to a key in the anchor library.

    Exact key first; else the library key with the highest token overlap. Lets a
    brief niche ('Gaming (MOBA)') line up with a library key even if not identical.
    """
    lib = anchor_library._load(anchor_library.resolve_lib_path(lib_path))
    keys = [k for k in lib if not k.startswith("_")]
    if niche in keys:
        return niche
    low = {k.lower(): k for k in keys}
    if niche.lower() in low:
        return low[niche.lower()]
    want = _tokens(niche)
    best, best_score = None, 0.0
    for k in keys:
        kt = _tokens(k)
        if not (want and kt):
            continue
        score = len(want & kt) / len(want | kt)
        if score > best_score:
            best, best_score = k, score
    return best if best_score > 0 else None


def _new_recommendation_id(product_niche: str, project_name: str, ts: str) -> str:
    h = hashlib.sha1(f"{product_niche}|{project_name}|{ts}".encode("utf-8")).hexdigest()[:6]
    return f"rec_{ts}_{h}"


def recommend(product_niche: str, project_name: str = "", *, db=None,
              lib_path=None, top_n: int = 3, bus: EventBus | None = None,
              persist: bool = False, seeds_dir=None) -> dict:
    bus = bus or EventBus()
    pid = project_name or product_niche
    bus.emit("BRIEF_RECEIVED", pid, {"product_niche": product_niche})

    records = _load_db(db)
    ref, quality, score = _match_reference(product_niche, records)
    bus.emit("REFERENCE_MATCHED", pid, {
        "match_quality": quality, "score": score,
        "reference_project": ref.get("project_name") if ref else None,
        "reference_niche": ref.get("product_niche") if ref else None,
    })

    lib_key = _library_key_for(product_niche, lib_path)
    hooks = anchor_library.suggest_hooks(lib_key, top_n,
                                         path=lib_path) if lib_key else []
    bus.emit("HOOKS_RECOMMENDED", pid, {
        "library_niche": lib_key, "count": len(hooks),
        "phrases": [h["phrase"] for h in hooks],
    })

    notes: list[str] = []
    if quality == "none":
        notes.append("No prior project in this niche — start fresh (cold start).")
    elif quality == "near":
        notes.append(
            f"No exact-niche reference; reusing nearest niche "
            f"'{ref.get('product_niche')}' (overlap {score}). Adapt, don't copy.")
    if lib_key and lib_key != product_niche:
        notes.append(f"Hooks drawn from anchor library niche '{lib_key}'.")
    if not hooks:
        notes.append("No hook anchors known for this niche yet.")

    rec_ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seed = {
        # --- identity (links seed -> provenance later) ---
        "recommendation_id": _new_recommendation_id(product_niche, project_name, rec_ts),
        "recommendation_timestamp": _dt.datetime.now(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"),
        "product_niche": product_niche,
        "project_name": project_name,
        "match_quality": quality,
        "match_score": score,
        "reference_project": ref.get("project_name") if ref else None,
        # forward intelligence the downstream skills consume:
        "suggested_hooks_next_time": hooks,                       # -> Storytelling
        "hook_successful_prior": ref.get("hook_successful") if ref else None,  # -> Storytelling
        "retention_benchmark": ref.get("retention_score") if ref else None,    # -> Retention Expert
        "retention_signals": ref.get("retention_signals") if ref else None,    # -> Retention Expert
        "highlight_patterns": ref.get("highlight_anchors", []) if ref else [],  # -> Timeline / cold-open
        "editing_specs_to_reuse": ref.get("editing_specs") if ref else None,   # -> Video Editor
        "render_specs_to_reuse": ref.get("render_specs") if ref else None,     # -> Video Editor
        "lesson_learned_prior": ref.get("lesson_learned") if ref else None,    # -> all skills (avoid past misses)
        "notes": notes,
    }
    if persist:
        seed_path = seed_store.persist_seed(seed, seeds_dir=seeds_dir)
        seed["_persisted_to"] = str(seed_path)
    bus.emit("CREATIVE_SEED_READY", pid, {
        "recommendation_id": seed["recommendation_id"],
        "match_quality": quality,
        "hooks": [h["phrase"] for h in hooks],
        "has_retention_signals": seed["retention_signals"] is not None,
        "highlight_pattern_count": len(seed["highlight_patterns"]),
        "persisted": bool(persist),
    })
    return seed


# ---------------------------------------------------------------------------
# Provenance Layer — turn a forward-loop seed + the decisions actually taken
# into the optional `provenance` block stamped onto the memory record (STEP 15).
# Answers, per record: "this result came from WHICH recommendation."
# ---------------------------------------------------------------------------
def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "project"


def make_loop_run_id(created_at: str, project_name: str) -> str:
    """Stable join key linking a forward seed, a record, and a telemetry row."""
    return f"{created_at}::{_slug(project_name)}"


def _norm_hook(h) -> str:
    return str(h).lower().strip().strip(".,!?;:")


def classify_hook_adoption(suggested: list, used) -> str:
    """How the storytelling step treated the recommended hooks."""
    sset = {_norm_hook(x) for x in (suggested or []) if str(x).strip()}
    if not sset:
        return "none_suggested"
    if used is None:
        return "unrecorded"
    uset = {_norm_hook(x) for x in used if str(x).strip()}
    if not uset:
        return "rejected"
    if uset <= sset:
        return "adopted"
    if uset & sset:
        return "partial"
    return "rejected"


def _seed_phrases(seed: dict) -> list[str]:
    out = []
    for h in (seed.get("suggested_hooks_next_time") or []):
        out.append(h.get("phrase") if isinstance(h, dict) else h)
    return [p for p in out if p]


def build_provenance(seed: dict | None, *, hooks_actually_used: list | None = None,
                     reused_editing_specs: bool | None = None,
                     storytelling_decision: str | None = None,
                     created_at: str | None = None, project_name: str | None = None,
                     loop_run_id: str | None = None) -> dict:
    """Map a creative_seed (recommendation_service output) + actual decisions ->
    the optional provenance/v3 block. Pure; writes nothing. Handles exact / near /
    cold_start uniformly (a missing seed => cold_start with everything null)."""
    seed = seed or {}
    raw_q = seed.get("match_quality", "none")
    match_quality = "cold_start" if raw_q in (None, "none", "") else raw_q
    suggested = _seed_phrases(seed)
    if loop_run_id is None and created_at and project_name:
        loop_run_id = make_loop_run_id(created_at, project_name)

    return {
        "schema": "provenance/v3",
        "loop_run_id": loop_run_id,
        "recommended": {
            "recommendation_id": seed.get("recommendation_id"),
            "recommendation_timestamp": seed.get("recommendation_timestamp"),
            "reference_project": None if match_quality == "cold_start" else seed.get("reference_project"),
            "match_quality": match_quality,
            "match_score": seed.get("match_score"),
            "suggested_hooks": suggested,
            "retention_benchmark": seed.get("retention_benchmark"),
            "reused_editing_specs_source": seed.get("editing_specs_to_reuse"),
        },
        "decided": {
            "hooks_actually_used": hooks_actually_used,
            "hook_adoption": classify_hook_adoption(suggested, hooks_actually_used),
            "reused_editing_specs": reused_editing_specs,
            "storytelling_decision": storytelling_decision,
        },
        "linkage": {
            "recommendation_available": bool(seed),
            "is_cold_start": match_quality == "cold_start",
        },
    }


def main() -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(description="Orchestrator Learning Bridge (forward loop)")
    ap.add_argument("--product-niche", required=True)
    ap.add_argument("--project-name", default="")
    ap.add_argument("--db", default=None)
    ap.add_argument("--lib-path", default=None,
                    help="anchor library path (else $SCOS_ANCHOR_LIB or default)")
    ap.add_argument("--top-n", type=int, default=3)
    ap.add_argument("--seeds-dir", default=None,
                    help="seed store dir (else $SCOS_SEEDS_DIR or work/seeds)")
    ap.add_argument("--no-persist", action="store_true",
                    help="do not write the seed to the seed store (debug only)")
    a = ap.parse_args()
    seed = recommend(a.product_niche, a.project_name, db=a.db, lib_path=a.lib_path,
                     top_n=a.top_n, persist=not a.no_persist, seeds_dir=a.seeds_dir)
    print("\n=== CREATIVE SEED (forward intelligence) ===")
    print(json.dumps(seed, ensure_ascii=False, indent=2))
    if seed.get("_persisted_to"):
        print(f"\n[seed persisted] {seed['_persisted_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
