"""Cohort 10E — durable render-attempt + authorization + capability registry.

This is the RENDER_ATTEMPT_STORE_OWNER. It persists exactly three
authoritative collections, each under one locked, atomically replaced JSON
envelope (mirrors the Cohort 10D ``MaterializationStore`` contract 1:1):

  * authorizations  (HvsRenderAuthorization to_dict)
  * capabilities    (HvsRenderCapability to_dict)
  * attempts        (HvsRenderAttempt to_dict)

Restart durability: a server restart re-reads this file and recovers the
exact authorization decision, the consumed capability state, the in-flight
STARTING/RUNNING attempt, the confirmed RENDER_SUCCEEDED outcome, and the
unknown RENDER_OUTCOME_UNKNOWN state — so no duplicate HVS render is started
on recovery.

Scope: this module ONLY persists render authorization/capability/attempt
state. It performs NO filesystem mutation at the HVS output root, NO
subprocess, NO render, NO network. The actual HVS render call lives behind an
injected callable in the service.
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

from .hvs_render_plan_models import (  # noqa: E402
    RENDER_SCHEMA_VERSION,
    STATE_RENDER_AUTHORIZATION_REQUIRED,
    STATE_RENDER_AUTHORIZED,
    STATE_RENDER_STARTING,
    STATE_RENDER_RUNNING,
    STATE_RENDER_OUTCOME_UNKNOWN,
    STATE_RENDER_RECONCILIATION_REQUIRED,
    STATE_RENDER_SUCCEEDED,
    HvsRenderAttempt,
    HvsRenderAuthorization,
    HvsRenderCapability,
)

# Canonical collection envelope kinds.
_STORE_KIND = "scos.hvs_render_attempt.v1"
_STORE_FILE_NAME = "hvs-render-attempt-v1.json"

# Truth states the store can resolve to (every read is exactly one).
TRUTH_AVAILABLE_WITH_DATA = "AVAILABLE_WITH_DATA"
TRUTH_EMPTY = "EMPTY"
TRUTH_UNAVAILABLE = "UNAVAILABLE"
TRUTH_CORRUPT = "CORRUPT"
TRUTH_INCOMPATIBLE_SCHEMA = "INCOMPATIBLE_SCHEMA"

ERR_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
ERR_STORE_CORRUPT = "STORE_CORRUPT"
ERR_SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class RenderAttemptStore:
    """Single-writer authoritative persistence for render authorizations,
    capabilities, and attempts.
    """

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
            if p.is_dir() or p.name != _STORE_FILE_NAME:
                self._store_path = p / _STORE_FILE_NAME
            else:
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
        if data.get("schema_version") != RENDER_SCHEMA_VERSION:
            return {
                "status": TRUTH_INCOMPATIBLE_SCHEMA,
                "detail": "unsupported schema_version",
            }
        for key in ("authorizations", "capabilities", "attempts"):
            if key not in data or not isinstance(data[key], dict):
                return {"status": TRUTH_CORRUPT, "detail": f"missing collection: {key}"}
        return {"status": TRUTH_AVAILABLE_WITH_DATA, "data": data}

    def read(self) -> dict[str, Any]:
        try:
            return self._read_raw()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": TRUTH_UNAVAILABLE, "detail": f"read error: {exc}"}

    # -- collections ------------------------------------------------------
    def _collections(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        res = self._read_raw()
        if res["status"] != TRUTH_AVAILABLE_WITH_DATA:
            return {}, {}, {}
        data = res["data"]
        return data["authorizations"], data["capabilities"], data["attempts"]

    def get_authorization(self, authorization_id: str) -> Optional[HvsRenderAuthorization]:
        auths, _, _ = self._collections()
        row = auths.get(authorization_id)
        return HvsRenderAuthorization.from_dict(row) if row else None

    def get_capability(self, capability_id: str) -> Optional[HvsRenderCapability]:
        _, caps, _ = self._collections()
        row = caps.get(capability_id)
        return HvsRenderCapability.from_dict(row) if row else None

    def get_attempt(self, attempt_id: str) -> Optional[HvsRenderAttempt]:
        _, _, attempts = self._collections()
        row = attempts.get(attempt_id)
        return HvsRenderAttempt.from_dict(row) if row else None

    def list_attempts_for_project(self, project_id: str) -> list[HvsRenderAttempt]:
        _, _, attempts = self._collections()
        return [
            HvsRenderAttempt.from_dict(r)
            for r in attempts.values()
            if r.get("project_id") == project_id
        ]

    # -- low-level write -------------------------------------------------
    def _write_envelope(self, data: dict[str, Any]) -> None:
        path = self._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": RENDER_SCHEMA_VERSION,
            "store_kind": _STORE_KIND,
            "written_at": _now_iso(),
            "authorizations": data.get("authorizations", {}),
            "capabilities": data.get("capabilities", {}),
            "attempts": data.get("attempts", {}),
        }
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        tmp = path.parent / f"{path.name}.tmp.{__import__('os').getpid()}"
        tmp.write_text(serialized, encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))  # validate complete bytes
        atomic_replace(tmp, path)

    def _mutate(self, fn) -> None:
        """Take the lock, call fn(collections dict), and persist."""
        with file_lock(self._store_path):
            res = self._read_raw()
            if res["status"] == TRUTH_EMPTY:
                data: dict[str, Any] = {
                    "authorizations": {},
                    "capabilities": {},
                    "attempts": {},
                }
            elif res["status"] == TRUTH_AVAILABLE_WITH_DATA:
                data = res["data"]
            else:
                # Corrupt / incompatible / unavailable store: fail closed.
                raise RuntimeError(f"store not writable: {res['status']}")
            fn(data)
            self._write_envelope(data)

    # -- writes ---------------------------------------------------------
    def put_authorization(self, auth: HvsRenderAuthorization) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["authorizations"][auth.authorization_id] = auth.to_dict()
        self._mutate(_fn)

    def put_capability(self, cap: HvsRenderCapability) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["capabilities"][cap.capability_id] = cap.to_dict()
        self._mutate(_fn)

    def put_attempt(self, attempt: HvsRenderAttempt) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["attempts"][attempt.attempt_id] = attempt.to_dict()
        self._mutate(_fn)

    def consume_capability(self, capability_id: str, *, consumed_at: str) -> Optional[HvsRenderCapability]:
        """Atomically mark a capability consumed; returns the prior state.

        Returns the PRE-consumption capability (consumed_at None) on
        success, or None if it was already consumed / missing. This is the
        single-use enforcement primitive: two concurrent consumers both
        call this under the lock; exactly one sees a not-yet-consumed
        capability and wins.
        """
        prior: list[Optional[HvsRenderCapability]] = [None]

        def _fn(data: dict[str, Any]) -> None:
            caps = data["capabilities"]
            row = caps.get(capability_id)
            if row is None:
                return
            cap = HvsRenderCapability.from_dict(row)
            if cap.is_consumed():
                return  # already consumed; do not overwrite the timestamp
            prior[0] = cap
            updated = HvsRenderCapability(
                schema_version=cap.schema_version,
                capability_id=cap.capability_id,
                authorization_id=cap.authorization_id,
                project_id=cap.project_id,
                project_revision=cap.project_revision,
                materialization_attempt_id=cap.materialization_attempt_id,
                materialization_plan_hash=cap.materialization_plan_hash,
                render_profile_id=cap.render_profile_id,
                render_plan_hash=cap.render_plan_hash,
                output_root_identity=cap.output_root_identity,
                issued_at=cap.issued_at,
                expires_at=cap.expires_at,
                consumed_at=consumed_at,
                operation=cap.operation,
            )
            caps[capability_id] = updated.to_dict()

        self._mutate(_fn)
        return prior[0]

    def try_claim_active(self, *, project_id: str, attempt_id: str) -> bool:
        """Atomically claim the single active-render slot for a project.

        Returns True if THIS attempt may proceed (no other active attempt
        exists for the project). Returns False if another attempt is already
        active (duplicate containment; the caller must fail closed without
        crossing the HVS render boundary). Runs entirely under the store lock
        so two concurrent requests cannot both win.
        """
        _ACTIVE = (
            STATE_RENDER_AUTHORIZATION_REQUIRED,
            STATE_RENDER_AUTHORIZED,
            STATE_RENDER_STARTING,
            STATE_RENDER_RUNNING,
        )
        won: list[bool] = [False]

        def _fn(data: dict[str, Any]) -> None:
            attempts = data["attempts"]
            for row in attempts.values():
                if row.get("project_id") != project_id:
                    continue
                if row.get("state") in _ACTIVE and row.get("attempt_id") != attempt_id:
                    return  # another active attempt owns the slot
            won[0] = True

        self._mutate(_fn)
        return won[0]

    def has_active_attempt(self, *, project_id: str, exclude_attempt_id: str) -> bool:
        """Read-only check: is another attempt currently active for project?"""
        res = self._read_raw()
        if res["status"] != TRUTH_AVAILABLE_WITH_DATA:
            return False
        _ACTIVE = (
            STATE_RENDER_AUTHORIZATION_REQUIRED,
            STATE_RENDER_AUTHORIZED,
            STATE_RENDER_STARTING,
            STATE_RENDER_RUNNING,
        )
        for row in res["data"]["attempts"].values():
            if row.get("project_id") != project_id:
                continue
            if row.get("state") in _ACTIVE and row.get("attempt_id") != exclude_attempt_id:
                return True
        return False

    def record_transport_unknown(
        self,
        *,
        attempt_id: str,
        project_id: str,
        project_revision: int,
        marked_at: str,
        error_code: str = "BRIDGE_TIMEOUT",
    ) -> Optional[HvsRenderAttempt]:
        """Record transport uncertainty for an existing non-success attempt.

        Zero HVS calls, zero render calls, idempotent for already-unknown
        attempts, and preserves terminal success/failure bytes.
        """
        updated: list[Optional[HvsRenderAttempt]] = [None]

        def _fn(data: dict[str, Any]) -> None:
            row = data["attempts"].get(attempt_id)
            if row is None:
                return
            attempt = HvsRenderAttempt.from_dict(row)
            if attempt.project_id != project_id or attempt.project_revision != project_revision:
                return
            if attempt.state == STATE_RENDER_SUCCEEDED:
                updated[0] = attempt
                return
            if attempt.state == STATE_RENDER_OUTCOME_UNKNOWN:
                updated[0] = attempt
                return
            if attempt.state not in (STATE_RENDER_STARTING, STATE_RENDER_RUNNING, STATE_RENDER_RECONCILIATION_REQUIRED):
                updated[0] = attempt
                return
            next_attempt = HvsRenderAttempt(
                **{
                    **attempt.to_dict(),
                    "state": STATE_RENDER_OUTCOME_UNKNOWN,
                    "updated_at": marked_at,
                    "finished_at": attempt.finished_at or marked_at,
                    "outcome": "unknown",
                    "error_code": error_code,
                    "error_detail": "transport outcome unknown; read-only reconciliation required",
                }
            )
            data["attempts"][attempt_id] = next_attempt.to_dict()
            updated[0] = next_attempt

        self._mutate(_fn)
        return updated[0]


__all__ = sorted(
    (
        "TRUTH_AVAILABLE_WITH_DATA",
        "TRUTH_EMPTY",
        "TRUTH_UNAVAILABLE",
        "TRUTH_CORRUPT",
        "TRUTH_INCOMPATIBLE_SCHEMA",
        "ERR_STORE_UNAVAILABLE",
        "ERR_STORE_CORRUPT",
        "ERR_SCHEMA_INCOMPATIBLE",
        "RenderAttemptStore",
    )
)
