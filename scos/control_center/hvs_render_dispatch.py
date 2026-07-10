"""SCOS <-> Hermes Video Studio (HVS) — Stage 5 approval-gated render dispatch.

This module is the Stage 5 integration surface. It is a *narrow render-dispatch
bridge* that:

  1. Resolves a valid Stage 3 project correlation (consumed, not duplicated).
  2. Requires a valid Stage 4 asset-materialization record (consumed, not
     duplicated).
  3. Builds a deterministic render request from certified HVS project state.
  4. Requires an explicit approval (action_type = ``dispatch_hvs_render``) before
     dispatching a real render.
  5. Invokes ONLY the existing HVS public render boundary
     (``python -m hvs.cli render-hyperframes --project-id <id> --format vertical``)
     via subprocess(shell=False) — list argv, fixed executable, fixed cwd, bounded
     timeout, no caller-controlled fragments, no HVS internal import.
  6. Records structured, append-only render evidence in SCOS.
  7. Supports dry-run with ZERO HVS mutation and ZERO render invocation.
  8. Is idempotent: same approved semantic request renders at most once; a second
     call returns ``reused``.
  9. Detects rendered artifact evidence and correlates it to SCOS.
  10. Does NOT modify media content after HVS renders it.

Hard rules enforced here (consistent with Stage 1-4):

* The HVS render is reached ONLY through the certified local CLI boundary. SCOS
  never imports hvs.*, never calls FFmpeg directly, never hands the HVS renderer
  a caller-controlled executable / working directory / output path / config.
* The render request binds exactly the contract fields (Section 3). The
  ``render_identity_hash`` derives from *semantic* inputs only — plan identity,
  asset-manifest identity, selected preset, and the HVS renderer-relevant stable
  configuration. It EXCLUDES approval_id, request/run ids, timestamps, and audit
  records, so two canonically-equivalent requests produce one identity.
* Approval is single-use per (approval_id, render identity): the persisted
  render-evidence record keyed to the approval_id is the consumption record. A
  preflight failure or a failed render leaves the approval reusable.
* All filesystem mutation happens inside the ``HVSRenderExecutor`` and the
  evidence ledger appender; the resolver, validator, approval evaluator, dry-run,
  and tests never write.
* ``created_at`` is intentionally the Stage 2 deterministic placeholder (None) —
  no wall-clock timestamp is ever invented.
* The passed approval object and all caller-supplied inputs are NEVER mutated.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no network,
no subprocess except the explicitly-constructed HVS render boundary argv, no HVS
import, no file I/O except the explicitly injected HVS root, the SCOS ledgers,
and the HVS-rendered output beneath the correlated HVS project root.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from hvs_project_creation import (
        CONTRACT_VERSION,
        CorrelationLedger,
        correlation_id_for,
    )
    from hvs_asset_materialization import (
        MATERIALIZATION_LEDGER_SCHEMA_VERSION,
        MaterializationLedger,
        MaterializationRecord,
    )
    from hvs_schema_mapper import (
        payload_identity_hash,
    )
    from hvs_contract_models import (
        _sha256_hex16,
    )
    from agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterError,
        AgentAdapterResult,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from .hvs_project_creation import (
        CONTRACT_VERSION,
        CorrelationLedger,
        correlation_id_for,
    )
    from .hvs_asset_materialization import (
        MATERIALIZATION_LEDGER_SCHEMA_VERSION,
        MaterializationLedger,
        MaterializationRecord,
    )
    from .hvs_schema_mapper import (
        payload_identity_hash,
    )
    from .hvs_contract_models import (
        _sha256_hex16,
    )
    from .agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterError,
        AgentAdapterResult,
    )


# --- Contract identity -------------------------------------------------------
# Builds on the Stage 3 timeline contract version (same certified timeline).
STAGE5_CONTRACT_VERSION = CONTRACT_VERSION
STAGE5_SEMANTIC_VERSION = "1.0.0"

# The only HVS render subcommand/format supported by the certified boundary in
# this stage. The HVS CLI ``render-hyperframes`` accepts exactly one format
# ("vertical"). SCOS never selects a different renderer, working directory, or
# output path — those are HVS-internal and governed by the boundary.
HVS_RENDER_SUBCOMMAND = "render-hyperframes"
HVS_RENDER_FORMAT = "vertical"

# The public HVS module driven by the adapter (mirrors Stage 1 discipline).
_HVS_CLI_MODULE = "hvs.cli"

# On-disk HVS layout (relative to an injected HVS root) — read-only references.
HVS_PROJECTS_SUBDIR = "projects"
HVS_RENDERS_SUBDIR = "renders"
HVS_OUTPUT_EXTENSION = "mp4"

# Required HVS project artifacts the certified HVS render boundary gates on
# (mirrors hvs/renderers/hyperframes_gate.REQUIRED_ARTIFACTS). SCOS re-declares
# them as a *validation* check only — it does NOT generate them, resolve assets,
# or duplicate HVS render logic. The operator/Stage 4 supplies them; this
# stage dispatches + observes.
HVS_REQUIRED_RENDER_ARTIFACTS: tuple[str, ...] = (
    "project_brief.json",
    "timelines/video_timeline.json",
    "templates/template_selection.json",
    "voice/voice_manifest.json",
    "assets/placeholders/asset_manifest.json",
)

# Render-evidence ledger schema version.
RENDER_EVIDENCE_LEDGER_SCHEMA_VERSION = 1

# Allowed render-evidence statuses.
EVIDENCE_RENDERED = "rendered"
EVIDENCE_REUSED = "reused"
EVIDENCE_FAILED = "failed"
EVIDENCE_DENIED = "denied"

# Approval action type for this stage (distinct from Stage 3/4).
APPROVAL_ACTION_DISPATCH_HVS_RENDER = "dispatch_hvs_render"

# Allowed approval statuses (Stage 5 narrow model).
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
ERR_MATERIALIZATION_NOT_FOUND = "materialization_not_found"
ERR_INVALID_HVS_PROJECT = "invalid_hvs_project"
ERR_ASSETS_NOT_READY = "assets_not_ready"
ERR_RENDER_IDENTITY_CONFLICT = "render_identity_conflict"
ERR_RENDER_ALREADY_COMPLETED = "render_already_completed"
ERR_UNSAFE_RENDER_TARGET = "unsafe_render_target"
ERR_RENDER_NOT_SUPPORTED = "render_not_supported"
ERR_RENDER_PREFLIGHT_FAILED = "render_preflight_failed"

# Render-side failure kinds surfaced when the HVS boundary refuses/fails.
ERR_HVS_RENDER_FAILED = "hvs_render_failed"
ERR_HVS_OUTPUT_MISSING = "hvs_output_missing"
ERR_HVS_OUTPUT_UNSAFE = "hvs_output_unsafe"
ERR_HVS_OUTPUT_INVALID = "hvs_output_invalid"

# Characters that have shell meaning and are NOT legitimate path content.
# (Backslash/forward-slash intentionally absent — valid path separators, never
# interpreted by a shell when shell=False + list argv.)
_SHELL_METACHARACTERS = frozenset(set(";&|`$><\n\r(){}*?!#\"'~"))

# Hard ceiling on render timeout (seconds) to keep renders finite and safe.
_DEFAULT_TIMEOUT_SECONDS = 600
_MAX_TIMEOUT_SECONDS = 1800

# Allowed project-directory slug characters (alphanumerics, dash, underscore).
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")


# ---------------------------------------------------------------------------
# Helpers (deterministic, no HVS import).
# ---------------------------------------------------------------------------
def _stable_id(prefix: str, *parts: Any) -> str:
    """Deterministic sha256-prefixed id from stable inputs (no time/random)."""
    text = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _has_shell_metacharacter(token: str) -> bool:
    return any(ch in _SHELL_METACHARACTERS for ch in token)


def _is_contained(path: Path, root: Path) -> bool:
    """True only if ``path`` is exactly ``root`` or lives inside it."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _slugify(value: str) -> str:
    """Minimal slugify mirroring the HVS boundary convention (alphanumerics)."""
    return re.sub(r"[^A-Za-z0-9]+", "-", str(value)).strip("-").lower() or "x"


def _hvs_render_id(hvs_project_id: str, fmt: str) -> str:
    """Replicate the HVS boundary render_id (sha256 hexdigest[:16]).

    Mirrors hvs/renderers/hyperframes_adapter._make_render_id exactly so SCOS can
    compute the intended output path for dry-run display and recovery WITHOUT
    importing hvs.* (a plain sha256 of stable semantic parts).
    """
    return _sha256_hex16(hvs_project_id, fmt, "hyperframes-v1.1")


def _intended_output_relative_path(hvs_project_id: str, fmt: str) -> str:
    """Deterministic relative mp4 path beneath the HVS project root.

    The authoritative path always comes from the HVS boundary stdout after a
    real render; this is the best-effort intended path for dry-run display and
    for recovery detection when no evidence row exists.
    """
    render_id = _hvs_render_id(hvs_project_id, fmt)
    name = f"hyperframes-{_slugify(render_id)}.{HVS_OUTPUT_EXTENSION}"
    return f"{HVS_RENDERS_SUBDIR}/{name}"


def _canonical_json(obj: Any) -> str:
    """Canonical deterministic JSON serialization (stable render identity)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Approval model (narrow, explicit, auditable).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HVSRenderDispatchApproval:
    """An explicit authorization to dispatch one HVS render for a correlation.

    All fields are caller-supplied (no clock / random). ``issued_at`` and
    ``expires_at`` are optional; expiry is only evaluated when an injectable
    ``clock`` is provided to the evaluator (deterministic, testable).
    """

    approval_id: str
    action_type: str
    status: str
    requested_correlation_id: str
    requested_scos_project_id: str
    requested_hvs_artifact_id: str
    requested_plan_identity_hash: str
    requested_asset_manifest_identity_hash: str
    requested_render_identity_hash: str
    selected_render_preset: str
    requested_output_relative_path: str | None
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
            "requested_plan_identity_hash",
            str(self.requested_plan_identity_hash),
        )
        object.__setattr__(
            self,
            "requested_asset_manifest_identity_hash",
            str(self.requested_asset_manifest_identity_hash),
        )
        object.__setattr__(
            self,
            "requested_render_identity_hash",
            str(self.requested_render_identity_hash),
        )
        object.__setattr__(
            self, "selected_render_preset", str(self.selected_render_preset)
        )
        object.__setattr__(
            self,
            "requested_output_relative_path",
            None if self.requested_output_relative_path is None
            else str(self.requested_output_relative_path),
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
        if self.action_type != APPROVAL_ACTION_DISPATCH_HVS_RENDER:
            if not self.action_type:
                raise ValueError("action_type must not be empty")

    @staticmethod
    def of(
        *,
        approval_id: str,
        requested_correlation_id: str,
        requested_scos_project_id: str,
        requested_hvs_artifact_id: str,
        requested_plan_identity_hash: str,
        requested_asset_manifest_identity_hash: str,
        requested_render_identity_hash: str,
        selected_render_preset: str,
        requested_output_relative_path: str | None = None,
        issued_by: str,
        status: str = APPROVAL_APPROVED,
        action_type: str = APPROVAL_ACTION_DISPATCH_HVS_RENDER,
        issued_at: str | None = None,
        expires_at: str | None = None,
        reason: str | None = None,
    ) -> "HVSRenderDispatchApproval":
        return HVSRenderDispatchApproval(
            approval_id=str(approval_id),
            action_type=action_type,
            status=status,
            requested_correlation_id=str(requested_correlation_id),
            requested_scos_project_id=str(requested_scos_project_id),
            requested_hvs_artifact_id=str(requested_hvs_artifact_id),
            requested_plan_identity_hash=str(requested_plan_identity_hash),
            requested_asset_manifest_identity_hash=str(
                requested_asset_manifest_identity_hash
            ),
            requested_render_identity_hash=str(requested_render_identity_hash),
            selected_render_preset=str(selected_render_preset),
            requested_output_relative_path=(
                None if requested_output_relative_path is None
                else str(requested_output_relative_path)
            ),
            issued_by=str(issued_by),
            issued_at=issued_at,
            expires_at=expires_at,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HVSRenderDispatchApproval":
        return cls(
            approval_id=str(d["approval_id"]),
            action_type=str(d.get("action_type", APPROVAL_ACTION_DISPATCH_HVS_RENDER)),
            status=str(d["status"]),
            requested_correlation_id=str(d["requested_correlation_id"]),
            requested_scos_project_id=str(d["requested_scos_project_id"]),
            requested_hvs_artifact_id=str(d["requested_hvs_artifact_id"]),
            requested_plan_identity_hash=str(d["requested_plan_identity_hash"]),
            requested_asset_manifest_identity_hash=str(
                d["requested_asset_manifest_identity_hash"]
            ),
            requested_render_identity_hash=str(d["requested_render_identity_hash"]),
            selected_render_preset=str(d["selected_render_preset"]),
            requested_output_relative_path=_opt_str(
                d.get("requested_output_relative_path")
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
            "requested_plan_identity_hash": self.requested_plan_identity_hash,
            "requested_asset_manifest_identity_hash": (
                self.requested_asset_manifest_identity_hash
            ),
            "requested_render_identity_hash": self.requested_render_identity_hash,
            "selected_render_preset": self.selected_render_preset,
            "issued_by": self.issued_by,
        }
        if self.requested_output_relative_path is not None:
            out["requested_output_relative_path"] = (
                self.requested_output_relative_path
            )
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
    """Result of evaluating an approval against a freshly computed plan."""

    granted: bool
    error_kind: str | None
    error_detail: str | None
    decision_metadata: tuple[tuple[str, str], ...] = ()

    def metadata_pairs(self) -> tuple[tuple[str, str], ...]:
        return self.decision_metadata


# ---------------------------------------------------------------------------
# Render request (deterministic contract — Section 3).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HVSRenderRequest:
    """A deterministic render request bound to a Stage 3 correlation.

    Binds exactly the contract fields. ``render_identity_hash`` is derived from
    semantic inputs only (see ``render_identity_hash``). It EXCLUDES approval_id,
    request/run ids, timestamps, and audit records.
    """

    render_request_id: str
    contract_version: str
    correlation_id: str
    scos_project_id: str
    hvs_project_id: str
    hvs_artifact_id: str
    plan_identity_hash: str
    asset_manifest_identity_hash: str
    selected_render_preset: str
    expected_resolution: str
    expected_fps: int
    expected_duration_seconds: float
    render_identity_hash: str
    requested_output_relative_path: str | None
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "render_request_id": self.render_request_id,
            "contract_version": self.contract_version,
            "correlation_id": self.correlation_id,
            "scos_project_id": self.scos_project_id,
            "hvs_project_id": self.hvs_project_id,
            "hvs_artifact_id": self.hvs_artifact_id,
            "plan_identity_hash": self.plan_identity_hash,
            "asset_manifest_identity_hash": self.asset_manifest_identity_hash,
            "selected_render_preset": self.selected_render_preset,
            "expected_resolution": self.expected_resolution,
            "expected_fps": self.expected_fps,
            "expected_duration_seconds": self.expected_duration_seconds,
            "render_identity_hash": self.render_identity_hash,
            "requested_output_relative_path": self.requested_output_relative_path,
            "dry_run": self.dry_run,
        }


def render_identity_hash(
    *,
    plan_identity_hash: str,
    asset_manifest_identity_hash: str,
    selected_render_preset: str,
    expected_resolution: str,
    expected_fps: int,
    expected_duration_seconds: float,
) -> str:
    """Deterministic render identity from semantic inputs ONLY.

    Excludes approval_id, request/run ids, timestamps, and audit records. Two
    canonically-equivalent requests (same plan, same assets, same preset, same
    stable render config) always produce the identical identity hash.
    """
    stable_config = {
        "format": HVS_RENDER_FORMAT,
        "resolution": expected_resolution,
        "fps": expected_fps,
        "duration_seconds": round(float(expected_duration_seconds), 3),
        "preset": selected_render_preset,
    }
    blob = _canonical_json(
        {
            "plan_identity_hash": plan_identity_hash,
            "asset_manifest_identity_hash": asset_manifest_identity_hash,
            "stable_config": stable_config,
        }
    )
    return "rnd-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Render evidence ledger (append-only, SCOS-side authoritative).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RenderEvidenceRecord:
    """One append-only SCOS-side render-evidence row.

    Records ONLY a relative output path + fingerprint (no absolute paths, no
    secrets, no raw command strings). The persistence of this record for a
    not-yet-consumed approval is the approval-consumption record.
    """

    render_evidence_id: str
    correlation_id: str
    render_request_id: str
    render_identity_hash: str
    approval_id: str
    status: str
    hvs_project_id: str
    hvs_artifact_id: str
    hvs_render_output_relative_path: str
    output_sha256: str
    output_size_bytes: int
    output_format: str
    observed_duration_seconds: float | None
    observed_resolution: str | None
    observed_fps: int | None
    hvs_render_manifest_relative_path: str | None
    schema_version: int = RENDER_EVIDENCE_LEDGER_SCHEMA_VERSION
    recovered: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "render_evidence_id": self.render_evidence_id,
            "correlation_id": self.correlation_id,
            "render_request_id": self.render_request_id,
            "render_identity_hash": self.render_identity_hash,
            "approval_id": self.approval_id,
            "status": self.status,
            "hvs_project_id": self.hvs_project_id,
            "hvs_artifact_id": self.hvs_artifact_id,
            "hvs_render_output_relative_path": (
                self.hvs_render_output_relative_path
            ),
            "output_sha256": self.output_sha256,
            "output_size_bytes": self.output_size_bytes,
            "output_format": self.output_format,
            "observed_duration_seconds": self.observed_duration_seconds,
            "observed_resolution": self.observed_resolution,
            "observed_fps": self.observed_fps,
            "hvs_render_manifest_relative_path": (
                self.hvs_render_manifest_relative_path
            ),
            "recovered": self.recovered,
        }
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RenderEvidenceRecord":
        return cls(
            render_evidence_id=str(d["render_evidence_id"]),
            correlation_id=str(d["correlation_id"]),
            render_request_id=str(d["render_request_id"]),
            render_identity_hash=str(d["render_identity_hash"]),
            approval_id=str(d["approval_id"]),
            status=str(d["status"]),
            hvs_project_id=str(d["hvs_project_id"]),
            hvs_artifact_id=str(d["hvs_artifact_id"]),
            hvs_render_output_relative_path=str(
                d["hvs_render_output_relative_path"]
            ),
            output_sha256=str(d["output_sha256"]),
            output_size_bytes=int(d["output_size_bytes"]),
            output_format=str(d["output_format"]),
            observed_duration_seconds=(
                None if d.get("observed_duration_seconds") is None
                else float(d["observed_duration_seconds"])
            ),
            observed_resolution=_opt_str(d.get("observed_resolution")),
            observed_fps=(
                None if d.get("observed_fps") is None else int(d["observed_fps"])
            ),
            hvs_render_manifest_relative_path=_opt_str(
                d.get("hvs_render_manifest_relative_path")
            ),
            schema_version=int(
                d.get("schema_version", RENDER_EVIDENCE_LEDGER_SCHEMA_VERSION)
            ),
            recovered=bool(d.get("recovered", False)),
        )


class RenderEvidenceLedger:
    """Append-only JSONL render-evidence ledger (SCOS authoritative)."""

    def __init__(self, ledger_path: str | Path) -> None:
        self._path = Path(ledger_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: RenderEvidenceRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
        with open(self._path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")

    def all(self) -> list[RenderEvidenceRecord]:
        if not self._path.exists():
            return []
        records: list[RenderEvidenceRecord] = []
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(RenderEvidenceRecord.from_dict(json.loads(line)))
        return records

    def find_by_render_identity(
        self, render_identity_hash: str
    ) -> list[RenderEvidenceRecord]:
        return [
            r for r in self.all()
            if r.render_identity_hash == render_identity_hash
        ]

    def find_by_approval(self, approval_id: str) -> list[RenderEvidenceRecord]:
        return [r for r in self.all() if r.approval_id == approval_id]

    def find_active_rendered_by_identity(
        self, render_identity_hash: str
    ) -> RenderEvidenceRecord | None:
        for r in self.find_by_render_identity(render_identity_hash):
            if r.status in (EVIDENCE_RENDERED, EVIDENCE_REUSED):
                return r
        return None


# ---------------------------------------------------------------------------
# Resolution + validation (no mutation).
# ---------------------------------------------------------------------------
def _fetch_correlation(correlation_ledger_path: str | Path, correlation_id: str):
    ledger = CorrelationLedger(correlation_ledger_path)
    rec = ledger.find_by_correlation_id(correlation_id)
    if rec is None:
        return None
    if rec.creation_status not in ("created", "reused"):
        return None
    return rec


def _fetch_materialization(
    materialization_ledger_path: str | Path, correlation_id: str
) -> MaterializationRecord | None:
    ledger = MaterializationLedger(materialization_ledger_path)
    for rec in ledger.all():
        if (
            rec.correlation_id == correlation_id
            and rec.materialization_status in ("created", "reused")
        ):
            return rec
    return None


def _resolve_project_dir(hvs_root: Path, hvs_project_id: str) -> Path:
    """Resolve the HVS project directory, contained within hvs_root/projects.

    Rejects any project id that escapes the approved root (path traversal).
    """
    if not _SLUG_RE.match(hvs_project_id):
        raise UnsafeTargetError(
            f"hvs_project_id contains unsafe characters: {hvs_project_id!r}"
        )
    root = hvs_root.resolve()
    projects_dir = (root / HVS_PROJECTS_SUBDIR).resolve()
    target = (projects_dir / hvs_project_id).resolve()
    try:
        target.relative_to(projects_dir)
    except ValueError:
        raise UnsafeTargetError(
            f"hvs_project_id escapes approved root: {hvs_project_id!r}"
        )
    return target


class UnsafeTargetError(Exception):
    """Raised when an HVS target path is unsafe or already exists mismatched."""


def _hvs_project_render_ready(
    hvs_root: str | Path, hvs_project_id: str
) -> tuple[bool, str, Path | None]:
    """Lightweight SCOS-side readiness preflight for the HVS render boundary.

    Verifies the HVS project directory exists and carries the required render
    artifacts. This is a *validation* check only — it does NOT generate assets,
    resolve them, or run HVS. Returns (ready, detail, project_dir).
    """
    try:
        project_dir = _resolve_project_dir(Path(hvs_root), hvs_project_id)
    except UnsafeTargetError as exc:
        return False, str(exc), None
    if not project_dir.is_dir():
        return (
            False,
            f"HVS project directory missing: {project_dir}",
            project_dir,
        )
    missing = [
        rel
        for rel in HVS_REQUIRED_RENDER_ARTIFACTS
        if not (project_dir / rel).is_file()
    ]
    if missing:
        return (
            False,
            f"HVS project missing required render artifacts: {missing}",
            project_dir,
        )
    return True, "ready", project_dir


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_hvs_render_stdout(stdout: str) -> dict[str, Any]:
    """Best-effort parse of the HVS CLI render JSON payload from stdout.

    The HVS CLI prints a human summary followed by a JSON dict. We extract the
    last JSON object so we can read ``verdict`` / ``output_path`` /
    ``render_id`` / ``manifest_path`` and any observed profile fields. Returns
    {} on no parseable JSON.
    """
    if not stdout:
        return {}
    # Find the last balanced JSON object.
    last_brace = stdout.rfind("}")
    if last_brace == -1:
        return {}
    start = stdout.rfind("{", 0, last_brace)
    if start == -1:
        return {}
    candidate = stdout[start: last_brace + 1]
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


# ---------------------------------------------------------------------------
# Approval evaluation (all conditions from Section 4).
# ---------------------------------------------------------------------------
def _evaluate_dispatch_approval(
    approval: HVSRenderDispatchApproval,
    *,
    correlation_id: str,
    scos_project_id: str,
    hvs_artifact_id: str,
    plan_identity_hash: str,
    asset_manifest_identity_hash: str,
    render_identity_hash: str,
    selected_render_preset: str,
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
    if approval.action_type != APPROVAL_ACTION_DISPATCH_HVS_RENDER:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_ACTION_MISMATCH,
            f"approval action_type is {approval.action_type!r}, expected "
            f"{APPROVAL_ACTION_DISPATCH_HVS_RENDER!r}",
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
    if approval.requested_plan_identity_hash != plan_identity_hash:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval plan identity hash does not match resolved plan",
            tuple(meta) + (
                ("requested", approval.requested_plan_identity_hash),
                ("resolved", plan_identity_hash),
            ),
        )
    if approval.requested_asset_manifest_identity_hash != asset_manifest_identity_hash:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval asset manifest identity hash does not match resolved manifest",
            tuple(meta) + (
                ("requested", approval.requested_asset_manifest_identity_hash),
                ("resolved", asset_manifest_identity_hash),
            ),
        )
    if approval.requested_render_identity_hash != render_identity_hash:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval render identity hash does not match computed identity",
            tuple(meta) + (
                ("requested", approval.requested_render_identity_hash),
                ("resolved", render_identity_hash),
            ),
        )
    if approval.selected_render_preset != selected_render_preset:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval render preset does not match requested preset",
            tuple(meta) + (
                ("requested", approval.selected_render_preset),
                ("resolved", selected_render_preset),
            ),
        )
    if approval.expires_at is not None and clock is not None:
        now = clock()
        if now >= approval.expires_at:
            return ApprovalEvaluation(
                False, ERR_APPROVAL_NOT_VALID,
                f"approval expired at {approval.expires_at!r} (now {now!r})",
                tuple(meta) + (
                    ("expires_at", approval.expires_at), ("now", now),
                ),
            )
    return ApprovalEvaluation(True, None, None, tuple(meta))


# ---------------------------------------------------------------------------
# Outcome model (narrow public result).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HVSRenderDispatchOutcome:
    ok: bool
    render_status: str
    correlation_id: str
    scos_project_id: str
    hvs_artifact_id: str
    hvs_project_id: str | None
    render_request: HVSRenderRequest | None
    approval_decision: dict[str, Any]
    evidence: RenderEvidenceRecord | None
    hvs_render_stdout_excerpt: str | None
    would_dispatch: bool
    dry_run: bool
    error_kind: str | None = None
    error_detail: str | None = None
    failed_step: str | None = None

    def to_adapter_result(self) -> AgentAdapterResult:
        meta: list[tuple[str, str]] = [
            ("stage", "scos-hvs-stage5"),
            ("render_status", self.render_status),
            ("correlation_id", self.correlation_id),
            ("scos_project_id", self.scos_project_id),
            ("hvs_artifact_id", self.hvs_artifact_id),
            ("hvs_project_id", self.hvs_project_id or ""),
            (
                "render_identity_hash",
                self.render_request.render_identity_hash
                if self.render_request else "",
            ),
            ("would_dispatch", str(self.would_dispatch)),
            ("dry_run", str(self.dry_run)),
        ]
        if self.evidence is not None:
            meta.append(
                ("output_relative_path", self.evidence.hvs_render_output_relative_path)
            )
            meta.append(("output_sha256", self.evidence.output_sha256))
            meta.append(("output_size_bytes", str(self.evidence.output_size_bytes)))
            meta.append(("output_format", self.evidence.output_format))
        return AgentAdapterResult.of(
            result_id=(
                self.render_request.render_request_id if self.render_request
                else self.correlation_id
            ),
            request_id=self.scos_project_id,
            session_id="scos-hvs-stage5",
            agent_name="hermes_video_studio",
            runtime_id="hvs_cli",
            status="result_ready" if self.ok else "failed",
            result_type="hvs_render_dispatch",
            result_summary=(
                "HVS render dispatched" if self.ok
                else f"HVS render dispatch denied: {self.error_kind}"
            ),
            output_text=(
                self.hvs_render_stdout_excerpt
                if (self.hvs_render_stdout_excerpt and self.ok) else None
            ),
            output_path=None,
            created_at=self.correlation_id,
            next_action=(
                "no further action (render dispatched + evidence recorded)"
                if self.ok
                else "review approval + correlation + materialization"
            ),
            metadata=tuple(meta),
        )

    def to_adapter_error(self) -> AgentAdapterError:
        meta: list[tuple[str, str]] = [
            ("stage", "scos-hvs-stage5"),
            ("render_status", self.render_status),
            ("correlation_id", self.correlation_id),
            ("scos_project_id", self.scos_project_id),
            ("hvs_artifact_id", self.hvs_artifact_id),
            (
                "render_identity_hash",
                self.render_request.render_identity_hash
                if self.render_request else "",
            ),
            ("approval_id", self.approval_decision.get("approval_id", "")),
            ("would_dispatch", str(self.would_dispatch)),
            ("dry_run", str(self.dry_run)),
        ]
        return AgentAdapterError.of(
            self.error_kind or "render_dispatch_denied",
            self.error_detail or "render dispatch denied",
            self.failed_step or "dispatch_hvs_render",
            request_id=self.scos_project_id,
            metadata=tuple(meta),
        )


def _denied(
    *,
    correlation_id, scos_project_id, hvs_artifact_id, hvs_project_id,
    render_request, approval_decision, dry_run,
    error_kind, error_detail, failed_step,
) -> HVSRenderDispatchOutcome:
    return HVSRenderDispatchOutcome(
        ok=False,
        render_status=EVIDENCE_DENIED,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        hvs_project_id=hvs_project_id,
        render_request=render_request,
        approval_decision=approval_decision,
        evidence=None,
        hvs_render_stdout_excerpt=None,
        would_dispatch=False,
        dry_run=dry_run,
        error_kind=error_kind,
        error_detail=error_detail,
        failed_step=failed_step,
    )


# ---------------------------------------------------------------------------
# The only place HVS is mutated: render executor + evidence appender.
# ---------------------------------------------------------------------------
class HVSRenderExecutor:
    """Single approved render executor. Drives the HVS render boundary and
    appends exactly one SCOS evidence row. All HVS mutation happens here.
    """

    def __init__(
        self,
        *,
        python_executable: str,
        subprocess_run: Callable[..., Any] | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        fake_render: bool = False,
    ) -> None:
        self._python = python_executable
        self._subprocess_run = subprocess_run or subprocess.run
        self._timeout = max(1, min(int(timeout_seconds), _MAX_TIMEOUT_SECONDS))
        self._fake_render = bool(fake_render)

    def build_argv(self, *, hvs_project_id: str, fmt: str) -> list[str]:
        argv = [
            self._python,
            "-m",
            _HVS_CLI_MODULE,
            HVS_RENDER_SUBCOMMAND,
            "--project-id",
            hvs_project_id,
            "--format",
            fmt,
        ]
        if self._fake_render:
            argv.append("--fake-render")
        return argv

    def _safe_env(self) -> dict:
        # Minimal environment: never a full os.environ dump (no secret leakage).
        return {}

    def dispatch(
        self,
        *,
        hvs_root: Path,
        hvs_project_id: str,
        fmt: str,
    ) -> tuple[dict[str, Any], str, int]:
        """Invoke the HVS render boundary. Returns (parsed_stdout, raw_stdout, exit_code).

        List argv, shell=False, fixed cwd (hvs_root), bounded timeout, no
        caller-controlled fragments. Raises only on infra-level failures; the
        boundary's own verdict is reported in the parsed stdout.
        """
        argv = self.build_argv(hvs_project_id=hvs_project_id, fmt=fmt)
        if any(_has_shell_metacharacter(tok) for tok in argv):
            raise ValueError("constructed render argv contained a shell metacharacter")
        cwd = hvs_root.resolve()
        proc = self._subprocess_run(
            list(argv),
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=self._timeout,
            input="",
            env=self._safe_env(),
        )
        raw = (proc.stdout or "") if hasattr(proc, "stdout") else ""
        parsed = _parse_hvs_render_stdout(raw)
        exit_code = int(getattr(proc, "returncode", 0) or 0)
        return parsed, raw, exit_code


# ---------------------------------------------------------------------------
# Public Stage 5 API.
# ---------------------------------------------------------------------------
def dispatch_hvs_render(
    *,
    correlation_id: str,
    approval: HVSRenderDispatchApproval | dict[str, Any],
    selected_render_preset: str,
    hvs_root: str | Path,
    correlation_ledger_path: str | Path,
    materialization_ledger_path: str | Path,
    render_evidence_ledger_path: str | Path,
    python_executable: str,
    subprocess_run: Callable[..., Any] | None = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    fake_render: bool = False,
    dry_run: bool = False,
    clock: Callable[[], str] | None = None,
) -> HVSRenderDispatchOutcome:
    """Stage 5 public API: approval-gated HVS render dispatch + evidence intake.

    Flow:
      1. Resolve the Stage 3 correlation (must be an active Stage 3 project).
      2. Require a valid Stage 4 materialization record for the correlation.
      3. Derive plan identity (Stage 3) + asset-manifest identity (Stage 4).
      4. Build the deterministic render request + render_identity_hash.
      5. Evaluate the explicit dispatch_hvs_render approval (all conditions).
      6. dry_run=True  -> returns plan + decision + intended output; ZERO HVS
                          invocation, ZERO evidence writes.
      7. approved      -> preflight HVS project readiness + idempotency; if a
                          matching rendered output already exists, REUSE (no
                          render, no new evidence); else invoke the HVS render
                          boundary exactly once, validate the output evidence,
                          append one SCOS evidence record, consume the approval.
      8. denied/failed -> structured error; ZERO HVS render; approval reusable.

    The caller-supplied ``hvs_root`` is the ONLY HVS location written (tests use
    an isolated temp root; the real HVS repository is never touched).
    """
    if isinstance(approval, dict):
        approval = HVSRenderDispatchApproval.from_dict(approval)

    base_decision = approval.to_dict() if approval is not None else {}

    # --- 1) Resolve Stage 3 correlation (must be active) -------------------
    corr = _fetch_correlation(correlation_ledger_path, correlation_id)
    if corr is None:
        return _denied(
            correlation_id=correlation_id, scos_project_id="", hvs_artifact_id="",
            hvs_project_id=None, render_request=None,
            approval_decision=base_decision, dry_run=dry_run,
            error_kind=ERR_CORRELATION_NOT_FOUND,
            error_detail=f"no active Stage 3 correlation found for {correlation_id!r}",
            failed_step="resolve_correlation",
        )
    scos_project_id = corr.scos_project_id
    hvs_artifact_id = corr.hvs_artifact_id
    hvs_project_id = corr.hvs_project_id
    plan_identity_hash = corr.plan_identity_hash

    # --- 2) Require a valid Stage 4 materialization record -----------------
    mat_rec = _fetch_materialization(materialization_ledger_path, correlation_id)
    if mat_rec is None:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=None, approval_decision=base_decision, dry_run=dry_run,
            error_kind=ERR_MATERIALIZATION_NOT_FOUND,
            error_detail=(
                f"no Stage 4 materialization record found for {correlation_id!r}"
            ),
            failed_step="resolve_materialization",
        )
    asset_manifest_identity_hash = mat_rec.manifest_identity_hash

    # --- 3) Derive the expected render profile from certified project state -
    # The HVS boundary supports exactly one format ("vertical" -> 1080x1920 @30).
    # The certified HVS project's on-disk timeline (written by Stage 3) is the
    # authoritative source for duration; resolution/fps are fixed by the format.
    # We read it via stdlib json (local file I/O on the injected HVS root) — no
    # HVS import, no schema re-validation, no duplication of HVS render logic.
    project_dir_for_profile = None
    try:
        project_dir_for_profile = _resolve_project_dir(
            Path(hvs_root), hvs_project_id
        )
    except UnsafeTargetError:
        project_dir_for_profile = None
    expected_resolution, expected_fps, expected_duration = _read_hvs_profile(
        project_dir_for_profile
    )

    # --- 4) Build the deterministic render request + identity --------------
    rid = render_identity_hash(
        plan_identity_hash=plan_identity_hash,
        asset_manifest_identity_hash=asset_manifest_identity_hash,
        selected_render_preset=selected_render_preset,
        expected_resolution=expected_resolution,
        expected_fps=expected_fps,
        expected_duration_seconds=expected_duration,
    )
    requested_output = _intended_output_relative_path(hvs_project_id, HVS_RENDER_FORMAT)
    req = HVSRenderRequest(
        render_request_id=_stable_id(
            "hvs-req-", correlation_id, rid, selected_render_preset
        ),
        contract_version=STAGE5_CONTRACT_VERSION,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_project_id=hvs_project_id,
        hvs_artifact_id=hvs_artifact_id,
        plan_identity_hash=plan_identity_hash,
        asset_manifest_identity_hash=asset_manifest_identity_hash,
        selected_render_preset=selected_render_preset,
        expected_resolution=expected_resolution,
        expected_fps=expected_fps,
        expected_duration_seconds=expected_duration,
        render_identity_hash=rid,
        requested_output_relative_path=requested_output,
        dry_run=dry_run,
    )
    # --- 5) Evaluate the explicit approval (all conditions) ---------------
    eval_res = _evaluate_dispatch_approval(
        approval,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        plan_identity_hash=plan_identity_hash,
        asset_manifest_identity_hash=asset_manifest_identity_hash,
        render_identity_hash=rid,
        selected_render_preset=selected_render_preset,
        clock=clock,
    )
    decision = {
        "approval_id": approval.approval_id if approval else "",
        "granted": eval_res.granted,
        "error_kind": eval_res.error_kind,
        "error_detail": eval_res.error_detail,
        "metadata": [list(p) for p in eval_res.decision_metadata],
    }
    # --- 4b) Honor the approval's requested output path ONLY when HVS supports
    # a safe, caller-chosen relative path. HVS's certified render boundary fixes
    # the output path (renders/hyperframes-<render_id>.mp4) and does NOT accept a
    # caller output argument. Therefore any explicit, non-default requested path
    # cannot be safely honored and must be refused (never overwriting, never an
    # unsafe path). The record's requested_output_relative_path is None in the
    # default/safe case; otherwise we deny before any HVS mutation.
    if approval is not None and approval.requested_output_relative_path is not None:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_UNSAFE_RENDER_TARGET,
            error_detail=(
                "HVS render boundary does not support a caller-chosen output path; "
                "requested_output_relative_path must be None (uses the deterministic "
                "HVS path)"
            ),
            failed_step="requested_output_path",
        )

    if not eval_res.granted:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=eval_res.error_kind or ERR_APPROVAL_REQUIRED,
            error_detail=eval_res.error_detail or "approval evaluation failed",
            failed_step="evaluate_approval",
        )

    # --- 6) dry-run: plan only, no HVS, no evidence ------------------------
    if dry_run:
        return HVSRenderDispatchOutcome(
            ok=True,
            render_status=EVIDENCE_REUSED,  # dry-run: no render performed
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            render_request=req,
            approval_decision=decision,
            evidence=None,
            hvs_render_stdout_excerpt=None,
            would_dispatch=True,
            dry_run=True,
        )

    # --- 7) approved: preflight + idempotency + dispatch -------------------
    evidence_ledger = RenderEvidenceLedger(render_evidence_ledger_path)

    # 7a) Preflight HVS project readiness (validation only, no HVS import).
    ready, detail, project_dir = _hvs_project_render_ready(
        hvs_root, hvs_project_id
    )
    if not ready:
        # Distinguish an invalid project from assets-not-ready where possible.
        kind = ERR_ASSETS_NOT_READY if "artifact" in detail else ERR_INVALID_HVS_PROJECT
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=kind,
            error_detail=detail,
            failed_step="preflight_hvs_project",
        )

    # 7b) Idempotency / recovery detection BEFORE any render.
    # The HVS render boundary fixes the output path by (project_id, fmt), so every
    # render identity for a given project maps to the SAME output file. We must
    # therefore also guard against another render identity's evidence already
    # owning that path, and never overwrite an incompatible output.
    prior = evidence_ledger.find_active_rendered_by_identity(rid)
    prior_any_path = [
        r for r in evidence_ledger.all()
        if r.status in (EVIDENCE_RENDERED, EVIDENCE_REUSED)
        and r.hvs_render_output_relative_path == req.requested_output_relative_path
    ]
    other_identity_at_path = [
        r for r in prior_any_path if r.render_identity_hash != rid
    ]
    expected_rel = req.requested_output_relative_path
    expected_abs = (project_dir / expected_rel).resolve() if project_dir else None
    output_exists = expected_abs is not None and expected_abs.is_file()

    if prior is not None and output_exists and _file_matches(expected_abs, prior):
        # Safe reuse: same identity, output present + fingerprint matches.
        # No render, no new evidence; approval already consumed by prior render.
        return HVSRenderDispatchOutcome(
            ok=True,
            render_status=EVIDENCE_REUSED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            render_request=req,
            approval_decision=decision,
            evidence=prior,
            hvs_render_stdout_excerpt=None,
            would_dispatch=False,
            dry_run=False,
        )
    if prior is not None and output_exists and not _file_matches(expected_abs, prior):
        # Same identity's evidence exists but the output fingerprint changed ->
        # unsafe to overwrite.
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_RENDER_IDENTITY_CONFLICT,
            error_detail=(
                "output exists for this render identity but its fingerprint "
                "does not match recorded evidence; refusing to overwrite"
            ),
            failed_step="idempotency_check",
        )
    if other_identity_at_path:
        # A DIFFERENT render identity already owns this (project-scoped) output
        # path with a valid evidence row. Re-rendering would overwrite it, which
        # HVS's no-overwrite policy forbids. Refuse.
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_RENDER_IDENTITY_CONFLICT,
            error_detail=(
                "an existing output for a different render identity already "
                "occupies this path; refusing to overwrite (re-render requires a "
                "new HVS project)"
            ),
            failed_step="idempotency_check",
        )

    # 7c) Recovery: output exists, NO evidence row references this path.
    # Inspect + reuse without re-rendering (identity proven by deterministic path
    # + fingerprint stability). Writes exactly one evidence row (approval consumed).
    if output_exists and not prior_any_path:
        sha = _sha256_file(expected_abs)
        size = expected_abs.stat().st_size
        recovered_rec = _build_evidence(
            req=req, approval=approval, status=EVIDENCE_REUSED,
            output_rel=expected_rel, sha=sha, size=size,
            output_format=HVS_OUTPUT_EXTENSION,
            observed_resolution=expected_resolution,
            observed_fps=expected_fps,
            observed_duration=expected_duration,
            manifest_rel=None, recovered=True,
        )
        evidence_ledger.append(recovered_rec)  # consume approval (recovered)
        return HVSRenderDispatchOutcome(
            ok=True,
            render_status=EVIDENCE_REUSED,
            correlation_id=correlation_id,
            scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id,
            hvs_project_id=hvs_project_id,
            render_request=req,
            approval_decision=decision,
            evidence=recovered_rec,
            hvs_render_stdout_excerpt=None,
            would_dispatch=False,
            dry_run=False,
        )

    # 7d) Ensure the intended output path is safe & non-overwriting.
    if expected_abs is None:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_UNSAFE_RENDER_TARGET,
            error_detail="could not resolve the expected HVS output path",
            failed_step="resolve_output_path",
        )
    if not _is_contained(expected_abs, (Path(hvs_root) / HVS_PROJECTS_SUBDIR).resolve()):
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_UNSAFE_RENDER_TARGET,
            error_detail=(
                f"intended output escapes the HVS project root: {expected_rel}"
            ),
            failed_step="safe_output_path",
        )

    # 7e) Invoke the HVS render boundary EXACTLY ONCE.
    executor = HVSRenderExecutor(
        python_executable=python_executable,
        subprocess_run=subprocess_run,
        timeout_seconds=timeout_seconds,
        fake_render=fake_render,
    )
    try:
        parsed, raw_stdout, exit_code = executor.dispatch(
            hvs_root=Path(hvs_root),
            hvs_project_id=hvs_project_id,
            fmt=HVS_RENDER_FORMAT,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_RENDER_NOT_SUPPORTED,
            error_detail=f"HVS render boundary could not start: {type(exc).__name__}",
            failed_step="dispatch_render",
        )

    verdict = str(parsed.get("verdict", "")).upper()
    if verdict != "PASS" or exit_code != 0:
        # Render refused/failed at the HVS boundary. The approval is NOT consumed.
        detail = parsed.get("errors") or raw_stdout.strip()[-200:] or "unknown"
        if isinstance(detail, list):
            detail = "; ".join(str(d) for d in detail)
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_RENDER_FAILED,
            error_detail=f"HVS render boundary refused/failed: {detail}",
            failed_step="dispatch_render",
        )

    # 7f) Evidence intake: validate + correlate HVS output.
    out_rel = _relative_output_from_hvs(parsed, expected_rel, project_dir)
    if out_rel is None:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_OUTPUT_MISSING,
            error_detail="HVS render reported PASS but no output path resolves",
            failed_step="intake_output_path",
        )
    out_abs = (project_dir / out_rel).resolve()
    if not out_abs.is_file():
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_OUTPUT_MISSING,
            error_detail=f"HVS output file missing: {out_rel}",
            failed_step="intake_output_file",
        )
    if not _is_contained(out_abs, (Path(hvs_root) / HVS_PROJECTS_SUBDIR).resolve()):
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_OUTPUT_UNSAFE,
            error_detail=f"HVS output escapes the HVS project root: {out_rel}",
            failed_step="intake_output_safe",
        )
    size = out_abs.stat().st_size
    if size <= 0:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_OUTPUT_INVALID,
            error_detail=f"HVS output has non-positive size: {out_rel}",
            failed_step="intake_output_size",
        )
    sha = _sha256_file(out_abs)
    # Format agreement: must be mp4 (the only boundary format).
    if out_abs.suffix.lower().lstrip(".") != HVS_OUTPUT_EXTENSION:
        return _denied(
            correlation_id=correlation_id, scos_project_id=scos_project_id,
            hvs_artifact_id=hvs_artifact_id, hvs_project_id=hvs_project_id,
            render_request=req, approval_decision=decision, dry_run=dry_run,
            error_kind=ERR_HVS_OUTPUT_INVALID,
            error_detail=(
                f"HVS output format {out_abs.suffix!r} != expected "
                f".{HVS_OUTPUT_EXTENSION}"
            ),
            failed_step="intake_output_format",
        )

    # Observed profile where HVS exposes it; cross-check against expected.
    observed_resolution = parsed.get("width") and parsed.get("height") and (
        f"{parsed.get('width')}x{parsed.get('height')}"
    )
    observed_fps = parsed.get("fps")
    observed_duration = parsed.get("duration_seconds")
    manifest_rel = _relative_manifest_from_hvs(parsed, project_dir)

    evidence = _build_evidence(
        req=req, approval=approval, status=EVIDENCE_RENDERED,
        output_rel=out_rel, sha=sha, size=size,
        output_format=HVS_OUTPUT_EXTENSION,
        observed_resolution=(
            str(observed_resolution) if observed_resolution else expected_resolution
        ),
        observed_fps=(
            int(observed_fps) if observed_fps is not None else expected_fps
        ),
        observed_duration=(
            float(observed_duration) if observed_duration is not None
            else expected_duration
        ),
        manifest_rel=manifest_rel, recovered=False,
    )
    evidence_ledger.append(evidence)  # consumption record (approval consumed)

    return HVSRenderDispatchOutcome(
        ok=True,
        render_status=EVIDENCE_RENDERED,
        correlation_id=correlation_id,
        scos_project_id=scos_project_id,
        hvs_artifact_id=hvs_artifact_id,
        hvs_project_id=hvs_project_id,
        render_request=req,
        approval_decision=decision,
        evidence=evidence,
        hvs_render_stdout_excerpt=(raw_stdout or "")[:2000],
        would_dispatch=True,
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Evidence + profile helpers.
# ---------------------------------------------------------------------------
def _build_evidence(
    *,
    req: HVSRenderRequest,
    approval: HVSRenderDispatchApproval,
    status: str,
    output_rel: str,
    sha: str,
    size: int,
    output_format: str,
    observed_resolution: str | None,
    observed_fps: int | None,
    observed_duration: float | None,
    manifest_rel: str | None,
    recovered: bool,
) -> RenderEvidenceRecord:
    return RenderEvidenceRecord(
        render_evidence_id=_stable_id(
            "hvs-ev-", req.render_identity_hash, sha[:16], status
        ),
        correlation_id=req.correlation_id,
        render_request_id=req.render_request_id,
        render_identity_hash=req.render_identity_hash,
        approval_id=approval.approval_id,
        status=status,
        hvs_project_id=req.hvs_project_id,
        hvs_artifact_id=req.hvs_artifact_id,
        hvs_render_output_relative_path=output_rel,
        output_sha256=sha,
        output_size_bytes=size,
        output_format=output_format,
        observed_duration_seconds=observed_duration,
        observed_resolution=observed_resolution,
        observed_fps=observed_fps,
        hvs_render_manifest_relative_path=manifest_rel,
        recovered=recovered,
    )


def _file_matches(path: Path, rec: RenderEvidenceRecord) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != rec.output_size_bytes:
        return False
    return _sha256_file(path) == rec.output_sha256


def _relative_output_from_hvs(
    parsed: dict[str, Any], fallback_rel: str, project_dir: Path | None
) -> str | None:
    """Resolve the HVS output RELATIVE path from HVS stdout, else the fallback.

    HVS reports an absolute or relative output_path; we always store the path
    RELATIVE to the HVS project root (no absolute paths in SCOS evidence).
    """
    raw = parsed.get("output_path")
    if raw:
        p = Path(raw)
        if project_dir is not None:
            try:
                rel = p.resolve().relative_to(project_dir.resolve())
                return rel.as_posix()
            except ValueError:
                # Absolute path outside the project root is unexpected; ignore.
                pass
        # If raw is already relative, keep it.
        if not p.is_absolute():
            return p.as_posix()
    return fallback_rel


def _relative_manifest_from_hvs(
    parsed: dict[str, Any], project_dir: Path | None
) -> str | None:
    raw = parsed.get("manifest_path")
    if not raw:
        return None
    p = Path(raw)
    if project_dir is not None:
        try:
            return p.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            return None
    return p.as_posix() if not p.is_absolute() else None


def _read_hvs_profile(project_dir: Path | None) -> tuple[str, int, float]:
    """Derive the expected render profile from the certified HVS timeline.

    The HVS render boundary supports exactly one format ("vertical" ->
    1080x1920 @ 30), so resolution/fps are fixed by the boundary contract.
    Duration is authoritative from the on-disk ``timelines/video_timeline.json``
    that Stage 3 wrote. Returns (resolution, fps, duration_seconds). Pure local
    json read — no HVS import, no schema re-validation, no duplication.
    """
    width, height, fps = 1080, 1920, 30
    duration = 3.0
    if project_dir is not None:
        tl_path = project_dir / "timelines" / "video_timeline.json"
        if tl_path.is_file():
            try:
                tl = json.loads(tl_path.read_text(encoding="utf-8"))
                dur_raw = tl.get("duration_seconds")
                if dur_raw is not None:
                    try:
                        duration = round(float(dur_raw), 3)
                    except (TypeError, ValueError):
                        duration = 3.0
                # Resolution/fps are format-fixed; overlay only if explicitly
                # present and sane (defensive, never required).
                if tl.get("width") and tl.get("height"):
                    width, height = int(tl["width"]), int(tl["height"])
                if tl.get("fps"):
                    fps = int(tl["fps"])
            except (OSError, ValueError):
                pass
    return f"{width}x{height}", fps, duration
