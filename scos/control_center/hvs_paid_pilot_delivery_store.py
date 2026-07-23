"""SCOS Cohort 10H — durable single-writer paid-pilot delivery store.

The DELIVERY_PACKAGE_OWNER. Persists exactly one authoritative collection of
paid-pilot delivery records under a locked, atomically replaced JSON envelope.

Design mirrors ``hvs_render_attempt_store.RenderAttemptStore`` (the
established Cohort 10E single-writer contract):
  * one locked JSON envelope file (``paid-pilot-delivery-v1.json``)
  * ``file_lock`` serializes all writes (concurrent-writer protection)
  * ``atomic_replace`` finalizes writes (no partial state visible)
  * truth-state resolution on every read (EMPTY / AVAILABLE_WITH_DATA /
    UNAVAILABLE / CORRUPT / INCOMPATIBLE_SCHEMA / LOCKED)
  * restart recovery = reopen the same file and read the record back

The store performs NO business transitions itself; it only persists the
authoritative record the service computes. It never spawns subprocesses, never
touches the network, and never exposes filesystem paths.

Location: SCOS runtime root ``memory/runtime/control-center`` (gitignored
runtime tree), outside the committed source working tree. Server-controlled.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

try:
    from _filelock import atomic_replace, file_lock, lock_path_for
except ImportError:  # direct-module execution (pytest inserts package dir)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "learning"))
    from _filelock import atomic_replace, file_lock, lock_path_for  # type: ignore

from scos.control_center.hvs_paid_pilot_delivery_models import (  # noqa: E402
    DELIVERY_SCHEMA_VERSION,
    PaidPilotDeliveryRecord,
)

# Canonical store envelope identity.
_STORE_KIND = "scos.paid_pilot_delivery.v1"
_STORE_FILE_NAME = "paid-pilot-delivery-v1.json"

# Truth states the store can resolve to (every read is exactly one).
TRUTH_EMPTY = "EMPTY"
TRUTH_AVAILABLE_WITH_DATA = "AVAILABLE_WITH_DATA"
TRUTH_UNAVAILABLE = "UNAVAILABLE"
TRUTH_CORRUPT = "CORRUPT"
TRUTH_INCOMPATIBLE_SCHEMA = "INCOMPATIBLE_SCHEMA"
TRUTH_LOCKED = "LOCKED"

ERR_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
ERR_STORE_CORRUPT = "STORE_CORRUPT"
ERR_SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class PaidPilotDeliveryStore:
    """Single-writer authoritative persistence for paid-pilot delivery records."""

    def __init__(
        self,
        *,
        store_path: Optional[Path] = None,
        base_dir: Optional[Path] = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self._base_dir = (
            Path(base_dir)
            if base_dir is not None
            else repo_root / "memory" / "runtime" / "control-center"
        )
        if store_path is not None:
            p = Path(store_path)
            if p.is_dir():
                self._store_path = p / _STORE_FILE_NAME
            else:
                # Any explicit file path (existing or .json) is used directly;
                # the canonical name is only appended when a *directory* is given.
                self._store_path = p
        else:
            self._store_path = self._base_dir / _STORE_FILE_NAME

    @property
    def store_path(self) -> Path:
        return self._store_path

    # -- low-level read -------------------------------------------------
    def _read_raw(self) -> dict[str, Any]:
        path = self._store_path
        if not path.exists():
            return {"status": TRUTH_EMPTY, "records": {}}
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"status": TRUTH_CORRUPT, "detail": f"malformed store: {exc}"}
        if not isinstance(data, dict):
            return {"status": TRUTH_CORRUPT, "detail": "store envelope is not an object"}
        kind = data.get("store_kind")
        if kind is not None and kind != _STORE_KIND:
            return {"status": TRUTH_CORRUPT, "detail": f"unknown store_kind: {kind!r}"}
        if data.get("schema_version") != DELIVERY_SCHEMA_VERSION:
            return {
                "status": TRUTH_INCOMPATIBLE_SCHEMA,
                "detail": "unsupported schema_version",
            }
        records = data.get("records")
        if not isinstance(records, dict):
            return {"status": TRUTH_CORRUPT, "detail": "missing records collection"}
        return {"status": TRUTH_AVAILABLE_WITH_DATA, "data": data}

    def read(self) -> dict[str, Any]:
        try:
            return self._read_raw()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": TRUTH_UNAVAILABLE, "detail": f"read error: {exc}"}

    # -- collection access -----------------------------------------------
    def _records(self) -> dict[str, Any]:
        res = self._read_raw()
        if res["status"] != TRUTH_AVAILABLE_WITH_DATA:
            return {}
        return res["data"]["records"]

    def get(self, delivery_id: str) -> Optional[PaidPilotDeliveryRecord]:
        row = self._records().get(delivery_id)
        return PaidPilotDeliveryRecord.from_dict(row) if row else None

    def list_all(self) -> list[PaidPilotDeliveryRecord]:
        return [PaidPilotDeliveryRecord.from_dict(r) for r in self._records().values()]

    # -- low-level write -------------------------------------------------
    def _write_envelope(self, data: dict[str, Any]) -> None:
        path = self._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": DELIVERY_SCHEMA_VERSION,
            "store_kind": _STORE_KIND,
            "written_at": _now_iso(),
            "records": data.get("records", {}),
        }
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        tmp = path.parent / f"{path.name}.tmp.{__import__('os').getpid()}"
        tmp.write_text(serialized, encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))  # validate complete bytes
        atomic_replace(tmp, path)

    def _mutate(self, fn) -> None:
        """Take the lock, call fn(records dict), and persist atomically."""
        with file_lock(self._store_path):
            res = self._read_raw()
            if res["status"] == TRUTH_EMPTY:
                data: dict[str, Any] = {"records": {}}
            elif res["status"] == TRUTH_AVAILABLE_WITH_DATA:
                data = res["data"]
            else:
                # Corrupt / incompatible / unavailable store: fail closed.
                raise RuntimeError(f"store not writable: {res['status']}")
            fn(data["records"])
            self._write_envelope(data)

    # -- writes ---------------------------------------------------------
    def put(self, record: PaidPilotDeliveryRecord) -> None:
        def _fn(records: dict[str, Any]) -> None:
            records[record.delivery_id] = record.to_dict()
        self._mutate(_fn)

    def delete_record(self, delivery_id: str) -> None:
        def _fn(records: dict[str, Any]) -> None:
            records.pop(delivery_id, None)
        self._mutate(_fn)
