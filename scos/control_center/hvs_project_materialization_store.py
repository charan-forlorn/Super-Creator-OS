"""Cohort 10D — durable materialization attempt + authorization registry.

This is the OUTCOME_STORE_OWNER. It persists exactly three
authoritative collections, each under one locked, atomically
replaced JSON envelope (mirrors the Cohort 10C
``solo_project_preparation.py`` store contract 1:1):

  * authorizations  (HvsProjectMaterializationAuthorization to_dict)
  * capabilities    (HvsProjectMaterializationCapability to_dict)
  * attempts        (HvsMaterializationAttempt to_dict)

Restart durability: a server restart re-reads this file and
recovers the exact authorization decision, the consumed
capability state, the in-flight STARTING attempt, the
confirmed HVS_PROJECT_MATERIALIZED outcome, and the
unknown OUTCOME_UNKNOWN state — so no duplicate HVS
project is created on recovery.

Scope: this module ONLY persists materialization
authorization/capability/attempt state. It performs NO
filesystem mutation at the HVS destination, NO subprocess,
NO render, NO network. The actual HVS materialization
call lives behind an injected callable in the service.
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

from .hvs_project_materialization_models import (  # noqa: E402
    MATERIALIZATION_SCHEMA_VERSION,
    STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
    STATE_MATERIALIZATION_AUTHORIZED,
    STATE_MATERIALIZATION_STARTING,
    HvsMaterializationAttempt,
    HvsProjectMaterializationAuthorization,
    HvsProjectMaterializationCapability,
    HvsRenderInputsAuthorization,
    HvsRenderInputsCapability,
    HvsRenderInputsAttempt,
)

# Canonical collection envelope kinds.
_STORE_KIND = "scos.hvs_project_materialization.v1"
_INTEGRITY_SUFFIX = ".integrity.json"
_TMP_SUFFIX = ".tmp"
# Canonical file name written inside the resolved store directory.
_STORE_FILE_NAME = "hvs-project-materialization-v1.json"

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
    # Caller-supplied clock is preferred; this is a defensive default
    # used only by the in-process store constructor when a writer
    # does not thread its own recorded_at. The service always
    # passes an explicit recorded_at.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class MaterializationStore:
    """Single-writer authoritative persistence for materialization
    authorizations, capabilities, and attempts.
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
            # `store_path` may be a directory (isolation harness) or a bare
            # name; resolve to the canonical envelope file inside it so the
            # read/write paths are always a FILE (never a directory, which
            # would raise PermissionError on read_text and surface as CORRUPT).
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
        if data.get("schema_version") != MATERIALIZATION_SCHEMA_VERSION:
            return {
                "status": TRUTH_INCOMPATIBLE_SCHEMA,
                "detail": "unsupported schema_version",
            }
        for key in ("authorizations", "capabilities", "attempts"):
            if key not in data or not isinstance(data[key], dict):
                return {"status": TRUTH_CORRUPT, "detail": f"missing collection: {key}"}
        # `downstream` is an additive Cohort 10E extension; tolerate its
        # absence in stores written before this change (backward compatible).
        data.setdefault("downstream", {})
        return {"status": TRUTH_AVAILABLE_WITH_DATA, "data": data}

    def read(self) -> dict[str, Any]:
        try:
            return self._read_raw()
        except Exception as exc:  # pragma: no cover - defensive
            return {"status": TRUTH_UNAVAILABLE, "detail": f"read error: {exc}"}

    # -- collections ------------------------------------------------------
    def _collections(self) -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        res = self._read_raw()
        if res["status"] != TRUTH_AVAILABLE_WITH_DATA:
            return {}, {}, {}, {}
        data = res["data"]
        return data["authorizations"], data["capabilities"], data["attempts"], data["downstream"]

    def get_authorization(self, authorization_id: str) -> Optional[HvsProjectMaterializationAuthorization]:
        auths, _, _, _ = self._collections()
        row = auths.get(authorization_id)
        return HvsProjectMaterializationAuthorization.from_dict(row) if row else None

    def get_capability(self, capability_id: str) -> Optional[HvsProjectMaterializationCapability]:
        _, caps, _, _ = self._collections()
        row = caps.get(capability_id)
        return HvsProjectMaterializationCapability.from_dict(row) if row else None

    def get_attempt(self, attempt_id: str) -> Optional[HvsMaterializationAttempt]:
        _, _, attempts, _ = self._collections()
        row = attempts.get(attempt_id)
        return HvsMaterializationAttempt.from_dict(row) if row else None

    def list_attempts_for_project(self, project_id: str) -> list[HvsMaterializationAttempt]:
        _, _, attempts, _ = self._collections()
        return [
            HvsMaterializationAttempt.from_dict(r)
            for r in attempts.values()
            if r.get("project_id") == project_id
        ]

    # -- low-level write -------------------------------------------------
    def _write_envelope(self, data: dict[str, Any]) -> None:
        path = self._store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "schema_version": MATERIALIZATION_SCHEMA_VERSION,
            "store_kind": _STORE_KIND,
            "written_at": _now_iso(),
            "authorizations": data.get("authorizations", {}),
            "capabilities": data.get("capabilities", {}),
            "attempts": data.get("attempts", {}),
            "downstream": data.get("downstream", {}),
        }
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        tmp = path.parent / f"{path.name}{_TMP_SUFFIX}.{__import__('os').getpid()}"
        tmp.write_text(serialized, encoding="utf-8")
        # Validate complete bytes before replace.
        json.loads(tmp.read_text(encoding="utf-8"))
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
                    "downstream": {},
                }
            elif res["status"] == TRUTH_AVAILABLE_WITH_DATA:
                data = res["data"]
            else:
                # Corrupt / incompatible / unavailable store: fail closed,
                # never implicitly recreate or mutate.
                raise RuntimeError(f"store not writable: {res['status']}")
            fn(data)
            self._write_envelope(data)

    # -- writes ---------------------------------------------------------
    def put_authorization(self, auth: HvsProjectMaterializationAuthorization) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["authorizations"][auth.authorization_id] = auth.to_dict()
        self._mutate(_fn)

    def put_capability(self, cap: HvsProjectMaterializationCapability) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["capabilities"][cap.capability_id] = cap.to_dict()
        self._mutate(_fn)

    def put_attempt(self, attempt: HvsMaterializationAttempt) -> None:
        def _fn(data: dict[str, Any]) -> None:
            data["attempts"][attempt.attempt_id] = attempt.to_dict()
        self._mutate(_fn)

    def consume_capability(self, capability_id: str, *, consumed_at: str) -> Optional[HvsProjectMaterializationCapability]:
        """Atomically mark a capability consumed; returns the prior state.

        Returns the PRE-consumption capability (consumed_at None) on
        success, or None if it was already consumed / missing. This
        is the single-use enforcement primitive: two concurrent
        consumers both call this under the lock; exactly one sees a
        not-yet-consumed capability and wins.
        """
        prior: list[Optional[HvsProjectMaterializationCapability]] = [None]

        def _fn(data: dict[str, Any]) -> None:
            caps = data["capabilities"]
            row = caps.get(capability_id)
            if row is None:
                return
            cap = HvsProjectMaterializationCapability.from_dict(row)
            if cap.is_consumed():
                return  # already consumed; do not overwrite the timestamp
            prior[0] = cap
            updated = HvsProjectMaterializationCapability(
                schema_version=cap.schema_version,
                capability_id=cap.capability_id,
                authorization_id=cap.authorization_id,
                project_id=cap.project_id,
                project_revision=cap.project_revision,
                plan_hash=cap.plan_hash,
                destination_identity=cap.destination_identity,
                issued_at=cap.issued_at,
                expires_at=cap.expires_at,
                consumed_at=consumed_at,
                operation=cap.operation,
            )
            caps[capability_id] = updated.to_dict()

        self._mutate(_fn)
        return prior[0]

    def try_claim_inflight(self, *, project_id: str, attempt_id: str) -> bool:
        """Atomically claim the single in-flight attempt slot for a project.

        Returns True if THIS attempt may proceed (no other in-flight
        attempt exists for the project). Returns False if another attempt
        is already in-flight (duplicate containment; the caller must fail
        closed without crossing the HVS boundary). Runs entirely under the
        store lock so two concurrent requests cannot both win.
        """
        _INFLIGHT = (STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
                     STATE_MATERIALIZATION_AUTHORIZED,
                     STATE_MATERIALIZATION_STARTING)
        won: list[bool] = [False]

        def _fn(data: dict[str, Any]) -> None:
            attempts = data["attempts"]
            for row in attempts.values():
                if row.get("project_id") != project_id:
                    continue
                if row.get("state") in _INFLIGHT and row.get("attempt_id") != attempt_id:
                    return  # another in-flight attempt owns the slot
            won[0] = True

        self._mutate(_fn)
        return won[0]


    def has_inflight_attempt(self, *, project_id: str, exclude_attempt_id: str) -> bool:
        """Read-only check: is another attempt currently in-flight for project?"""
        res = self._read_raw()
        if res["status"] != TRUTH_AVAILABLE_WITH_DATA:
            return False
        _INFLIGHT = (STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
                     STATE_MATERIALIZATION_AUTHORIZED,
                     STATE_MATERIALIZATION_STARTING)
        for row in res["data"]["attempts"].values():
            if row.get("project_id") != project_id:
                continue
            if row.get("state") in _INFLIGHT and row.get("attempt_id") != exclude_attempt_id:
                return True
        return False


    # -- Cohort 10E downstream render-input materialization sub-ledger ------
    # The SAME store, SAME lock, SAME authority as the materialization ledger
    # above. The downstream operation is a separate, narrower lifecycle, so its
    # authorizations/capabilities/attempts are segregated into a dedicated
    # `downstream` collection to avoid co-mingling contract shapes (different
    # operation identity, different state machine). No second store/authority
    # is introduced.

    def get_render_inputs_authorization(self, authorization_id: str) -> Optional[HvsRenderInputsAuthorization]:
        _, _, _, ds = self._collections()
        row = ds.get("render_inputs_authorizations", {}).get(authorization_id)
        return HvsRenderInputsAuthorization.from_dict(row) if row else None

    def get_render_inputs_capability(self, capability_id: str) -> Optional[HvsRenderInputsCapability]:
        _, _, _, ds = self._collections()
        row = ds.get("render_inputs_capabilities", {}).get(capability_id)
        return HvsRenderInputsCapability.from_dict(row) if row else None

    def get_render_inputs_attempt(self, attempt_id: str) -> Optional[HvsRenderInputsAttempt]:
        _, _, _, ds = self._collections()
        row = ds.get("render_inputs_attempts", {}).get(attempt_id)
        return HvsRenderInputsAttempt.from_dict(row) if row else None

    def list_render_inputs_attempts_for_project(self, project_id: str) -> list[HvsRenderInputsAttempt]:
        _, _, _, ds = self._collections()
        return [
            HvsRenderInputsAttempt.from_dict(r)
            for r in ds.get("render_inputs_attempts", {}).values()
            if r.get("source_project_id") == project_id or r.get("hvs_project_id") == project_id
        ]

    def put_render_inputs_authorization(self, auth: HvsRenderInputsAuthorization) -> None:
        def _fn(data: dict[str, Any]) -> None:
            ds = data.setdefault("downstream", {})
            coll = ds.setdefault("render_inputs_authorizations", {})
            coll[auth.authorization_id] = auth.to_dict()
        self._mutate(_fn)

    def put_render_inputs_capability(self, cap: HvsRenderInputsCapability) -> None:
        def _fn(data: dict[str, Any]) -> None:
            ds = data.setdefault("downstream", {})
            coll = ds.setdefault("render_inputs_capabilities", {})
            cap_problems = cap.validate()
            if cap_problems:
                # Never persist a malformed capability; surface via caller.
                return
            coll[cap.capability_id] = cap.to_dict()
        self._mutate(_fn)

    def put_render_inputs_attempt(self, attempt: HvsRenderInputsAttempt) -> None:
        def _fn(data: dict[str, Any]) -> None:
            ds = data.setdefault("downstream", {})
            coll = ds.setdefault("render_inputs_attempts", {})
            coll[attempt.attempt_id] = attempt.to_dict()
        self._mutate(_fn)

    def consume_render_inputs_capability(
        self, capability_id: str, *, consumed_at: str
    ) -> Optional[HvsRenderInputsCapability]:
        """Atomically mark a downstream capability consumed; return prior state.

        Returns the PRE-consumption capability (consumed_at None) on success,
        or None if already consumed / missing — the single-use enforcement
        primitive for the downstream operation.
        """
        prior: list[Optional[HvsRenderInputsCapability]] = [None]

        def _fn(data: dict[str, Any]) -> None:
            ds = data.setdefault("downstream", {})
            caps = ds.setdefault("render_inputs_capabilities", {})
            row = caps.get(capability_id)
            if row is None:
                return
            cap = HvsRenderInputsCapability.from_dict(row)
            if cap.is_consumed():
                return
            prior[0] = cap
            updated = HvsRenderInputsCapability(
                schema_version=cap.schema_version,
                capability_id=cap.capability_id,
                authorization_id=cap.authorization_id,
                source_project_id=cap.source_project_id,
                hvs_project_id=cap.hvs_project_id,
                project_revision=cap.project_revision,
                initialization_fingerprint=cap.initialization_fingerprint,
                destination_identity=cap.destination_identity,
                issued_at=cap.issued_at,
                expires_at=cap.expires_at,
                consumed_at=consumed_at,
                operation=cap.operation,
            )
            caps[capability_id] = updated.to_dict()

        self._mutate(_fn)
        return prior[0]


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
        "MaterializationStore",
    )
)
