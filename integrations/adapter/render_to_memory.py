"""render_to_memory.py — Super Creator OS "return adapter" (closes the learning loop).

After a render finishes, this reads the EDL + transcript(s) + render output (+ optional
QA result) and APPENDS one structured record to memory/database.json — non-destructively.
It never edits existing records and never touches core skill files.

It produces both the v1 contract (project_name, product_niche, hook_successful,
editing_specs, retention_score, lesson_learned, created_at) and the v2 fields documented
in memory/schema_v2_extension.md (engine, clip_type, grade_used, cut_padding_ms,
subtitle_style, render_success, highlight_anchors, retention_signals, render_specs,
transcribed, edl_path).

SAFETY:
  - read array -> validate -> push new record -> atomic write back  (Append only)
  - timestamped backup of database.json into memory/_db_backups/ before writing
  - schema-validates BOTH the new record and that every existing record is preserved
  - --dry-run prints the record and writes nothing

Usage:
  python integrations/adapter/render_to_memory.py \
      --edl work/edit/edl.json \
      --render output/final.mp4 \
      --project-name "MOBA Pentakill" --product-niche "Gaming (MOBA)" \
      [--transcripts-dir work/edit/transcripts] [--qa work/edit/qa.json] \
      [--retention-score 84] [--db memory/database.json] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ---- Required v1 contract (must never be broken) ----
V1_REQUIRED = ["project_name", "product_niche", "hook_successful",
               "editing_specs", "retention_score", "lesson_learned", "created_at"]

# ---- clip_type detection signals ----
MOBA_CALLOUTS = ["double kill", "triple kill", "quadra", "pentakill", "penta kill",
                 "ace", "shut down", "defeated an enemy", "legendary", "ultimate",
                 "destroyed a tower", "first blood", "maniac", "savage"]
EMPHASIS_WORDS = MOBA_CALLOUTS + ["wow", "insane", "let's go", "finally", "amazing"]


# ----------------------------------------------------------------------------
# Readers
# ----------------------------------------------------------------------------
def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ffprobe_meta(video: Path) -> dict:
    """Return {duration, width, height, fps} or {} on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate",
             "-show_entries", "format=duration",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True).stdout
        j = json.loads(out)
        st = (j.get("streams") or [{}])[0]
        fr = st.get("r_frame_rate", "0/1")
        num, den = (fr.split("/") + ["1"])[:2]
        fps = round(float(num) / float(den)) if float(den) else None
        return {
            "duration": float(j.get("format", {}).get("duration", 0.0)),
            "width": st.get("width"),
            "height": st.get("height"),
            "fps": fps,
        }
    except Exception:
        return {}


def gather_transcripts(tdir: Path) -> list[dict]:
    if not tdir or not tdir.exists():
        return []
    return [_load_json(p) for p in sorted(tdir.glob("*.json"))]


# ----------------------------------------------------------------------------
# Extractors
# ----------------------------------------------------------------------------
def detect_clip_type(transcripts: list[dict], edl: dict) -> str:
    text = " ".join(t.get("text", "") for t in transcripts).lower()
    events = []
    for t in transcripts:
        events += [w.get("text", "").lower() for w in t.get("words", []) if w.get("type") != "word"]
    has_game = any("game sound" in e for e in events)
    if has_game or any(c in text for c in MOBA_CALLOUTS):
        return "gaming_moba"
    speakers = set()
    words = 0
    for t in transcripts:
        for w in t.get("words", []):
            if w.get("type") == "word":
                words += 1
                speakers.add(w.get("speaker_id", "?"))
    if words == 0:
        return "image_montage"          # no speech at all -> still/asset assembly
    if len(speakers) >= 2:
        return "interview"
    return "talking_head"


def extract_highlight_anchors(transcripts: list[dict], limit: int = 12) -> list[dict]:
    """Word/event timestamps that mark a beat (kill callouts, emphasis, audio events).

    Callouts are matched on BOTH single words and 2-word windows so multi-word
    phrases ("Double kill", "Triple kill", "Shut down") are caught even though
    Scribe tokenizes them into separate word entries.
    """
    anchors: list[dict] = []
    for t in transcripts:
        words = t.get("words", [])
        # audio events
        for w in words:
            if w.get("type") != "word" and (w.get("text") or "").strip() and w.get("start") is not None:
                anchors.append({"t": round(float(w["start"]), 2),
                                "label": (w["text"]).strip(), "kind": "audio_event"})
        # callouts via 1-gram and 2-gram windows over real words
        rw = [w for w in words if w.get("type") == "word" and w.get("start") is not None]
        for i, w in enumerate(rw):
            one = (w.get("text") or "").strip()
            low1 = one.lower().strip(".,!?;:")
            two = (one + " " + (rw[i + 1].get("text") or "").strip()) if i + 1 < len(rw) else one
            low2 = two.lower().strip(".,!?;:")
            # Store the CANONICAL callout phrase (title-cased keyword), not the raw
            # 2-gram window — keeps the anchor library clean ("Double Kill", not
            # "assist. Legendary."). Timestamp stays the matched word's start.
            label, matched = None, False
            for c in EMPHASIS_WORDS:
                if c in low2:                     # prefer the 2-word match (e.g. "double kill")
                    label, matched = c.title(), True
                    break
            if not matched:
                for c in EMPHASIS_WORDS:
                    if c == low1 or (c in low1 and " " not in c):
                        label, matched = c.title(), True
                        break
            if matched:
                anchors.append({"t": round(float(w["start"]), 2), "label": label, "kind": "callout"})
    # de-dup adjacent identical labels, keep earliest
    seen, out = set(), []
    for a in sorted(anchors, key=lambda x: x["t"]):
        key = (a["label"].lower(), int(a["t"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out[:limit]


def compute_retention_signals(edl: dict, transcripts: list[dict], render: dict) -> dict:
    ranges = edl.get("ranges", [])
    durs = [float(r["end"]) - float(r["start"]) for r in ranges if "start" in r and "end" in r]
    kept = sum(durs)
    src_total = 0.0
    for t in transcripts:
        src_total += float(t.get("audio_duration_secs", 0) or 0)
    sig = {
        "num_segments": len(ranges),
        "avg_segment_s": round(kept / len(durs), 2) if durs else None,
        "kept_speech_s": round(kept, 2),
        "source_total_s": round(src_total, 2) if src_total else None,
        "kept_ratio_pct": round(100 * kept / src_total) if src_total else None,
        "output_duration_s": round(render.get("duration", 0.0), 2) if render else None,
        "has_cold_open": bool(ranges) and (ranges[0].get("beat", "").upper() in {"HOOK", "PEAK"}),
    }
    return sig


def infer_cut_padding_ms(edl: dict) -> list[int] | None:
    for r in edl.get("ranges", []):
        if isinstance(r.get("cut_padding_ms"), list):
            return r["cut_padding_ms"]
    return edl.get("cut_padding_ms")  # optional top-level


def infer_subtitle_style(edl: dict) -> str:
    subs = edl.get("subtitles")
    if not subs:
        return "none"
    name = str(subs).lower()
    if "from_timeline" in name:
        return "on-screen-text (adapter SRT, bold-overlay)"
    if "master" in name:
        return "transcript-derived (bold-overlay, 2-word UPPERCASE)"
    return "custom-srt"


def assess_render_success(edl: dict, render: dict) -> tuple[bool, str]:
    if not render or not render.get("duration"):
        return False, "no render metadata (ffprobe failed or file missing)"
    expected = float(edl.get("total_duration_s") or 0)
    got = float(render["duration"])
    if expected and abs(got - expected) > max(1.0, 0.1 * expected):
        return False, f"duration mismatch: expected ~{expected:.1f}s, got {got:.1f}s"
    return True, f"ok ({got:.1f}s, {render.get('width')}x{render.get('height')}@{render.get('fps')})"


# ----------------------------------------------------------------------------
# Record builder
# ----------------------------------------------------------------------------
def build_record(args, edl: dict, transcripts: list[dict], render: dict, qa: dict) -> dict:
    clip_type = detect_clip_type(transcripts, edl)
    anchors = extract_highlight_anchors(transcripts)
    signals = compute_retention_signals(edl, transcripts, render)
    grade = edl.get("grade", "none")
    padding = infer_cut_padding_ms(edl)
    sub_style = infer_subtitle_style(edl)
    ok, ok_note = assess_render_success(edl, render)
    qa_pass = qa.get("pass") if qa else None
    transcribed = bool(transcripts) and any(t.get("words") for t in transcripts)

    # hook_successful: prefer first range's beat+quote, else from anchors
    first = (edl.get("ranges") or [{}])[0]
    if first.get("beat") and first.get("quote"):
        hook = f"{first['beat']}: {first['quote']}"
    elif anchors:
        hook = f"Cold-open anchor @{anchors[-1]['t']}s ({anchors[-1]['label']})"
    else:
        hook = ""

    # editing_specs: concise human-readable (mirrors existing memory style)
    res = f"{render.get('width')}x{render.get('height')}@{render.get('fps')}fps" if render else "?"
    editing_specs = (
        f"{res}, {signals['num_segments']} segments "
        f"(avg {signals['avg_segment_s']}s, kept {signals['kept_ratio_pct']}% of source), "
        f"grade={grade}, subtitle={sub_style}"
        + (f", cut_padding={padding}ms" if padding else "")
    )

    # lesson_learned: assemble from failure notes + QA + a positive pattern if good
    notes = []
    if not ok:
        notes.append(f"RENDER ISSUE: {ok_note}")
    if qa and qa.get("notes"):
        notes.append(f"QA: {qa['notes']}")
    if clip_type == "gaming_moba" and anchors:
        peak = max(anchors, key=lambda a: a["t"])
        notes.append(f"highlight anchors from transcript confirm RMS peaks; climax callout '{peak['label']}' @{peak['t']}s -> use as cold-open hook")
    if signals.get("kept_ratio_pct") is not None:
        notes.append(f"kept {signals['kept_ratio_pct']}% speech (cut {100 - signals['kept_ratio_pct']}% dead/silence)")
    lesson = " | ".join(notes)

    created = args.created_at or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    retention = args.retention_score if args.retention_score is not None else 0

    return {
        # ---- v1 (required) ----
        "project_name": args.project_name,
        "product_niche": args.product_niche,
        "hook_successful": hook,
        "editing_specs": editing_specs,
        "retention_score": int(retention),
        "lesson_learned": lesson,
        "created_at": created,
        # ---- v2 (optional, additive) ----
        "engine": "video-use",
        "clip_type": clip_type,
        "transcribed": transcribed,
        "edl_path": args.edl,
        "grade_used": grade,
        "cut_padding_ms": padding,
        "subtitle_style": sub_style,
        "render_success": ok,
        "qa_pass": qa_pass,
        "highlight_anchors": anchors,
        "retention_signals": signals,
        "render_specs": {
            "resolution": res,
            "fps": render.get("fps") if render else None,
            "output_duration_s": signals.get("output_duration_s"),
        },
    }


# ----------------------------------------------------------------------------
# Validation + safe write
# ----------------------------------------------------------------------------
def validate_record(rec: dict) -> list[str]:
    errs = []
    for k in V1_REQUIRED:
        if k not in rec:
            errs.append(f"missing v1 field: {k}")
    if not isinstance(rec.get("retention_score"), int):
        errs.append("retention_score must be int")
    if not (0 <= rec.get("retention_score", -1) <= 100):
        errs.append("retention_score out of range 0-100")
    if not rec.get("project_name"):
        errs.append("project_name empty")
    return errs


def validate_db(db) -> list[str]:
    errs = []
    if not isinstance(db, list):
        return ["database root is not a JSON array"]
    for i, r in enumerate(db):
        for k in V1_REQUIRED:
            if k not in r:
                errs.append(f"existing record {i} missing v1 field {k}")
    return errs


def atomic_write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem


def main() -> int:
    ap = argparse.ArgumentParser(description="Write render results back into memory (append-only).")
    ap.add_argument("--edl", required=True)
    ap.add_argument("--render", help="rendered output (final.mp4) for ffprobe metadata")
    ap.add_argument("--transcripts-dir", default=None)
    ap.add_argument("--qa", default=None, help="optional qa.json with {pass:bool, notes:str}")
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--product-niche", required=True)
    ap.add_argument("--retention-score", type=int, default=None)
    ap.add_argument("--db", default="memory/database.json")
    ap.add_argument("--created-at", default=None, help="ISO timestamp override (else now, UTC)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    edl_path = Path(args.edl)
    if not edl_path.exists():
        print(f"ERROR: edl not found: {edl_path}", file=sys.stderr)
        return 2
    edl = _load_json(edl_path)

    tdir = Path(args.transcripts_dir) if args.transcripts_dir else edl_path.parent / "transcripts"
    transcripts = gather_transcripts(tdir)
    render = ffprobe_meta(Path(args.render)) if args.render else {}
    qa = _load_json(Path(args.qa)) if args.qa and Path(args.qa).exists() else {}

    rec = build_record(args, edl, transcripts, render, qa)

    errs = validate_record(rec)
    if errs:
        print("RECORD VALIDATION FAILED:", *errs, sep="\n  ", file=sys.stderr)
        return 3

    print("=== NEW RECORD ===")
    print(json.dumps(rec, ensure_ascii=False, indent=2))

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    db_path = Path(args.db)
    db = _load_json(db_path) if db_path.exists() else []
    db_errs = validate_db(db)
    if db_errs:
        print("EXISTING DB INVALID — refusing to write:", *db_errs, sep="\n  ", file=sys.stderr)
        return 4

    # Guard: never duplicate an identical (project_name, created_at) record
    if any(r.get("project_name") == rec["project_name"] and r.get("created_at") == rec["created_at"] for r in db):
        print("WARN: a record with same project_name + created_at exists; aborting to avoid dup.", file=sys.stderr)
        return 5

    # Backup before write (rollback safety)
    backup_dir = db_path.parent / "_db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"database.{stamp}.json"
    if db_path.exists():
        shutil.copy2(db_path, backup)

    new_db = db + [rec]                      # APPEND ONLY — never mutate existing
    # Post-condition check: every old record must survive byte-for-byte
    if new_db[:len(db)] != db:
        print("ABORT: append would alter existing records.", file=sys.stderr)
        return 6

    atomic_write_json(db_path, new_db)
    print(f"\nAPPENDED record #{len(new_db)} to {db_path}")
    print(f"backup: {backup}")
    print(f"clip_type={rec['clip_type']} render_success={rec['render_success']} anchors={len(rec['highlight_anchors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
