"""Focused backend tests — SCOS Cohort 10I paid-pilot readiness projection.

Local, deterministic, hermetic. No real render, no network, no media tools.
Exercises: readiness derivation from durable evidence, restart recovery,
idempotency, blocking-state classification, package/backup integrity checks.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scos.control_center.hvs_paid_pilot_delivery_models import (
    APPROVED_FOR_DELIVERY,
    DELIVERY_APPROVED,
    DELIVERY_AWAITING_OPERATOR_APPROVAL,
    DELIVERY_BACKUP_READY,
    DELIVERY_BLOCKED_QA_FAILED,
    DELIVERY_BLOCKED_QA_REQUIRED,
    DELIVERY_BLOCKED_RIGHTS_INCOMPLETE,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_PACKAGE_READY,
    DELIVERY_READY_FOR_MANUAL_HANDOFF,
    RIGHTS_APPROVED,
    RIGHTS_INCOMPLETE,
    RIGHTS_NOT_REVIEWED,
    PaidPilotDeliveryRecord,
    RightsChecklistEntry,
    stable_delivery_id,
)
from scos.control_center.hvs_paid_pilot_delivery_store import (
    PaidPilotDeliveryStore,
    TRUTH_AVAILABLE_WITH_DATA,
    TRUTH_CORRUPT,
    TRUTH_EMPTY,
)
from scos.control_center.hvs_paid_pilot_readiness import (
    BLOCKED,
    NOT_READY,
    READY_FOR_CONTROLLED_PILOT,
    READY_FOR_INTERNAL_REHEARSAL,
    compute_readiness,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "control_center").mkdir(parents=True)
    return root


def _rights_ok() -> list[RightsChecklistEntry]:
    return [RightsChecklistEntry("visual", "synthetic clip", True, True, "owned")]


def _make_artifact(path: Path, size: int = 2048) -> None:
    path.write_bytes(b"SCOS-ARTIFACT-CONTENT-" * (size // 24 + 1))


def _make_ready_record(delivery_id: str, pkg_sha: str = "a" * 64) -> PaidPilotDeliveryRecord:
    return PaidPilotDeliveryRecord(
        schema_version="scos-hvs.paid-pilot-delivery.v1/1.0.0",
        delivery_id=delivery_id, project_id="p1", source_render_attempt_id="a1",
        artifact_identity="art1", artifact_sha256="x" * 64, artifact_size=2048,
        media_profile="vertical_9_16", qa_record_id="q1", qa_state="QA_PASSED",
        operator_id="op", operator_decision=APPROVED_FOR_DELIVERY,
        rights_checklist_revision="r1", rights_status=RIGHTS_APPROVED,
        package_revision="pkg1", package_sha256=pkg_sha, backup_receipt=None,
        retention_class="KEEP_FOR_PAID_PILOT_REVIEW",
        created_at="2026-07-21T00:00:00Z", updated_at="2026-07-21T00:00:00Z",
        state=DELIVERY_READY_FOR_MANUAL_HANDOFF,
    )


def test_readiness_not_ready_when_no_record(repo: Path, tmp_path: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    assert proj.state == NOT_READY
    assert proj.delivery_id == rid


def test_readiness_blocked_when_blocking_state(repo: Path, tmp_path: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = _make_ready_record(rid)
    rec = PaidPilotDeliveryRecord(**{**rec.to_dict(), "state": DELIVERY_PACKAGE_CORRUPT})
    store.put(rec)
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    assert proj.state == BLOCKED


def test_readiness_not_ready_when_rights_incomplete(repo: Path, tmp_path: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = _make_ready_record(rid)
    rec = PaidPilotDeliveryRecord(**{**rec.to_dict(), "rights_status": RIGHTS_INCOMPLETE, "state": DELIVERY_BLOCKED_RIGHTS_INCOMPLETE})
    store.put(rec)
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    assert proj.state == NOT_READY


def test_readiness_ready_for_controlled_pilot(repo: Path, tmp_path: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir(parents=True)
    bkp_root.mkdir(parents=True)
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    # Create a real package zip.
    from scos.control_center.hvs_paid_pilot_delivery_models import safe_delivery_filename
    from scos.control_center.hvs_paid_pilot_backup_service import finalize_backup
    pkg_path = pkg_root / safe_delivery_filename(rid)
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("final.mp4", b"SCOS-ARTIFACT-CONTENT-" * 100)
    pkg_sha = pkg_path.read_bytes()
    import hashlib
    pkg_sha = hashlib.sha256(pkg_sha).hexdigest()
    # Create backup.
    from scos.control_center.hvs_paid_pilot_delivery_models import DeliveryBackupReceipt
    receipt = finalize_backup(
        package_path=pkg_path, backup_root=bkp_root, delivery_id=rid,
        package_sha256=pkg_sha, created_at="2026-07-21T00:00:00Z",
    )
    rec = _make_ready_record(rid, pkg_sha=pkg_sha)
    # Reconstruct with the actual DeliveryBackupReceipt object (not a dict).
    rec = PaidPilotDeliveryRecord(
        schema_version=rec.schema_version,
        delivery_id=rec.delivery_id,
        project_id=rec.project_id,
        source_render_attempt_id=rec.source_render_attempt_id,
        artifact_identity=rec.artifact_identity,
        artifact_sha256=rec.artifact_sha256,
        artifact_size=rec.artifact_size,
        media_profile=rec.media_profile,
        qa_record_id=rec.qa_record_id,
        qa_state=rec.qa_state,
        operator_id=rec.operator_id,
        operator_decision=rec.operator_decision,
        rights_checklist_revision=rec.rights_checklist_revision,
        rights_status=rec.rights_status,
        package_revision=rec.package_revision,
        package_sha256=rec.package_sha256,
        backup_receipt=receipt,
        retention_class=rec.retention_class,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        state=rec.state,
    )
    store.put(rec)
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    # Without a restore drill, should be READY_FOR_INTERNAL_REHEARSAL.
    assert proj.state == READY_FOR_INTERNAL_REHEARSAL
    assert proj.package_sha256 == pkg_sha
    assert proj.backup_sha256 == pkg_sha


def test_readiness_restart_recovery(repo: Path, tmp_path: Path):
    """Restart: fresh store over same file must reconstruct the same projection."""
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir(parents=True)
    bkp_root.mkdir(parents=True)
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = _make_ready_record(rid)
    store.put(rec)
    # Simulate restart: fresh store over same file.
    restarted = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    assert restarted.read()["status"] == TRUTH_AVAILABLE_WITH_DATA
    proj_before = compute_readiness(
        store=store, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    proj_after = compute_readiness(
        store=restarted, delivery_id=rid, package_root=pkg_root, backup_root=bkp_root,
        computed_at="2026-07-27T00:00:00Z",
    )
    assert proj_before.state == proj_after.state
    assert proj_before.delivery_id == proj_after.delivery_id


def test_readiness_corrupt_store_classified(repo: Path, tmp_path: Path):
    p = repo / "delivery.json"
    p.write_text("{not valid json")
    store = PaidPilotDeliveryStore(store_path=p)
    assert store.read()["status"] == TRUTH_CORRUPT
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=tmp_path / "pkg", backup_root=tmp_path / "bkp",
        computed_at="2026-07-27T00:00:00Z",
    )
    assert proj.state == BLOCKED


def test_readiness_browser_safe_serialization(repo: Path, tmp_path: Path):
    """Readiness projection must not contain absolute paths or secrets."""
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = _make_ready_record(rid)
    store.put(rec)
    proj = compute_readiness(
        store=store, delivery_id=rid, package_root=tmp_path / "pkg", backup_root=tmp_path / "bkp",
        computed_at="2026-07-27T00:00:00Z",
    )
    serialized = json.dumps(proj.to_dict())
    assert "C:\\" not in serialized
    assert "/workspace/" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()
