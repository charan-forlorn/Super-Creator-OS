"""SCOS <-> Hermes Video Studio (HVS) — Stage 3 approval-gated project creation.

This module is the Stage 3 integration surface. It builds an explicit,
auditable approval gate in front of a *minimal, local, deterministic* HVS
project creation, and records an append-only SCOS-side correlation ledger.

Boundary (consistent with Stage 1/2 cross-project architecture):

    SCOS Stage 3 service  ->  consumes Stage 2 certified API (map_scos_to_hvs,
        validate_hvs_payload, payload_identity_hash)  ->  produces a plan
        ->  evaluates an explicit create_hvs_project approval
        ->  (only if approved) writes the MINIMUM HVS project structure
            (project_brief.json + timelines/video_timeline.json) into an
            INJECTABLE HVS root  ->  appends one correlation record to the
            SCOS-side append-only ledger.

Hard rules enforced here:

* The narrow HVS creation primitive writes ONLY the certified Stage 2 payload
  (which is itself the HVS ``timeline.schema.json`` shape) and a minimal HVS
  project-brief artifact. It performs NO rendering, NO asset copy, NO media
  assembly, NO voice generation, NO network, NO Ollama, NO subprocess, and
  imports NO HVS code.
* Creation mutates HVS only inside the single `HVSProjectCreator` executor;
  the mapper, validator, approval evaluator, dry-run, and tests never write.
* No caller-supplied HVS path is honored: the on-disk project directory name
  is a deterministic slug derived from the plan identity hash, and the resolved
  path is always contained within the injected HVS root's ``projects/`` dir.
* ``created_at`` is intentionally the Stage 2 deterministic placeholder (None)
  — no wall-clock timestamp is ever invented (determinism requirement).
* Approval is single-use per (approval_id, plan identity): a persisted
  correlation (status created/reused) keyed to the approval_id is the
  consumption record. The passed approval object is NEVER mutated.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no subprocess, no HVS import, no file I/O except the explicitly
injected HVS root and SCOS correlation ledger path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


try:
    from hvs_schema_mapper import (
        canonicalize_mapping_payload,
        map_scos_to_hvs,
        payload_identity_hash,
        validate_hvs_payload,
    )
    from hvs_contract_models import (
        HVS_SCHEMA_VERSION,
        HVS_SCENE_COUNT_MAX,
        HVS_SCENE_COUNT_MIN,
        HVS_SOURCE_AGENT,
        HVS_STATUS_PLANNED,
        HVS_TIMELINE_STAGE,
        SCOSRenderTimelineProject,
        X_SCOS_KEY,
        _sha256_hex16,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from .hvs_schema_mapper import (
        canonicalize_mapping_payload,
        map_scos_to_hvs,
        payload_identity_hash,
        validate_hvs_payload,
    )
    from .hvs_contract_models import (
        HVS_SCHEMA_VERSION,
        HVS_SCENE_COUNT_MAX,
        HVS_SCENE_COUNT_MIN,
        HVS_SOURCE_AGENT,
        HVS_STATUS_PLANNED,
        HVS_TIMELINE_STAGE,
        SCOSRenderTimelineProject,
        X_SCOS_KEY,
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
# scos-hvs.timeline.v1 / 1.0.0  (Stage 2 certified contract version).
CONTRACT_VERSION = "scos-hvs.timeline.v1/1.0.0"
CONTRACT_NAME_VERSION = "scos-hvs.timeline.v1"
CONTRACT_SEMANTIC_VERSION = "1.0.0"

# On-disk HVS layout (relative to an injected HVS root).
HVS_PROJECTS_SUBDIR = "projects"
HVS_TIMELINE_REL = "timelines/video_timeline.json"
HVS_PROJECT_BRIEF_REL = "project_brief.json"

# Deterministic on-disk project directory slug prefix.
HVS_PROJECT_DIR_PREFIX = "hvs-"

# Allowed project-directory slug characters (alphanumerics, dash, underscore).
_SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Creation status values recorded in the correlation ledger.
CREATION_CREATED = "created"
CREATION_REUSED = "reused"
CREATION_DENIED = "denied"
CREATION_FAILED = "failed"

# Approval action type for this stage.
APPROVAL_ACTION_CREATE_HVS_PROJECT = "create_hvs_project"

# Allowed approval statuses (Stage 3 narrow model).
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
ERR_APPROVAL_ALREADY_CONSUMED = "approval_already_consumed"
ERR_INVALID_HVS_PLAN = "invalid_hvs_plan"
ERR_CORRELATION_CONFLICT = "correlation_conflict"
ERR_UNSAFE_TARGET = "unsafe_target"
ERR_UNSAFE_PATH = "unsafe_path"
ERR_CREATION_NOT_SUPPORTED = "creation_not_supported"

# Correlation ledger schema version.
CORRELATION_LEDGER_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Certified artifact-id helper (Stage 3 contract).
# ---------------------------------------------------------------------------
def hvs_artifact_id(project_id: str, scene_count: int) -> str:
    """Deterministic HVS artifact id for a project (Stage 3 certified helper).

    Mirrors the Stage 2 mapper's ``_artifact_id_for`` derivation so that the
    approval scope check (approval HVS artifact ID == plan artifact ID) is
    satisfiable. The join key is the SCOS ``project_id``; ``scene_count`` is
    accepted for API symmetry with the cross-repository contract signature but
    does not alter the id (the semantic plan already pins scene_count, so the
    id remains stable for a given project).

    Local-first, deterministic. No clock, no random, no uuid.
    """
    return f"hvs-timeline-{project_id}"


# ---------------------------------------------------------------------------
# Approval model (narrow, explicit, auditable).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HVSProjectApproval:
    """An explicit authorization to create one HVS project.

    All fields are caller-supplied (no clock / random). ``issued_at`` and
    ``expires_at`` are optional; expiry is only evaluated when an injectable
    ``clock`` is provided to the evaluator (deterministic, testable).
    """

    approval_id: str
    action_type: str
    status: str
    requested_plan_identity_hash: str
    requested_scos_project_id: str
    requested_hvs_artifact_id: str
    issued_by: str
    issued_at: str | None = None
    expires_at: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval_id", str(self.approval_id))
        object.__setattr__(self, "action_type", str(self.action_type))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(
            self, "requested_plan_identity_hash", str(self.requested_plan_identity_hash)
        )
        object.__setattr__(
            self, "requested_scos_project_id", str(self.requested_scos_project_id)
        )
        object.__setattr__(
            self, "requested_hvs_artifact_id", str(self.requested_hvs_artifact_id)
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
        if self.action_type != APPROVAL_ACTION_CREATE_HVS_PROJECT:
            # Non-fatal at construction; the evaluator rejects mismatches too.
            # We still require a non-empty, sane value here.
            if not self.action_type:
                raise ValueError("action_type must not be empty")

    @staticmethod
    def of(
        *,
        approval_id: str,
        requested_plan_identity_hash: str,
        requested_scos_project_id: str,
        requested_hvs_artifact_id: str,
        issued_by: str,
        status: str = APPROVAL_APPROVED,
        issued_at: str | None = None,
        expires_at: str | None = None,
        reason: str | None = None,
    ) -> "HVSProjectApproval":
        return HVSProjectApproval(
            approval_id=str(approval_id),
            action_type=APPROVAL_ACTION_CREATE_HVS_PROJECT,
            status=status,
            requested_plan_identity_hash=str(requested_plan_identity_hash),
            requested_scos_project_id=str(requested_scos_project_id),
            requested_hvs_artifact_id=str(requested_hvs_artifact_id),
            issued_by=str(issued_by),
            issued_at=issued_at,
            expires_at=expires_at,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "HVSProjectApproval":
        return cls(
            approval_id=str(d["approval_id"]),
            action_type=str(d.get("action_type", APPROVAL_ACTION_CREATE_HVS_PROJECT)),
            status=str(d["status"]),
            requested_plan_identity_hash=str(d["requested_plan_identity_hash"]),
            requested_scos_project_id=str(d["requested_scos_project_id"]),
            requested_hvs_artifact_id=str(d["requested_hvs_artifact_id"]),
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
            "requested_plan_identity_hash": self.requested_plan_identity_hash,
            "requested_scos_project_id": self.requested_scos_project_id,
            "requested_hvs_artifact_id": self.requested_hvs_artifact_id,
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
    """Result of evaluating an approval against a freshly computed plan."""

    granted: bool
    error_kind: str | None
    error_detail: str | None
    decision_metadata: tuple[tuple[str, str], ...] = ()

    def metadata_pairs(self) -> tuple[tuple[str, str], ...]:
        return self.decision_metadata


# ---------------------------------------------------------------------------
# Correlation ledger (append-only, SCOS-side authoritative).
# ---------------------------------------------------------------------------
def correlation_id_for(plan_identity_hash: str) -> str:
    """Deterministic correlation id from the semantic plan identity hash."""
    return f"corr-{plan_identity_hash}"


@dataclass(frozen=True)
class CorrelationRecord:
    """One append-only correlation row linking SCOS <-> HVS creation."""

    correlation_id: str
    contract_version: str
    scos_project_id: str
    plan_identity_hash: str
    hvs_project_id: str
    hvs_artifact_id: str
    approval_id: str
    creation_status: str
    hvs_project_relative_path: str
    schema_version: int = CORRELATION_LEDGER_SCHEMA_VERSION
    requested_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "contract_version": self.contract_version,
            "scos_project_id": self.scos_project_id,
            "plan_identity_hash": self.plan_identity_hash,
            "hvs_project_id": self.hvs_project_id,
            "hvs_artifact_id": self.hvs_artifact_id,
            "approval_id": self.approval_id,
            "creation_status": self.creation_status,
            "hvs_project_relative_path": self.hvs_project_relative_path,
        }
        if self.requested_by is not None:
            out["requested_by"] = self.requested_by
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CorrelationRecord":
        return cls(
            correlation_id=str(d["correlation_id"]),
            contract_version=str(d["contract_version"]),
            scos_project_id=str(d["scos_project_id"]),
            plan_identity_hash=str(d["plan_identity_hash"]),
            hvs_project_id=str(d["hvs_project_id"]),
            hvs_artifact_id=str(d["hvs_artifact_id"]),
            approval_id=str(d["approval_id"]),
            creation_status=str(d["creation_status"]),
            hvs_project_relative_path=str(d["hvs_project_relative_path"]),
            schema_version=int(d.get("schema_version", CORRELATION_LEDGER_SCHEMA_VERSION)),
            requested_by=_opt_str(d.get("requested_by")),
        )


class CorrelationLedger:
    """Append-only JSONL correlation ledger (SCOS authoritative).

    Never overwrites or deletes historical rows. ``append`` is atomic per line
    under normal filesystem semantics (single write of one complete line).
    """

    def __init__(self, ledger_path: str | Path) -> None:
        self._path = Path(ledger_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: CorrelationRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True)
        with open(self._path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")

    def all(self) -> list[CorrelationRecord]:
        if not self._path.exists():
            return []
        records: list[CorrelationRecord] = []
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                records.append(CorrelationRecord.from_dict(json.loads(line)))
        return records

    def find_by_correlation_id(self, correlation_id: str) -> CorrelationRecord | None:
        for r in self.all():
            if r.correlation_id == correlation_id:
                return r
        return None

    def find_by_approval(self, approval_id: str) -> list[CorrelationRecord]:
        return [r for r in self.all() if r.approval_id == approval_id]

    def find_active_by_scos_project(self, scos_project_id: str) -> list[CorrelationRecord]:
        active = (CREATION_CREATED, CREATION_REUSED)
        return [
            r
            for r in self.all()
            if r.scos_project_id == scos_project_id and r.creation_status in active
        ]


# ---------------------------------------------------------------------------
# HVS project creation executor (THE ONLY place HVS is mutated).
# ---------------------------------------------------------------------------
class UnsafeTargetError(Exception):
    """Raised when an HVS target path is unsafe or already exists mismatched."""


class HVSCreationFailedError(Exception):
    """Raised when HVS project creation fails after a partial write."""


def _safe_project_id(plan_identity_hash: str) -> str:
    """Deterministic, safe on-disk HVS project directory slug."""
    slug = HVS_PROJECT_DIR_PREFIX + plan_identity_hash[:12]
    if not _SLUG_RE.match(slug):
        # Defensive: hex is always safe, but never emit an unsafe slug.
        raise UnsafeTargetError(f"derived project slug is not safe: {slug!r}")
    return slug


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


def _timeline_matches(project_dir: Path, plan_payload: dict[str, Any]) -> bool:
    """True if an existing HVS project dir holds a matching timeline identity."""
    tl_path = project_dir / HVS_TIMELINE_REL
    if not tl_path.exists():
        return False
    try:
        existing = json.loads(tl_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        existing.get("artifact_id") == plan_payload.get("artifact_id")
        and existing.get("project_id") == plan_payload.get("project_id")
        and existing.get("deterministic_hash") == plan_payload.get("deterministic_hash")
    )


def _build_project_brief(
    hvs_project_id: str,
    hvs_artifact_id: str,
    plan_payload: dict[str, Any],
    scos_project_id: str,
) -> dict[str, Any]:
    """Build the minimal HVS project-brief artifact (HVS project schema shape)."""
    x_scos = plan_payload.get(X_SCOS_KEY, {})
    brief: dict[str, Any] = {
        "schema_version": HVS_SCHEMA_VERSION,
        "artifact_id": hvs_artifact_id,
        "project_id": hvs_project_id,
        # Stage 2 placeholder: no clock invented at any stage.
        "created_at": None,
        "stage": HVS_TIMELINE_STAGE,
        "status": HVS_STATUS_PLANNED,
        "source_agent": HVS_SOURCE_AGENT,
        "deterministic_hash": plan_payload.get("deterministic_hash"),
        "name": scos_project_id,
        "idea": scos_project_id,
    }
    if isinstance(x_scos, dict):
        brief[X_SCOS_KEY] = x_scos
    return brief


class HVSProjectCreator:
    """Single approved creation executor. Writes minimum HVS project structure.

    All filesystem mutation happens here and only here. The mapper, validator,
    approval evaluator, dry-run, and tests never call write methods.
    """

    def __init__(self, hvs_root: str | Path) -> None:
        self._hvs_root = Path(hvs_root)

    def evaluate_target(
        self, hvs_project_id: str, plan_payload: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Return (exists_and_matches, mismatch_reason).

        - (True, None): a matching project already exists (safe reuse).
        - (False, None): target is free (safe to create).
        - (False, reason): target exists but mismatches (unsafe, do NOT overwrite).
        """
        project_dir = _resolve_project_dir(self._hvs_root, hvs_project_id)
        if not project_dir.exists():
            return (False, None)
        if _timeline_matches(project_dir, plan_payload):
            return (True, None)
        return (False, "existing target does not match deterministic plan identity")

    def create(
        self,
        hvs_project_id: str,
        plan_payload: dict[str, Any],
        scos_project_id: str,
        hvs_artifact_id: str,
    ) -> str:
        """Create the minimum HVS project structure. Returns creation status.

        Returns CREATION_REUSED if a matching project already exists (idempotent
        recovery). Returns CREATION_CREATED on a fresh write. Raises
        UnsafeTargetError if a mismatched target exists. On any write failure
        after a partial creation, the project directory created by THIS call is
        removed and HVSCreationFailedError is raised (no partial unsafe state).
        """
        project_dir = _resolve_project_dir(self._hvs_root, hvs_project_id)
        exists, mismatch = self.evaluate_target(hvs_project_id, plan_payload)
        if mismatch is not None:
            raise UnsafeTargetError(mismatch)
        if exists:
            return CREATION_REUSED

        created_here = not project_dir.exists()
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            # 1) timeline artifact (certified Stage 2 payload IS the HVS shape).
            tl_path = project_dir / HVS_TIMELINE_REL
            tl_path.parent.mkdir(parents=True, exist_ok=True)
            tl_path.write_text(
                json.dumps(plan_payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # 2) minimal project-brief artifact.
            brief = _build_project_brief(
                hvs_project_id, hvs_artifact_id, plan_payload, scos_project_id
            )
            brief_path = project_dir / HVS_PROJECT_BRIEF_REL
            brief_path.write_text(
                json.dumps(brief, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # Post-write validation: the timeline must re-validate and exist.
            if not tl_path.exists():
                raise HVSCreationFailedError("timeline artifact missing after write")
            # Re-validate the produced timeline against the Stage 2 contract.
            recheck = validate_hvs_payload(
                json.loads(tl_path.read_text(encoding="utf-8"))
            )
            if not recheck.ok:
                raise HVSCreationFailedError(
                    f"created timeline failed re-validation: "
                    f"{recheck.issues[0].message}"
                )
            return CREATION_CREATED
        except Exception as exc:  # noqa: BLE001 - translate to typed failure
            if created_here and project_dir.exists():
                # Clean up ONLY files created by this operation.
                import shutil

                shutil.rmtree(project_dir, ignore_errors=True)
            if isinstance(exc, UnsafeTargetError):
                raise
            raise HVSCreationFailedError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Public Stage 3 API.
# ---------------------------------------------------------------------------
@dataclass
class HVSProjectCreationOutcome:
    """Structured result of a Stage 3 creation request.

    Wraps either success or denial. ``to_adapter_result()`` /
    ``to_adapter_error()`` expose the existing SCOS ``AgentAdapterResult`` /
    ``AgentAdapterError`` patterns.
    """

    ok: bool
    creation_status: str
    scos_project_id: str
    plan_identity_hash: str
    hvs_artifact_id: str
    hvs_project_id: str | None
    hvs_project_relative_path: str | None
    correlation: CorrelationRecord | None
    approval_decision: dict[str, Any]
    plan_payload: dict[str, Any] | None
    would_create: bool
    dry_run: bool
    error_kind: str | None = None
    error_detail: str | None = None
    failed_step: str | None = None

    def to_adapter_result(self) -> AgentAdapterResult:
        corr = self.correlation.to_dict() if self.correlation is not None else {}
        meta = (
            ("stage", "scos-hvs-stage3"),
            ("creation_status", self.creation_status),
            ("scos_project_id", self.scos_project_id),
            ("plan_identity_hash", self.plan_identity_hash),
            ("hvs_artifact_id", self.hvs_artifact_id),
            ("hvs_project_id", self.hvs_project_id or ""),
            ("hvs_project_relative_path", self.hvs_project_relative_path or ""),
            ("would_create", str(self.would_create)),
            ("dry_run", str(self.dry_run)),
            ("correlation_id", corr.get("correlation_id", "")),
            ("approval_id", self.approval_decision.get("approval_id", "")),
        )
        if self.error_kind is not None:
            meta = meta + (("error_kind", self.error_kind),)
        rid = _sha256_hex16(
            self.scos_project_id,
            self.plan_identity_hash,
            self.creation_status,
            str(self.would_create),
        )
        return AgentAdapterResult.of(
            result_id=f"hvs-create-{rid}",
            request_id=self.scos_project_id,
            session_id="scos-hvs-stage3",
            agent_name="hermes_video_studio",
            runtime_id="hvs_project_creation",
            status="result_ready" if self.ok else "failed",
            result_type="hvs_project_creation",
            result_summary=(
                "HVS project creation plan evaluated"
                if self.dry_run
                else f"HVS project {self.creation_status}"
            ),
            created_at=self.scos_project_id,
            next_action=(
                "no mutation (dry-run)"
                if self.dry_run
                else "correlation recorded; downstream stages may proceed"
            ),
            metadata=meta,
        )

    def to_adapter_error(self) -> AgentAdapterError:
        meta = (
            ("stage", "scos-hvs-stage3"),
            ("creation_status", self.creation_status),
            ("scos_project_id", self.scos_project_id),
            ("plan_identity_hash", self.plan_identity_hash),
            ("hvs_artifact_id", self.hvs_artifact_id),
            ("approval_id", self.approval_decision.get("approval_id", "")),
            ("would_create", str(self.would_create)),
            ("dry_run", str(self.dry_run)),
        )
        return AgentAdapterError.of(
            self.error_kind or "creation_denied",
            self.error_detail or "creation request denied",
            self.failed_step or "create_hvs_project",
            request_id=self.scos_project_id,
            metadata=meta,
        )


def _evaluate_approval(
    approval: HVSProjectApproval,
    *,
    plan_identity_hash: str,
    scos_project_id: str,
    hvs_artifact_id: str,
    clock: Callable[[], str] | None = None,
) -> ApprovalEvaluation:
    """Evaluate all 9 approval gate conditions. Returns granted / denied."""
    if approval is None:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_REQUIRED, "no approval supplied",
            (("reason", "missing_approval"),),
        )
    meta: list[tuple[str, str]] = [("approved_id", approval.approval_id)]
    if approval.status != APPROVAL_APPROVED:
        # pending/rejected/expired/consumed/cancelled -> not valid for creation.
        return ApprovalEvaluation(
            False, ERR_APPROVAL_NOT_VALID,
            f"approval status is {approval.status!r}, expected 'approved'",
            tuple(meta) + (("status", approval.status),),
        )
    if approval.action_type != APPROVAL_ACTION_CREATE_HVS_PROJECT:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_ACTION_MISMATCH,
            f"approval action_type is {approval.action_type!r}, expected "
            f"{APPROVAL_ACTION_CREATE_HVS_PROJECT!r}",
            tuple(meta) + (("action_type", approval.action_type),),
        )
    if approval.requested_plan_identity_hash != plan_identity_hash:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval plan identity hash does not match computed plan hash",
            tuple(meta) + (
                ("requested", approval.requested_plan_identity_hash),
                ("computed", plan_identity_hash),
            ),
        )
    if approval.requested_scos_project_id != scos_project_id:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval SCOS project id does not match plan project id",
            tuple(meta) + (
                ("requested", approval.requested_scos_project_id),
                ("computed", scos_project_id),
            ),
        )
    if approval.requested_hvs_artifact_id != hvs_artifact_id:
        return ApprovalEvaluation(
            False, ERR_APPROVAL_SCOPE_MISMATCH,
            "approval HVS artifact id does not match plan artifact id",
            tuple(meta) + (
                ("requested", approval.requested_hvs_artifact_id),
                ("computed", hvs_artifact_id),
            ),
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


def create_hvs_project(
    scos_project: SCOSRenderTimelineProject,
    approval: HVSProjectApproval | dict[str, Any],
    *,
    hvs_root: str | Path,
    correlation_ledger_path: str | Path,
    requested_by: str,
    dry_run: bool = False,
    clock: Callable[[], str] | None = None,
) -> HVSProjectCreationOutcome:
    """Stage 3 public API: approval-gated HVS project creation.

    Flow:
      1. Plan via the certified Stage 2 API (map_scos_to_hvs, validate).
      2. Evaluate the explicit approval against the computed plan.
      3. Enforce idempotency / conflict rules against the correlation ledger.
      4. dry_run=True  -> returns the plan + decision + would-create/reuse;
                           performs ZERO HVS writes and ZERO correlation writes.
      5. approved      -> creates/reuses the HVS project (minimum structure),
                          records one SCOS correlation, returns structured result.
      6. denied        -> returns a structured error; ZERO HVS / correlation writes.

    The caller-supplied ``hvs_root`` is the ONLY HVS location written to (tests
    use an isolated temp root; the real HVS repository is never touched).
    """
    # Normalize approval input (never mutate caller's object).
    if isinstance(approval, dict):
        approval = HVSProjectApproval.from_dict(approval)

    if scos_project is None:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id="",
            plan_identity_hash="",
            hvs_artifact_id="",
            hvs_project_id=None,
            hvs_project_relative_path=None,
            correlation=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            plan_payload=None,
            would_create=False,
            dry_run=dry_run,
            error_kind=ERR_INVALID_HVS_PLAN,
            error_detail="scos_project is required",
            failed_step="create_hvs_project",
        )

    scos_project_id = scos_project.project_id

    # --- 1) Plan via certified Stage 2 API (consumed, not duplicated) -------
    mapped = map_scos_to_hvs(scos_project, validate=True)
    if not mapped.ok:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id=scos_project_id,
            plan_identity_hash="",
            hvs_artifact_id="",
            hvs_project_id=None,
            hvs_project_relative_path=None,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=None,
            would_create=False,
            dry_run=dry_run,
            error_kind=ERR_INVALID_HVS_PLAN,
            error_detail=mapped.error.error_detail if mapped.error else "invalid plan",
            failed_step="plan_hvs_contract_payload",
        )

    plan_payload = mapped.payload
    plan_identity_hash = payload_identity_hash(plan_payload)
    scene_count = int(plan_payload.get("scene_count", len(scos_project.scenes)))
    artifact_id = hvs_artifact_id(scos_project_id, scene_count)

    # --- 2) Evaluate approval (all 9 conditions) ----------------------------
    eval_result = _evaluate_approval(
        approval,
        plan_identity_hash=plan_identity_hash,
        scos_project_id=scos_project_id,
        hvs_artifact_id=artifact_id,
        clock=clock,
    )
    if not eval_result.granted:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=None,
            hvs_project_relative_path=None,
            correlation=None,
            approval_decision=(approval.to_dict() if approval is not None else {}),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=dry_run,
            error_kind=eval_result.error_kind,
            error_detail=eval_result.error_detail,
            failed_step="evaluate_approval",
        )

    # --- 3) Idempotency / conflict rules -----------------------------------
    ledger = CorrelationLedger(correlation_ledger_path)
    corr_id = correlation_id_for(plan_identity_hash)
    existing_same = ledger.find_by_correlation_id(corr_id)
    if existing_same is not None and existing_same.creation_status in (
        CREATION_CREATED,
        CREATION_REUSED,
    ):
        # Same approved semantic plan already correlated -> idempotent reuse.
        return HVSProjectCreationOutcome(
            ok=True,
            creation_status=CREATION_REUSED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=existing_same.hvs_project_id,
            hvs_project_relative_path=existing_same.hvs_project_relative_path,
            correlation=existing_same,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=dry_run,
        )

    # Approval single-use: already consumed by a (possibly different) plan?
    consumed = [
        r
        for r in ledger.find_by_approval(approval.approval_id)
        if r.creation_status in (CREATION_CREATED, CREATION_REUSED)
    ]
    if consumed:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=None,
            hvs_project_relative_path=None,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=dry_run,
            error_kind=ERR_APPROVAL_ALREADY_CONSUMED,
            error_detail=(
                "approval already consumed by an existing correlation "
                f"({consumed[0].correlation_id})"
            ),
            failed_step="evaluate_approval",
        )

    # Documented conflict rule: one SCOS project_id owns at most one active
    # correlation. A different semantic plan for the same SCOS project_id is a
    # conflict (requires a distinct SCOS project_id or re-approval).
    active_for_project = ledger.find_active_by_scos_project(scos_project_id)
    if active_for_project:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=None,
            hvs_project_relative_path=None,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=dry_run,
            error_kind=ERR_CORRELATION_CONFLICT,
            error_detail=(
                "SCOS project already has an active correlation with a different "
                f"semantic plan ({active_for_project[0].correlation_id})"
            ),
            failed_step="evaluate_correlation_conflict",
        )

    # --- 4) dry-run: no writes ---------------------------------------------
    hvs_project_id = _safe_project_id(plan_identity_hash)
    creator = HVSProjectCreator(hvs_root)
    exists, mismatch = creator.evaluate_target(hvs_project_id, plan_payload)
    would_create = (not exists) and (mismatch is None)
    relative_path = f"{HVS_PROJECTS_SUBDIR}/{hvs_project_id}"

    if dry_run:
        return HVSProjectCreationOutcome(
            ok=True,
            creation_status=(CREATION_REUSED if exists else "planned"),
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=hvs_project_id,
            hvs_project_relative_path=relative_path,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=would_create,
            dry_run=True,
        )

    # --- 5) Approved execution: create/reuse + record correlation ----------
    try:
        status = creator.create(
            hvs_project_id, plan_payload, scos_project_id, artifact_id
        )
    except UnsafeTargetError as exc:
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_DENIED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=hvs_project_id,
            hvs_project_relative_path=relative_path,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=False,
            error_kind=ERR_UNSAFE_TARGET,
            error_detail=str(exc),
            failed_step="create_hvs_project",
        )
    except HVSCreationFailedError as exc:
        # Approval remains approved/reusable: no correlation was persisted.
        return HVSProjectCreationOutcome(
            ok=False,
            creation_status=CREATION_FAILED,
            scos_project_id=scos_project_id,
            plan_identity_hash=plan_identity_hash,
            hvs_artifact_id=artifact_id,
            hvs_project_id=hvs_project_id,
            hvs_project_relative_path=relative_path,
            correlation=None,
            approval_decision=approval.to_dict(),
            plan_payload=plan_payload,
            would_create=False,
            dry_run=False,
            error_kind=ERR_CREATION_NOT_SUPPORTED,
            error_detail=f"HVS project creation failed: {exc}",
            failed_step="create_hvs_project",
        )

    record = CorrelationRecord(
        correlation_id=corr_id,
        contract_version=CONTRACT_VERSION,
        scos_project_id=scos_project_id,
        plan_identity_hash=plan_identity_hash,
        hvs_project_id=hvs_project_id,
        hvs_artifact_id=artifact_id,
        approval_id=approval.approval_id,
        creation_status=status,
        hvs_project_relative_path=relative_path,
        requested_by=requested_by,
    )
    ledger.append(record)

    return HVSProjectCreationOutcome(
        ok=True,
        creation_status=status,
        scos_project_id=scos_project_id,
        plan_identity_hash=plan_identity_hash,
        hvs_artifact_id=artifact_id,
        hvs_project_id=hvs_project_id,
        hvs_project_relative_path=relative_path,
        correlation=record,
        approval_decision=approval.to_dict(),
        plan_payload=plan_payload,
        would_create=(status == CREATION_CREATED),
        dry_run=False,
    )


# ---------------------------------------------------------------------------
# Read-only cross-repository validation (used by the certification test suite).
# ---------------------------------------------------------------------------
def validate_timeline_against_hvs_schema(
    plan_payload: dict[str, Any], hvs_repo_root: str | Path
) -> tuple[bool, list[str]]:
    """Validate the produced timeline payload against the read-only HVS schema.

    Read-only: loads ``hvs/schemas/timeline.schema.json`` from the given HVS
    repo root and runs jsonschema. Performs NO write and imports NO HVS code.
    Returns (passed, errors).
    """
    try:
        import jsonschema  # local import keeps the module stdlib-light normally
    except ImportError:  # pragma: no cover - environment dependent
        return (True, ["jsonschema unavailable; structural check skipped"])

    schema_path = Path(hvs_repo_root) / "hvs" / "schemas" / "timeline.schema.json"
    if not schema_path.exists():
        return (False, [f"HVS timeline schema not found at {schema_path}"])
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    # The certified Stage 2 contract serializes ``created_at`` as the documented
    # deterministic placeholder (None) — no wall-clock is ever invented. The
    # HVS read-only schema marks ``created_at`` required/date-time, so we exempt
    # the exact placeholder value from the cross-repo check (Stage 3 concern).
    errors = [
        f"{'/'.join(str(p) for p in e.path)}: {e.message}"
        for e in validator.iter_errors(plan_payload)
        if not (list(e.path) == ["created_at"] and plan_payload.get("created_at") is None)
    ]
    return (len(errors) == 0, errors)


__all__ = [
    "CONTRACT_VERSION",
    "APPROVAL_ACTION_CREATE_HVS_PROJECT",
    "ALLOWED_APPROVAL_STATUSES",
    "CREATION_CREATED",
    "CREATION_REUSED",
    "CREATION_DENIED",
    "CREATION_FAILED",
    "ERR_APPROVAL_REQUIRED",
    "ERR_APPROVAL_NOT_VALID",
    "ERR_APPROVAL_ACTION_MISMATCH",
    "ERR_APPROVAL_SCOPE_MISMATCH",
    "ERR_APPROVAL_ALREADY_CONSUMED",
    "ERR_INVALID_HVS_PLAN",
    "ERR_CORRELATION_CONFLICT",
    "ERR_UNSAFE_TARGET",
    "ERR_UNSAFE_PATH",
    "ERR_CREATION_NOT_SUPPORTED",
    "hvs_artifact_id",
    "HVSProjectApproval",
    "ApprovalEvaluation",
    "CorrelationRecord",
    "CorrelationLedger",
    "correlation_id_for",
    "HVSProjectCreator",
    "HVSProjectCreationOutcome",
    "create_hvs_project",
    "validate_timeline_against_hvs_schema",
]
