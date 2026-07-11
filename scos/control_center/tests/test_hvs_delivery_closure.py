from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_delivery_closure_audit import read_closure_events
from scos.control_center.hvs_delivery_closure_models import (
    CLOSURE_ACCEPTED,
    CLOSURE_REJECTED,
    CLOSURE_REVISION_OPEN,
    CLOSURE_WITHOUT_CONFIRMATION,
    SOURCE_EMAIL_OBSERVED,
    SOURCE_NONE_AVAILABLE,
)
from scos.control_center.hvs_delivery_closure_service import (
    close_delivery,
    get_closure,
    open_revision_request,
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


def _delivery(repo_root: Path, status: str = DEL_DELIVERED_MANUALLY):
    (repo_root / "scos" / "work").mkdir(parents=True, exist_ok=True)
    artifact = repo_root / "artifact.bin"
    artifact.write_bytes(b"STAGE7-CLOSURE-ARTIFACT" * 5)
    sha = _sha(artifact)
    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": f"packet-{repo_root.name}",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "project-stage7",
        "validation_id": f"validation-{repo_root.name}",
        "hvs": {"validation_id": f"validation-{repo_root.name}", "project_id": "project-stage7", "verdict": "PASS", "export_ready": True},
        "artifact": {"path": str(artifact), "sha256": sha, "size_bytes": artifact.stat().st_size},
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    decide_approval(approval_id=req.approval_request_id, decision="approve", operator_id="op", decided_at="t", repo_root=repo_root)
    pkg = prepare_delivery_package(approval_id=req.approval_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    materialize_delivery_package(package_id=pkg.package_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    delivery = record_manual_delivery(
        package_id=pkg.package_id,
        status=status,
        operator_id="op",
        channel=CHANNEL_OTHER_MANUAL,
        recipient_label="synthetic-customer",
        reason="not delivered" if status != DEL_DELIVERED_MANUALLY else None,
        repo_root=repo_root,
        recorded_at="t",
    )
    return artifact, pkg.package_id, delivery


def _receipt(repo_root: Path, delivery_id: str, status: str):
    kwargs = {
        "delivery_record_id": delivery_id,
        "repo_root": repo_root,
        "status": status,
        "source_type": SOURCE_EMAIL_OBSERVED if status != "unconfirmed" else SOURCE_NONE_AVAILABLE,
        "operator_id": "op",
        "customer_reference": "customer-ref",
        "statement_summary": "Customer evidence summary.",
        "recorded_at": "t",
    }
    if status == "revision-requested":
        kwargs["revision_summary"] = "Change the final caption."
        kwargs["statement_summary"] = "Customer requested a revision."
    if status == "rejected":
        kwargs["rejection_reason"] = "Delivery was not acceptable."
        kwargs["statement_summary"] = "Customer rejected the delivery."
    if status == "unconfirmed":
        kwargs["operator_note"] = "No confirmation was available."
        kwargs["statement_summary"] = "No confirmation available."
    return record_customer_receipt_evidence(**kwargs)


def test_acknowledgment_closes_accepted_and_does_not_confirm_money(repo_root):
    _, _, delivery = _delivery(repo_root)
    receipt = _receipt(repo_root, delivery.delivery_record.delivery_record_id, "acknowledged")
    close = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer acknowledged acceptance.",
        recorded_at="t",
    )
    assert close.ok is True
    assert close.closure.closure_status == CLOSURE_ACCEPTED
    assert close.closure.accepted_by_customer is True
    assert close.closure.payment_confirmed is False
    assert close.closure.invoice_created_by_scos is False
    assert close.closure.revenue_recognized_by_scos is False
    assert close.to_dict()["customer_contact_executed_by_scos"] is False
    loaded = get_closure(closure_id=close.closure.closure_id, repo_root=repo_root)
    assert loaded.ok is True


def test_closure_idempotent_and_conflicting_final_rejected(repo_root):
    _, _, delivery = _delivery(repo_root)
    receipt = _receipt(repo_root, delivery.delivery_record.delivery_record_id, "acknowledged")
    first = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer accepted.",
        recorded_at="t1",
    )
    second = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer accepted again.",
        recorded_at="t2",
    )
    assert first.ok and second.ok
    assert first.closure.closure_id == second.closure.closure_id
    conflict = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="cancel",
        reason="conflict",
        recorded_at="t3",
    )
    assert conflict.ok is False
    assert conflict.error_code == "record_conflict"


def test_revision_request_and_revision_open_closure(repo_root):
    _, _, delivery = _delivery(repo_root)
    receipt = _receipt(repo_root, delivery.delivery_record.delivery_record_id, "revision-requested")
    revision = open_revision_request(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        revision_summary="Change the final caption.",
        change_categories=["caption", "text"],
        priority="normal",
        recorded_at="t",
    )
    assert revision.ok is True
    assert revision.revision_request.rendering_not_started is True
    duplicate = open_revision_request(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        revision_summary="Change the final caption.",
        change_categories=["text", "caption"],
        priority="normal",
        recorded_at="later",
    )
    assert duplicate.revision_request.revision_request_id == revision.revision_request.revision_request_id
    conflicting = open_revision_request(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        revision_summary="Change the music.",
        change_categories=["audio"],
        priority="normal",
        recorded_at="later",
    )
    assert conflicting.ok is False
    closed = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="revision_open",
        reason="Manual revision required.",
        recorded_at="t",
    )
    assert closed.ok is True
    assert closed.closure.closure_status == CLOSURE_REVISION_OPEN
    assert closed.closure.open_revision_request_id == revision.revision_request.revision_request_id


def test_rejected_and_unconfirmed_closure_paths(repo_root):
    _, _, delivery = _delivery(repo_root)
    receipt = _receipt(repo_root, delivery.delivery_record.delivery_record_id, "rejected")
    rejected = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="reject",
        reason="Customer rejected the delivery.",
        recorded_at="t",
    )
    assert rejected.ok is True
    assert rejected.closure.closure_status == CLOSURE_REJECTED

    repo2 = repo_root.parent / "repo2"
    _, _, delivery2 = _delivery(repo2)
    receipt2 = _receipt(repo2, delivery2.delivery_record.delivery_record_id, "unconfirmed")
    no_reason = close_delivery(
        receipt_evidence_id=receipt2.receipt_evidence.receipt_evidence_id,
        repo_root=repo2,
        operator_id="op",
        decision="close_without_confirmation",
        reason="",
        recorded_at="t",
    )
    assert no_reason.ok is False
    unconfirmed = close_delivery(
        receipt_evidence_id=receipt2.receipt_evidence.receipt_evidence_id,
        repo_root=repo2,
        operator_id="op",
        decision="close_without_confirmation",
        reason="Operator explicitly closed without confirmation.",
        recorded_at="t",
    )
    assert unconfirmed.ok is True
    assert unconfirmed.closure.closure_status == CLOSURE_WITHOUT_CONFIRMATION
    assert unconfirmed.closure.accepted_by_customer is False


def test_prerequisites_and_integrity_failures_block_closure(repo_root):
    artifact, _, delivery = _delivery(repo_root)
    receipt = _receipt(repo_root, delivery.delivery_record.delivery_record_id, "acknowledged")
    import json

    manifest_path = next((repo_root / "scos" / "work" / "hvs_delivery_packages").glob("*/delivery_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    packaged = manifest_path.parent / manifest["packaged_artifact_relative_path"]
    packaged.write_bytes(b"tamper")
    blocked = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer accepted.",
        recorded_at="t",
    )
    assert blocked.ok is False
    assert blocked.error_code == "artifact_sha_mismatch"

    repo2 = repo_root.parent / "repo-failed"
    _, _, failed_delivery = _delivery(repo2, status="DELIVERY_FAILED")
    missing = record_customer_receipt_evidence(
        delivery_record_id=failed_delivery.delivery_record.delivery_record_id,
        repo_root=repo2,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="customer-ref",
        statement_summary="Customer accepted.",
        recorded_at="t",
    )
    assert missing.ok is False


def test_cli_receipt_revision_closure_json(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    _, _, delivery = _delivery(repo_root)
    assert cli_mod.main([
        "record-hvs-customer-receipt",
        "--delivery-record-id", delivery.delivery_record.delivery_record_id,
        "--status", "acknowledged",
        "--source-type", SOURCE_EMAIL_OBSERVED,
        "--operator-id", "op",
        "--customer-reference", "customer-ref",
        "--statement-summary", "Customer accepted the delivery.",
    ]) == 0
    receipt = next((repo_root / "scos" / "work" / "hvs_delivery_packages").glob("*/receipt_evidence_*.json"))
    import json

    rid = json.loads(receipt.read_text(encoding="utf-8"))["receipt_evidence_id"]
    assert cli_mod.main([
        "close-hvs-delivery",
        "--receipt-evidence-id", rid,
        "--operator-id", "op",
        "--decision", "accept",
        "--reason", "Customer accepted.",
    ]) == 0
    events = read_closure_events(
        audit_log_path=repo_root / "scos" / "work" / "hvs_delivery_packages" / "delivery_closure_audit.jsonl"
    )
    assert any(e.event_type == "DELIVERY_ACCEPTED_AND_CLOSED" for e in events)
    assert cli_mod.main([
        "record-hvs-customer-receipt",
        "--delivery-record-id", delivery.delivery_record.delivery_record_id,
        "--status", "paid",
        "--source-type", SOURCE_EMAIL_OBSERVED,
        "--operator-id", "op",
        "--customer-reference", "customer-ref",
        "--statement-summary", "invalid",
    ]) == 2
