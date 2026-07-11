from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_delivery_closure_models import (
    CLOSURE_ACCEPTED,
    CLOSURE_REJECTED,
    SOURCE_EMAIL_OBSERVED,
)
from scos.control_center.hvs_delivery_closure_service import (
    close_delivery,
    record_customer_receipt_evidence,
)
from scos.control_center.hvs_invoice_models import (
    CANCELLED,
    DISPUTED,
    ERR_PARTIAL_PAYMENT_UNSUPPORTED,
    INVOICE_DRAFT_PENDING,
    OVERDUE,
    PAID,
    PAYMENT_FOLLOW_UP_DUE,
    PAYMENT_PENDING,
    READY_FOR_MANUAL_INVOICE,
    _reject_sensitive_data,
)
from scos.control_center.hvs_invoice_service import (
    create_invoice_preparation,
    inspect_invoice_preparation,
    inspect_payment_status,
    list_payment_follow_up_queue,
    mark_invoice_ready,
    mark_invoice_sent,
    record_payment_status_decision,
    update_invoice_draft,
    verify_invoice_source_integrity,
)
from scos.control_center.hvs_invoice_store import compute_line_hash, invoice_audit_path, read_invoice_events
from scos.control_center.hvs_local_delivery_models import CHANNEL_OTHER_MANUAL, DEL_DELIVERED_MANUALLY
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


def _delivery(repo_root: Path):
    (repo_root / "scos" / "work").mkdir(parents=True, exist_ok=True)
    artifact = repo_root / "artifact.bin"
    artifact.write_bytes(b"STAGE8A-INVOICE-ARTIFACT" * 5)
    sha = _sha(artifact)
    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": f"packet-{repo_root.name}",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "project-stage8a",
        "validation_id": f"validation-{repo_root.name}",
        "hvs": {"validation_id": f"validation-{repo_root.name}", "project_id": "project-stage8a", "verdict": "PASS", "export_ready": True},
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
        recipient_label="test-customer-stage8a",
        repo_root=repo_root,
        recorded_at="t",
    )
    return delivery.delivery_record.delivery_record_id


def _closure(repo_root: Path, *, accepted: bool = True):
    delivery_id = _delivery(repo_root)
    receipt = record_customer_receipt_evidence(
        delivery_record_id=delivery_id,
        repo_root=repo_root,
        status="acknowledged" if accepted else "rejected",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="test-customer-stage8a",
        statement_summary="Customer accepted delivery." if accepted else "Customer rejected delivery.",
        rejection_reason=None if accepted else "Wrong version.",
        recorded_at="t",
    )
    return close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept" if accepted else "reject",
        reason="Customer accepted." if accepted else "Customer rejected.",
        recorded_at="t",
    )


def _invoice(repo_root: Path):
    closure = _closure(repo_root)
    result = create_invoice_preparation(
        delivery_closure_id=closure.closure.closure_id,
        repo_root=repo_root,
        customer_id="test-customer-stage8a",
        billing_scope_key="stage8a-main-scope",
        line_items=[
            {"description": "Manual HVS video delivery", "quantity": "2", "unit_price": "100.005", "billing_scope_key": "stage8a-main-scope"},
            {"description": "Caption review", "quantity": 1, "unit_price": "50", "billing_scope_key": "stage8a-main-scope", "note": "PO 123"},
        ],
        currency="USD",
        payment_terms="Net 7 manual invoice",
        tax_amount="10.005",
        discount_amount="5",
        operator_id="op",
        recorded_at="2026-07-12T00:00:00+00:00",
    )
    assert result.ok is True
    return result


def _sent_invoice(repo_root: Path):
    inv = _invoice(repo_root).invoice
    ready = mark_invoice_ready(invoice_preparation_id=inv.invoice_preparation_id, repo_root=repo_root, operator_id="op", recorded_at="t1")
    assert ready.ok is True
    sent = mark_invoice_sent(
        invoice_preparation_id=inv.invoice_preparation_id,
        repo_root=repo_root,
        operator_id="op",
        sent_date="2026-07-12",
        invoice_number="INV-STAGE8A-001",
        due_date="2026-07-19",
        follow_up_date="2026-07-15",
        recorded_at="t2",
    )
    assert sent.ok is True
    return sent


def test_create_requires_accepted_closure_and_preserves_safety_flags(repo_root):
    accepted = _closure(repo_root)
    assert accepted.closure.closure_status == CLOSURE_ACCEPTED
    created = create_invoice_preparation(
        delivery_closure_id=accepted.closure.closure_id,
        repo_root=repo_root,
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-a",
        line_items=[{"description": "Delivery", "quantity": "1", "unit_price": "10", "billing_scope_key": "scope-a"}],
        currency="THB",
        payment_terms="Due on receipt",
        operator_id="op",
        recorded_at="t",
    )
    assert created.ok is True
    record = created.invoice
    assert record.status == INVOICE_DRAFT_PENDING
    assert record.automation_allowed is False
    assert record.invoice_created_by_scos is False
    assert record.invoice_sent_by_scos is False
    assert record.payment_confirmed_by_scos is False
    assert record.customer_contact_executed_by_scos is False
    assert record.revenue_recognized_by_scos is False
    assert created.to_dict()["manual_action_required"] is True

    repo2 = repo_root.parent / "repo-rejected"
    rejected = _closure(repo2, accepted=False)
    assert rejected.closure.closure_status == CLOSURE_REJECTED
    blocked = create_invoice_preparation(
        delivery_closure_id=rejected.closure.closure_id,
        repo_root=repo2,
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-a",
        line_items=[{"description": "Delivery", "quantity": "1", "unit_price": "10", "billing_scope_key": "scope-a"}],
        currency="THB",
        payment_terms="Due on receipt",
        operator_id="op",
        recorded_at="t",
    )
    assert blocked.ok is False
    assert blocked.error_code == "INELIGIBLE_CLOSURE"


def test_money_decimal_rounding_currency_and_float_rejections(repo_root):
    created = _invoice(repo_root)
    record = created.invoice
    assert record.currency == "USD"
    assert record.subtotal == record.line_items[0].amount + record.line_items[1].amount
    assert record.to_dict()["line_items"][0]["amount"] == "200.01"
    assert record.to_dict()["tax_amount"] == "10.01"
    assert record.to_dict()["total_amount"] == "255.02"

    closure = _closure(repo_root.parent / "repo-invalid-money")
    bad_currency = create_invoice_preparation(
        delivery_closure_id=closure.closure.closure_id,
        repo_root=repo_root.parent / "repo-invalid-money",
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-a",
        line_items=[{"description": "Delivery", "quantity": "1", "unit_price": "10", "billing_scope_key": "scope-a"}],
        currency="BTC",
        payment_terms="Due",
        operator_id="op",
        recorded_at="t",
    )
    assert bad_currency.ok is False
    assert create_invoice_preparation(
        delivery_closure_id=closure.closure.closure_id,
        repo_root=repo_root.parent / "repo-invalid-money",
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-b",
        line_items=[{"description": "Delivery", "quantity": 1.5, "unit_price": "10", "billing_scope_key": "scope-b"}],
        currency="USD",
        payment_terms="Due",
        operator_id="op",
        recorded_at="t",
    ).ok is False
    assert create_invoice_preparation(
        delivery_closure_id=closure.closure.closure_id,
        repo_root=repo_root.parent / "repo-invalid-money",
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-c",
        line_items=[{"description": "Delivery", "quantity": "0", "unit_price": "10", "billing_scope_key": "scope-c"}],
        currency="USD",
        payment_terms="Due",
        operator_id="op",
        recorded_at="t",
    ).ok is False
    assert create_invoice_preparation(
        delivery_closure_id=closure.closure.closure_id,
        repo_root=repo_root.parent / "repo-invalid-money",
        customer_id="test-customer-stage8a",
        billing_scope_key="scope-d",
        line_items=[{"description": "Delivery", "quantity": "1", "unit_price": "-1", "billing_scope_key": "scope-d"}],
        currency="USD",
        payment_terms="Due",
        operator_id="op",
        recorded_at="t",
    ).ok is False


def test_deterministic_ids_idempotency_duplicate_scope_and_append_only(repo_root):
    first = _invoice(repo_root)
    second = create_invoice_preparation(
        delivery_closure_id=first.invoice.delivery_closure_id,
        repo_root=repo_root,
        customer_id="test-customer-stage8a",
        billing_scope_key="stage8a-main-scope",
        line_items=[
            {"description": "Manual HVS video delivery", "quantity": "2", "unit_price": "100.005", "billing_scope_key": "stage8a-main-scope"},
            {"description": "Caption review", "quantity": 1, "unit_price": "50", "billing_scope_key": "stage8a-main-scope", "note": "PO 123"},
        ],
        currency="USD",
        payment_terms="Net 7 manual invoice",
        tax_amount="10.005",
        discount_amount="5",
        operator_id="op",
        recorded_at="later",
    )
    assert second.ok is True
    assert second.invoice.invoice_preparation_id == first.invoice.invoice_preparation_id
    conflict = create_invoice_preparation(
        delivery_closure_id=first.invoice.delivery_closure_id,
        repo_root=repo_root,
        customer_id="test-customer-stage8a",
        billing_scope_key="stage8a-main-scope",
        line_items=[{"description": "Different scope content", "quantity": "1", "unit_price": "10", "billing_scope_key": "stage8a-main-scope"}],
        currency="USD",
        payment_terms="Net 7 manual invoice",
        operator_id="op",
        recorded_at="later",
    )
    assert conflict.ok is False
    assert conflict.error_code == "DUPLICATE_COMMERCIAL_SCOPE"
    events = read_invoice_events(audit_log_path=invoice_audit_path(repo_root))
    assert len(events) == 1
    assert events[0].automation_allowed is False


def test_update_ready_sent_inspect_and_invalid_transitions(repo_root):
    inv = _invoice(repo_root).invoice
    updated = update_invoice_draft(
        invoice_preparation_id=inv.invoice_preparation_id,
        repo_root=repo_root,
        operator_id="op",
        line_items=[{"description": "Delivery updated", "quantity": "1", "unit_price": "125", "billing_scope_key": "stage8a-main-scope"}],
        recorded_at="t1",
    )
    assert updated.ok is True
    ready = mark_invoice_ready(invoice_preparation_id=updated.invoice.invoice_preparation_id, repo_root=repo_root, operator_id="op", recorded_at="t2")
    assert ready.ok is True
    assert ready.invoice.status == READY_FOR_MANUAL_INVOICE
    assert mark_invoice_ready(invoice_preparation_id=ready.invoice.invoice_preparation_id, repo_root=repo_root, operator_id="op", recorded_at="t3").ok is False
    sent = mark_invoice_sent(
        invoice_preparation_id=ready.invoice.invoice_preparation_id,
        repo_root=repo_root,
        operator_id="op",
        sent_date="2026-07-12",
        invoice_number="INV-STAGE8A-002",
        due_date="2026-07-19",
        follow_up_date="2026-07-15",
        recorded_at="t4",
    )
    assert sent.ok is True
    assert sent.invoice.status == PAYMENT_PENDING
    assert sent.to_dict()["invoice_not_sent"] is False
    assert inspect_invoice_preparation(invoice_preparation_id=sent.invoice.invoice_preparation_id, repo_root=repo_root).ok is True
    assert verify_invoice_source_integrity(invoice_preparation_id=sent.invoice.invoice_preparation_id, repo_root=repo_root).source_integrity_ok is True


def test_follow_up_queue_is_read_only_and_payment_state_machine(repo_root):
    sent = _sent_invoice(repo_root)
    before_hash = compute_line_hash(invoice_audit_path(repo_root))
    queue = list_payment_follow_up_queue(repo_root=repo_root, as_of="2026-07-16")
    after_hash = compute_line_hash(invoice_audit_path(repo_root))
    assert before_hash == after_hash
    assert len(queue.follow_up_queue) == 1
    assert queue.follow_up_queue[0].queue_status == PAYMENT_FOLLOW_UP_DUE

    due = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="follow_up_due",
        operator_id="op",
        recorded_at="t3",
    )
    assert due.ok is True
    assert due.invoice.status == PAYMENT_FOLLOW_UP_DUE
    overdue = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="overdue",
        operator_id="op",
        recorded_at="t4",
    )
    assert overdue.ok is True
    assert overdue.invoice.status == OVERDUE
    dispute_missing = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="dispute",
        operator_id="op",
        recorded_at="t5",
    )
    assert dispute_missing.ok is False
    disputed = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="dispute",
        operator_id="op",
        reason="Customer asked about line item.",
        recorded_at="t6",
    )
    assert disputed.ok is True
    assert disputed.invoice.status == DISPUTED
    resolved = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="resolve_dispute",
        operator_id="op",
        resolution_note="Operator clarified the invoice.",
        recorded_at="t7",
    )
    assert resolved.ok is True
    assert resolved.invoice.status == PAYMENT_PENDING


def test_payment_rejects_partial_currency_mismatch_and_accepts_full(repo_root):
    sent = _sent_invoice(repo_root)
    partial = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount="1",
        currency="USD",
        payment_reference="bank transfer ref 123",
        recorded_at="t",
    )
    assert partial.ok is False
    assert partial.error_code == ERR_PARTIAL_PAYMENT_UNSUPPORTED
    mismatch = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount=sent.invoice.to_dict()["total_amount"],
        currency="THB",
        payment_reference="bank transfer ref 123",
        recorded_at="t",
    )
    assert mismatch.ok is False
    paid = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount=sent.invoice.to_dict()["total_amount"],
        currency="USD",
        payment_reference="bank transfer ref 123",
        recorded_at="t",
    )
    assert paid.ok is True
    assert paid.invoice.status == PAID
    assert paid.invoice.payment_confirmed_by_scos is False
    assert inspect_payment_status(invoice_preparation_id=sent.invoice.invoice_preparation_id, repo_root=repo_root).invoice.status == PAID
    assert list_payment_follow_up_queue(repo_root=repo_root, as_of="2026-07-20").follow_up_queue == ()


def test_cancel_path_and_disputed_paid_requires_resolution_note(repo_root):
    sent = _sent_invoice(repo_root)
    disputed = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="dispute",
        operator_id="op",
        reason="Customer disputes amount.",
        recorded_at="t",
    )
    assert disputed.ok is True
    no_note_paid = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount=sent.invoice.to_dict()["total_amount"],
        currency="USD",
        payment_reference="bank transfer ref 456",
        recorded_at="t",
    )
    assert no_note_paid.ok is False

    repo2 = repo_root.parent / "repo-cancel"
    sent2 = _sent_invoice(repo2)
    cancelled = record_payment_status_decision(
        invoice_preparation_id=sent2.invoice.invoice_preparation_id,
        repo_root=repo2,
        decision="cancel",
        operator_id="op",
        reason="Manual cancellation approved.",
        recorded_at="t",
    )
    assert cancelled.ok is True
    assert cancelled.invoice.status == CANCELLED
    assert record_payment_status_decision(
        invoice_preparation_id=sent2.invoice.invoice_preparation_id,
        repo_root=repo2,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount=sent2.invoice.to_dict()["total_amount"],
        currency="USD",
        payment_reference="ref",
        recorded_at="t",
    ).ok is False


@pytest.mark.parametrize(
    "field",
    [
        "4111 1111 1111 1111",
        "cvv: 123",
        "online banking password: secret",
        "access_token=abcd",
        "Bearer abcdef",
        "api_key: secret",
        "seed phrase alpha beta gamma",
        "-----" + "BEGIN RSA " + "PRIVATE" + " KEY-----",
    ],
)
def test_sensitive_data_guard_rejects_generic_categories(field):
    with pytest.raises(Exception) as excinfo:
        _reject_sensitive_data(field)
    assert str(excinfo.value)
    assert field not in str(excinfo.value)


def test_sensitive_data_guard_allows_invoice_references(repo_root):
    _reject_sensitive_data("INV-2026-001", "bank transfer receipt reference BTR-123", "PO-999", "short operator note")
    sent = _sent_invoice(repo_root)
    paid = record_payment_status_decision(
        invoice_preparation_id=sent.invoice.invoice_preparation_id,
        repo_root=repo_root,
        decision="paid",
        operator_id="op",
        paid_date="2026-07-13",
        paid_amount=sent.invoice.to_dict()["total_amount"],
        currency="USD",
        payment_reference="transaction reference TX-2026-001",
        recorded_at="t",
    )
    assert paid.ok is True


def test_cli_invoice_payment_commands(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    closure = _closure(repo_root)
    assert cli_mod.main([
        "create-hvs-invoice-preparation",
        "--closure-id", closure.closure.closure_id,
        "--customer-id", "test-customer-stage8a",
        "--billing-scope-key", "cli-scope",
        "--currency", "USD",
        "--payment-terms", "Net 7",
        "--operator-id", "op",
        "--line-description", "Manual delivery",
        "--line-quantity", "1",
        "--line-unit-price", "99.99",
    ]) == 0
    events = read_invoice_events(audit_log_path=invoice_audit_path(repo_root))
    invoice_id = events[-1].invoice_preparation_id
    assert cli_mod.main(["inspect-hvs-invoice-preparation", "--invoice-preparation-id", invoice_id]) == 0
    assert cli_mod.main(["mark-hvs-invoice-ready", "--invoice-preparation-id", invoice_id, "--operator-id", "op"]) == 0
    assert cli_mod.main([
        "mark-hvs-invoice-sent",
        "--invoice-preparation-id", invoice_id,
        "--operator-id", "op",
        "--sent-date", "2026-07-12",
        "--invoice-number", "INV-CLI-001",
        "--due-date", "2026-07-19",
        "--follow-up-date", "2026-07-15",
    ]) == 0
    assert cli_mod.main(["list-hvs-payment-follow-ups", "--as-of", "2026-07-16"]) == 0
    assert cli_mod.main(["inspect-hvs-payment-status", "--invoice-preparation-id", invoice_id]) == 0
    assert cli_mod.main([
        "record-hvs-payment-status",
        "--invoice-preparation-id", invoice_id,
        "--decision", "paid",
        "--operator-id", "op",
        "--paid-date", "2026-07-13",
        "--paid-amount", "99.99",
        "--currency", "USD",
        "--payment-reference", "bank transfer ref cli",
    ]) == 0
