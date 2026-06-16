"""archive_manager.py — snapshot a finished project's metadata for audit/replay.

Copies the decision artifacts (edl, packed transcript, qa result, a pointer to the
render) into integrations/learning/archive/<project_id>/ plus a manifest.json.
Never deletes or mutates source files; archive is write-once per project_id.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
from pathlib import Path

ARCHIVE_ROOT = Path(__file__).resolve().parent / "archive"
ENV_ARCHIVE = "SCOS_ARCHIVE"  # redirect the archive root (test/staging isolation)


def resolve_archive_root(explicit: str | os.PathLike | None = None) -> Path:
    """explicit arg > $SCOS_ARCHIVE > default archive/."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_ARCHIVE)
    return Path(env) if env else ARCHIVE_ROOT


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9ก-๙_-]+", "_", name).strip("_")
    return s[:80] or "project"


def archive_project(project_id: str, artifacts: dict, record: dict | None = None,
                    archive_root: str | os.PathLike | None = None) -> tuple[bool, str]:
    """artifacts: {edl: path, packed: path, qa: path, render: path}. All optional."""
    root = resolve_archive_root(archive_root)
    pid = slugify(project_id)
    dest = root / pid
    if dest.exists():
        # write-once: don't clobber an existing archive; version it
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = root / f"{pid}__{stamp}"
    dest.mkdir(parents=True, exist_ok=True)

    copied = {}
    for key, p in (artifacts or {}).items():
        if not p:
            continue
        src = Path(p)
        if src.exists() and src.is_file():
            target = dest / f"{key}{src.suffix}"
            shutil.copy2(src, target)
            copied[key] = target.name
        else:
            copied[key] = f"(missing: {p})"

    manifest = {
        "project_id": project_id,
        "archived_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifacts": copied,
        "record_summary": {
            k: record.get(k) for k in ("product_niche", "clip_type", "retention_score",
                                       "render_success", "grade_used")
        } if record else {},
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return True, str(dest)
