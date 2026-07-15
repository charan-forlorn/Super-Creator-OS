"""SCOS video-job end-of-job orchestrator (Part B) — verify-then-delete source.

Implements the standing-authorization protocol from CLAUDE.md: at the FINAL
step of an edit job, delete source media in `input/reference/` ONLY when all
three are confirmed true:

  1. Rendered output exists in `output/`.
  2. The learning record was appended to `memory/database.json`.
  3. The provenance/archive snapshot exists in
     `integrations/learning/archive/<project>/`.

SAFETY:
  - Dry-run by default. Nothing is deleted unless `--execute` is passed.
  - Deletion is scoped to explicit `--source` paths; each must live inside the
    reference dir and match a strict video-extension allowlist (plus optional
    explicitly-listed sidecars). No recursive, no globs across the tree.
  - If any precondition fails, deletion is refused and the blockers are listed.

This module does NOT render. Rendering is HVS's job. This only verifies the
three completion signals and (optionally) cleans up the source.

Run:
  .venv\\Scripts\\python.exe scripts\\video_job_cleanup.py verify \\
      --project "RoV Double Kill" --source "input/reference/IMG_9402.MOV"
  .venv\\Scripts\\python.exe scripts\\video_job_cleanup.py verify \\
      --project "RoV Double Kill" --source "input/reference/IMG_9402.MOV" --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# --- locations ------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = _ROOT / "input" / "reference"
DEFAULT_OUTPUT = _ROOT / "output"
DEFAULT_DB = _ROOT / "memory" / "database.json"
DEFAULT_ARCHIVE_ROOT = _ROOT / "integrations" / "learning" / "archive"

# Strict allowlist for source deletion (protocol: mp4/mov + job sidecars).
_VIDEO_EXTS = {".mp4", ".mov"}
_SIDECAR_EXTS = {".txt", ".rms.txt", ".json", ".log"}
_SLUG_SEP = (" ", "-", "_")


def _slug(text: str) -> str:
    # normalize whitespace + separators so "RoV Double Kill" matches
    # "rov_double_kill_final" / "RoV-Double-Kill" etc.
    norm = text.strip().lower()
    for sep in ("-", "_", "/"):
        norm = norm.replace(sep, " ")
    return " ".join(norm.split())


def _load_db(db_path: Path) -> list[dict]:
    if not db_path.is_file():
        return []
    try:
        data = json.loads(db_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


# --- precondition checks --------------------------------------------------
def render_output_exists(output_dir: Path, project: str, render_hint: Optional[str] = None) -> tuple[bool, str]:
    if render_hint:
        p = Path(render_hint)
        if not p.is_absolute():
            p = output_dir / p
        ok = p.is_file()
        return ok, str(p) if ok else f"ไม่พบไฟล์ render ที่ระบุ: {p}"
    # fallback: any file in output/ whose stem contains the project slug
    slug = _slug(project)
    if output_dir.is_dir():
        for f in output_dir.iterdir():
            if f.is_file() and slug and slug in _slug(f.stem):
                return True, str(f)
    return False, f"ไม่พบไฟล์ render ที่เข้ากับโปรเจกต์ใน {output_dir}"


def learning_record_exists(db_path: Path, project: str) -> tuple[bool, str]:
    slug = _slug(project)
    rows = _load_db(db_path)
    for r in rows:
        if isinstance(r, dict) and slug and slug in _slug(str(r.get("project_name", ""))):
            return True, f"พบ learning record: {r.get('project_name')}"
    return False, f"ไม่พบ learning record สำหรับ '{project}' ใน {db_path}"


def archive_exists(archive_root: Path, project: str) -> tuple[bool, str]:
    # match a subdir under archive_root whose slug contains the project slug
    slug = _slug(project)
    if not archive_root.is_dir():
        return False, f"ไม่พบ archive root: {archive_root}"
    for d in archive_root.iterdir():
        if d.is_dir() and slug and slug in _slug(d.name):
            files = [p for p in d.rglob("*") if p.is_file()]
            if files:
                return True, f"พบ archive: {d.name} ({len(files)} ไฟล์)"
            return False, f"archive {d.name} ว่างเปล่า"
    return False, f"ไม่พบโฟลเดอร์ archive ที่เข้ากับ '{project}'"


def verify_job(
    project: str,
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    db_path: Path = DEFAULT_DB,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    render_hint: Optional[str] = None,
) -> dict:
    checks = {
        "render": render_output_exists(output_dir, project, render_hint),
        "learning": learning_record_exists(db_path, project),
        "archive": archive_exists(archive_root, project),
    }
    report = {
        "project": project,
        "all_pass": all(ok for ok, _ in checks.values()),
        "checks": {k: {"ok": ok, "detail": detail} for k, (ok, detail) in checks.items()},
        "blockers": [detail for ok, detail in checks.values() if not ok],
    }
    return report


# --- scoped deletion ------------------------------------------------------
def _is_allowed_source(path: Path, reference_dir: Path, allow_sidecars: bool) -> tuple[bool, str]:
    try:
        path.resolve().relative_to(reference_dir.resolve())
    except ValueError:
        return False, f"ไม่อยู่ใน reference dir: {path}"
    ext = path.suffix.lower()
    if ext in _VIDEO_EXTS:
        return True, "video source"
    if allow_sidecars and ext in _SIDECAR_EXTS:
        return True, "sidecar"
    return False, f"นามสกุลไม่ได้รับอนุญาตให้ลบ: {ext}"


def plan_deletion(sources: list[str], reference_dir: Path = DEFAULT_REFERENCE, allow_sidecars: bool = False) -> dict:
    planned = []
    rejected = []
    for s in sources:
        p = Path(s)
        if not p.is_absolute():
            p = reference_dir / p
        if not p.exists():
            rejected.append((str(p), "ไฟล์ไม่มีอยู่จริง"))
            continue
        ok, why = _is_allowed_source(p, reference_dir, allow_sidecars)
        if ok:
            planned.append(str(p))
        else:
            rejected.append((str(p), why))
    return {"planned": planned, "rejected": rejected}


def cleanup(
    sources: list[str],
    report: dict,
    reference_dir: Path = DEFAULT_REFERENCE,
    execute: bool = False,
    allow_sidecars: bool = False,
) -> dict:
    if not report["all_pass"]:
        return {
            "executed": False,
            "deleted": [],
            "refused": True,
            "dry_run": not execute,
            "reason": "เงื่อนไขยังไม่ครบ: " + "; ".join(report["blockers"]),
        }
    plan = plan_deletion(sources, reference_dir, allow_sidecars)
    deleted = []
    for path_str in plan["planned"]:
        p = Path(path_str)
        if execute:
            p.unlink()
            deleted.append(path_str)
    return {
        "executed": execute,
        "deleted": deleted,
        "rejected": plan["rejected"],
        "planned_count": len(plan["planned"]),
        "dry_run": not execute,
    }


# --- CLI ------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SCOS video-job verify-then-delete orchestrator")
    p.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)

    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="ตรวจเงื่อนไขจบงาน + เตรียมลบ source")
    v.add_argument("--project", required=True)
    v.add_argument("--source", action="append", default=[], help="ไฟล์ source (ระบุซ้ำได้)")
    v.add_argument("--render", default=None, help="ระบุ path render ชัดเจน (เลือกได้)")
    v.add_argument("--allow-sidecars", action="store_true")
    v.add_argument("--execute", action="store_true", help="ลบจริง (ต้องทุกเงื่อนไขผ่าน)")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "verify":
        report = verify_job(
            args.project,
            output_dir=args.output,
            db_path=args.db,
            archive_root=args.archive_root,
            render_hint=args.render,
        )
        print(f"โปรเจกต์: {report['project']}")
        for name, c in report["checks"].items():
            print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {name}: {c['detail']}")
        if not report["all_pass"]:
            print("ผล: ยังไม่ครบเงื่อนไข → ไม่ลบ source")
            return 1
        plan = plan_deletion(args.source, args.reference, args.allow_sidecars)
        print(f"เงื่อนไขครบ ✓  จะลบ {len(plan['planned'])} ไฟล์" +
              (" (DRY-RUN)" if not args.execute else " (EXECUTE)"))
        for s in plan["planned"]:
            print(f"  - {s}")
        for s, why in plan["rejected"]:
            print(f"  x ปฏิเสธ: {s} → {why}")
        res = cleanup(args.source, report, args.reference, args.execute, args.allow_sidecars)
        if res.get("deleted"):
            print(f"ลบแล้ว {len(res['deleted'])} ไฟล์")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
