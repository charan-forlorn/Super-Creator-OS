"""Canonical paid-pilot project-identity mapping (single source of truth).

Every downstream route (intake, materialization, render-readiness) must agree
on ONE internal project identity for a given external ``project_ref``. This
module is the sole authority that:

  * derives a deterministic canonical internal ID (``spp-`` + 12 lowercase hex);
  * persists the mapping record (external -> canonical, plus pilot/customer);
  * returns the SAME mapping on exact replay (no second write);
  * fails closed on conflicting replay.

The canonical ID is accepted by the materialization boundary
(``/^spp-[a-f0-9]{12}$/``), so a single mapping satisfies intake,
materialization and render-readiness without translation shims.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

MAPPING_SCHEMA_VERSION = "scos-hvs.pilot-identity.v1/1.0.0"
MAPPING_VERSION = "1"
CANONICAL_RE = __import__("re").compile(r"^spp-[a-f0-9]{12}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def derive_canonical_id(project_ref: str) -> str:
    """Deterministic, idempotent canonical internal ID for a project_ref."""
    ref = (project_ref or "").strip()
    if not ref:
        raise ValueError("PROJECT_REF_REQUIRED")
    return "spp-" + hashlib.sha256(ref.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class IdentityMapping:
    external_project_ref: str
    canonical_internal_project_id: str
    pilot_id: str
    customer_ref: str
    mapping_version: str
    created_at: str
    packet_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IdentityMapping":
        return cls(**{k: d.get(k, "") for k in (
            "external_project_ref", "canonical_internal_project_id", "pilot_id",
            "customer_ref", "mapping_version", "created_at", "packet_sha256",
        )})


class IdentityStore:
    """Append-only mapping store. Exact replay appends nothing new."""

    def __init__(self, store_path: Path):
        self.path = Path(store_path)

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except Exception:
            return []

    def find(self, external_project_ref: str) -> Optional[IdentityMapping]:
        for rec in self._read():
            if rec.get("external_project_ref") == external_project_ref:
                return IdentityMapping.from_dict(rec)
        return None

    def _append(self, rec: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        import os

        os.close(fd)
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        Path(tmp).write_text(existing + json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def persist(self, mapping: IdentityMapping) -> tuple[bool, Optional[str]]:
        """Persist a mapping.

        Returns ``(wrote_new, conflict_code)``:
          * wrote_new=True  -> a new mapping record was appended;
          * wrote_new=False -> exact replay, no write;
          * conflict_code set -> conflicting replay, caller must fail closed.
        """
        prior = self.find(mapping.external_project_ref)
        if prior is not None:
            if prior.canonical_internal_project_id == mapping.canonical_internal_project_id \
               and prior.pilot_id == mapping.pilot_id \
               and prior.customer_ref == mapping.customer_ref:
                return (False, None)  # exact replay — no second write
            return (False, "CONFLICTING_IDENTITY_REPLAY")
        self._append(mapping.to_dict())
        return (True, None)


def build_mapping(
    *,
    external_project_ref: str,
    pilot_id: str,
    customer_ref: str,
    packet_sha256: str = "",
    created_at: Optional[str] = None,
) -> IdentityMapping:
    return IdentityMapping(
        external_project_ref=external_project_ref,
        canonical_internal_project_id=derive_canonical_id(external_project_ref),
        pilot_id=pilot_id,
        customer_ref=customer_ref,
        mapping_version=MAPPING_VERSION,
        created_at=created_at or _now_iso(),
        packet_sha256=packet_sha256,
    )
