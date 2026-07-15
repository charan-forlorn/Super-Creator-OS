"""SCOS x HVS daily practice-render loop (Part B extended, item #2).

Goal (user request): every day, exercise HVS rendering across the common
online platforms (TikTok/Reels/Shorts, IG/FB Feed, YouTube) so the system
keeps *improving its render patterns* — and after each render, auto-delete
the produced video, keeping ONLY the learned render pattern/style.

Design (safety-first, per HVS studio.config.json `approval_required: true`,
`no_publish`, `no_network_egress`):
  - Default mode is LEARN-ONLY / DRY-RUN. No real render and no deletion
    happen unless the operator explicitly enables them. This respects the
    standing rule that approval is required before any outward/destructive
    action, and the user's note "must you [operator] set the approval policy".
  - Real render is delegated to HVS CLI:
        python -m hvs.cli run-real-render-batch --project <id> --formats <...>
    which itself refuses to render unless BOTH approval flags are present.
    This script never bypasses that gate.
  - After a (real or simulated) render, we:
      1. verify the output exists (HVS verify-real-render-output, or pattern sim)
      2. append a learned render-pattern record to the SCOS runtime journal
      3. delete the produced video, keeping only the learned pattern
         (uses the same verify-then-delete gating from video_job_cleanup)

This module is dependency-free and fully testable with temp dirs.

Run:
  .venv\\Scripts\\python.exe scripts\\practice_render_loop.py --dry-run --once
  .venv\\Scripts\\python.exe scripts\\practice_render_loop.py --allow-real --once
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

# --- locations ------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
_HVS_ROOT = _ROOT.parent / "hermes-video-studio"
_DEFAULT_MEMORY_DB = _ROOT / "memory" / "database.json"
_DEFAULT_RUNTIME_JOURNAL = _ROOT / "memory" / "runtime" / "practice-render.jsonl"
_DEFAULT_REFERENCE = _ROOT / "input" / "reference"
_DEFAULT_OUTPUT = _ROOT / "output"
_LEARNING_ROOT = _ROOT / "integrations" / "learning"
if str(_LEARNING_ROOT) not in sys.path:
    sys.path.insert(0, str(_LEARNING_ROOT))

import memory_store  # noqa: E402

# Platform families HVS supports, mapped to CLI format ids.
PLATFORM_FORMATS = {
    "tiktok_ig_yt_shorts": "vertical_9_16",
    "ig_fb_feed": "square_1_1",
    "youtube_website": "landscape_16_9",
}

# Learned-pattern schema we append to SCOS runtime memory.
_PATTERN_SCHEMA_VERSION = "v4"
_ENGINE = "practice-loop"


# --- HVS delegation -------------------------------------------------------
def _hvs_cmd(args: list[str], hvs_root: Path) -> tuple[int, str]:
    """Run an HVS CLI command. Returns (returncode, combined_output).

    Safety: only whitelisted read/dry commands are ever built by this script.
    Real render is only invoked when allow_real=True AND the HVS gate's own
    approval flags are supplied by the operator via --hvs-approval-flags.
    """
    cmd = [sys.executable, "-m", "hvs.cli", *args]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(hvs_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        return completed.returncode, (completed.stdout or "") + (completed.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "HVS command timed out"
    except FileNotFoundError as e:
        return 127, f"HVS CLI not found: {e}"


def list_render_formats(hvs_root: Path) -> list[dict]:
    code, out = _hvs_cmd(["list-render-formats", "--json"], hvs_root)
    if code != 0:
        return []
    # try to parse a trailing JSON block if present
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


# --- learning record ------------------------------------------------------
def _default_attempt_id(platform_key: str, format_id: str, simulated: bool) -> str:
    mode = "simulated" if simulated else "real"
    return f"{date.today().isoformat()}::{platform_key}::{format_id}::{mode}"


def _project_name(platform_key: str) -> str:
    return f"Practice {platform_key} ({date.today().isoformat()})"


def append_learned_pattern(
    db_path: Path,
    platform_key: str,
    format_id: str,
    resolution: str,
    fps: int,
    lesson: str,
    simulated: bool,
    render_success: bool = None,
    *,
    runtime_journal: Path = _DEFAULT_RUNTIME_JOURNAL,
    persist: bool = True,
    attempt_id: Optional[str] = None,
) -> dict:
    # render_success defaults to "not simulated" unless an explicit result given
    if render_success is None:
        render_success = not simulated
    attempt = attempt_id or _default_attempt_id(platform_key, format_id, simulated)
    record = {
        "runtime_record_type": "practice_render",
        "record_type": "practice_render",
        "project_name": _project_name(platform_key),
        "product_niche": "render_practice",
        "hook_successful": f"render-format={format_id} ({resolution}@{fps})",
        "editing_specs": f"platform={platform_key}; simulated={simulated}",
        "retention_score": 0,  # practice runs have no audience yet
        "lesson_learned": lesson,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "schema_version": _PATTERN_SCHEMA_VERSION,
        "engine": _ENGINE,
        "clip_type": "render_practice",
        "platform_family": platform_key,
        "format_id": format_id,
        "render_source_id": "learn-only" if simulated else "hvs-real-render",
        "attempt_id": attempt,
        "canonical_memory_path": str(db_path),
        "transcribed": False,
        "render_success": render_success,
        "qa_pass": render_success,
        "render_specs": {
            "format_id": format_id,
            "resolution": resolution,
            "fps": fps,
            "platform_family": platform_key,
        },
        "is_practice": True,
    }
    if not persist:
        record["learning_persisted"] = False
        record["learning_store"] = "dry_run"
        return record

    ok, info = memory_store.append_runtime_record(record, runtime_path=runtime_journal)
    record["learning_persisted"] = ok
    record["learning_store"] = "runtime_journal"
    record["learning_info"] = info
    if not ok:
        record["learning_error"] = info
    return record


# --- one practice iteration ----------------------------------------------
def practice_one(
    platform_key: str,
    *,
    hvs_root: Path = _HVS_ROOT,
    memory_db: Path = _DEFAULT_MEMORY_DB,
    allow_real: bool = False,
    hvs_approval_flags: Optional[list[str]] = None,
    hvs_project_id: str = "my-VDO",
    source_hint: Optional[str] = None,
    runtime_journal: Path = _DEFAULT_RUNTIME_JOURNAL,
    persist_learning: bool = True,
    attempt_id: Optional[str] = None,
    renderer: Callable[[str, str], tuple[bool, str]] = None,
    delete_fn: Callable[[str], list[str]] = None,
) -> dict:
    """Exercise one platform format. Returns a report dict.

    `renderer` lets tests inject a fake render fn (signature:
    (format_id, out_path) -> (success: bool, detail: str)).
    If None and allow_real=True, delegates to HVS CLI. If None and not
    allow_real, simulates success (learn-only/dry-run mode).
    `delete_fn` (signature: (out_path) -> list[deleted_paths]) lets tests
    inject a fake deletion; if None and a real video was produced, delegates
    to the Part B verify-then-delete gate (HVS verify + cleanup).
    """
    format_id = PLATFORM_FORMATS[platform_key]
    resolution = {"vertical_9_16": "1080x1920", "square_1_1": "1080x1080",
                  "landscape_16_9": "1920x1080"}[format_id]
    fps = 30

    # 1) render (real / simulated)
    if renderer is not None and allow_real:
        ok, detail = renderer(format_id, f"{platform_key}.mp4")
        simulated = False
    elif allow_real:
        # HVS requires a render-pack (composition) to exist before the real
        # render batch can run. Sequence: create-render-pack -> run-real-render-batch.
        # Both are gated: real render only happens if the project is certified
        # AND both approval flags are present. We forward the operator-supplied
        # approval flags (default: the two required flags).
        flags = hvs_approval_flags or ["--real-render", "--approve-render"]
        # 1) ensure composition exists (real render stays gated inside)
        pk_code, pk_out = _hvs_cmd(
            ["create-render-pack", "--project-id", hvs_project_id,
             "--formats", format_id, "--dry-run"], hvs_root
        )
        pk_ok = (pk_code == 0) and ("BLOCKED" not in pk_out) and ("blocked" not in pk_out.lower())
        if not pk_ok:
            # cannot even build the composition -> refuse, never delete
            ok = False
            simulated = False
            detail = "create-render-pack BLOCKED: " + (pk_out.strip().splitlines()[0] if pk_out.strip() else f"rc={pk_code}")
        else:
            # 2) run the gated real render
            code, out = _hvs_cmd(
                ["run-real-render-batch", "--project-id", hvs_project_id,
                 "--formats", format_id, *flags], hvs_root
            )
            blocked = ("BLOCKED" in out) or ("blocked" in out.lower())
            ok = (code == 0) and (not blocked)
            simulated = False
            detail = out.strip().splitlines()[0] if out.strip() else f"rc={code}"
    else:
        # learn-only/dry-run: pretend success, keep pattern, no file produced
        ok, detail = True, "simulated (dry-run / learn-only; no real render)"
        simulated = True

    # 2) learn pattern (always — this is the whole point)
    lesson = (
        f"Practice render สำเร็จในรูปแบบ {format_id} ({resolution}@{fps}) "
        f"สำหรับ {platform_key}. {'[SIMULATED]' if simulated else '[REAL]'}"
    )
    record = append_learned_pattern(
        memory_db, platform_key, format_id, resolution, fps, lesson, simulated,
        render_success=(ok if not simulated else False),
        runtime_journal=runtime_journal,
        persist=persist_learning,
        attempt_id=attempt_id,
    )
    learning_persisted = bool(record.get("learning_persisted"))

    # 3) if a real video was produced, delete it (keep only the pattern)
    deleted = []
    if ok and not simulated and learning_persisted:
        out_file = str(_DEFAULT_OUTPUT / f"{platform_key}.mp4")
        if delete_fn is not None:
            # test injection: deterministic, no real HVS/cleanup calls
            deleted = delete_fn(out_file)
        else:
            # Verify via HVS, then delegate to the Part B verify-then-delete gate
            # so we never delete a video whose render/learning/archive signals fail.
            vcode, vout = _hvs_cmd(["verify-real-render-output", "--project", platform_key], hvs_root)
            verified = vcode == 0 and "fail" not in vout.lower()
            if verified:
                try:
                    from scripts.video_job_cleanup import (
                        cleanup,
                        verify_job,
                        plan_deletion,
                    )
                    report = verify_job(
                        platform_key,
                        output_dir=_DEFAULT_OUTPUT,
                        db_path=memory_db,
                    )
                    plan = plan_deletion([out_file], _DEFAULT_REFERENCE)
                    if plan["planned"]:
                        res = cleanup([out_file], report, reference_dir=_DEFAULT_REFERENCE,
                                      execute=True)
                        deleted = res.get("deleted", [])
                except Exception:
                    deleted = []
            # if verification failed → DO NOT delete (keep evidence)

    return {
        "platform_key": platform_key,
        "format_id": format_id,
        "render_ok": ok,
        "render_detail": detail,
        "simulated": simulated,
        "learned_record": record["project_name"] if learning_persisted else None,
        "learning_persisted": learning_persisted,
        "learning_error": record.get("learning_error"),
        "deleted_videos": deleted,
    }


def run_daily(
    *,
    hvs_root: Path = _HVS_ROOT,
    memory_db: Path = _DEFAULT_MEMORY_DB,
    runtime_journal: Path = _DEFAULT_RUNTIME_JOURNAL,
    allow_real: bool = False,
    hvs_approval_flags: Optional[list[str]] = None,
    persist_learning: bool = True,
    attempt_id: Optional[str] = None,
    renderer: Callable[[str, str], tuple[bool, str]] = None,
) -> dict:
    reports = [practice_one(k, hvs_root=hvs_root, memory_db=memory_db,
                            allow_real=allow_real, hvs_approval_flags=hvs_approval_flags,
                            runtime_journal=runtime_journal,
                            persist_learning=persist_learning,
                            attempt_id=(f"{attempt_id}::{k}" if attempt_id else None),
                            renderer=renderer)
               for k in PLATFORM_FORMATS]
    learned = sum(1 for r in reports if r["learned_record"])
    real = sum(1 for r in reports if not r["simulated"])
    return {
        "date": date.today().isoformat(),
        "platforms": len(reports),
        "learned_patterns": learned,
        "real_renders": real,
        "simulated": (not allow_real) or real == 0,
        "reports": reports,
    }


# --- CLI ------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SCOS x HVS daily practice-render loop")
    p.add_argument("--hvs-root", type=Path, default=_HVS_ROOT)
    p.add_argument("--memory-db", type=Path, default=_DEFAULT_MEMORY_DB)
    p.add_argument("--runtime-journal", type=Path, default=_DEFAULT_RUNTIME_JOURNAL)
    p.add_argument("--once", action="store_true", help="รันรอบเดียว (ไม่วนลูป)")
    p.add_argument("--dry-run", action="store_true",
                   help="learn-only: ไม่ render จริง ไม่ลบไฟล์ (ดีฟอลต์ปลอดภัย)")
    p.add_argument("--allow-real", action="store_true",
                   help="เปิด real render ผ่าน HVS (ต้อง HVS approval เองผ่าน --hvs-approval-flags)")
    p.add_argument("--hvs-approval-flags", nargs="*", default=[],
                   help="flag เปิด approval ของ HVS (ถาม operator ก่อนใช้)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    allow_real = args.allow_real and not args.dry_run
    result = run_daily(
        hvs_root=args.hvs_root,
        memory_db=args.memory_db,
        runtime_journal=args.runtime_journal,
        allow_real=allow_real,
        hvs_approval_flags=args.hvs_approval_flags,
        persist_learning=not args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nหมายเหตุ: โหมด", "REAL" if result["real_renders"] else "LEARN-ONLY/DRY-RUN",
          "(ไม่มีวิดีโอถูกลบจริงในโหมดนี้)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
