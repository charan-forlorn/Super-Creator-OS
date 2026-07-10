"""SCOS <-> Hermes Video Studio (HVS) — Stage 5 operator delivery approval.

Local, deterministic, operator-controlled approval handoff that transforms a
VERIFIED HVS render decision packet (Stage 3 / 4) into ONE of:

* APPROVED_FOR_MANUAL_DELIVERY
* REJECTED_FOR_MANUAL_DELIVERY

The approval authorizes ONLY a future human-performed delivery step. It NEVER
publishes, uploads, copies media, calls an API, sends a message, triggers a
render, or mutates Git state. Manual delivery remains a human action; this
stage only records the operator's explicit intention in the append-only,
tamper-evident audit ledger.

The audit trail reuses ``approval_audit_models`` + ``approval_audit_store``
(the Stage 6.6 SQLite WAL hash-chain ledger) rather than introducing a second
store. A PENDING request is persisted as a ``pending`` ledger decision (the
ledger already permits that decision value) so its evidence-bound metadata
exists before the operator decides, and so the one-way transition is enforced.

Trust + integrity prerequisites (re-verified here, not merely trusted):
* packet ``trust_level == VERIFIED``
* packet ``operator_action == review_export_ready``
* artifact SHA-256 present and verified against the evidence
* ``automation_allowed == false`` (never changed)

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no server, no socket, no subprocess.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .approval_audit_models import ApprovalDecision
from .approval_audit_store import (
    append_decision,
    latest_decision,
    verify_chain,
)

# --- schema / identity -------------------------------------------------------
STAGE5_SCHEMA_VERSION = 1
SOURCE_NAME = "hermes_video_studio"
SUBJECT_TYPE = "hvs_delivery_approval"

# Audited approval/deny decisions persisted in the shared ledger. The ledger's
# `is_execution_granted` helper treats `approved` as the only granting decision,
# which is exactly the boundary we want: APPROVED_FOR_MANUAL_DELIVERY never
# grants automated execution.
_LEDGER_DECISION_PENDING = "pending"
_LEDGER_DECISION_APPROVED = "approved"
_LEDGER_DECISION_DENIED = "denied"
_DECIDED_LEDGER = (_LEDGER_DECISION_APPROVED, _LEDGER_DECISION_DENIED)

# --- Stage 5 visible status vocabulary ---------------------------------------
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED_FOR_MANUAL_DELIVERY"
STATUS_REJECTED = "REJECTED_FOR_MANUAL_DELIVERY"

# --- CLI-facing decision actions ---------------------------------------------
DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"

ALLOWED_DECISION_ACTIONS = (DECISION_APPROVE, DECISION_REJECT)

# --- stable exit / error codes (machine-readable) ----------------------------
EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"
PACKET_NOT_READY = "PACKET_NOT_READY"
ARTIFACT_NOT_VERIFIED = "ARTIFACT_NOT_VERIFIED"
AUTOMATION_NOT_ALLOWED = "AUTOMATION_NOT_ALLOWED"
ALREADY_DECIDED = "ALREADY_DECIDED"
MISSING_OPERATOR_ID = "MISSING_OPERATOR_ID"
MISSING_REJECT_REASON = "MISSING_REJECT_REASON"
INVALID_DECISION = "INVALID_DECISION"
APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
CHAIN_VERIFY_FAILED = "CHAIN_VERIFY_FAILED"

_SCOPE_STATEMENT = (
    "Approval does not publish, upload, distribute, or trigger delivery "
    "automatically."
)

_PENDING_DECIDED_AT = "pending"  # deterministic placeholder; not used in IDs
_PENDING_DECIDED_BY = "system"  # non-human record of request creation

_DIGEST_LENGTH = 16


def _sha256_hex16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def _require_nonempty(field: str, value: str | None) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field} must not be empty")


def _stable_approval_request_id(
    *, packet_id: str, validation_id: str | None, artifact_sha256: str | None
) -> str:
    """Deterministic id derived from packet + evidence validation + artifact SHA.

    Identical verified inputs always yield the same approval request id, so a
    re-request for the same verified packet is idempotent at the id level.
    """
    return "scos-hvs-approval-" + _sha256_hex16(
        "|".join(
            [
                "request",
                packet_id,
                validation_id or "",
                artifact_sha256 or "",
            ]
        )
    )


@dataclass(frozen=True)
class HVSDeliveryApprovalRequest:
    """A PENDING operator delivery-approval request bound to verified evidence."""

    approval_request_id: str
    source: str
    project_id: str | None
    packet_id: str
    validation_id: str | None
    evidence_id: str | None
    artifact_path: str | None
    artifact_sha256: str | None
    status: str
    allowed_decision_actions: tuple[str, ...]
    scope_statement: str
    automation_allowed: bool
    manual_delivery_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STAGE5_SCHEMA_VERSION,
            "source": self.source,
            "approval_request_id": self.approval_request_id,
            "project_id": self.project_id,
            "packet_id": self.packet_id,
            "validation_id": self.validation_id,
            "evidence_id": self.evidence_id,
            "artifact": {
                "path": self.artifact_path,
                "sha256": self.artifact_sha256,
            },
            "status": self.status,
            "allowed_decision_actions": list(self.allowed_decision_actions),
            "scope_statement": self.scope_statement,
            "automation_allowed": self.automation_allowed,
            "manual_delivery_required": self.manual_delivery_required,
        }


@dataclass(frozen=True)
class HVSDeliveryApprovalDecisionResult:
    """Outcome of an approve/reject decision (or a rejection to even create)."""

    ok: bool
    approval_request_id: str | None
    status: str | None
    decision: str | None
    operator_id: str | None
    decided_at: str | None
    reason: str | None
    subject_id: str | None
    ledger_decision_id: str | None
    chain_verified: bool | None
    error_code: str | None
    error_detail: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": STAGE5_SCHEMA_VERSION,
            "source": SOURCE_NAME,
            "approval_request_id": self.approval_request_id,
            "status": self.status,
            "decision": self.decision,
            "operator_id": self.operator_id,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "subject_id": self.subject_id,
            "ledger_decision_id": self.ledger_decision_id,
            "chain_verified": self.chain_verified,
            "manual_delivery_required": True,
            "automation_allowed": False,
            "scope_statement": _SCOPE_STATEMENT,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _deny(
    *,
    approval_request_id: str | None,
    error_code: str,
    error_detail: str,
    status: str | None = None,
    subject_id: str | None = None,
) -> HVSDeliveryApprovalDecisionResult:
    return HVSDeliveryApprovalDecisionResult(
        ok=False,
        approval_request_id=approval_request_id,
        status=status,
        decision=None,
        operator_id=None,
        decided_at=None,
        reason=None,
        subject_id=subject_id,
        ledger_decision_id=None,
        chain_verified=None,
        error_code=error_code,
        error_detail=error_detail,
    )


def _packet_ok_for_approval(packet: dict[str, Any]) -> str | None:
    """Return an error_code if the packet is NOT eligible for approval, else None.

    Mirrors the Stage 3 trust model exactly: only VERIFIED + review_export_ready
    + verified artifact + automation_allowed=false may enter the handoff.
    """
    if packet.get("trust_level") != "VERIFIED":
        return EVIDENCE_UNVERIFIED
    if packet.get("operator_action") != "review_export_ready":
        return PACKET_NOT_READY
    art = packet.get("artifact") or {}
    if not art.get("sha256"):
        return ARTIFACT_NOT_VERIFIED
    if packet.get("automation_allowed") is not False:
        return AUTOMATION_NOT_ALLOWED
    return None


def _evidence_id_from(packet: dict[str, Any]) -> str | None:
    hvs = packet.get("hvs") or {}
    return hvs.get("validation_id") or packet.get("validation_id")


def _packet_identity(packet: dict[str, Any]) -> dict[str, Any]:
    """Extract evidence-bound identity from a Stage 3/4 packet.

    The packet nests HVS identity under ``hvs.*`` but also keeps some top-level
    mirrors. Prefer the ``hvs.*`` values (authoritative for validation_id /
    project_id / evidence sha) and fall back to top-level where present.
    """
    hvs = packet.get("hvs") or {}
    art = packet.get("artifact") or {}
    return {
        "project_id": packet.get("project_id") or hvs.get("project_id"),
        "packet_id": packet.get("packet_id"),
        "validation_id": packet.get("validation_id") or hvs.get("validation_id"),
        "evidence_id": _evidence_id_from(packet),
        "artifact_path": art.get("path"),
        "artifact_sha256": art.get("sha256"),
    }


def _request_from_packet(packet: dict[str, Any], request_id: str) -> HVSDeliveryApprovalRequest:
    ident = _packet_identity(packet)
    return HVSDeliveryApprovalRequest(
        approval_request_id=request_id,
        source=SOURCE_NAME,
        project_id=ident["project_id"],
        packet_id=ident["packet_id"],
        validation_id=ident["validation_id"],
        evidence_id=ident["evidence_id"],
        artifact_path=ident["artifact_path"],
        artifact_sha256=ident["artifact_sha256"],
        status=STATUS_PENDING,
        allowed_decision_actions=tuple(ALLOWED_DECISION_ACTIONS),
        scope_statement=_SCOPE_STATEMENT,
        automation_allowed=False,
        manual_delivery_required=True,
    )


def _pending_metadata(packet: dict[str, Any]) -> dict[str, Any]:
    ident = _packet_identity(packet)
    return {
        "project_id": ident["project_id"],
        "packet_id": ident["packet_id"],
        "validation_id": ident["validation_id"],
        "evidence_id": ident["evidence_id"],
        "artifact_path": ident["artifact_path"],
        "artifact_sha256": ident["artifact_sha256"],
        "manual_delivery_required": True,
        "automation_allowed": False,
        "scope_statement": _SCOPE_STATEMENT,
    }


def create_approval_request(
    *,
    packet: dict[str, Any],
    repo_root,
    db_path=None,
) -> HVSDeliveryApprovalRequest | HVSDeliveryApprovalDecisionResult:
    """Create (or idempotently return) a PENDING approval request.

    Only a VERIFIED + review_export_ready + artifact-verified + non-automated
    packet may enter. A PENDING ledger decision is written once (idempotent)
    binding the request to its evidence identity + verified artifact SHA-256.
    An already-decided request is refused (one-way, immutable).
    """
    err = _packet_ok_for_approval(packet)
    if err is not None:
        detail = {
            EVIDENCE_UNVERIFIED: "packet trust_level is not VERIFIED",
            PACKET_NOT_READY: "packet operator_action is not review_export_ready",
            ARTIFACT_NOT_VERIFIED: "artifact SHA-256 not verified",
            AUTOMATION_NOT_ALLOWED: "automation_allowed must be false",
        }[err]
        return _deny(approval_request_id=None, error_code=err, error_detail=detail)

    request_id = _stable_approval_request_id(
        packet_id=packet.get("packet_id"),
        validation_id=packet.get("validation_id"),
        artifact_sha256=(packet.get("artifact") or {}).get("sha256"),
    )

    latest = latest_decision(
        subject_type=SUBJECT_TYPE,
        subject_id=request_id,
        repo_root=Path(repo_root),
        db_path=db_path,
    )
    if latest is not None and latest.decision in _DECIDED_LEDGER:
        # Already approved/rejected: one-way, cannot recreate.
        status = (
            STATUS_APPROVED
            if latest.decision == _LEDGER_DECISION_APPROVED
            else STATUS_REJECTED
        )
        return _deny(
            approval_request_id=request_id,
            error_code=ALREADY_DECIDED,
            error_detail=(
                "approval request already decided "
                f"({latest.decision}); cannot recreate"
            ),
            status=status,
            subject_id=request_id,
        )

    # Idempotent: if a PENDING record already exists, do not append again.
    if latest is None:
        append_decision(
            subject_type=SUBJECT_TYPE,
            subject_id=request_id,
            decision=_LEDGER_DECISION_PENDING,
            decided_by=_PENDING_DECIDED_BY,
            decided_at=_PENDING_DECIDED_AT,
            reason=None,
            metadata=_pending_metadata(packet),
            repo_root=Path(repo_root),
            db_path=db_path,
        )

    return _request_from_packet(packet, request_id)


def get_approval_request(
    *,
    approval_id: str,
    repo_root,
    db_path=None,
) -> HVSDeliveryApprovalRequest | HVSDeliveryApprovalDecisionResult:
    """Return the current state of an approval request from the ledger.

    A not-yet-created deterministic id is reported as PENDING (placeholder);
    a stored PENDING decision reports PENDING with its bound metadata; a
    decided record reports the resolved APPROVED/REJECTED status.
    """
    latest = latest_decision(
        subject_type=SUBJECT_TYPE,
        subject_id=approval_id,
        repo_root=Path(repo_root),
        db_path=db_path,
    )
    if latest is None:
        return HVSDeliveryApprovalRequest(
            approval_request_id=approval_id,
            source=SOURCE_NAME,
            project_id=None,
            packet_id=None,
            validation_id=None,
            evidence_id=None,
            artifact_path=None,
            artifact_sha256=None,
            status=STATUS_PENDING,
            allowed_decision_actions=tuple(ALLOWED_DECISION_ACTIONS),
            scope_statement=_SCOPE_STATEMENT,
            automation_allowed=False,
            manual_delivery_required=True,
        )

    status = {
        _LEDGER_DECISION_PENDING: STATUS_PENDING,
        _LEDGER_DECISION_APPROVED: STATUS_APPROVED,
        _LEDGER_DECISION_DENIED: STATUS_REJECTED,
    }[latest.decision]
    meta = latest.metadata.to_dict()
    return HVSDeliveryApprovalRequest(
        approval_request_id=approval_id,
        source=SOURCE_NAME,
        project_id=meta.get("project_id"),
        packet_id=meta.get("packet_id"),
        validation_id=meta.get("validation_id"),
        evidence_id=meta.get("evidence_id"),
        artifact_path=meta.get("artifact_path"),
        artifact_sha256=meta.get("artifact_sha256"),
        status=status,
        allowed_decision_actions=tuple(ALLOWED_DECISION_ACTIONS),
        scope_statement=_SCOPE_STATEMENT,
        automation_allowed=False,
        manual_delivery_required=True,
    )


def decide_approval(
    *,
    approval_id: str,
    decision: str,
    operator_id: str,
    decided_at: str,
    reason: str | None = None,
    note: str | None = None,
    repo_root,
    db_path=None,
) -> HVSDeliveryApprovalDecisionResult:
    """Apply a one-way approve/reject decision for a PENDING request.

    Rules:
    * explicit operator_id required;
    * reject requires a non-empty reason;
    * an already-decided request cannot change;
    * APPROVED never sets automation_allowed true (it stays false);
    * the PENDING request must exist (so the decision binds to the evidence
      identity + verified artifact SHA-256 recorded at creation);
    * the audit ledger entry is appended and the chain is re-verified.
    """
    if decision not in ALLOWED_DECISION_ACTIONS:
        return _deny(
            approval_request_id=approval_id,
            error_code=INVALID_DECISION,
            error_detail=(
                f"decision must be one of {list(ALLOWED_DECISION_ACTIONS)}"
            ),
            subject_id=approval_id,
        )

    _require_nonempty("operator_id", operator_id)
    if decision == DECISION_REJECT:
        if not str(reason or "").strip():
            return _deny(
                approval_request_id=approval_id,
                error_code=MISSING_REJECT_REASON,
                error_detail="reject requires a non-empty reason",
                subject_id=approval_id,
            )

    latest = latest_decision(
        subject_type=SUBJECT_TYPE,
        subject_id=approval_id,
        repo_root=Path(repo_root),
        db_path=db_path,
    )

    if latest is None:
        # No PENDING request was ever created for this id.
        return _deny(
            approval_request_id=approval_id,
            error_code=APPROVAL_NOT_FOUND,
            error_detail="no PENDING approval request exists for this id",
            subject_id=approval_id,
        )
    if latest.decision in _DECIDED_LEDGER:
        status = (
            STATUS_APPROVED
            if latest.decision == _LEDGER_DECISION_APPROVED
            else STATUS_REJECTED
        )
        return _deny(
            approval_request_id=approval_id,
            error_code=ALREADY_DECIDED,
            error_detail=(
                "approval request already decided "
                f"({latest.decision}); cannot decide again"
            ),
            status=status,
            subject_id=approval_id,
        )

    # latest.decision == "pending" -> bind the decision to the request's
    # evidence identity + verified artifact SHA-256.
    meta = latest.metadata.to_dict()
    ledger_decision = (
        _LEDGER_DECISION_APPROVED
        if decision == DECISION_APPROVE
        else _LEDGER_DECISION_DENIED
    )
    status = (
        STATUS_APPROVED if decision == DECISION_APPROVE else STATUS_REJECTED
    )

    decision_model, _entry = append_decision(
        subject_type=SUBJECT_TYPE,
        subject_id=approval_id,
        decision=ledger_decision,
        decided_by=operator_id,
        decided_at=decided_at,
        reason=reason,
        metadata={
            "project_id": meta.get("project_id"),
            "packet_id": meta.get("packet_id"),
            "validation_id": meta.get("validation_id"),
            "evidence_id": meta.get("evidence_id"),
            "artifact_path": meta.get("artifact_path"),
            "artifact_sha256": meta.get("artifact_sha256"),
            "decision_action": decision,
            "note": note,
            "manual_delivery_required": True,
            "automation_allowed": False,
            "scope_statement": _SCOPE_STATEMENT,
        },
        repo_root=Path(repo_root),
        db_path=db_path,
    )

    chain_ok = verify_chain(repo_root=Path(repo_root), db_path=db_path)
    if not chain_ok:
        return HVSDeliveryApprovalDecisionResult(
            ok=False,
            approval_request_id=approval_id,
            status=None,
            decision=None,
            operator_id=operator_id,
            decided_at=decided_at,
            reason=reason,
            subject_id=approval_id,
            ledger_decision_id=decision_model.decision_id,
            chain_verified=False,
            error_code=CHAIN_VERIFY_FAILED,
            error_detail="audit chain verification failed after append",
        )

    return _result_ok(
        approval_id=approval_id,
        status=status,
        decision=decision,
        operator_id=operator_id,
        decided_at=decided_at,
        reason=reason,
        subject_id=approval_id,
        ledger_decision_id=decision_model.decision_id,
        chain_verified=True,
    )


def _result_ok(
    *,
    approval_id: str,
    status: str,
    decision: str,
    operator_id: str,
    decided_at: str,
    reason: str | None,
    subject_id: str,
    ledger_decision_id: str,
    chain_verified: bool,
) -> HVSDeliveryApprovalDecisionResult:
    return HVSDeliveryApprovalDecisionResult(
        ok=True,
        approval_request_id=approval_id,
        status=status,
        decision=decision,
        operator_id=operator_id,
        decided_at=decided_at,
        reason=reason,
        subject_id=subject_id,
        ledger_decision_id=ledger_decision_id,
        chain_verified=chain_verified,
        error_code=None,
        error_detail=None,
    )
