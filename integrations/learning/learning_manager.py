"""learning_manager.py — autonomous learning loop controller.

Replaces the manual human trigger between QA and memory. Given a finished project
(EDL + transcripts + render + QA), it:

  1. emits PROJECT_RENDERED
  2. checks QA status
     - FAIL -> emit PROJECT_QA_FAILED, log failure note, write NOTHING to memory
     - PASS -> emit PROJECT_QA_PASSED, then:
         a. build the structured record (reuses render_to_memory.build_record)
         b. validate + safe_append to memory/database.json (backup, atomic, append-only)
            -> emit MEMORY_RECORD_CREATED
         c. archive project metadata
         d. update highlight_anchor_library (per niche) -> emit HIGHLIGHT_PATTERN_DISCOVERED
         e. emit PROJECT_COMPLETE
  3. return a summary dict to the Orchestrator

ADDITIVE: imports the adapter (read-only reuse), never edits it or any core file.
Run on Windows via vu-style invocation (UTF-8 forced here too).

CLI:
  python integrations/learning/learning_manager.py \
      --edl work/edit/edl.json --render work/edit/final.mp4 \
      --transcripts-dir work/edit/transcripts \
      --project-name "<name>" --product-niche "<niche>" \
      --qa-pass true --retention-score 84 [--db ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# --- make sibling + adapter modules importable regardless of cwd ---
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))                       # learning/
sys.path.insert(0, str(_HERE.parent / "adapter"))    # adapter/

from event_bus import EventBus                       # noqa: E402
from memory_writer import safe_append                # noqa: E402
from archive_manager import archive_project          # noqa: E402
import anchor_library                                # noqa: E402
import render_to_memory as rtm                       # noqa: E402  (forward reuse)


def _force_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def process_project(edl_path, project_name, product_niche, *, render=None,
                    transcripts_dir=None, qa_pass=None, qa_notes="",
                    retention_score=None, db=None, created_at=None,
                    dry_run=False, bus: EventBus | None = None) -> dict:
    bus = bus or EventBus()
    edl_path = Path(edl_path)
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    tdir = Path(transcripts_dir) if transcripts_dir else edl_path.parent / "transcripts"
    transcripts = rtm.gather_transcripts(tdir)
    render_meta = rtm.ffprobe_meta(Path(render)) if render else {}

    pid = project_name
    bus.emit("PROJECT_RENDERED", pid, {"edl": str(edl_path), "render": render,
                                       "render_ok": bool(render_meta)})

    # ---- QA gate ----
    if qa_pass is False:
        bus.emit("PROJECT_QA_FAILED", pid, {"notes": qa_notes})
        return {"status": "qa_failed", "memory_written": False,
                "note": qa_notes or "QA failed — memory not written"}
    bus.emit("PROJECT_QA_PASSED", pid, {"notes": qa_notes})

    # ---- build structured record (reuse adapter logic) ----
    ns = SimpleNamespace(edl=str(edl_path), project_name=project_name,
                         product_niche=product_niche, retention_score=retention_score,
                         created_at=created_at)
    qa = {"pass": qa_pass, "notes": qa_notes} if qa_pass is not None else {}
    record = rtm.build_record(ns, edl, transcripts, render_meta, qa)

    if not record.get("render_success"):
        bus.emit("RENDER_FAILURE_DETECTED", pid,
                 {"editing_specs": record.get("editing_specs")})

    if dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return {"status": "dry_run", "memory_written": False, "record": record}

    # ---- safe append to memory ----
    ok, info = safe_append(record, db)
    if not ok:
        bus.emit("RENDER_FAILURE_DETECTED", pid, {"memory_write_error": info})
        return {"status": "memory_write_failed", "memory_written": False, "note": info}
    bus.emit("MEMORY_RECORD_CREATED", pid, {"info": info, "clip_type": record["clip_type"]})

    # ---- archive ----
    arch_ok, arch_dest = archive_project(pid, {
        "edl": str(edl_path),
        "packed": str(tdir.parent / "takes_packed.md"),
        "render": render,
    }, record)

    # ---- update highlight anchor library ----
    discovered: list[str] = []
    anc_ok, anc_info, discovered = anchor_library.record_project_anchors(
        product_niche, record.get("highlight_anchors", []),
        record["retention_score"], record["render_success"])
    if discovered:
        bus.emit("HIGHLIGHT_PATTERN_DISCOVERED", pid,
                 {"niche": product_niche, "new_phrases": discovered})

    bus.emit("PROJECT_COMPLETE", pid, {"memory": info, "archive": arch_dest,
                                       "anchors": anc_info})
    return {
        "status": "complete", "memory_written": True, "memory_info": info,
        "archive": arch_dest, "anchor_update": anc_info, "discovered": discovered,
        "clip_type": record["clip_type"], "render_success": record["render_success"],
        "suggested_hooks_next_time": anchor_library.suggest_hooks(product_niche),
    }


def _b(v):  # parse a tri-state bool flag
    if v is None:
        return None
    return str(v).strip().lower() in {"1", "true", "yes", "pass", "passed"}


def main() -> int:
    _force_utf8()
    ap = argparse.ArgumentParser(description="Autonomous learning loop controller")
    ap.add_argument("--edl", required=True)
    ap.add_argument("--render")
    ap.add_argument("--transcripts-dir")
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--product-niche", required=True)
    ap.add_argument("--qa-pass", default=None, help="true/false/pass/fail")
    ap.add_argument("--qa-notes", default="")
    ap.add_argument("--retention-score", type=int, default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--created-at", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    result = process_project(
        a.edl, a.project_name, a.product_niche, render=a.render,
        transcripts_dir=a.transcripts_dir, qa_pass=_b(a.qa_pass), qa_notes=a.qa_notes,
        retention_score=a.retention_score, db=a.db, created_at=a.created_at,
        dry_run=a.dry_run)
    print("\n=== LEARNING MANAGER RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"complete", "dry_run", "qa_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
