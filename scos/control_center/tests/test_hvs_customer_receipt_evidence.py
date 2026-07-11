from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_delivery_closure_audit import read_closure_events
from scos.control_center.hvs_delivery_closure_models import (
    REC_ACKNOWLEDGED,
    REC_DELIVERY_REJECTED,
    REC_REVISION_REQUESTED,
    REC_UNCONFIRMED,
    SOURCE_EMAIL_OBSERVED,
    SOURCE_NONE_AVAILABLE,
)
from scos.control_center.hvs_delivery_closure_service import (
    get_receipt_evidence,
    record_customer_receipt_evidence,
)
from scos.control_center.hvs_local_delivery_models import (
    CHANNEL_OTHER_MANUAL,
    DEL_DELIVERED_MANUALLY,
)
from scos.control_center.hvs_local_delivery_service import (
    materialize_delivery_package,
    prepare_delivery_package,
    record_manual_delivery,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _delivered(repo_root: Path):
    (repo_root / "scos" / "work").mkdir(parents=True, exist_ok=True)
    artifact = repo_root / "artifact.bin"
    artifact.write_bytes(b"STAGE7-RECEIPT-ARTIFACT" * 5)
    sha = _sha(artifact)
    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": "stage7-packet",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "stage7-project",
        "validation_id": "stage7-validation",
        "hvs": {
            "validation_id": "stage7-validation",
            "project_id": "stage7-project",
            "verdict": "PASS",
            "export_ready": True,
        },
        "artifact": {"path": str(artifact), "sha256": sha, "size_bytes": artifact.stat().st_size},
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    decide_approval(
        approval_id=req.approval_request_id,
        decision="approve",
        operator_id="op-stage7",
        decided_at="2026-07-12T00:00:00+00:00",
        repo_root=repo_root,
    )
    pkg = prepare_delivery_package(
        approval_id=req.approval_request_id,
        operator_id="op-stage7",
        repo_root=repo_root,
        recorded_at="2026-07-12T00:00:01+00:00",
    )
    materialize_delivery_package(
        package_id=pkg.package_id,
        operator_id="op-stage7",
        repo_root=repo_root,
        recorded_at="2026-07-12T00:00:02+00:00",
    )
    delivery = record_manual_delivery(
        package_id=pkg.package_id,
        status=DEL_DELIVERED_MANUALLY,
        operator_id="op-stage7",
        channel=CHANNEL_OTHER_MANUAL,
        recipient_label="synthetic-customer",
        repo_root=repo_root,
        recorded_at="2026-07-12T00:00:03+00:00",
    )
    return artifact, pkg.package_id, delivery.delivery_record.delivery_record_id


def _ack(repo_root: Path, delivery_record_id: str, when: str = "2026-07-12T00:00:04+00:00"):
    return record_customer_receipt_evidence(
        delivery_record_id=delivery_record_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op-stage7",
        customer_reference="customer-ref",
        statement_summary="Customer confirmed receipt and accepted the delivered artifact.",
        recorded_at=when,
    )


def test_acknowledgment_created_deterministic_and_idempotent(repo_root):
    _, _, delivery_id = _delivered(repo_root)
    first = _ack(repo_root, delivery_id, "2026-07-12T00:00:04+00:00")
    second = _ack(repo_root, delivery_id, "2099-01-01T00:00:00+00:00")
    assert first.ok is True
    assert first.receipt_evidence.receipt_status == REC_ACKNOWLEDGED
    assert first.receipt_evidence.receipt_evidence_id == second.receipt_evidence.receipt_evidence_id
    assert first.to_dict()["automation_allowed"] is False
    assert first.to_dict()["customer_contact_executed_by_scos"] is False
    assert first.to_dict()["externally_verified_by_scos"] is False
    loaded = get_receipt_evidence(
        receipt_evidence_id=first.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
    )
    assert loaded.ok is True


def test_conflicting_receipt_rejected(repo_root):
    _, _, delivery_id = _delivered(repo_root)
    assert _ack(repo_root, delivery_id).ok is True
    conflict = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="unconfirmed",
        source_type=SOURCE_NONE_AVAILABLE,
        operator_id="op-stage7",
        customer_reference="customer-ref",
        statement_summary="No confirmation is available.",
        operator_note="Operator could not confirm receipt.",
        recorded_at="2026-07-12T00:00:05+00:00",
    )
    assert conflict.ok is False
    assert conflict.error_code == "record_conflict"


def test_required_fields_and_bounded_status_source(repo_root):
    _, _, delivery_id = _delivered(repo_root)
    missing_operator = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="",
        customer_reference="customer-ref",
        statement_summary="Customer accepted.",
        recorded_at="t",
    )
    assert missing_operator.ok is False
    bad_source = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type="email_api",
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer accepted.",
        recorded_at="t",
    )
    assert bad_source.ok is False
    bad_status = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="paid",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer accepted.",
        recorded_at="t",
    )
    assert bad_status.ok is False


def test_revision_rejection_and_unconfirmed_validation(repo_root):
    _, _, delivery_id = _delivered(repo_root)
    missing_revision = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="revision-requested",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer asked for a change.",
        recorded_at="t",
    )
    assert missing_revision.ok is False

    revision = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="revision-requested",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer requested a caption adjustment.",
        revision_summary="Adjust the closing caption wording.",
        recorded_at="t",
    )
    assert revision.ok is True
    assert revision.receipt_evidence.receipt_status == REC_REVISION_REQUESTED

    _, _, delivery_id_2 = _delivered(repo_root.parent / "repo2")
    repo2 = repo_root.parent / "repo2"
    missing_rejection = record_customer_receipt_evidence(
        delivery_record_id=delivery_id_2,
        repo_root=repo2,
        status="rejected",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer rejected delivery.",
        recorded_at="t",
    )
    assert missing_rejection.ok is False
    rejection = record_customer_receipt_evidence(
        delivery_record_id=delivery_id_2,
        repo_root=repo2,
        status="rejected",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer rejected delivery after review.",
        rejection_reason="Wrong product version delivered.",
        recorded_at="t",
    )
    assert rejection.ok is True
    assert rejection.receipt_evidence.receipt_status == REC_DELIVERY_REJECTED

    repo3 = repo_root.parent / "repo3"
    _, _, delivery_id_3 = _delivered(repo3)
    unconfirmed_missing_note = record_customer_receipt_evidence(
        delivery_record_id=delivery_id_3,
        repo_root=repo3,
        status="unconfirmed",
        source_type=SOURCE_NONE_AVAILABLE,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="",
        recorded_at="t",
    )
    assert unconfirmed_missing_note.ok is False
    unconfirmed = record_customer_receipt_evidence(
        delivery_record_id=delivery_id_3,
        repo_root=repo3,
        status="unconfirmed",
        source_type=SOURCE_NONE_AVAILABLE,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="No confirmation is available.",
        operator_note="Operator saw no receipt confirmation.",
        recorded_at="t",
    )
    assert unconfirmed.ok is True
    assert unconfirmed.receipt_evidence.receipt_status == REC_UNCONFIRMED


def test_raw_payload_and_unsafe_prerequisites_rejected(repo_root):
    artifact, package_id, delivery_id = _delivered(repo_root)
    raw = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="From: customer@example.test To: op Subject: delivery accepted",
        recorded_at="t",
    )
    assert raw.ok is False

    import json

    manifest_path = next((repo_root / "scos" / "work" / "hvs_delivery_packages").glob("*/delivery_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packaged = manifest_path.parent / manifest["packaged_artifact_relative_path"]
    packaged.write_bytes(b"tampered")
    rejected = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer accepted.",
        recorded_at="t",
    )
    assert rejected.ok is False
    assert rejected.error_code == "artifact_sha_mismatch"
    events = read_closure_events(
        audit_log_path=repo_root / "scos" / "work" / "hvs_delivery_packages" / "delivery_closure_audit.jsonl"
    )
    assert any(e.event_type == "INTEGRITY_REVALIDATION_FAILED" for e in events)
    assert package_id in str(events[-1].to_dict())
