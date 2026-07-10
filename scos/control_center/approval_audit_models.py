"""SCOS Stage 6.6 operator approval persistence & audit trail models.

Immutable dataclasses for a unified, append-only, tamper-evident approval
and audit ledger. Every operator approve/deny decision for any subject
(commands, packets, git proposals, future adapter dispatches) is modeled as
an ``ApprovalDecision`` and recorded as an ``AuditEntry`` in a SHA-256 hash
chain.

IDs are content-derived (SHA-256 over the canonical payload), so identical
inputs always produce identical ids. ``entry_hash`` is the hash-chain link:
each entry commits to its predecessor via ``prev_hash`` and to its own
canonical payload via ``entry_hash``.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    from .operator_packet_review_models import FrozenMap
    from .sqlite_state_schema import stable_json_dumps
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap
    from sqlite_state_schema import stable_json_dumps

CONTROL_CENTER_APPROVAL_AUDIT_SCHEMA_VERSION = 1

ALLOWED_APPROVAL_DECISIONS = ("pending", "approved", "denied")

ALLOWED_APPROVAL_SUBJECT_TYPES = (
    "command",
    "packet",
    "git_proposal",
    "adapter_dispatch",
    "hvs_delivery_approval",
)

# Genesis entries have no predecessor; the chain links to this sentinel.
GENESIS_PREV_HASH = "0" * 64

_DIGEST_LENGTH = 16


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _require_nonempty(field_name: str, value: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_str(value) -> str | None:
    return None if value is None else str(value)


def _frozen_map(value=None) -> FrozenMap:
    if isinstance(value, FrozenMap):
        return value
    return FrozenMap.of(value)


def _canonical_decision_pairs(
    *,
    subject_type: str,
    subject_id: str,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str | None,
    metadata: FrozenMap,
) -> tuple[tuple[str, str], ...]:
    """Deterministic (key, value) pairs for a decision's canonical payload.

    Sorted by key so the same decision always hashes to the same id.
    """
    return (
        ("subject_type", subject_type),
        ("subject_id", subject_id),
        ("decision", decision),
        ("decided_by", decided_by),
        ("decided_at", decided_at),
        ("reason", "" if reason is None else str(reason)),
        ("metadata_json", stable_json_dumps(metadata.to_dict())),
    )


def _canonical_entry_pairs(
    *,
    sequence: int,
    prev_hash: str,
    decision_id: str,
    subject_type: str,
    subject_id: str,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str | None,
    metadata_json: str,
) -> tuple[tuple[str, str], ...]:
    """Deterministic (key, value) pairs for an audit entry's canonical payload.

    Excludes the entry's own ``entry_hash`` / ``entry_id`` (derived outputs).
    """
    return (
        ("sequence", str(sequence)),
        ("prev_hash", prev_hash),
        ("decision_id", decision_id),
        ("subject_type", subject_type),
        ("subject_id", subject_id),
        ("decision", decision),
        ("decided_by", decided_by),
        ("decided_at", decided_at),
        ("reason", "" if reason is None else str(reason)),
        ("metadata_json", metadata_json),
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _short_id(canonical_pairs: tuple[tuple[str, str], ...]) -> str:
    canonical = "\n".join(f"{k}={v}" for k, v in canonical_pairs)
    return _sha256_hex(canonical)[:_DIGEST_LENGTH]


@dataclass(frozen=True)
class ApprovalDecision:
    """A single operator approve/deny decision for one subject."""

    decision_id: str
    subject_type: str
    subject_id: str
    decision: str
    decided_by: str
    decided_at: str
    reason: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "subject_type", str(self.subject_type))
        object.__setattr__(self, "subject_id", str(self.subject_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", _optional_str(self.reason))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("subject_type", self.subject_type)
        _require_nonempty("subject_id", self.subject_id)
        _require_nonempty("decided_by", self.decided_by)
        _require_nonempty("decided_at", self.decided_at)
        _require_allowed("subject_type", self.subject_type, ALLOWED_APPROVAL_SUBJECT_TYPES)
        _require_allowed("decision", self.decision, ALLOWED_APPROVAL_DECISIONS)
        _require_nonempty("decision_id", self.decision_id)

    @staticmethod
    def of(
        *,
        subject_type: str,
        subject_id: str,
        decision: str,
        decided_by: str,
        decided_at: str,
        reason: str | None = None,
        metadata=None,
    ) -> "ApprovalDecision":
        metadata_map = _frozen_map(metadata)
        pairs = _canonical_decision_pairs(
            subject_type=subject_type,
            subject_id=subject_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            metadata=metadata_map,
        )
        decision_id = _short_id(pairs)
        return ApprovalDecision(
            decision_id=decision_id,
            subject_type=subject_type,
            subject_id=subject_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=_optional_str(reason),
            metadata=metadata_map,
        )

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class AuditEntry:
    """One append-only, hash-chained audit entry recording a decision."""

    entry_id: str
    sequence: int
    prev_hash: str
    entry_hash: str
    decision_id: str
    subject_type: str
    subject_id: str
    decision: str
    decided_by: str
    decided_at: str
    reason: str | None
    metadata_json: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", str(self.entry_id))
        object.__setattr__(self, "sequence", int(self.sequence))
        object.__setattr__(self, "prev_hash", str(self.prev_hash))
        object.__setattr__(self, "entry_hash", str(self.entry_hash))
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "subject_type", str(self.subject_type))
        object.__setattr__(self, "subject_id", str(self.subject_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", _optional_str(self.reason))
        object.__setattr__(self, "metadata_json", str(self.metadata_json))
        _require_nonempty("entry_id", self.entry_id)
        _require_nonempty("decision_id", self.decision_id)
        _require_nonempty("subject_type", self.subject_type)
        _require_nonempty("subject_id", self.subject_id)
        _require_nonempty("decided_by", self.decided_by)
        _require_nonempty("decided_at", self.decided_at)
        _require_nonempty("prev_hash", self.prev_hash)
        _require_nonempty("entry_hash", self.entry_hash)
        _require_allowed("decision", self.decision, ALLOWED_APPROVAL_DECISIONS)
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")

    @staticmethod
    def of(
        *,
        sequence: int,
        prev_hash: str,
        decision: ApprovalDecision,
        metadata_json: str | None = None,
    ) -> "AuditEntry":
        """Build an ``AuditEntry`` for a decision, computing its ``entry_hash``."""
        if not isinstance(decision, ApprovalDecision):
            raise ValueError("decision must be an ApprovalDecision")
        meta_json = (
            metadata_json
            if metadata_json is not None
            else stable_json_dumps(decision.metadata.to_dict())
        )
        pairs = _canonical_entry_pairs(
            sequence=sequence,
            prev_hash=prev_hash,
            decision_id=decision.decision_id,
            subject_type=decision.subject_type,
            subject_id=decision.subject_id,
            decision=decision.decision,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
            reason=decision.reason,
            metadata_json=meta_json,
        )
        entry_hash = _sha256_hex("\n".join(f"{k}={v}" for k, v in pairs))
        entry_id = _short_id(pairs)
        return AuditEntry(
            entry_id=entry_id,
            sequence=sequence,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            decision_id=decision.decision_id,
            subject_type=decision.subject_type,
            subject_id=decision.subject_id,
            decision=decision.decision,
            decided_by=decision.decided_by,
            decided_at=decision.decided_at,
            reason=_optional_str(decision.reason),
            metadata_json=meta_json,
        )

    def canonical_entry_pairs(self) -> tuple[tuple[str, str], ...]:
        """The canonical payload pairs used to (re)compute ``entry_hash``."""
        return _canonical_entry_pairs(
            sequence=self.sequence,
            prev_hash=self.prev_hash,
            decision_id=self.decision_id,
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            decision=self.decision,
            decided_by=self.decided_by,
            decided_at=self.decided_at,
            reason=self.reason,
            metadata_json=self.metadata_json,
        )

    def recompute_entry_hash(self) -> str:
        return _sha256_hex(
            "\n".join(f"{k}={v}" for k, v in self.canonical_entry_pairs())
        )

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "sequence": self.sequence,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "decision_id": self.decision_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "metadata_json": self.metadata_json,
        }
