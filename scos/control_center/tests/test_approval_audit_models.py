"""test_approval_audit_models.py - SCOS Stage 6.6 approval/audit models suite.

Covers deterministic hash-chain creation, stable hashes, payload-change
detection, prev_hash linking, and entry_hash recomputation. Plain executable
script (no pytest) following the repo's __main__ dual-mode convention.

Run: python scos/control_center/tests/test_approval_audit_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from approval_audit_models import (  # noqa: E402
    GENESIS_PREV_HASH,
    ApprovalDecision,
    AuditEntry,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _decision(subject_type="command", subject_id="cmd-1", decision="approved",
              decided_by="operator", decided_at="2026-07-08T00:00:00Z",
              reason="looks good", metadata=None):
    return ApprovalDecision.of(
        subject_type=subject_type,
        subject_id=subject_id,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
        reason=reason,
        metadata=metadata,
    )


def test_1_deterministic_hash_chain() -> None:
    d = _decision()
    e1 = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d)
    e2 = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d)
    check("same decision builds identical entry_hash", e1.entry_hash == e2.entry_hash)
    check("genesis prev_hash is sentinel", e1.prev_hash == GENESIS_PREV_HASH)
    check("entry recompute matches stored hash", e1.recompute_entry_hash() == e1.entry_hash)


def test_2_same_payload_stable_hash() -> None:
    d_a = _decision(decided_at="2026-07-08T00:00:00Z")
    d_b = _decision(decided_at="2026-07-08T00:00:00Z")
    check("identical decisions share decision_id", d_a.decision_id == d_b.decision_id)
    e_a = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d_a)
    e_b = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d_b)
    check("identical decisions share entry_id", e_a.entry_id == e_b.entry_id)


def test_3_change_payload_changes_hash() -> None:
    d_a = _decision(decision="approved")
    d_b = _decision(decision="denied")
    e_a = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d_a)
    e_b = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d_b)
    check("different decision values yield different entry_hash", e_a.entry_hash != e_b.entry_hash)
    check("different decision values yield different decision_id", d_a.decision_id != d_b.decision_id)


def test_4_prev_hash_links_entries() -> None:
    d1 = _decision(subject_id="cmd-1", decided_at="t1")
    d2 = _decision(subject_id="cmd-1", decided_at="t2")
    e1 = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d1)
    e2 = AuditEntry.of(sequence=2, prev_hash=e1.entry_hash, decision=d2)
    check("entry2.prev_hash equals entry1.entry_hash", e2.prev_hash == e1.entry_hash)
    check("entry2 does not equal entry1 hash", e2.entry_hash != e1.entry_hash)


def test_5_verify_valid_chain_returns_true() -> None:
    # Model-level chain validity (store-level persistence test in the store suite).
    d1 = _decision(subject_id="cmd-1", decided_at="t1")
    d2 = _decision(subject_id="cmd-1", decided_at="t2")
    e1 = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d1)
    e2 = AuditEntry.of(sequence=2, prev_hash=e1.entry_hash, decision=d2)
    check("valid two-entry chain recomputes consistently",
          e1.recompute_entry_hash() == e1.entry_hash and e2.recompute_entry_hash() == e2.entry_hash)
    check("e2.prev_hash links to e1 hash", e2.prev_hash == e1.entry_hash)


def test_6_tampered_payload_detected() -> None:
    d = _decision(reason="original reason")
    e = AuditEntry.of(sequence=1, prev_hash=GENESIS_PREV_HASH, decision=d)
    # Tamper: pretend the stored payload differs from the hash.
    tampered = AuditEntry(
        entry_id=e.entry_id,
        sequence=e.sequence,
        prev_hash=e.prev_hash,
        entry_hash=e.entry_hash,
        decision_id=e.decision_id,
        subject_type=e.subject_type,
        subject_id=e.subject_id,
        decision=e.decision,
        decided_by=e.decided_by,
        decided_at=e.decided_at,
        reason="altered reason",
        metadata_json=e.metadata_json,
    )
    check("tampered reason changes recomputed hash", tampered.recompute_entry_hash() != tampered.entry_hash)


def test_7_decision_id_content_derived() -> None:
    d1 = _decision(decided_by="alice")
    d2 = _decision(decided_by="bob")
    check("different operator yields different decision_id", d1.decision_id != d2.decision_id)


def test_8_invalid_decision_rejected() -> None:
    raised = False
    try:
        ApprovalDecision.of(
            subject_type="command",
            subject_id="cmd-x",
            decision="maybe",  # not allowed
            decided_by="op",
            decided_at="t",
        )
    except ValueError:
        raised = True
    check("invalid decision value raises ValueError", raised)


def test_9_invalid_subject_type_rejected() -> None:
    raised = False
    try:
        ApprovalDecision.of(
            subject_type="rocket_launch",  # not allowed
            subject_id="x",
            decision="approved",
            decided_by="op",
            decided_at="t",
        )
    except ValueError:
        raised = True
    check("invalid subject_type raises ValueError", raised)


def test_10_secret_metadata_rejected() -> None:
    raised = False
    try:
        _decision(metadata={"api_key": "sk-123"})
    except ValueError:
        raised = True
    check("secret-bearing metadata key raises ValueError", raised)


def main() -> int:
    print("test_approval_audit_models.py")
    test_1_deterministic_hash_chain()
    test_2_same_payload_stable_hash()
    test_3_change_payload_changes_hash()
    test_4_prev_hash_links_entries()
    test_5_verify_valid_chain_returns_true()
    test_6_tampered_payload_detected()
    test_7_decision_id_content_derived()
    test_8_invalid_decision_rejected()
    test_9_invalid_subject_type_rejected()
    test_10_secret_metadata_rejected()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
