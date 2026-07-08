"""test_approval_audit_integration.py - SCOS Stage 6.7 integration suite.

Wires the Stage 6.6 approval-audit ledger into the operator approval gate and
command runner, and verifies:

  * approve_command / reject_command persist to the tamper-evident ledger
  * run_approved_command is blocked unless the ledger grants execution
  * a persisted denial survives a new store instance and still blocks
  * a tampered ledger blocks execution (hash chain invalid)
  * command_runner reads the ledger but never appends a duplicate row

Plain executable script (no pytest) following the repo's __main__ dual-mode
convention. Uses a temporary SQLite DB, never touches the real repo state.

Run: python scos/control_center/tests/test_approval_audit_integration.py
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

from approval_audit_store import is_execution_granted, verify_chain  # noqa: E402
from command_models import ApprovedCommand, CommandDraft  # noqa: E402
from command_runner import run_approved_command  # noqa: E402
from operator_approval import approve_command, reject_command  # noqa: E402

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
    tmp = Path(tempfile.mkdtemp(prefix="scos_67_"))
    return tmp, tmp / "state" / "cc.sqlite3"


def _draft(command_id="cmd-67", command_type="RUN_SMOKE_CHECK"):
    return CommandDraft.of(
        command_id=command_id,
        command_type=command_type,
        requested_by="operator-a",
        created_at="2026-07-05T10:00:00Z",
        summary="smoke check",
        args=(),
        metadata=(("origin", "control-center"),),
    )


def _approved_command(command_id="cmd-67"):
    return ApprovedCommand.of(
        command_id=command_id,
        command_type="RUN_SMOKE_CHECK",
        approved_by="operator-a",
        approved_at="2026-07-05T10:05:00Z",
    )


def test_approve_persists_ledger_row() -> None:
    tmp, db = _tmp_db()
    try:
        approve_command(
            draft=_draft(),
            approved_by="operator-a",
            approved_at="2026-07-05T10:05:00Z",
            reason="reviewed",
            repo_root=tmp,
            db_path=db,
        )
        check("is_execution_granted True after approve", is_execution_granted(
            subject_type="command", subject_id="cmd-67",
            repo_root=tmp, db_path=db))
        check("chain intact after approve", verify_chain(repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_reject_persists_denial() -> None:
    tmp, db = _tmp_db()
    try:
        reject_command(
            draft=_draft(),
            rejected_by="operator-a",
            rejected_at="2026-07-05T10:05:00Z",
            reason="not safe",
            repo_root=tmp,
            db_path=db,
        )
        check("is_execution_granted False after reject",
              not is_execution_granted(
                  subject_type="command", subject_id="cmd-67",
                  repo_root=tmp, db_path=db))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rejected_command_blocks_runner() -> None:
    tmp, db = _tmp_db()
    try:
        reject_command(
            draft=_draft(),
            rejected_by="operator-a",
            rejected_at="2026-07-05T10:05:00Z",
            reason="no",
            repo_root=tmp,
            db_path=db,
        )
        result = run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
            enforce_audit_grant=True,
            audit_repo_root=tmp, audit_db_path=db,
        )
        check("denied command blocked by runner", result.ok is False)
        check("blocked reason recorded",
              dict(result.metadata).get("blocked_reason", "").startswith(
                  "execution not granted"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_ledger_blocks_execution() -> None:
    tmp, db = _tmp_db()
    try:
        # No approval recorded at all.
        result = run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
            enforce_audit_grant=True,
            audit_repo_root=tmp, audit_db_path=db,
        )
        check("missing ledger blocks execution", result.ok is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_denial_survives_restart_and_blocks() -> None:
    tmp, db = _tmp_db()
    try:
        reject_command(
            draft=_draft(),
            rejected_by="operator-a",
            rejected_at="2026-07-05T10:05:00Z",
            reason="no",
            repo_root=tmp,
            db_path=db,
        )
        # Re-open against the same file (simulates a fresh store instance).
        granted = is_execution_granted(
            subject_type="command", subject_id="cmd-67",
            repo_root=tmp, db_path=db)
        check("denial persists after reopen", granted is False)
        result = run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
            enforce_audit_grant=True,
            audit_repo_root=tmp, audit_db_path=db,
        )
        check("runner still blocks after restart", result.ok is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tampered_ledger_blocks() -> None:
    tmp, db = _tmp_db()
    try:
        approve_command(
            draft=_draft(),
            approved_by="operator-a",
            approved_at="2026-07-05T10:05:00Z",
            reason="original",
            repo_root=tmp,
            db_path=db,
        )
        # Tamper the persisted payload byte-for-byte (valid UTF-8).
        raw = db.read_bytes()
        idx = raw.find(b"original")
        raw = raw[:idx] + b"Xriginal" + raw[idx + len(b"original"):]
        db.write_bytes(raw)
        check("verify_chain detects tampering",
              not verify_chain(repo_root=tmp, db_path=db))
        result = run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
            enforce_audit_grant=True,
            audit_repo_root=tmp, audit_db_path=db,
        )
        check("tampered ledger blocks execution", result.ok is False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_runner_does_not_duplicate_ledger_rows() -> None:
    tmp, db = _tmp_db()
    try:
        approve_command(
            draft=_draft(),
            approved_by="operator-a",
            approved_at="2026-07-05T10:05:00Z",
            reason="ok",
            repo_root=tmp,
            db_path=db,
        )
        before = _count_rows(tmp, db)
        # run_approved_command with enforce on must NOT append a ledger row.
        run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
            enforce_audit_grant=True,
            audit_repo_root=tmp, audit_db_path=db,
        )
        after = _count_rows(tmp, db)
        check("runner appends no duplicate ledger row", after == before)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _count_rows(repo_root, db_path):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM audit_ledger").fetchone()[0]
    finally:
        conn.close()


def test_existing_runner_still_works_without_enforcement() -> None:
    # Pre-6.7 behavior preserved: no ledger, no enforcement flag -> executes.
    tmp, db = _tmp_db()
    try:
        result = run_approved_command(
            repo_root=str(tmp),
            approved_command=_approved_command(),
            started_at="t1", finished_at="t2",
            dry_run=True,
        )
        check("runner executes without enforcement (backward compat)",
              result.ok is True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("test_approval_audit_integration.py")
    test_approve_persists_ledger_row()
    test_reject_persists_denial()
    test_rejected_command_blocks_runner()
    test_missing_ledger_blocks_execution()
    test_denial_survives_restart_and_blocks()
    test_tampered_ledger_blocks()
    test_runner_does_not_duplicate_ledger_rows()
    test_existing_runner_still_works_without_enforcement()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
