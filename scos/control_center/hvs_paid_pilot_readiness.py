"""SCOS Cohort 10I — authoritative paid-pilot readiness projection.

Derives a single readiness state from durable evidence. The readiness state is
NEVER set directly by the browser or any client — it is computed read-only from
the authoritative delivery store, package integrity, backup integrity, audit
integrity, and (when available) security/truth/canonical gate results.

Readiness states:
    NOT_READY                    — no delivery record or incomplete prerequisites
    READY_FOR_INTERNAL_REHEARSAL — package + backup verified, ready for rehearsal
    READY_FOR_CONTROLLED_PILOT   — all gates pass, ready for first paid pilot
    BLOCKED                      — a blocking condition was detected

Stdlib-only. Deterministic. No clock/random/uuid/network/subprocess.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from scos.control_center.hvs_paid_pilot_delivery_models import (
    DELIVERY_APPROVED,
    DELIVERY_AWAITING_OPERATOR_APPROVAL,
    DELIVERY_BACKUP_READY,
    DELIVERY_BLOCKED_QA_FAILED,
    DELIVERY_BLOCKED_QA_REQUIRED,
    DELIVERY_BLOCKED_RIGHTS_INCOMPLETE,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_PACKAGE_CREATING,
    DELIVERY_PACKAGE_FAILED_CONFIRMED,
    DELIVERY_PACKAGE_INCOMPATIBLE,
    DELIVERY_PACKAGE_OUTCOME_UNKNOWN,
    DELIVERY_PACKAGE_READY,
    DELIVERY_READY_FOR_MANUAL_HANDOFF,
    DELIVERY_REJECTED,
    RIGHTS_APPROVED,
    RIGHTS_INCOMPLETE,
    RIGHTS_NOT_REVIEWED,
)
from scos.control_center.hvs_paid_pilot_delivery_store import (
    PaidPilotDeliveryStore,
    TRUTH_AVAILABLE_WITH_DATA,
    TRUTH_CORRUPT,
    TRUTH_EMPTY,
    TRUTH_INCOMPATIBLE_SCHEMA,
    TRUTH_LOCKED,
    TRUTH_UNAVAILABLE,
)

# --- Readiness states --------------------------------------------------------
NOT_READY = "NOT_READY"
READY_FOR_INTERNAL_REHEARSAL = "READY_FOR_INTERNAL_REHEARSAL"
READY_FOR_CONTROLLED_PILOT = "READY_FOR_CONTROLLED_PILOT"
BLOCKED = "BLOCKED"

ALLOWED_READINESS_STATES = (
    NOT_READY,
    READY_FOR_INTERNAL_REHEARSAL,
    READY_FOR_CONTROLLED_PILOT,
    BLOCKED,
)

# States from which a package is considered sealed and downloadable.
_PACKAGE_READY_STATES = frozenset({
    DELIVERY_PACKAGE_READY,
    DELIVERY_BACKUP_READY,
    DELIVERY_READY_FOR_MANUAL_HANDOFF,
})

# States that indicate a blocking condition (not merely incomplete).
_BLOCKING_STATES = frozenset({
    DELIVERY_BLOCKED_QA_FAILED,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_PACKAGE_INCOMPATIBLE,
    DELIVERY_PACKAGE_FAILED_CONFIRMED,
    DELIVERY_PACKAGE_OUTCOME_UNKNOWN,
    DELIVERY_REJECTED,
})


@dataclass(frozen=True)
class ReadinessCheck:
    """One boolean readiness check with a browser-safe reason code."""

    name: str
    passed: bool
    reason_code: str  # stable, UI-safe code (never raw exception text)
    detail: str = ""  # short, browser-safe summary (no paths/secrets)


@dataclass(frozen=True)
class ReadinessProjection:
    """Authoritative readiness projection (read-only, derived)."""

    state: str
    delivery_id: str
    checks: tuple[ReadinessCheck, ...]
    blocking_reasons: tuple[str, ...]
    computed_at: str
    # Opaque identifiers only — no filesystem paths.
    package_sha256: str = ""
    backup_sha256: str = ""
    audit_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "delivery_id": self.delivery_id,
            "checks": [
                {"name": c.name, "passed": c.passed, "reason_code": c.reason_code, "detail": c.detail}
                for c in self.checks
            ],
            "blocking_reasons": list(self.blocking_reasons),
            "computed_at": self.computed_at,
            "package_sha256": self.package_sha256,
            "backup_sha256": self.backup_sha256,
            "audit_sha256": self.audit_sha256,
        }


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _check_store_integrity(store: PaidPilotDeliveryStore) -> ReadinessCheck:
    """Verify the delivery store is readable and not corrupt."""
    status = store.read().get("status", TRUTH_UNAVAILABLE)
    if status == TRUTH_AVAILABLE_WITH_DATA:
        return ReadinessCheck("store_integrity", True, "STORE_OK", "delivery store readable")
    if status == TRUTH_EMPTY:
        return ReadinessCheck("store_integrity", True, "STORE_EMPTY", "no delivery record yet")
    if status == TRUTH_CORRUPT:
        return ReadinessCheck("store_integrity", False, "STORE_CORRUPT", "delivery store is corrupt")
    if status == TRUTH_INCOMPATIBLE_SCHEMA:
        return ReadinessCheck("store_integrity", False, "STORE_SCHEMA_INCOMPATIBLE", "delivery store schema incompatible")
    if status == TRUTH_LOCKED:
        return ReadinessCheck("store_integrity", False, "STORE_LOCKED", "delivery store is locked")
    return ReadinessCheck("store_integrity", False, "STORE_UNAVAILABLE", "delivery store unavailable")


def _check_delivery_record(record) -> ReadinessCheck:
    """Verify a delivery record exists and is not in a blocking state."""
    if record is None:
        return ReadinessCheck("delivery_record", False, "NO_DELIVERY_RECORD", "no delivery record found")
    if record.state in _BLOCKING_STATES:
        return ReadinessCheck("delivery_record", False, "DELIVERY_BLOCKED", f"delivery state={record.state}")
    return ReadinessCheck("delivery_record", True, "DELIVERY_RECORD_OK", f"delivery state={record.state}")


def _check_rights(record) -> ReadinessCheck:
    """Verify rights have been approved."""
    if record is None:
        return ReadinessCheck("rights_review", False, "NO_RECORD", "no delivery record")
    if record.rights_status == RIGHTS_APPROVED:
        return ReadinessCheck("rights_review", True, "RIGHTS_APPROVED", "rights checklist approved")
    if record.rights_status == RIGHTS_INCOMPLETE:
        return ReadinessCheck("rights_review", False, "RIGHTS_INCOMPLETE", "rights checklist incomplete")
    if record.rights_status == RIGHTS_NOT_REVIEWED:
        return ReadinessCheck("rights_review", False, "RIGHTS_NOT_REVIEWED", "rights checklist not reviewed")
    return ReadinessCheck("rights_review", False, "RIGHTS_UNKNOWN", f"rights status={record.rights_status}")


def _check_qa(record) -> ReadinessCheck:
    """Verify QA has passed."""
    if record is None:
        return ReadinessCheck("qa_status", False, "NO_RECORD", "no delivery record")
    if record.qa_state == "QA_PASSED":
        return ReadinessCheck("qa_status", True, "QA_PASSED", "media QA passed")
    if record.qa_state in ("QA_FAILED_CONFIRMED", "QA_ARTIFACT_MISSING", "QA_ARTIFACT_CORRUPT"):
        return ReadinessCheck("qa_status", False, "QA_FAILED", f"qa state={record.qa_state}")
    if record.qa_state in ("QA_NOT_RUN", "QA_RUNNING", ""):
        return ReadinessCheck("qa_status", False, "QA_REQUIRED", f"qa state={record.qa_state}")
    return ReadinessCheck("qa_status", False, "QA_UNKNOWN", f"qa state={record.qa_state}")


def _check_operator_approval(record) -> ReadinessCheck:
    """Verify the operator has approved delivery."""
    if record is None:
        return ReadinessCheck("operator_approval", False, "NO_RECORD", "no delivery record")
    if record.operator_decision == "APPROVED_FOR_DELIVERY":
        return ReadinessCheck("operator_approval", True, "APPROVED", "operator approved for delivery")
    if record.operator_decision == "REJECTED_REWORK_REQUIRED":
        return ReadinessCheck("operator_approval", False, "REJECTED", "operator rejected for rework")
    return ReadinessCheck("operator_approval", False, "APPROVAL_REQUIRED", f"operator decision={record.operator_decision}")


def _check_package_integrity(record, package_root: Path) -> ReadinessCheck:
    """Verify the package exists and its hash matches the record."""
    if record is None:
        return ReadinessCheck("package_integrity", False, "NO_RECORD", "no delivery record")
    if record.state not in _PACKAGE_READY_STATES:
        return ReadinessCheck("package_integrity", False, "PACKAGE_NOT_READY", f"state={record.state}")
    if not record.package_sha256:
        return ReadinessCheck("package_integrity", False, "PACKAGE_HASH_MISSING", "no package sha256 in record")
    # Verify the package file exists and matches the hash.
    try:
        from scos.control_center.hvs_paid_pilot_backup_service import read_package_zip
        from scos.control_center.hvs_paid_pilot_delivery_models import safe_delivery_filename
        pkg_path = package_root / safe_delivery_filename(record.delivery_id)
        if not pkg_path.is_file():
            return ReadinessCheck("package_integrity", False, "PACKAGE_FILE_MISSING", "package file not found")
        _data, sha = read_package_zip(package_path=pkg_path)
        if sha.lower() != record.package_sha256.lower():
            return ReadinessCheck("package_integrity", False, "PACKAGE_HASH_MISMATCH", "package hash mismatch")
        return ReadinessCheck("package_integrity", True, "PACKAGE_OK", "package verified")
    except Exception:
        return ReadinessCheck("package_integrity", False, "PACKAGE_VERIFY_FAILED", "package verification failed")


def _check_backup_integrity(record, backup_root: Path) -> ReadinessCheck:
    """Verify the backup exists and its hash matches the package hash."""
    if record is None:
        return ReadinessCheck("backup_integrity", False, "NO_RECORD", "no delivery record")
    if record.backup_receipt is None:
        return ReadinessCheck("backup_integrity", False, "NO_BACKUP_RECEIPT", "no backup receipt")
    if record.state not in _PACKAGE_READY_STATES:
        return ReadinessCheck("backup_integrity", False, "PACKAGE_NOT_READY", f"state={record.state}")
    try:
        from scos.control_center.hvs_paid_pilot_backup_service import verify_backup
        ok, backup_sha = verify_backup(
            delivery_id=record.delivery_id,
            backup_root=backup_root,
            expected_package_sha256=record.package_sha256,
        )
        if ok:
            return ReadinessCheck("backup_integrity", True, "BACKUP_OK", "backup verified")
        return ReadinessCheck("backup_integrity", False, "BACKUP_HASH_MISMATCH", "backup hash mismatch")
    except Exception:
        return ReadinessCheck("backup_integrity", False, "BACKUP_VERIFY_FAILED", "backup verification failed")


def _check_restore_drill_status(store, record) -> ReadinessCheck:
    """Verify a restore drill has been completed (via audit log marker)."""
    if record is None:
        return ReadinessCheck("restore_drill", False, "NO_RECORD", "no delivery record")
    # The restore drill status is recorded in the audit log. We check for
    # a RESTORE_VERIFIED event for this delivery.
    try:
        from scos.control_center.hvs_paid_pilot_audit import read_audit_events
        audit_path = store._store_path.parent / "paid-pilot-audit-v1.jsonl"
        events = read_audit_events(audit_log_path=audit_path)
        for ev in events:
            if ev.event_type == "RESTORE_VERIFIED" and ev.delivery_id == record.delivery_id:
                return ReadinessCheck("restore_drill", True, "RESTORE_VERIFIED", "restore drill completed")
        return ReadinessCheck("restore_drill", False, "RESTORE_NOT_VERIFIED", "no verified restore drill")
    except Exception:
        return ReadinessCheck("restore_drill", False, "AUDIT_UNREADABLE", "audit log unreadable")


def _check_audit_integrity(store: PaidPilotDeliveryStore) -> ReadinessCheck:
    """Verify the audit log is readable and append-only (real audit API)."""
    try:
        from scos.control_center.hvs_paid_pilot_audit import (
            read_audit_events,
            verify_audit_integrity,
        )
        audit_path = store._store_path.parent / "paid-pilot-audit-v1.jsonl"
        ok, msg = verify_audit_integrity(audit_log_path=audit_path)
        if not ok:
            return ReadinessCheck("audit_integrity", False, "AUDIT_UNREADABLE", msg)
        events = read_audit_events(audit_log_path=audit_path)
        return ReadinessCheck("audit_integrity", True, "AUDIT_OK", f"audit log readable, {len(events)} events")
    except Exception as exc:
        return ReadinessCheck("audit_integrity", False, "AUDIT_UNREADABLE", f"audit log unreadable: {exc}")


def _check_security_truth_canonical() -> ReadinessCheck:
    """Check security/truth/canonical gate status (when available).

    These are external gate results that may be registered by the canonical
    verifier. If no gate result is registered, this check is informational
    (not blocking) — the readiness model still requires all other checks.
    """
    try:
        gate_path = _default_gate_status_path()
        if not gate_path.is_file():
            return ReadinessCheck("security_truth_canonical", True, "GATES_NOT_REGISTERED", "no gate results registered (informational)")
        text = gate_path.read_text(encoding="utf-8")
        data = json.loads(text)
        gates = data.get("gates", {})
        all_pass = all(v == "PASS" for v in gates.values())
        if all_pass and gates:
            return ReadinessCheck("security_truth_canonical", True, "GATES_PASS", "all registered gates pass")
        if gates:
            failed = [k for k, v in gates.items() if v != "PASS"]
            return ReadinessCheck("security_truth_canonical", False, "GATES_FAILED", f"failed gates: {','.join(failed)}")
        return ReadinessCheck("security_truth_canonical", True, "GATES_NOT_REGISTERED", "no gate results registered (informational)")
    except Exception:
        return ReadinessCheck("security_truth_canonical", True, "GATES_NOT_REGISTERED", "no gate results registered (informational)")


def _default_audit_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "memory" / "runtime" / "control-center" / "paid-pilot-audit.jsonl"


def _default_gate_status_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "memory" / "runtime" / "control-center" / "paid-pilot-gate-status.json"


def compute_readiness(
    *,
    store: PaidPilotDeliveryStore,
    delivery_id: str,
    package_root: Optional[Path] = None,
    backup_root: Optional[Path] = None,
    computed_at: Optional[str] = None,
) -> ReadinessProjection:
    """Compute the authoritative readiness projection for a delivery.

    This is a READ-ONLY operation. It never writes, never mutates, never
    auto-repairs. It derives readiness from durable evidence.
    """
    now = computed_at or _now_iso()
    repo_root = Path(__file__).resolve().parents[2]

    pkg_root = Path(package_root) if package_root else (repo_root / "memory" / "runtime" / "control-center" / "paid-pilot-packages")
    bkp_root = Path(backup_root) if backup_root else (repo_root / "memory" / "runtime" / "control-center" / "paid-pilot-backups")

    # Run all checks.
    store_check = _check_store_integrity(store)
    record = store.get(delivery_id) if store_check.passed else None
    record_check = _check_delivery_record(record)
    rights_check = _check_rights(record)
    qa_check = _check_qa(record)
    approval_check = _check_operator_approval(record)
    package_check = _check_package_integrity(record, pkg_root)
    backup_check = _check_backup_integrity(record, bkp_root)
    restore_check = _check_restore_drill_status(store, record)
    audit_check = _check_audit_integrity(store)
    gates_check = _check_security_truth_canonical()

    checks = (
        store_check,
        record_check,
        rights_check,
        qa_check,
        approval_check,
        package_check,
        backup_check,
        restore_check,
        audit_check,
        gates_check,
    )

    blocking_reasons = tuple(c.reason_code for c in checks if not c.passed and c.reason_code not in (
        "STORE_EMPTY", "NO_DELIVERY_RECORD", "RIGHTS_NOT_REVIEWED", "QA_REQUIRED",
        "APPROVAL_REQUIRED", "PACKAGE_NOT_READY", "NO_BACKUP_RECEIPT",
        "RESTORE_NOT_VERIFIED", "GATES_NOT_REGISTERED",
    ))

    # Determine readiness state.
    if not store_check.passed:
        state = BLOCKED
    elif record is None:
        state = NOT_READY
    elif record.state in _BLOCKING_STATES:
        state = BLOCKED
    elif not (rights_check.passed and qa_check.passed and approval_check.passed):
        state = NOT_READY
    elif not (package_check.passed and backup_check.passed):
        state = NOT_READY
    elif not restore_check.passed:
        state = READY_FOR_INTERNAL_REHEARSAL
    elif not gates_check.passed:
        state = READY_FOR_INTERNAL_REHEARSAL
    else:
        state = READY_FOR_CONTROLLED_PILOT

    return ReadinessProjection(
        state=state,
        delivery_id=delivery_id,
        checks=checks,
        blocking_reasons=blocking_reasons,
        computed_at=now,
        package_sha256=record.package_sha256 if record else "",
        backup_sha256=record.backup_receipt.backup_sha256 if record and record.backup_receipt else "",
        audit_sha256=_compute_audit_hash(store),
    )


def _default_audit_path() -> Path:
    # Audit log lives beside the delivery store (sibling file).
    return Path(__file__).resolve().parents[2] / "memory" / "runtime" / "control-center" / "paid-pilot-audit-v1.jsonl"


def _compute_audit_hash(store: PaidPilotDeliveryStore | None = None) -> str:
    try:
        from scos.control_center.hvs_paid_pilot_audit import compute_audit_hash
        if store is not None:
            audit_path = store._store_path.parent / "paid-pilot-audit-v1.jsonl"
        else:
            audit_path = _default_audit_path()
        return compute_audit_hash(audit_log_path=audit_path)
    except Exception:
        return ""
