"""seed_store.py — inter-step seed buffer (closes the STEP 1.5 -> STEP 15 human gap).

STEP 1.5 (recommendation_service) writes the creative_seed here; STEP 15
(learning_manager) auto-resolves it by project name — so the operator no longer
passes --seed-json by hand. The seed's identity fields (recommendation_id,
reference_project, match_quality, ...) are later frozen into the record's
provenance block, so this store is a transient handoff queue, NOT a system of
record (the durable copy lives in provenance).

Design:
  - one latest seed per project: work/seeds/<slug(project_name)>.json
  - atomic write (tmp -> os.replace), Windows-safe
  - resolution order for the store dir: explicit arg > $SCOS_SEEDS_DIR > default
  - consume(): archive a used seed under work/seeds/_consumed/ (audit, not deletion)
  - cleanup(): drop seeds older than N days (handoff buffers are short-lived)

ADDITIVE: touches no core file, no memory contract. Seeds are not memory records.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DEFAULT_SEEDS_DIR = _HERE.parents[1] / "work" / "seeds"
ENV_SEEDS_DIR = "SCOS_SEEDS_DIR"


def resolve_seeds_dir(explicit: str | os.PathLike | None = None) -> Path:
    """explicit arg > $SCOS_SEEDS_DIR > work/seeds. Enables prod/staging/test isolation."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_SEEDS_DIR)
    return Path(env) if env else DEFAULT_SEEDS_DIR


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "project"


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on same filesystem (Windows-safe)


def _key(seed: dict) -> str:
    return _slug(seed.get("project_name") or seed.get("product_niche") or "project")


def persist_seed(seed: dict, seeds_dir: str | os.PathLike | None = None) -> Path:
    """Write the latest seed for a project. Overwrites a prior un-consumed seed
    for the same project (a re-recommendation supersedes the old one)."""
    d = resolve_seeds_dir(seeds_dir)
    path = d / f"{_key(seed)}.json"
    _atomic_write(path, seed)
    return path


def resolve_seed(project_name: str,
                 seeds_dir: str | os.PathLike | None = None) -> dict | None:
    """Load the pending seed for a project, or None if none was persisted."""
    path = resolve_seeds_dir(seeds_dir) / f"{_slug(project_name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def consume_seed(project_name: str,
                 seeds_dir: str | os.PathLike | None = None) -> str | None:
    """Move a used seed into _consumed/ (kept for audit, not deleted). No-op if absent."""
    d = resolve_seeds_dir(seeds_dir)
    path = d / f"{_slug(project_name)}.json"
    if not path.exists():
        return None
    dest_dir = d / "_consumed"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = dest_dir / f"{_slug(project_name)}.{stamp}.json"
    shutil.move(str(path), str(dest))
    return str(dest)


def cleanup_seeds(max_age_days: int = 14,
                  seeds_dir: str | os.PathLike | None = None) -> list[str]:
    """Delete pending seeds older than max_age_days (stale handoffs). Returns removed paths.
    Does not touch _consumed/ (that is the audit trail)."""
    d = resolve_seeds_dir(seeds_dir)
    if not d.exists():
        return []
    cutoff = _dt.datetime.now().timestamp() - max_age_days * 86400
    removed: list[str] = []
    for f in d.glob("*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed.append(str(f))
    return removed
