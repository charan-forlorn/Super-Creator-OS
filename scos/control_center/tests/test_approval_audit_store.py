"""test_approval_audit_store.py - SCOS Stage 6.6 approval/audit store suite.

Covers durable persistence, restart survival via SQLite WAL, denial blocking
execution, and hash-chain tamper detection by mutating bytes in the actual
database file. Plain executable script (no pytest) following the repo's
__main__ dual-mode convention.

Run: python scos/control_center/tests/test_approval_audit_store.py
"""

from __future__ import annotations

import shutil
import struct
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from approval_audit_store import (  # noqa: E402
    append_decision,
    append_audit_entry,
    is_execution_granted,
    latest_decision,
    load_decisions,
    verify_chain,
)
from approval_audit_models import ApprovalDecision  # noqa: E402

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


def _tmp_db():
    tmp = Path(tempfile.mkdtemp(prefix="scos_audit_"))
    return tmp, tmp / "state" / "cc.sqlite3"


def _decision(subject_type="command", subject_id="cmd-1", decision="approved",
              decided_by="operator", decided_at="2026-07-08T00:00:00Z",
              reason="ok", metadata=None):
    return ApprovalDecision.of(
        subject_type=subject_type,
        subject_id=subject_id,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
        reason=reason,
        metadata=metadata,
    )


def test_1_append_and_load_decisions() -> None:
    tmp, db = _tmp_db()
    try:
        d, e = append_decision(
            subject_type="command", subject_id="cmd-1", decision="approved",
            decided_by="op", decided_at="t1", repo_root=tmp, db_path=db,
        )
        check("append returns a decision", isinstance(d, ApprovalDecision))
        check("append returns an audit entry", e.sequence == 1)
        loaded = load_decisions(subject_type="command", subject_id="cmd-1",
                                repo_root=tmp, db_path=db)
        check("one decision loaded", len(loaded) == 1)
        check("loaded decision is approved", loaded[0].decision == "approved")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_chain_valid_after_append() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="command", subject_id="cmd-1",
                        decision="pending", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)
        append_decision(subject_type="command", subject_id="cmd-1",
                        decision="approved", decided_by="op", decided_at="t2",
                        repo_root=tmp, db_path=db)
        check("chain verifies true after two appends", verify_chain(repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_persists_after_restart() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="git_proposal", subject_id="pr-7",
                        decision="approved", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)
        # Re-open against the same file (simulates process restart).
        loaded = load_decisions(subject_type="git_proposal", subject_id="pr-7",
                                repo_root=tmp, db_path=db)
        check("decision persists after reopen", len(loaded) == 1)
        check("persisted decision still approved", loaded[0].decision == "approved")
        check("chain still verifies after reopen", verify_chain(repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_4_denied_decision_persists_and_blocks() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="command", subject_id="cmd-deny",
                        decision="denied", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)
        latest = latest_decision(subject_type="command", subject_id="cmd-deny",
                                 repo_root=tmp, db_path=db)
        check("denied decision persisted", latest is not None and latest.decision == "denied")
        check("denied decision blocks execution", not is_execution_granted(
            subject_type="command", subject_id="cmd-deny", repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_5_pending_does_not_grant() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="packet", subject_id="pkt-1",
                        decision="pending", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)
        check("pending does not grant execution", not is_execution_granted(
            subject_type="packet", subject_id="pkt-1", repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_6_latest_decision_wins() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="command", subject_id="cmd-2",
                        decision="pending", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)
        append_decision(subject_type="command", subject_id="cmd-2",
                        decision="approved", decided_by="op", decided_at="t2",
                        repo_root=tmp, db_path=db)
        latest = latest_decision(subject_type="command", subject_id="cmd-2",
                                 repo_root=tmp, db_path=db)
        check("latest decision is approved", latest.decision == "approved")
        check("latest decision grants execution", is_execution_granted(
            subject_type="command", subject_id="cmd-2", repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_7_tamper_detected_in_persisted_db() -> None:
    tmp, db = _tmp_db()
    try:
        append_decision(subject_type="command", subject_id="cmd-1",
                        decision="approved", decided_by="op", decided_at="t1",
                        reason="original", repo_root=tmp, db_path=db)
        check("chain valid before tamper", verify_chain(repo_root=tmp, db_path=db))
        # Mutate the persisted payload in a UTF-8-safe way: replace the reason
        # text byte-for-byte with a different valid ASCII string so the row
        # still decodes, but the stored entry_hash no longer matches the
        # recomputed hash of the altered payload.
        raw = db.read_bytes()
        target = b"original"
        replacement = b"Xriginal"
        idx = raw.find(target)
        check("target reason found in db bytes", idx != -1)
        raw = raw[:idx] + replacement + raw[idx + len(target):]
        db.write_bytes(raw)
        # The stored entry_hash no longer matches the recomputed hash.
        check("verify_chain detects tampering", not verify_chain(repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_8_append_audit_entry_low_level() -> None:
    tmp, db = _tmp_db()
    try:
        d = _decision(subject_id="cmd-low", decided_at="t1")
        e = append_audit_entry(decision=d, repo_root=tmp, db_path=db)
        check("low-level append yields sequence 1", e.sequence == 1)
        check("chain verifies after low-level append", verify_chain(repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_9_existing_state_store_unaffected() -> None:
    # Importing the existing store must still work; schema version bump must
    # not break the prior DurableApprovalRecord table usage contract here.
    try:
        from sqlite_state_store import SQLiteStateStore  # noqa: F401
        from state_models import DurableApprovalRecord  # noqa: F401
        check("existing state store + models import cleanly", True)
    except Exception as exc:  # pragma: no cover
        check(f"existing state store import failed: {exc}", False)


def test_10_denial_blocks_execution_path_in_test() -> None:
    tmp, db = _tmp_db()
    try:
        # Simulate an execution path guarded by is_execution_granted.
        subject = ("command", "cmd-guard")
        append_decision(subject_type=subject[0], subject_id=subject[1],
                        decision="denied", decided_by="op", decided_at="t1",
                        repo_root=tmp, db_path=db)

        def execute():
            if not is_execution_granted(subject_type=subject[0],
                                        subject_id=subject[1],
                                        repo_root=tmp, db_path=db):
                raise PermissionError("denied: execution blocked")
            return "executed"

        blocked = False
        try:
            execute()
        except PermissionError:
            blocked = True
        check("denied decision blocks the execution path", blocked)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("test_approval_audit_store.py")
    test_1_append_and_load_decisions()
    test_2_chain_valid_after_append()
    test_3_persists_after_restart()
    test_4_denied_decision_persists_and_blocks()
    test_5_pending_does_not_grant()
    test_6_latest_decision_wins()
    test_7_tamper_detected_in_persisted_db()
    test_8_append_audit_entry_low_level()
    test_9_existing_state_store_unaffected()
    test_10_denial_blocks_execution_path_in_test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
