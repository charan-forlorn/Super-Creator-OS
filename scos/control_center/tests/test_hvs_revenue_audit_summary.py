from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_delivery_closure_models import (
    SOURCE_EMAIL_OBSERVED,
    SOURCE_NONE_AVAILABLE,
)
from scos.control_center.hvs_delivery_closure_service import (
    close_delivery,
    create_revenue_audit_summary,
    get_revenue_audit_summary,
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
from scos.control_center.hvs_revenue_audit import (
    INV_BLOCKED_BY_MISSING_COMMERCIAL,
    INV_BLOCKED_BY_REJECTION,
    INV_BLOCKED_BY_REVISION,
    INV_BLOCKED_BY_UNCONFIRMED,
    INV_READY_FOR_MANUAL_REVIEW,
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
    artifact.write_bytes(b"STAGE7-REVENUE-ARTIFACT" * 5)
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
        status=DEL_DELIVERED_MANUALLY,
        operator_id="op",
        channel=CHANNEL_OTHER_MANUAL,
        recipient_label="synthetic-customer",
        repo_root=repo_root,
        recorded_at="t",
    )
    return delivery.delivery_record.delivery_record_id


def _closed(repo_root: Path, status: str):
    delivery_id = _delivered(repo_root)
    kwargs = {
        "delivery_record_id": delivery_id,
        "repo_root": repo_root,
        "operator_id": "op",
        "customer_reference": "customer-ref",
        "recorded_at": "t",
    }
    if status == "accepted":
        receipt = record_customer_receipt_evidence(
            **kwargs,
            status="acknowledged",
            source_type=SOURCE_EMAIL_OBSERVED,
            statement_summary="Customer accepted delivery.",
        )
        return close_delivery(
            receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
            repo_root=repo_root,
            operator_id="op",
            decision="accept",
            reason="Customer accepted.",
            recorded_at="t",
        )
    if status == "revision":
        receipt = record_customer_receipt_evidence(
            **kwargs,
            status="revision-requested",
            source_type=SOURCE_EMAIL_OBSERVED,
            statement_summary="Customer requested revision.",
            revision_summary="Change caption.",
        )
        open_revision_request(
            receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
            repo_root=repo_root,
            operator_id="op",
            revision_summary="Change caption.",
            change_categories=["caption"],
            priority="normal",
            recorded_at="t",
        )
        return close_delivery(
            receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
            repo_root=repo_root,
            operator_id="op",
            decision="revision_open",
            reason="Revision required.",
            recorded_at="t",
        )
    if status == "rejected":
        receipt = record_customer_receipt_evidence(
            **kwargs,
            status="rejected",
            source_type=SOURCE_EMAIL_OBSERVED,
            statement_summary="Customer rejected delivery.",
            rejection_reason="Wrong version.",
        )
        return close_delivery(
            receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
            repo_root=repo_root,
            operator_id="op",
            decision="reject",
            reason="Customer rejected.",
            recorded_at="t",
        )
    receipt = record_customer_receipt_evidence(
        **kwargs,
        status="unconfirmed",
        source_type=SOURCE_NONE_AVAILABLE,
        statement_summary="No confirmation.",
        operator_note="No confirmation available.",
    )
    return close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="close_without_confirmation",
        reason="Operator explicitly closed without confirmation.",
        recorded_at="t",
    )


def test_accepted_ready_for_manual_invoice_review(repo_root):
    closure = _closed(repo_root, "accepted")
    summary = create_revenue_audit_summary(
        closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="fictional-contract-001",
        agreed_amount_minor=125000,
        currency="THB",
        recorded_at="2026-07-12T00:00:00+00:00",
    )
    assert summary.ok is True
    s = summary.revenue_summary
    assert s.invoice_readiness == INV_READY_FOR_MANUAL_REVIEW
    assert s.payment_status == "NOT_VERIFIED"
    assert s.invoice_created_by_scos is False
    assert s.payment_confirmed_by_scos is False
    assert s.revenue_recognized_by_scos is False
    assert s.tax_calculated_by_scos is False
    assert s.customer_contact_executed_by_scos is False
    assert s.automation_allowed is False
    loaded = get_revenue_audit_summary(summary_id=s.summary_id, repo_root=repo_root)
    assert loaded.ok is True


def test_summary_idempotent_timestamp_independent_and_conflict(repo_root):
    closure = _closed(repo_root, "accepted")
    first = create_revenue_audit_summary(
        closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="fictional-contract-001",
        agreed_amount_minor=125000,
        currency="USD",
        recorded_at="t1",
    )
    second = create_revenue_audit_summary(
        closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="fictional-contract-001",
        agreed_amount_minor=125000,
        currency="USD",
        recorded_at="t2",
    )
    assert first.revenue_summary.summary_id == second.revenue_summary.summary_id
    conflict = create_revenue_audit_summary(
        closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="different-ref",
        agreed_amount_minor=125000,
        currency="USD",
        recorded_at="t3",
    )
    assert conflict.ok is False
    assert conflict.error_code == "record_conflict"


def test_blocked_readiness_states(repo_root):
    revision = _closed(repo_root, "revision")
    rev_summary = create_revenue_audit_summary(
        closure_id=revision.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="fictional-contract-rev",
        agreed_amount_minor=100,
        currency="USD",
        recorded_at="t",
    )
    assert rev_summary.revenue_summary.invoice_readiness == INV_BLOCKED_BY_REVISION

    repo2 = repo_root.parent / "repo-rejected"
    rejected = _closed(repo2, "rejected")
    rej_summary = create_revenue_audit_summary(
        closure_id=rejected.closure.closure_id,
        repo_root=repo2,
        operator_id="op",
        commercial_reference="fictional-contract-rej",
        agreed_amount_minor=100,
        currency="USD",
        recorded_at="t",
    )
    assert rej_summary.revenue_summary.invoice_readiness == INV_BLOCKED_BY_REJECTION

    repo3 = repo_root.parent / "repo-unconfirmed"
    unconfirmed = _closed(repo3, "unconfirmed")
    unc_summary = create_revenue_audit_summary(
        closure_id=unconfirmed.closure.closure_id,
        repo_root=repo3,
        operator_id="op",
        commercial_reference="fictional-contract-unc",
        agreed_amount_minor=100,
        currency="USD",
        recorded_at="t",
    )
    assert unc_summary.revenue_summary.invoice_readiness == INV_BLOCKED_BY_UNCONFIRMED


def test_missing_money_data_unsupported_currency_and_float_rejected(repo_root):
    closure = _closed(repo_root, "accepted")
    missing = create_revenue_audit_summary(
        closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        operator_id="op",
        commercial_reference="fictional-contract-001",
        recorded_at="t",
    )
    assert missing.ok is True
    assert missing.revenue_summary.invoice_readiness == INV_BLOCKED_BY_MISSING_COMMERCIAL

    repo2 = repo_root.parent / "repo-currency"
    closure2 = _closed(repo2, "accepted")
    bad_currency = create_revenue_audit_summary(
        closure_id=closure2.closure.closure_id,
        repo_root=repo2,
        operator_id="op",
        commercial_reference="fictional-contract-002",
        agreed_amount_minor=100,
        currency="BTC",
        recorded_at="t",
    )
    assert bad_currency.ok is False

    bad_float = create_revenue_audit_summary(
        closure_id=closure2.closure.closure_id,
        repo_root=repo2,
        operator_id="op",
        commercial_reference="fictional-contract-002",
        agreed_amount_minor=100.5,
        currency="USD",
        recorded_at="t",
    )
    assert bad_float.ok is False


def test_cli_revenue_summary_and_invalid_amount(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    closure = _closed(repo_root, "accepted")
    assert cli_mod.main([
        "create-hvs-revenue-audit-summary",
        "--closure-id", closure.closure.closure_id,
        "--operator-id", "op",
        "--commercial-reference", "fictional-contract-cli",
        "--amount-minor", "1200",
        "--currency", "USD",
    ]) == 0
    assert cli_mod.main([
        "create-hvs-revenue-audit-summary",
        "--closure-id", closure.closure.closure_id,
        "--operator-id", "op",
        "--commercial-reference", "fictional-contract-cli",
        "--amount-minor", "12.50",
        "--currency", "USD",
    ]) == 2
