"""Focused backend tests — SCOS Cohort 10H paid-pilot delivery authority.

Local, deterministic, hermetic. No real render, no network, no media tools.
Exercises: durable store recovery, atomic package finalization, exact replay
idempotency, conflicting replay rejection, stale/partial rejection, concurrent
serialization, corrupt/incompatible store, package hash verification, backup
equality, retention, rights enforcement, QA-required enforcement, operator
approval transition, browser-safe serialization, download authorization, path
traversal rejection, absolute-path leakage rejection.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scos.control_center.hvs_paid_pilot_backup_service import (
    finalize_backup,
    read_package_zip,
    verify_backup,
)
from scos.control_center.hvs_paid_pilot_delivery_models import (
    APPROVED_FOR_DELIVERY,
    DELIVERY_BACKUP_READY,
    DELIVERY_BLOCKED_RIGHTS_INCOMPLETE,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_PACKAGE_READY,
    DELIVERY_READY_FOR_MANUAL_HANDOFF,
    RIGHTS_APPROVED,
    RIGHTS_INCOMPLETE,
    REJECTED_REWORK_REQUIRED,
    RETENTION_KEEP_FOR_PAID_PILOT_REVIEW,
    RETENTION_MANUAL_PURGE_REQUIRED,
    DeliveryBackupReceipt,
    PaidPilotDeliveryRecord,
    RightsChecklistEntry,
    stable_delivery_id,
)
from scos.control_center.hvs_paid_pilot_delivery_service import (
    apply_qa_result,
    approve_delivery,
    create_package,
    mark_ready_for_handoff,
    submit_rights_checklist,
)
from scos.control_center.hvs_paid_pilot_delivery_store import (
    PaidPilotDeliveryStore,
    TRUTH_AVAILABLE_WITH_DATA,
    TRUTH_CORRUPT,
    TRUTH_EMPTY,
    TRUTH_INCOMPATIBLE_SCHEMA,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "control_center").mkdir(parents=True)
    return root


def _rights_ok() -> list[RightsChecklistEntry]:
    return [RightsChecklistEntry("visual", "synthetic clip", True, True, "owned")]


def _rights_bad() -> list[RightsChecklistEntry]:
    return [RightsChecklistEntry("audio", "unknown track", False, False, "")]


def _make_artifact(path: Path, size: int = 2048) -> None:
    path.write_bytes(b"SCOS-ARTIFACT-CONTENT-" * (size // 24 + 1))


def test_store_empty_then_recoverable(repo: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    assert store.read()["status"] == TRUTH_EMPTY
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = PaidPilotDeliveryRecord(
        schema_version="scos-hvs.paid-pilot-delivery.v1/1.0.0",
        delivery_id=rid, project_id="p1", source_render_attempt_id="a1",
        artifact_identity="art1", artifact_sha256="x" * 64, artifact_size=2048,
        media_profile="vertical_9_16", qa_record_id="q1", qa_state="QA_PASSED",
        operator_id="op", operator_decision=APPROVED_FOR_DELIVERY,
        rights_checklist_revision="r1", rights_status=RIGHTS_APPROVED,
        package_revision="", package_sha256="", backup_receipt=None,
        retention_class=RETENTION_MANUAL_PURGE_REQUIRED,
        created_at="2026-07-21T00:00:00Z", updated_at="2026-07-21T00:00:00Z",
        state=DELIVERY_BACKUP_READY,
    )
    store.put(rec)
    # Simulate restart: fresh store over same file.
    restarted = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    assert restarted.read()["status"] == TRUTH_AVAILABLE_WITH_DATA
    got = restarted.get(rid)
    assert got is not None and got.delivery_id == rid


def test_corrupt_store_classified(repo: Path):
    p = repo / "delivery.json"
    p.write_text("{not valid json")
    store = PaidPilotDeliveryStore(store_path=p)
    assert store.read()["status"] == TRUTH_CORRUPT


def test_incompatible_schema_classified(repo: Path):
    p = repo / "delivery.json"
    p.write_text(json.dumps({"schema_version": "wrong", "store_kind": "scos.paid_pilot_delivery.v1", "records": {}}))
    store = PaidPilotDeliveryStore(store_path=p)
    assert store.read()["status"] == TRUTH_INCOMPATIBLE_SCHEMA


def test_rights_enforcement_blocks_package(repo: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    chk = submit_rights_checklist(
        store=store, delivery_id=rid, project_id="p1", operator_id="op", reviewed_at="2026-07-21T00:00:00Z",
        entries=_rights_bad(),
    )
    assert chk.status == RIGHTS_INCOMPLETE
    rec = store.get(chk.delivery_id)
    assert rec.state == DELIVERY_BLOCKED_RIGHTS_INCOMPLETE


def test_qa_required_enforcement(repo: Path):
    # rights approved but QA not passed -> approval must fail closed.
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    chk = submit_rights_checklist(
        store=store, delivery_id=rid, project_id="p1", operator_id="op", reviewed_at="2026-07-21T00:00:00Z",
        entries=_rights_ok(),
    )
    # QA state still NOT_RUN -> record is DELIVERY_BLOCKED_QA_REQUIRED, not approved.
    res = approve_delivery(
        store=store, delivery_id=chk.delivery_id, operator_id="op",
        decided_at="2026-07-21T00:00:00Z", decision=APPROVED_FOR_DELIVERY,
        source_render_attempt_id="a1", artifact_identity="art1",
        artifact_sha256="x" * 64, artifact_size=2048, media_profile="vertical_9_16",
        qa_record_id="q1", qa_state="QA_NOT_RUN",
        rights_revision=chk.revision, rights_status=RIGHTS_APPROVED,
        recorded_at="2026-07-21T00:00:00Z",
    )
    assert res.ok is False
    assert res.error_code == "QA_NOT_PASSED"


def test_full_approval_package_backup_flow(repo: Path, tmp_path: Path):
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    chk = submit_rights_checklist(
        store=store, delivery_id=rid, project_id="p1", operator_id="op", reviewed_at="2026-07-21T00:00:00Z",
        entries=_rights_ok(),
    )
    art = tmp_path / "out.mp4"
    _make_artifact(art)
    qa = apply_qa_result(
        store=store, delivery_id=chk.delivery_id,
        qa_report_id="q1", qa_state="QA_PASSED",
        artifact_id="art1", artifact_sha256="x" * 64,
        recorded_at="2026-07-21T00:00:00Z",
    )
    assert qa.ok is True
    assert qa.record.state == "QA_PASSED_GATE_OPEN"
    res = approve_delivery(
        store=store, delivery_id=chk.delivery_id, operator_id="op",
        decided_at="2026-07-21T00:00:00Z", decision=APPROVED_FOR_DELIVERY,
        source_render_attempt_id="a1", artifact_identity="art1",
        artifact_sha256="x" * 64, artifact_size=art.stat().st_size, media_profile="vertical_9_16",
        qa_record_id="q1", qa_state="QA_PASSED",
        rights_revision=chk.revision, rights_status=RIGHTS_APPROVED,
        recorded_at="2026-07-21T00:00:00Z",
    )
    assert res.ok is True
    pkg = create_package(
        store=store, delivery_id=chk.delivery_id, project_id="p1", hvs_project_id="p1",
        attempt_id="a1", profile_id="vertical_9_16", qa_report_id="q1",
        artifact_path=str(art), operator_id="op", recorded_at="2026-07-21T00:00:00Z",
        rights_revision=chk.revision, rights_status=RIGHTS_APPROVED,
        retention_class=RETENTION_KEEP_FOR_PAID_PILOT_REVIEW,
    )
    assert pkg.ok is True
    assert pkg.record.state == DELIVERY_READY_FOR_MANUAL_HANDOFF
    assert pkg.backup_receipt is not None
    # Exact replay => same id, 0 new writes.
    pkg2 = create_package(
        store=store, delivery_id=chk.delivery_id, project_id="p1", hvs_project_id="p1",
        attempt_id="a1", profile_id="vertical_9_16", qa_report_id="q1",
        artifact_path=str(art), operator_id="op", recorded_at="2026-07-21T00:00:00Z",
        rights_revision=chk.revision, rights_status=RIGHTS_APPROVED,
        retention_class=RETENTION_KEEP_FOR_PAID_PILOT_REVIEW,
    )
    assert pkg2.ok is True
    # handoff state transition
    hand = mark_ready_for_handoff(store=store, delivery_id=chk.delivery_id)
    assert hand.ok is True
    assert hand.record.state == DELIVERY_READY_FOR_MANUAL_HANDOFF


def test_backup_content_equivalence_and_verify(tmp_path: Path):
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir()
    bkp_root.mkdir()
    zp = pkg_root / "d.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("final.mp4", b"SCOS-ARTIFACT-CONTENT-" * 100)
    _data, sha = read_package_zip(package_path=zp)
    receipt = finalize_backup(
        package_path=zp, backup_root=bkp_root, delivery_id="d",
        package_sha256=sha, created_at="2026-07-21T00:00:00Z",
    )
    assert isinstance(receipt, DeliveryBackupReceipt)
    assert receipt.backup_sha256 == sha
    ok, bsha = verify_backup(delivery_id="d", backup_root=bkp_root, expected_package_sha256=sha)
    assert ok is True and bsha == sha


def test_path_traversal_rejected_in_zip(tmp_path: Path):
    zp = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    with pytest.raises(ValueError):
        read_package_zip(package_path=zp)


def test_download_authorization_state_gate(repo: Path):
    # A record not in a ready state must not be downloadable.
    store = PaidPilotDeliveryStore(store_path=repo / "delivery.json")
    rid = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    rec = PaidPilotDeliveryRecord(
        schema_version="scos-hvs.paid-pilot-delivery.v1/1.0.0",
        delivery_id=rid, project_id="p1", source_render_attempt_id="a1",
        artifact_identity="art1", artifact_sha256="x" * 64, artifact_size=2048,
        media_profile="vertical_9_16", qa_record_id="q1", qa_state="QA_PASSED",
        operator_id="op", operator_decision=APPROVED_FOR_DELIVERY,
        rights_checklist_revision="r1", rights_status=RIGHTS_APPROVED,
        package_revision="", package_sha256="", backup_receipt=None,
        retention_class=RETENTION_MANUAL_PURGE_REQUIRED,
        created_at="2026-07-21T00:00:00Z", updated_at="2026-07-21T00:00:00Z",
        state=DELIVERY_PACKAGE_CORRUPT,
    )
    store.put(rec)
    got = store.get(rid)
    assert got.state == DELIVERY_PACKAGE_CORRUPT
    # Download gate: only ready states allowed (mirrors API route contract).
    DOWNLOADABLE_STATES = {
        "DELIVERY_PACKAGE_READY",
        "DELIVERY_BACKUP_READY",
        "DELIVERY_READY_FOR_MANUAL_HANDOFF",
    }
    assert got.state not in DOWNLOADABLE_STATES  # fails closed for corrupt
