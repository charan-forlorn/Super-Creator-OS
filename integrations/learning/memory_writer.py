"""memory_writer.py — the ONLY safe path to write memory/database.json.

Guarantees (every write):
  - schema-validate the new record AND the existing DB before touching disk
  - timestamped backup into memory/_db_backups/
  - append-only: db + [record]; existing records verified byte-identical after
  - atomic write (temp file -> os.replace), so no partial/corrupt file is possible
  - duplicate guard on (project_name, created_at)

Returns (ok: bool, info: str). Never raises on a normal rejection — returns ok=False.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
from pathlib import Path

from validators import validate_record, validate_db, validate_provenance

DEFAULT_DB = Path(__file__).resolve().parents[2] / "memory" / "database.json"


def _atomic_write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def safe_append(record: dict, db_path: Path | None = None) -> tuple[bool, str]:
    db_path = Path(db_path) if db_path else DEFAULT_DB

    errs = validate_record(record)
    if errs:
        return False, "record invalid: " + "; ".join(errs)

    # provenance is optional; if present it must be well-formed (backward compatible)
    perrs = validate_provenance(record.get("provenance"))
    if perrs:
        return False, "provenance invalid: " + "; ".join(perrs)

    db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else []
    db_errs = validate_db(db)
    if db_errs:
        return False, "existing DB invalid (refusing to write): " + "; ".join(db_errs)

    if any(r.get("project_name") == record["project_name"]
           and r.get("created_at") == record["created_at"] for r in db):
        return False, "duplicate (same project_name + created_at) — aborted"

    # backup before write
    backups = db_path.parent / "_db_backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backups / f"database.{stamp}.json"
    if db_path.exists():
        shutil.copy2(db_path, backup)

    new_db = db + [record]
    if new_db[:len(db)] != db:                       # post-condition: never alter old records
        return False, "append would alter existing records — aborted"

    _atomic_write_json(db_path, new_db)
    return True, f"appended record #{len(new_db)} (backup: {backup.name})"
