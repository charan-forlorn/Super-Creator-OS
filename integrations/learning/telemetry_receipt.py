"""Causal observed-telemetry receipt.

Binds an analytics export to existing SCOS provenance-bearing loop_run_id values
without creating observations. A receipt is VALID only when every imported row
joins to a current record; otherwise the result is explicitly ORPHAN and no
learning qualification is implied.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from integrations.learning.telemetry_export import _load_rows, import_export


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _db_runs(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    rows = json.loads(db_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("database.json must be an array")
    return {
        str((row.get("provenance") or {}).get("loop_run_id"))
        for row in rows
        if isinstance(row, dict) and (row.get("provenance") or {}).get("loop_run_id")
    }


def build_telemetry_receipt(
    *,
    export_path: str | Path,
    db_path: str | Path,
    telemetry_path: str | Path,
    receipt_path: str | Path,
    source: str = "manual",
) -> dict[str, Any]:
    export = Path(export_path).resolve()
    db = Path(db_path).resolve()
    telemetry = Path(telemetry_path).resolve()
    receipt = Path(receipt_path).resolve()

    if not export.is_file():
        return {"status": "BLOCKED", "reason": "EXPORT_NOT_FOUND"}

    export_sha = _sha256(export)
    export_rows = _load_rows(export)
    observed_runs = {
        str(row.get(name))
        for row in export_rows
        if isinstance(row, dict)
        for name in ("loop_run_id", "loopRunId", "run_id")
        if row.get(name)
    }
    provenance_runs = _db_runs(db)
    joined_runs = observed_runs & provenance_runs
    orphan_runs = sorted(observed_runs - provenance_runs)

    result = import_export(
        export,
        telemetry_path=telemetry,
        db_path=db,
        source=source,
    )
    if not result.get("ok"):
        return {
            "status": "BLOCKED",
            "reason": "IMPORT_REJECTED",
            "export_sha256": export_sha,
            "import_result": result,
        }

    if not observed_runs:
        return {
            "status": "BLOCKED",
            "reason": "NO_OBSERVATIONS",
            "export_sha256": export_sha,
            "import_result": result,
        }
    status = "OBSERVATIONS_JOINED" if not orphan_runs else "ORPHAN_OBSERVATIONS"
    payload = {
        "schema_version": 1,
        "status": status,
        "source": source,
        "export_path": str(export),
        "export_sha256": export_sha,
        "db_path": str(db),
        "telemetry_path": str(telemetry),
        "rows_imported": result.get("rows_imported", 0),
        "observed_loop_run_ids": sorted(observed_runs),
        "joined_loop_run_ids": sorted(observed_runs & provenance_runs),
        "orphan_loop_run_ids": orphan_runs,
        "learning_qualification": False,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["receipt_id"] = "telrec-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


__all__ = ["build_telemetry_receipt"]
