"""SCOS <-> Hermes Video Studio (HVS) — Stage 4 approval-gated asset materialization.

This module is the Stage 4 integration surface. It bridges a Stage 3-correlated
HVS project to explicit, approved *local source assets* and performs a narrow,
copy-only materialization of those assets into the HVS project-local asset
directory. It is the deterministic, approval-gated "bring the approved source
files into the project" step.

Boundary (consistent with Stage 1/3 cross-project architecture):

    Stage 4 service  ->  consumes Stage 2 asset-reference model + Stage 3
        correlation ledger + HVS project layout  ->  resolves each requested
        source asset to an approved local file  ->  validates against an
        explicit safe local asset policy  ->  evaluates an explicit
        materialize_hvs_assets approval  ->  (only if approved) copies the
        files byte-exactly into the HVS project-root assets dir  ->  writes a
        deterministic HVS-side asset manifest + appends SCOS-side correlation
        evidence (materialization ledger)  ->  consumes the approval.

Hard rules enforced here:

* COPY ONLY. No generation, transformation, transcoding, optimization,
  download, render, media assembly, voice generation, AI generation, or
  processing of any source asset. ``shutil.copyfile`` only.
* The source asset is NEVER modified, deleted, overwritten, moved, or renamed.
* No arbitrary destination paths are accepted; the destination is always a
  deterministic project-local path beneath the Stage 3 correlated HVS project
  root (``assets/<slot_type>/<sha256[:16]>-<safe_basename>``).
* Source roots must be injected/explicitly approved. Resolution requires
  ``resolved_path.relative_to(approved_root)``; symlink escapes, ``..``,
  absolute caller paths, UNC/network paths, URLs, device paths, and null bytes
  are rejected.
* The HVS target is resolved through the same slug-safety discipline as Stage 3
  (``projects/<pid>`` must not escape the injected HVS root).
* Approval is single-use per (approval_id, manifest identity): a persisted
  materialization record keyed to the approval_id is the consumption record.
* All filesystem mutation happens inside the ``HVSAssetMaterializer`` executor
  and the evidence/ledger appenders; the resolver, validator, approval
  evaluator, dry-run, and tests never write.
* ``created_at`` is intentionally the Stage 2 deterministic placeholder (None)
  — no wall-clock timestamp is ever invented.
* The passed approval object and all caller-supplied inputs are NEVER mutated.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no subprocess, no HVS import, no file I/O except the explicitly
injected approved source roots, the injected HVS root, and the SCOS
materialization ledger path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


try:
    from hvs_project_creation import (
        CONTRACT_VERSION,
        CORRELATION_LEDGER_SCHEMA_VERSION,
        CorrelationLedger,
        UnsafeTargetError,
        correlation_id_for,
    )
    from hvs_contract_models import (
        SCOSAssetRef,
        _reject_path_traversal,
        _sha256_hex16,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from .hvs_project_creation import (
        CONTRACT_VERSION,
        CORRELATION_LEDGER_SCHEMA_VERSION,
        CorrelationLedger,
        UnsafeTargetError,
        correlation_id_for,
    )
    from .hvs_contract_models import (
        SCOSAssetRef,
        _reject_path_traversal,
        _sha256_hex16,
    )

try:
    from agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterError,
        AgentAdapterResult,
    )
except ImportError:  # direct-module execution
    from .agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterError,
        AgentAdapterResult,
    )


# --- Contract identity -------------------------------------------------------
# Stage 4 builds on the Stage 3 contract version (same timeline contract).
STAGE4_CONTRACT_VERSION = CONTRACT_VERSION
STAGE4_SEMANTIC_VERSION = "1.0.0"

# On-disk HVS project subdir + asset-relative layout (relative to an HVS root).
HVS_PROJECTS_SUBDIR = "projects"
HVS_ASSETS_REL = "assets"
ASSET_MANIFEST_REL = f"{HVS_ASSETS_REL}/asset_manifest.stage4.json"

# Deterministic on-disk destination slug prefix (per Stage 3 discipline).
HVS_PROJECT_DIR_PREFIX = "hvs-"

# Allowed project-directory slug characters (alphanumerics, dash, underscore).
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Manifest / evidence ledger schema versions.
ASSET_MANIFEST_SCHEMA_VERSION = "scos-hvs.asset-materialization.v1/1.0.0"
MATERIALIZATION_LEDGER_SCHEMA_VERSION = 1

# Safe basename policy (project-local destination basename).
_SAFE_BASENAME_RE = re.compile(r"[^A-Za-z0-9._-]")

# Materialization status values recorded in the SCOS ledger.
MAT_CREATED = "created"
MAT_REUSED = "reused"
MAT_DENIED = "denied"
MAT_FAILED = "failed"

# Approval action type for this stage (distinct from Stage 3).
APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS = "materialize_hvs_assets"

# Allowed approval statuses (subset reused from Stage 3 conventions).
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"
APPROVAL_REJECTED = "rejected"
APPROVAL_EXPIRED = "expired"
APPROVAL_CONSUMED = "consumed"
APPROVAL_CANCELLED = "cancelled"
ALLOWED_APPROVAL_STATUSES = (
    APPROVAL_PENDING,
    APPROVAL_APPROVED,
    APPROVAL_REJECTED,
    APPROVAL_EXPIRED,
    APPROVAL_CONSUMED,
    APPROVAL_CANCELLED,
)

# Structured denial error kinds (explicit, deterministic taxonomy).
ERR_APPROVAL_REQUIRED = "approval_required"
ERR_APPROVAL_NOT_VALID = "approval_not_valid"
ERR_APPROVAL_ACTION_MISMATCH = "approval_action_mismatch"
ERR_APPROVAL_SCOPE_MISMATCH = "approval_scope_mismatch"
ERR_CORRELATION_NOT_FOUND = "correlation_not_found"
ERR_INVALID_ASSET_REFERENCE = "invalid_asset_reference"
ERR_UNSAFE_SOURCE_PATH = "unsafe_source_path"
ERR_UNSUPPORTED_ASSET_TYPE = "unsupported_asset_type"
ERR_SOURCE_ASSET_MISSING = "source_asset_missing"
ERR_SOURCE_ASSET_CHANGED = "source_asset_changed"
ERR_DESTINATION_CONFLICT = "destination_conflict"
ERR_UNSAFE_TARGET = "unsafe_target"
ERR_MATERIALIZATION_NOT_SUPPORTED = "materialization_not_supported"

# Canonical HVS slot-type -> accepted extension allow-list, derived from the
# observed HVS asset_slot conventions (Stage 7 placeholder pipeline). Stage 2's
# emitted asset_slots carry empty accepted_formats, so the effective allow-list
# is this canonical map. The allow-list is NEVER silently extended.
SLOT_TYPE_ACCEPTED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "background": (".png", ".jpg", ".jpeg", ".mp4"),
    "subject": (".png", ".jpg", ".jpeg", ".webp"),
    "overlay_text": (".srt", ".ass", ".txt"),
    "music_or_audio_placeholder": (".mp3", ".wav", ".m4a"),
    "optional_b_roll": (".mp4", ".mov"),
}


# ---------------------------------------------------------------------------
# Approved source-root policy model.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SourceRoot:
    """An explicitly approved local directory that may supply source assets.

    Only ``root_id`` + ``root_path`` are stored; resolution requires
    ``resolved_path.relative_to(Path(root_path).resolve())``. No absolute paths
    are ever persisted into SCOS ledger/manifest/results — only root_id +
    relative path are recorded.
    """

    root_id: str
    root_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_id", str(self.root_id))
        object.__setattr__(self, "root_path", str(self.root_path))

    def to_dict(self) -> dict[str, Any]:
        return {"root_id": self.root_id, "root_path": self.root_path}


def resolve_source_root(root: SourceRoot, *, require_exists: bool = True) -> Path:
    """Resolve an approved source root, rejecting unsafe roots eagerly.

    Rejects null bytes, UNC/network paths, device paths, and URLs in the
    configured root path. Raises AssetResolutionError on any policy violation.
    """
    raw = root.root_path
    if raw is None or raw == "":
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH, "source root path is empty", root_id=root.root_id
        )
    _assert_not_network_or_device(raw, root.root_id)
    if "\x00" in raw:
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH, "null byte in root path", root_id=root.root_id
        )
    resolved = Path(raw).resolve()
    if require_exists and not resolved.is_dir():
        raise AssetResolutionError(
            ERR_SOURCE_ASSET_MISSING,
            f"source root is not an existing directory: {resolved}",
            root_id=root.root_id,
        )
    return resolved


# ---------------------------------------------------------------------------
# Resolved asset model (Stage 4 internal, narrow).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedAsset:
    """A resolved + validated local source asset, ready for materialization.

    Absolute paths are NEVER persisted. Storage uses root_id + relative path.
    """

    source_asset_id: str
    source_relative_path: str
    source_root_id: str
    source_file_sha256: str
    source_size_bytes: int
    source_extension: str
    declared_slot_id: str
    declared_slot_type: str
    materialization_identity_hash: str
    intended_hvs_relative_path: str
    resolution_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset_id": self.source_asset_id,
            "source_relative_path": self.source_relative_path,
            "source_root_id": self.source_root_id,
            "source_file_sha256": self.source_file_sha256,
            "source_size_bytes": self.source_size_bytes,
            "source_extension": self.source_extension,
            "declared_slot_id": self.declared_slot_id,
            "declared_slot_type": self.declared_slot_type,
            "materialization_identity_hash": self.materialization_identity_hash,
            "intended_hvs_relative_path": self.intended_hvs_relative_path,
            "resolution_status": self.resolution_status,
        }


class AssetResolutionError(Exception):
    """Structured resolution/validation failure (kind + detail + context)."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        root_id: str | None = None,
        asset_id: str | None = None,
    ) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.root_id = root_id
        self.asset_id = asset_id


def _assert_not_network_or_device(value: str, ctx: str) -> None:
    """Reject UNC (\\\\), URLs (://), and device (\\\\.\\ or /dev/) paths.

    A plain relative or local absolute path (e.g. ``/c/foo`` or ``C:\\\\foo``)
    is permitted; only network/device/URL forms are rejected.
    """
    lowered = value.lower()
    if "://" in lowered:
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH, f"URL scheme in path is forbidden: {value!r}",
            root_id=ctx,
        )
    # UNC / device paths begin with \\ and are not the simple absolute form.
    if value.startswith("\\\\") or value.startswith("//"):
        # Allowed only if it is exactly a local absolute path expressed via /
        # drive mapping (handled elsewhere); bare // or \\ is UNC/network.
        if "://" not in lowered and not re.match(r"^//[A-Za-z]:", value):
            raise AssetResolutionError(
                ERR_UNSAFE_SOURCE_PATH, f"UNC/network path is forbidden: {value!r}",
                root_id=ctx,
            )
    if lowered.startswith("\\\\.\\") or lowered.startswith("//./"):
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH, f"device path is forbidden: {value!r}",
            root_id=ctx,
        )


def _safe_basename(name: str) -> str:
    """Sanitize a source basename into a project-local safe basename.

    Collapses ``..`` segments, strips directory separators, and replaces any
    character outside ``[A-Za-z0-9._-]`` with ``_``. Always returns a non-empty
    basename (falls back to ``asset``).
    """
    # Normalize separators and collapse traversal.
    norm = name.replace("\\", "/")
    parts = [p for p in norm.split("/") if p not in ("", ".", "..")]
    base = parts[-1] if parts else ""
    base = _SAFE_BASENAME_RE.sub("_", base)
    base = base[:128]
    if not base:
        base = "asset"
    return base


def _sha256_stream(path: Path) -> str:
    """Streamed, deterministic SHA-256 hexdigest (full, not truncated)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ext_for(path: Path) -> str:
    return path.suffix.lower()


# ---------------------------------------------------------------------------
# Asset resolution + validation.
# ---------------------------------------------------------------------------
def resolve_asset(
    asset_ref: SCOSAssetRef,
    *,
    source_root: SourceRoot,
    hvs_project_root: Path,
    hvs_project_id: str,
    correlation_id: str,
    require_sha256: str | None = None,
) -> ResolvedAsset:
    """Resolve + validate one Stage 2 asset reference against an approved root.

    Pure resolver: performs NO write. Raises ``AssetResolutionError`` on any
    policy violation (returns structured error kinds, no silent substitution).
    """
    if asset_ref is None or not getattr(asset_ref, "asset_id", ""):
        raise AssetResolutionError(
            ERR_INVALID_ASSET_REFERENCE, "asset reference missing asset_id"
        )
    asset_id = asset_ref.asset_id
    slot_type = asset_ref.asset_type
    declared_slot_id = asset_ref.asset_id  # slot id == scos asset id (Stage 2)

    # Reject unsafe declared path (Stage 2 path field) before any filesystem op.
    declared_path = getattr(asset_ref, "path", None)
    if declared_path is not None and declared_path != "":
        verdict = _reject_path_traversal(declared_path, "asset.path")
        if verdict == "path_traversal":
            raise AssetResolutionError(
                ERR_UNSAFE_SOURCE_PATH,
                f"asset {asset_id!r} declared path contains traversal",
                asset_id=asset_id,
            )

    if slot_type not in SLOT_TYPE_ACCEPTED_EXTENSIONS:
        raise AssetResolutionError(
            ERR_UNSUPPORTED_ASSET_TYPE,
            f"slot_type {slot_type!r} is not in the allow-list",
            asset_id=asset_id,
        )

    root_resolved = resolve_source_root(source_root, require_exists=True)

    # The source relative path is the Stage 2 asset.path; if empty, derive from
    # asset_id (never invent arbitrary paths). We REQUIRE an explicit relative
    # path for safety (no wildcard discovery outside approved roots).
    rel = declared_path
    if rel is None or rel == "":
        raise AssetResolutionError(
            ERR_INVALID_ASSET_REFERENCE,
            f"asset {asset_id!r} has no source relative path",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )
    # Normalize separators; reject any embedded traversal in the requested rel.
    rel_norm = rel.replace("\\", "/")
    if ".." in [seg for seg in rel_norm.split("/") if seg != ""]:
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH,
            f"asset {asset_id!r} relative path contains '..' traversal",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )
    if "\x00" in rel_norm:
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH,
            f"asset {asset_id!r} relative path contains null byte",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )

    candidate = (root_resolved / rel_norm).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH,
            f"asset {asset_id!r} resolves outside approved root",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )
    # Reject symlink escapes.
    if candidate.is_symlink():
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH,
            f"asset {asset_id!r} resolves through a symlink (escape risk)",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )

    if not candidate.exists():
        raise AssetResolutionError(
            ERR_SOURCE_ASSET_MISSING,
            f"source asset not found: {rel_norm}",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )
    if not candidate.is_file():
        raise AssetResolutionError(
            ERR_UNSAFE_SOURCE_PATH,
            f"source asset is not a regular file: {rel_norm}",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )
    size = candidate.stat().st_size
    if size <= 0:
        raise AssetResolutionError(
            ERR_SOURCE_ASSET_MISSING,
            f"source asset has non-positive size: {rel_norm}",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )

    ext = _ext_for(candidate)
    allowed = SLOT_TYPE_ACCEPTED_EXTENSIONS[slot_type]
    if ext not in allowed:
        raise AssetResolutionError(
            ERR_UNSUPPORTED_ASSET_TYPE,
            f"asset {asset_id!r} extension {ext!r} not allowed for slot "
            f"{slot_type!r} (expected {allowed})",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )

    sha = _sha256_stream(candidate)

    # Optional pinned SHA-256 (e.g. from a prior planning phase). A mismatch is
    # a hard failure (no silent substitution).
    if require_sha256 is not None and require_sha256 != sha:
        raise AssetResolutionError(
            ERR_SOURCE_ASSET_CHANGED,
            f"asset {asset_id!r} SHA-256 changed since approval "
            f"(expected {require_sha256}, got {sha})",
            asset_id=asset_id,
            root_id=source_root.root_id,
        )

    safe_base = _safe_basename(candidate.name)
    intended_rel = f"{HVS_ASSETS_REL}/{slot_type}/{sha[:16]}-{safe_base}"

    # Guard: intended destination must remain beneath the HVS project assets dir.
    hvs_root_resolved = Path(hvs_project_root).resolve()
    proj_assets = (
        hvs_root_resolved / HVS_PROJECTS_SUBDIR / hvs_project_id / HVS_ASSETS_REL
    ).resolve()
    dest = (proj_assets / f"{slot_type}/{sha[:16]}-{safe_base}").resolve()
    try:
        dest.relative_to(proj_assets)
    except ValueError:
        raise AssetResolutionError(
            ERR_UNSAFE_TARGET,
            f"intended destination escapes HVS project assets dir",
            asset_id=asset_id,
        )

    mid = _sha256_hex16(
        correlation_id,
        asset_id,
        source_root.root_id,
        rel_norm,
        sha,
        str(size),
        slot_type,
        intended_rel,
    )

    rel_for_storage = rel_norm
    if rel_for_storage.startswith("./"):
        rel_for_storage = rel_for_storage[2:]

    return ResolvedAsset(
        source_asset_id=asset_id,
        source_relative_path=rel_for_storage,
        source_root_id=source_root.root_id,
        source_file_sha256=sha,
        source_size_bytes=size,
        source_extension=ext,
        declared_slot_id=declared_slot_id,
        declared_slot_type=slot_type,
        materialization_identity_hash=mid,
        intended_hvs_relative_path=intended_rel,
        resolution_status="resolved",
    )


def asset_manifest_identity_hash(resolved: list[ResolvedAsset]) -> str:
    """Deterministic manifest identity over sorted per-asset identity hashes."""
    ids = sorted(r.materialization_identity_hash for r in resolved)
    return _sha256_hex16("|".join(ids))


# ---------------------------------------------------------------------------
# Approval model (Stage 4, narrow, explicit, auditable).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HVSAssetMaterializationApproval:
    """An explicit authorization to materialize approved assets into an HVS project.

    Distinct from Stage 3's ``create_hvs_project``: action_type is
    ``materialize_hvs_assets`` and the scope binds a correlation id, the asset
    manifest identity, and the exact approved roots + asset ids.

    All fields are caller-supplied (no clock / random). ``issued_at`` /
    ``expires_at`` are optional; expiry is only evaluated when an injectable
    ``clock`` is provided to the evaluator (deterministic, testable).
    """

    approval_id: str
    action_type: str
    status: str
    requested_correlation_id: str
    requested_scos_project_id: str
    requested_hvs_artifact_id: str
    requested_asset_manifest_identity_hash: str
    approved_source_root_ids: tuple[str, ...]
    approved_asset_ids: tuple[str, ...]
    issued_by: str
    issued_at: str | None = None
    expires_at: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", str(self.approval_id))
        object.__setattr__(self, "action_type", str(self.action_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(
            self, "requested_correlation_id", str(self.requested_correlation_id)
        )
        object.__setattr__(
            self, "requested_scos_project_id", str(self.requested_scos_project_id)
        )
        object.__setattr__(
            self, "requested_hvs_artifact_id", str(self.requested_hvs_artifact_id)
        )
        object.__setattr__(
            self,
            "requested_asset_manifest_identity_hash",
            str(self.requested_asset_manifest_identity_hash),
        )
        object.__setattr__(
            self,
            "approved_source_root_ids",
            tuple(str(x) for x in self.approved_source_root_ids),
        )
        object.__setattr__(
            self,
            "approved_asset_ids", tuple(str(x) for x in self.approved_asset_ids)
        )
        object.__setattr__(self, "issued_by", str(self.issued_by))
        object.__setattr__(self, "issued_at", _opt_str(self.issued_at))
        object.__setattr__(self, "expires_at", _opt_str(self.expires_at))
        object.__setattr__(self, "reason", _opt_str(self.reason))
        if self.status not in ALLOWED_APPROVAL_STATUSES:
            raise ValueError(
                f"status must be one of {ALLOWED_APPROVAL_STATUSES}, got "
                f"{self.status!r}"
            )
        if not self.action_type:
            raise ValueError("action_type must not be empty")

    @staticmethod
    def of(
        *,
        approval_id: str,
        requested_correlation_id: str,
        requested_scos_project_id: str,
        requested_hvs_artifact_id: str,
        requested_asset_manifest_identity_hash: str,
        approved_source_root_ids: Any,
        approved_asset_ids: Any,
        issued_by: str,
        status: str = APPROVAL_APPROVED,
        issued_at: str | None = None,
        expires_at: str | None = None,
        reason: str | None = None,
    ) -> "HVSAssetMaterializationApproval":
        return HVSAssetMaterializationApproval(
            approval_id=str(approval_id),
            action_type=APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS,
            status=status,
            requested_correlation_id=str(requested_correlation_id),
            requested_scos_project_id=str(requested_scos_project_id),
            requested_hvs_artifact_id=str(requested_hvs_artifact_id),
            requested_asset_manifest_identity_hash=str(
                requested_asset_manifest_identity_hash
            ),
            approved_source_root_ids=tuple(str(x) for x in approved_source_root_ids),
            approved_asset_ids=tuple(str(x) for x in approved_asset_ids),
            issued_by=str(issued_by),
            issued_at=issued_at,
            expires_at=expires_at,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HVSAssetMaterializationApproval":
        return cls(
            approval_id=str(d["approval_id"]),
            action_type=str(
                d.get("action_type", APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS)
            ),
            status=str(d["status"]),
            requested_correlation_id=str(d["requested_correlation_id"]),
            requested_scos_project_id=str(d["requested_scos_project_id"]),
            requested_hvs_artifact_id=str(d["requested_hvs_artifact_id"]),
            requested_asset_manifest_identity_hash=str(
                d["requested_asset_manifest_identity_hash"]
            ),
            approved_source_root_ids=tuple(
                str(x) for x in (d.get("approved_source_root_ids") or [])
            ),
            approved_asset_ids=tuple(
                str(x) for x in (d.get("approved_asset_ids") or [])
            ),
            issued_by=str(d.get("issued_by", d.get("issued_by_operator", ""))),
            issued_at=_opt_str(d.get("issued_at")),
            expires_at=_opt_str(d.get("expires_at")),
            reason=_opt_str(d.get("reason")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "approval_id": self.approval_id,
            "action_type": self.action_type,
            "status": self.status,
            "requested_correlation_id": self.requested_correlation_id,
            "requested_scos_project_id": self.requested_scos_project_id,
            "requested_hvs_artifact_id": self.requested_hvs_artifact_id,
            "requested_asset_manifest_identity_hash": (
                self.requested_asset_manifest_identity_hash
            ),
            "approved_source_root_ids": list(self.approved_source_root_ids),
            "approved_asset_ids": list(self.approved_asset_ids),
            "issued_by": self.issued_by,
        }
        if self.issued_at is not None:
            out["issued_at"] = self.issued_at
        if self.expires_at is not None:
            out["expires_at"] = self.expires_at
        if self.reason is not None:
            out["reason"] = self.reason
        return out


def _opt_str(v: Any) -> str | None:
    return None if v is None else str(v)


@dataclass(frozen=True)
class ApprovalEvaluation:
    """Result of evaluating a materialization approval against resolved assets."""

    granted: bool
    error_kind: str | None
    error_detail: str | None
    decision_metadata: tuple[tuple[str, str], ...] = ()

    def metadata_pairs(self) -> tuple[tuple[str, str], ...]:
        return self.decision_metadata


# ---------------------------------------------------------------------------
# SCOS-side materialization evidence ledger (append-only, authoritative).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MaterializationRecord:
    """One append-only SCOS-side materialization evidence row.

    Records only relative destination paths + fingerprints (no absolute source
    paths, no secrets). The persistence of this record for a not-yet-consumed
    approval is the approval-consumption record.
    """

    materialization_id: str
    correlation_id: str
    contract_version: str
    scos_project_id: str
    hvs_artifact_id: str
    hvs_project_id: str
    approval_id: str
    manifest_identity_hash: str
    materialization_status: str
    asset_fingerprints: tuple[tuple[str, str, str], ...]  # (asset_id, sha, rel_dest)
    schema_version: int = MATERIALIZATION_LEDGER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "materialization_id": self.materialization_id,
            "correlation_id": self.correlation_id,
            "contract_version": self.contract_version,
            "scos_project_id": self.scos_project_id,
            "hvs_artifact_id": self.hvs_artifact_id,
            "hvs_project_id": self.hvs_project_id,
            "approval_id": self.approval_id,
            "manifest_identity_hash": self.manifest_identity_hash,
            "materialization_status": self.materialization_status,
            "asset_fingerprints": [
                {"asset_id": a, "sha256": s, "destination_relative_path": d}
                for (a, s, d) in self.asset_fingerprints
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MaterializationRecord":
        fps = tuple(
            (f["asset_id"], f["sha256"], f["destination_relative_path"])
            for f in d.get("asset_fingerprints", [])
        )
        return cls(
            materialization_id=str(d["materialization_id"]),
            correlation_id=str(d["correlation_id"]),
            contract_version=str(d["contract_version"]),
            scos_project_id=str(d["scos_project_id"]),
            hvs_artifact_id=str(d["hvs_artifact_id"]),
            hvs_project_id=str(d["hvs_project_id"]),
            approval_id=str(d["approval_id"]),
            manifest_identity_hash=str(d["manifest_identity_hash"]),
            materialization_status=str(d["materialization_status"]),
            asset_fingerprints=fps,
            schema_version=int(
                d.get("schema_version", MATERIALIZATION_LEDGER_SCHEMA_VERSION)
            ),
        )


class MaterializationLedger:
    """Append-only JSONL materialization ledger (SCOS authoritative)."""

    def __init__(self, ledger_path: str | Path) -> None:
        self._path = Path(ledger_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: MaterializationRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
        with open(self._path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")

    def all(self) -> list[MaterializationRecord]:
        if not self._path.exists():
            return []
        records: list[MaterializationRecord] = []
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(MaterializationRecord.from_dict(json.loads(line)))
        return records

    def find_by_approval(self, approval_id: str) -> list[MaterializationRecord]:
        return [r for r in self.all() if r.approval_id == approval_id]


# ---------------------------------------------------------------------------
# HVS-side materialization manifest builder + executor (THE ONLY write sites).
# ---------------------------------------------------------------------------
def _build_hvs_asset_manifest(
    *,
    correlation_id: str,
    hvs_project_id: str,
    hvs_artifact_id: str,
    manifest_identity_hash: str,
    resolved: list[ResolvedAsset],
    source_root_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Build the deterministic HVS-side asset manifest (no absolute paths)."""
    assets = []
    for r in resolved:
        # Determine per-asset status: reused if destination already byte-matches.
        assets.append(
            {
                "source_asset_id": r.source_asset_id,
                "slot_id": r.declared_slot_id,
                "slot_type": r.declared_slot_type,
                "source_root_id": r.source_root_id,
                "source_relative_path": r.source_relative_path,
                "source_sha256": r.source_file_sha256,
                "source_size_bytes": r.source_size_bytes,
                "source_extension": r.source_extension,
                "materialization_identity_hash": r.materialization_identity_hash,
                "destination_relative_path": r.intended_hvs_relative_path,
                "status": "materialized",  # refined by executor post-copy
            }
        )
    return {
        "schema_version": ASSET_MANIFEST_SCHEMA_VERSION,
        "contract_version": ASSET_MANIFEST_SCHEMA_VERSION,
        "semantic_version": STAGE4_SEMANTIC_VERSION,
        "correlation_id": correlation_id,
        "hvs_project_id": hvs_project_id,
        "hvs_artifact_id": hvs_artifact_id,
        "asset_manifest_identity_hash": manifest_identity_hash,
        "approved_source_root_ids": list(source_root_ids),
        "asset_count": len(assets),
        "assets": assets,
        "created_at": None,  # Stage 2 placeholder: no clock invented.
    }


class HVSAssetMaterializer:
    """Single approved materialization executor. Copies approved assets.

    All filesystem mutation happens here and only here. Copy-only
    (``shutil.copyfile``); no transform/render/network. Idempotent: an existing
    byte-identical destination is reused; a mismatched destination fails.
    """

    def __init__(self, hvs_root: str | Path) -> None:
        self._hvs_root = Path(hvs_root)

    def _project_assets_dir(self, hvs_project_id: str) -> Path:
        if not _SLUG_RE.match(hvs_project_id):
            raise UnsafeTargetError(
                f"hvs_project_id contains unsafe characters: {hvs_project_id!r}"
            )
        root = self._hvs_root.resolve()
        projects_dir = (root / HVS_PROJECTS_SUBDIR).resolve()
        proj_dir = (projects_dir / hvs_project_id).resolve()
        try:
            proj_dir.relative_to(projects_dir)
        except ValueError:
            raise UnsafeTargetError(
                f"hvs_project_id escapes approved root: {hvs_project_id!r}"
            )
        if not proj_dir.exists():
            raise UnsafeTargetError(
                f"HVS project dir does not exist: {hvs_project_id!r}"
            )
        return (proj_dir / HVS_ASSETS_REL).resolve()

    def _dest_path(self, assets_dir: Path, resolved: ResolvedAsset) -> Path:
        dest = (assets_dir / resolved.intended_hvs_relative_path).resolve()
        # Hard containment check (defense in depth).
        try:
            dest.relative_to(assets_dir)
        except ValueError:
            raise UnsafeTargetError(
                f"destination escapes project assets dir: "
                f"{resolved.intended_hvs_relative_path!r}"
            )
        return dest

    def _exists_matching(self, dest: Path, sha: str) -> str | None:
        """Return status for an existing destination: 'reused' if byte-match,
        raise destination_conflict if mismatched (different SHA)."""
        if not dest.exists():
            return None
        if not dest.is_file():
            raise AssetResolutionError(
                ERR_DESTINATION_CONFLICT,
                f"destination exists but is not a regular file: {dest}",
            )
        try:
            existing_sha = _sha256_stream(dest)
        except OSError as exc:
            raise AssetResolutionError(
                ERR_DESTINATION_CONFLICT,
                f"could not read existing destination: {exc}",
            )
        if existing_sha != sha:
            raise AssetResolutionError(
                ERR_DESTINATION_CONFLICT,
                f"destination exists with different SHA-256 "
                f"(expected {sha}, found {existing_sha})",
            )
        return "reused"

    def materialize(
        self,
        hvs_project_id: str,
        resolved: list[ResolvedAsset],
        source_roots_by_id: dict[str, SourceRoot],
    ) -> tuple[list[tuple[ResolvedAsset, str]], bool]:
        """Copy approved assets. Returns (per-asset (resolved, status), any_created).

        ``status`` is 'created' or 'reused'. Raises on any destination conflict
        BEFORE copying, so a conflict leaves the operation cleanly aborted.
        ``source_roots_by_id`` maps root_id -> SourceRoot to locate the file.
        """
        assets_dir = self._project_assets_dir(hvs_project_id)
        results: list[tuple[ResolvedAsset, str]] = []
        any_created = False
        # Phase A: pre-check all destinations for conflicts (atomic-ish gate).
        planned: list[tuple[ResolvedAsset, Path, str | None]] = []
        for r in resolved:
            dest = self._dest_path(assets_dir, r)
            pre = self._exists_matching(dest, r.source_file_sha256)
            planned.append((r, dest, pre))
        # Phase B: copy (resume-safe: skip already-matching).
        for r, dest, pre in planned:
            if pre == "reused":
                results.append((r, "reused"))
                continue
            root = source_roots_by_id.get(r.source_root_id)
            if root is None:
                raise AssetResolutionError(
                    ERR_UNSAFE_SOURCE_PATH,
                    f"approved source root missing for {r.source_root_id!r}",
                    root_id=r.source_root_id,
                    asset_id=r.source_asset_id,
                )
            src = (Path(root.root_path).resolve() / r.source_relative_path).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copy-only, byte-exact. Source is never modified.
            shutil.copyfile(src, dest)
            if not dest.exists() or _sha256_stream(dest) != r.source_file_sha256:
                raise AssetResolutionError(
                    ERR_MATERIALIZATION_NOT_SUPPORTED,
                    f"copy verification failed for {r.source_asset_id!r}",
                    asset_id=r.source_asset_id,
                )
            any_created = True
            results.append((r, "created"))
        return results, any_created


# ---------------------------------------------------------------------------
# Approval evaluation (all 9+ conditions).
# ---------------------------------------------------------------------------
def _evaluate_materialization_approval(
    approval: HVSAssetMaterializationApproval,
    *,
    correlation_id: str,
    scos_project_id: str,
    hvs_artifact_id: str,
    manifest_identity_hash: str,
    resolved: list[ResolvedAsset],
    approved_root_ids: tuple[str, ...],
    clock: Callable[[], str] | None = None,
) -> ApprovalEvaluation:
    if approval is None:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_REQUIRED, "no approval supplied",
            (("reason", "missing_approval"),),
        )
    meta: list[tuple[str, str]] = [("approval_id", approval.approval_id)]
    if approval.status != APPROVAL_APPROVED:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_NOT_VALID,
            f"approval status is {approval.status!r}, expected 'approved'",
            tuple(meta) + (("status", approval.status),),
        )
    if approval.action_type != APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_ACTION_MISMATCH,
            f"approval action_type is {approval.action_type!r}, expected "
            f"{APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS!r}",
            tuple(meta) + (("action_type", approval.action_type),),
        )
    if approval.requested_correlation_id != correlation_id:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval correlation id does not match resolved correlation",
            tuple(meta) + (
                ("requested", approval.requested_correlation_id),
                ("resolved", correlation_id),
            ),
        )
    if approval.requested_scos_project_id != scos_project_id:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval SCOS project id does not match",
            tuple(meta) + (
                ("requested", approval.requested_scos_project_id),
                ("resolved", scos_project_id),
            ),
        )
    if approval.requested_hvs_artifact_id != hvs_artifact_id:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval HVS artifact id does not match",
            tuple(meta) + (
                ("requested", approval.requested_hvs_artifact_id),
                ("resolved", hvs_artifact_id),
            ),
        )
    if approval.requested_asset_manifest_identity_hash != manifest_identity_hash:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval asset manifest identity does not match resolved manifest",
            tuple(meta) + (
                ("requested", approval.requested_asset_manifest_identity_hash),
                ("resolved", manifest_identity_hash),
            ),
        )
    # Every approved root must be present.
    approved_roots_set = set(approval.approved_source_root_ids)
    for root_id in approved_root_ids:
        if root_id not in approved_roots_set:
            return ApprovalEvaluation(
                False, ERR_APPROVAL_SCOPE_MISMATCH,
                f"source root {root_id!r} is not in the approval scope",
                tuple(meta) + (("unapproved_root", root_id),),
            )
    # Every resolved asset id must be approved.
    approved_assets_set = set(approval.approved_asset_ids)
    for r in resolved:
        if r.source_asset_id not in approved_assets_set:
            return ApprovalEvaluation(
                False, ERR_APPROVAL_SCOPE_MISMATCH,
                f"asset {r.source_asset_id!r} is not in the approval scope",
                tuple(meta) + (("unapproved_asset", r.source_asset_id),),
            )
    if approval.expires_at is not None and clock is not None:
        now = clock()
        if now >= approval.expires_at:
            return ApprovalEvaluation(
                False, ERR_APPROVAL_NOT_VALID,
                f"approval expired at {approval.expires_at!r} (now {now!r})",
                tuple(meta) + (("expires_at", approval.expires_at), ("now", now)),
            )
    return ApprovalEvaluation(True, None, None, tuple(meta))


# ---------------------------------------------------------------------------
# Public Stage 4 API.
# ---------------------------------------------------------------------------
@dataclass
class HVSAssetMaterializationOutcome:
    """Structured result of a Stage 4 materialization request."""

    ok: bool
    materialization_status: str
    correlation_id: str
    scos_project_id: str
    hvs_artifact_id: str
    hvs_project_id: str | None
    manifest_identity_hash: str
    resolved_assets: tuple[ResolvedAsset, ...]
    per_asset_status: tuple[tuple[str, str], ...]  # (asset_id, status)
    materialization_record: MaterializationRecord | None
    approval_decision: dict[str, Any]
    hvs_manifest: dict[str, Any] | None
    would_materialize: bool
    dry_run: bool
    error_kind: str | None = None
    error_detail: str | None = None
    failed_step: str | None = None

    def to_adapter_result(self) -> AgentAdapterResult:
        meta = (
            ("stage", "scos-hvs-stage4"),
            ("materialization_status", self.materialization_status),
            ("correlation_id", self.correlation_id),
            ("scos_project_id", self.scos_project_id),
            ("hvs_artifact_id", self.hvs_artifact_id),
            ("hvs_project_id", self.hvs_project_id or ""),
            ("manifest_identity_hash", self.manifest_identity_hash),
            ("would_materialize", str(self.would_materialize)),
            ("dry_run", str(self.dry_run)),
            ("approval_id", self.approval_decision.get("approval_id", "")),
        )
        if self.error_kind is not None:
            meta = meta + (("error_kind", self.error_kind),)
        rid = _sha256_hex16(
            self.correlation_id,
            self.manifest_identity_hash,
            self.materialization_status,
            str(self.would_materialize),
        )
        return AgentAdapterResult.of(
            result_id=f"hvs-materialize-{rid}",
            request_id=self.scos_project_id,
            session_id="scos-hvs-stage4",
            agent_name="hermes_video_studio",
            runtime_id="hvs_asset_materialization",
            status="result_ready" if self.ok else "failed",
            result_type="hvs_asset_materialization",
            result_summary=(
                "HVS asset materialization plan evaluated"
                if self.dry_run
                else f"HVS assets {self.materialization_status}"
            ),
            created_at=self.correlation_id,
            next_action=(
                "no mutation (dry-run)"
                if self.dry_run
                else "manifest + evidence recorded"
            ),
            metadata=meta,
        )

    def to_adapter_error(self) -> AgentAdapterError:
        meta = (
            ("stage", "scos-hvs-stage4"),
            ("materialization_status", self.materialization_status),
            ("correlation_id", self.correlation_id),
            ("scos_project_id", self.scos_project_id),
            ("hvs_artifact_id", self.hvs_artifact_id),
            ("approval_id", self.approval_decision.get("approval_id", "")),
            ("would_materialize", str(self.would_materialize)),
            ("dry_run", str(self.dry_run)),
        )
        return AgentAdapterError.of(
            self.error_kind or "materialization_denied",
            self.error_detail or "materialization request denied",
            self.failed_step or "materialize_hvs_assets",
            request_id=self.scos_project_id,
            metadata=meta,
        )


def _fetch_correlation(
    correlation_ledger_path: str | Path,
    correlation_id: str,
    *,
    require_active: bool = True,
):
    ledger = CorrelationLedger(correlation_ledger_path)
    rec = ledger.find_by_correlation_id(correlation_id)
    if rec is None:
        return None
    if require_active and rec.creation_status not in ("created", "reused"):
        return None
    return rec


def materialize_hvs_assets(
    *,
    correlation_id: str,
    asset_refs: list[SCOSAssetRef],
    source_roots: list[SourceRoot],
    approval: HVSAssetMaterializationApproval | dict[str, Any],
    hvs_root: str | Path,
    correlation_ledger_path: str | Path,
    materialization_ledger_path: str | Path,
    requested_by: str,
    dry_run: bool = False,
    clock: Callable[[], str] | None = None,
) -> HVSAssetMaterializationOutcome:
    """Stage 4 public API: approval-gated, copy-only HVS asset materialization.

    Flow:
      1. Resolve the Stage 3 correlation (must be an active Stage 3 project).
      2. Resolve + validate each asset ref against the approved source roots.
      3. Compute the deterministic asset manifest identity hash.
      4. Evaluate the explicit materialize_hvs_assets approval (all conditions).
      5. Enforce idempotency / conflict rules against the materialization ledger.
      6. dry_run=True  -> returns plan + decision; ZERO writes (no HVS copy, no
                          manifest, no ledger, no approval consumption).
      7. approved      -> copies approved assets (byte-exact, resume-safe),
                          writes the HVS asset manifest, appends SCOS evidence,
                          and consumes the approval (record persists).
      8. denied        -> structured error; ZERO writes; approval remains reusable.

    The caller-supplied ``hvs_root`` is the ONLY HVS location written (tests use
    an isolated temp root; the real HVS repository is never touched).
    """
    # Normalize approval input (never mutate caller's object).
    if isinstance(approval, dict):
        approval = HVSAssetMaterializationApproval.from_dict(approval)

    if not correlation_id:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id="",
            scos_project_id="",
            hvs_artifact_id="",
            hvs_project_id=None,
            manifest_identity_hash="",
            resolved_assets=(),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
            error_kind=ERR_CORRELATION_NOT_FOUND,
            error_detail="correlation_id is required",
            failed_step="resolve_correlation",
        )

    # --- 1) Resolve Stage 3 correlation (must be active) -------------------
    corr = _fetch_correlation(correlation_ledger_path, correlation_id)
    if corr is None:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id="",
            hvs_artifact_id="",
            hvs_project_id=None,
            manifest_identity_hash="",
            resolved_assets=(),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
            error_kind=ERR_CORRELATION_NOT_FOUND,
            error_detail=(
                "no active Stage 3 correlation found for "
                f"{correlation_id!r}"
            ),
            failed_step="resolve_correlation",
        )

    scos_project_id = corr.scos_project_id
    hvs_artifact_id = corr.hvs_artifact_id
    hvs_project_id = corr.hvs_project_id

    # --- 2) Resolve + validate each asset ----------------------------------
    roots_by_id = {r.root_id: r for r in source_roots}
    resolved: list[ResolvedAsset] = []
    try:
        for ref in asset_refs:
            # Map each asset to its approved root: a slot may be approved under
            # any approved root; we resolve against each approved root in order
            # and require the file to live under exactly one approved root.
            matched: ResolvedAsset | None = None
            last_err: AssetResolutionError | None = None
            for r in source_roots:
                try:
                    cand = resolve_asset(
                        ref,
                        source_root=r,
                        hvs_project_root=Path(hvs_root),
                        hvs_project_id=hvs_project_id,
                        correlation_id=correlation_id,
                    )
                    if matched is not None and matched.source_root_id != r.root_id:
                        # Ambiguous: resolves under multiple approved roots.
                        raise AssetResolutionError(
                            ERR_UNSAFE_SOURCE_PATH,
                            f"asset {ref.asset_id!r} resolves under multiple "
                            "approved roots; disambiguate by exact root",
                            asset_id=ref.asset_id,
                        )
                    matched = cand
                    break
                except AssetResolutionError as exc:
                    if exc.kind != ERR_SOURCE_ASSET_MISSING:
                        # A hard policy rejection (unsafe/unsupported/changed)
                        # must not be masked by trying other roots.
                        raise
                    last_err = exc
            if matched is None:
                if last_err is not None:
                    raise last_err
                raise AssetResolutionError(
                    ERR_SOURCE_ASSET_MISSING,
                    f"asset {ref.asset_id!r} not found in any approved root",
                    asset_id=ref.asset_id,
                )
            resolved.append(matched)
    except AssetResolutionError as exc:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash="",
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
            error_kind=exc.kind,
            error_detail=exc.detail,
            failed_step="resolve_assets",
        )

    manifest_identity_hash = asset_manifest_identity_hash(resolved)
    approved_root_ids = tuple(sorted(r.root_id for r in source_roots))

    # --- 4) Evaluate approval (all conditions) -----------------------------
    eval_result = _evaluate_materialization_approval(
        approval,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        manifest_identity_hash=manifest_identity_hash,
        resolved=resolved,
        approved_root_ids=approved_root_ids,
        clock=clock,
    )
    if not eval_result.granted:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
            error_kind=eval_result.error_kind,
            error_detail=eval_result.error_detail,
            failed_step="evaluate_approval",
        )

    # --- 5) Idempotency / conflict rules ----------------------------------
    mat_ledger = MaterializationLedger(materialization_ledger_path)
    existing_same = [
        r
        for r in mat_ledger.all()
        if r.correlation_id == correlation_id
        and r.manifest_identity_hash == manifest_identity_hash
        and r.materialization_status in (MAT_CREATED, MAT_REUSED)
    ]
    if existing_same:
        # Same approved semantic asset set already materialized -> idempotent.
        prev = existing_same[0]
        return HVSAssetMaterializationOutcome(
            ok=True,
            materialization_status=MAT_REUSED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=tuple(
                (fp[0], "reused") for fp in prev.asset_fingerprints
            ),
            materialization_record=prev,
            approval_decision=approval.to_dict(),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
        )

    # Divergent asset set for an active correlation (different manifest id):
    # documented conflict rule -> destination_conflict (no partial overwrite).
    divergent = [
        r
        for r in mat_ledger.all()
        if r.correlation_id == correlation_id
        and r.manifest_identity_hash != manifest_identity_hash
        and r.materialization_status in (MAT_CREATED, MAT_REUSED)
    ]
    if divergent:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=approval.to_dict(),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=dry_run,
            error_kind=ERR_DESTINATION_CONFLICT,
            error_detail=(
                "a divergent asset set is already materialized for this "
                f"correlation ({divergent[0].materialization_id}); "
                "re-materialization of a different set is not supported"
            ),
            failed_step="evaluate_divergent_conflict",
        )

    # --- 6) dry-run: no writes ---------------------------------------------
    if dry_run:
        return HVSAssetMaterializationOutcome(
            ok=True,
            materialization_status="planned",
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=tuple(
                (r.source_asset_id, "planned") for r in resolved
            ),
            materialization_record=None,
            approval_decision=approval.to_dict(),
            hvs_manifest=_build_hvs_asset_manifest(
                correlation_id=correlation_id,
                hvs_project_id=hvs_project_id,
                hvs_artifact_id=hvs_artifact_id,
                manifest_identity_hash=manifest_identity_hash,
                resolved=resolved,
                source_root_ids=approved_root_ids,
            ),
            would_materialize=True,
            dry_run=True,
        )

    # --- 7) Approved execution: copy + manifest + evidence ----------------
    materializer = HVSAssetMaterializer(hvs_root)
    try:
        results, _any_created = materializer.materialize(
            hvs_project_id, resolved, roots_by_id
        )
    except AssetResolutionError as exc:
        # Pre-copy or mid-copy conflict: approval remains reusable (no record).
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=approval.to_dict(),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=False,
            error_kind=exc.kind,
            error_detail=exc.detail,
            failed_step="materialize_assets",
        )
    except UnsafeTargetError as exc:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_DENIED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=approval.to_dict(),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=False,
            error_kind=ERR_UNSAFE_TARGET,
            error_detail=str(exc),
            failed_step="materialize_assets",
        )

    # Refine per-asset status in the manifest.
    status_by_asset = {a.source_asset_id: s for (a, s) in results}
    hvs_manifest = _build_hvs_asset_manifest(
        correlation_id=correlation_id,
        hvs_project_id=hvs_project_id,
        hvs_artifact_id=hvs_artifact_id,
        manifest_identity_hash=manifest_identity_hash,
        resolved=resolved,
        source_root_ids=approved_root_ids,
    )
    for a in hvs_manifest["assets"]:
        a["status"] = status_by_asset.get(a["source_asset_id"], "materialized")

    # Write HVS-side manifest (the only HVS mutation).
    try:
        assets_dir = (
            Path(hvs_root).resolve()
            / HVS_PROJECTS_SUBDIR
            / hvs_project_id
            / HVS_ASSETS_REL
        ).resolve()
        manifest_path = assets_dir / "asset_manifest.stage4.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(hvs_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return HVSAssetMaterializationOutcome(
            ok=False,
            materialization_status=MAT_FAILED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            manifest_identity_hash=manifest_identity_hash,
            resolved_assets=tuple(resolved),
            per_asset_status=(),
            materialization_record=None,
            approval_decision=approval.to_dict(),
            hvs_manifest=None,
            would_materialize=False,
            dry_run=False,
            error_kind=ERR_MATERIALIZATION_NOT_SUPPORTED,
            error_detail=f"failed to write HVS manifest: {exc}",
            failed_step="write_hvs_manifest",
        )

    # Append SCOS-side evidence (this is the approval-consumption record).
    fingerprints = tuple(
        (r.source_asset_id, r.source_file_sha256, r.intended_hvs_relative_path)
        for r in resolved
    )
    mat_id = f"mat-{manifest_identity_hash}"
    overall_status = MAT_REUSED if all(s == "reused" for _, s in results) else MAT_CREATED
    record = MaterializationRecord(
        materialization_id=mat_id,
        correlation_id=correlation_id,
        contract_version=STAGE4_CONTRACT_VERSION,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        hvs_project_id=hvs_project_id,
        approval_id=approval.approval_id,
        manifest_identity_hash=manifest_identity_hash,
        materialization_status=overall_status,
        asset_fingerprints=fingerprints,
    )
    mat_ledger.append(record)

    return HVSAssetMaterializationOutcome(
        ok=True,
        materialization_status=overall_status,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        hvs_project_id=hvs_project_id,
        manifest_identity_hash=manifest_identity_hash,
        resolved_assets=tuple(resolved),
        per_asset_status=tuple(
            (a.source_asset_id, s) for (a, s) in results
        ),
        materialization_record=record,
        approval_decision=approval.to_dict(),
        hvs_manifest=hvs_manifest,
        would_materialize=(overall_status == MAT_CREATED),
        dry_run=False,
    )


__all__ = [
    "STAGE4_CONTRACT_VERSION",
    "ASSET_MANIFEST_SCHEMA_VERSION",
    "MATERIALIZATION_LEDGER_SCHEMA_VERSION",
    "APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS",
    "ALLOWED_APPROVAL_STATUSES",
    "MAT_CREATED",
    "MAT_REUSED",
    "MAT_DENIED",
    "MAT_FAILED",
    "ERR_APPROVAL_REQUIRED",
    "ERR_APPROVAL_NOT_VALID",
    "ERR_APPROVAL_ACTION_MISMATCH",
    "ERR_APPROVAL_SCOPE_MISMATCH",
    "ERR_CORRELATION_NOT_FOUND",
    "ERR_INVALID_ASSET_REFERENCE",
    "ERR_UNSAFE_SOURCE_PATH",
    "ERR_UNSUPPORTED_ASSET_TYPE",
    "ERR_SOURCE_ASSET_MISSING",
    "ERR_SOURCE_ASSET_CHANGED",
    "ERR_DESTINATION_CONFLICT",
    "ERR_UNSAFE_TARGET",
    "ERR_MATERIALIZATION_NOT_SUPPORTED",
    "SourceRoot",
    "ResolvedAsset",
    "AssetResolutionError",
    "resolve_asset",
    "asset_manifest_identity_hash",
    "HVSAssetMaterializationApproval",
    "ApprovalEvaluation",
    "MaterializationRecord",
    "MaterializationLedger",
    "HVSAssetMaterializer",
    "HVSAssetMaterializationOutcome",
    "materialize_hvs_assets",
]
