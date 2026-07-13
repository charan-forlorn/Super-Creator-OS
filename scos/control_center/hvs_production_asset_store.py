"""Stage 8M — append-only local persistence for production asset intake.

Mirrors the Stage 8L store discipline: append-only JSONL ledger under the
gitignored ``scos/work/`` runtime root, immutable prior events, deterministic
ids, idempotent replay, conflicting-replay rejection, read-only inspection.

Runtime paths are gitignored; no asset bytes, secrets, or HVS project data are
ever staged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .hvs_commercial_proposal_models import _safe_text, stable_id
from .hvs_production_asset_models import (
    ALLOWED_EVENT_TYPES,
    STAGE8M_EVENT_SCHEMA_VERSION,
    ProductionAssetEvent,
)
from .hvs_customer_outcome_models import validate_calendar_date


_RUNTIME_RELATIVE = "scos/work/hvs_production_asset_intake"
_LEDGER_NAME = "production_asset_intake.jsonl"
_CONTRACTS_DIR = "production_asset_manifests"


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / _RUNTIME_RELATIVE


def asset_intake_path(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _LEDGER_NAME


def manifest_contracts_dir(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _CONTRACTS_DIR


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe production asset store path")
    return value


def _validate_event(event: ProductionAssetEvent) -> None:
    if event.schema_version != STAGE8M_EVENT_SCHEMA_VERSION:
        raise ValueError("production asset event schema version mismatch")
    if event.event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported production asset event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, getattr(event, field))
    validate_calendar_date("recorded_at", event.recorded_at)
    if not isinstance(event.record, dict):
        raise ValueError("production asset event record must be a dict")


def read_asset_intake_events(*, audit_log_path: Any) -> tuple[ProductionAssetEvent, ...]:
    path = _validate_path(audit_log_path)
    if not path.is_file():
        return ()
    events: list[ProductionAssetEvent] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = ProductionAssetEvent(**json.loads(line))
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed production asset event at line {number}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting production asset event")
        seen.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_asset_intake_event(
    *,
    audit_log_path: Any,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> ProductionAssetEvent:
    event = ProductionAssetEvent(
        STAGE8M_EVENT_SCHEMA_VERSION,
        stable_id(
            "scos-hvs-production-asset-event",
            {"event_type": event_type, "subject_id": subject_id, "record": record},
        ),
        event_type,
        subject_id,
        operator_id,
        recorded_at,
        record,
    )
    _validate_event(event)
    for existing in read_asset_intake_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict():
                return existing
            raise ValueError("conflicting production asset event")
    path = _validate_path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
    return event


def write_manifest_contract_file(*, repo_root: Any, manifest_id: str, manifest: dict[str, Any]) -> Path:
    target_dir = manifest_contracts_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{manifest_id}.json"
    body = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    if path.exists() and path.read_text(encoding="utf-8") != body:
        raise ValueError("conflicting production asset manifest file")
    if not path.exists():
        path.write_text(body, encoding="utf-8")
    return path


def read_manifest_contract_file(*, repo_root: Any, manifest_id: str) -> dict[str, Any] | None:
    path = manifest_contracts_dir(repo_root) / f"{manifest_id}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("malformed production asset manifest file") from exc


# ---------------------------------------------------------------------------
# Stage 8L reverification loader
# ---------------------------------------------------------------------------
# The certified Stage 8L SCOS-side initialization evidence is recorded in the
# certified acceptance fixture; the live ground truth is the HVS project itself.
_STAGE8L_ACCEPTANCE_LEDGER_GLOB = "scos/work/stage8l_acceptance/*/scos/work/hvs_delivery_packages/hvs_project_initialization.jsonl"


def _load_stage8l_evidence_from_repo(repo_root: Any) -> dict[str, Any] | None:
    """Find the certified Stage 8L VERIFIED evidence for the given project.

    Searches the canonical runtime path first, then the certified acceptance
    fixtures. Returns the VERIFIED record dict, or None if no evidence exists.
    """
    repo = Path(repo_root)
    candidates: list[Path] = []
    canonical = repo / "scos" / "work" / "hvs_delivery_packages" / "hvs_project_initialization.jsonl"
    if canonical.is_file():
        candidates.append(canonical)
    for match in repo.glob(_STAGE8L_ACCEPTANCE_LEDGER_GLOB):
        candidates.append(match)
    verified: dict[str, Any] | None = None
    for ledger in candidates:
        try:
            lines = ledger.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = evt.get("record") or {}
            if rec.get("event_type" if "event_type" in evt else "event_type") is not None:
                pass
            # The store persists event_type at the top level and record.* as the
            # payload; both shapes are normalized here.
            event_type = evt.get("event_type") or rec.get("event_type")
            if event_type != "PROJECT_INITIALIZATION_VERIFIED":
                continue
            verified = rec
            break
        if verified is not None:
            break
    return verified
