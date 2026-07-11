"""SCOS <-> HVS Stage 8A manual invoice preparation service."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .hvs_delivery_closure_models import CLOSURE_ACCEPTED, _normalize_text, _safe_optional_label
from .hvs_delivery_closure_service import get_closure
from .hvs_invoice_models import (
    CANCELLED,
    DISPUTED,
    ERR_ARTIFACT_SHA_MISMATCH,
    ERR_CONFLICT,
    ERR_CURRENCY_MISMATCH,
    ERR_DUPLICATE_COMMERCIAL_SCOPE,
    ERR_INELIGIBLE_CLOSURE,
    ERR_INVALID_INPUT,
    ERR_INVALID_TRANSITION,
    ERR_NOT_FOUND,
    ERR_PARTIAL_PAYMENT_UNSUPPORTED,
    ERR_SENSITIVE_DATA,
    EVT_INVOICE_DRAFT_UPDATED,
    EVT_INVOICE_MARKED_SENT,
    EVT_INVOICE_PREPARATION_CREATED,
    EVT_INVOICE_READY_FOR_MANUAL_INVOICE,
    EVT_PAYMENT_STATUS_DECISION_RECORDED,
    INVOICE_DRAFT_PENDING,
    INVOICE_PREPARATION_SCHEMA_VERSION,
    OVERDUE,
    PAID,
    PAYMENT_FOLLOW_UP_DUE,
    PAYMENT_PENDING,
    READY_FOR_MANUAL_INVOICE,
    InvoiceLineItem,
    InvoicePreparationRecord,
    PaymentFollowUpItem,
    SensitiveDataError,
    invoice_line_from_input,
    invoice_record_from_dict,
    money_to_json,
    normalize_currency,
    normalize_money,
    quantize_money,
    stable_commercial_scope_id,
    stable_invoice_preparation_id,
    _reject_sensitive_data,
)
from .hvs_invoice_store import append_invoice_event, invoice_audit_path, read_invoice_events
from .hvs_local_delivery_models import _require_nonempty


@dataclass(frozen=True)
class InvoiceServiceResult:
    ok: bool
    invoice: InvoicePreparationRecord | None = None
    invoices: tuple[InvoicePreparationRecord, ...] = ()
    follow_up_queue: tuple[PaymentFollowUpItem, ...] = ()
    source_integrity_ok: bool | None = None
    error_code: str | None = None
    error_detail: str | None = None
    manual_action_required: bool = True
    permitted_next_actions: tuple[str, ...] = ()
    invoice_not_sent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "invoice": self.invoice.to_dict() if self.invoice else None,
            "invoices": [r.to_dict() for r in self.invoices],
            "follow_up_queue": [item.to_dict() for item in self.follow_up_queue],
            "source_integrity_ok": self.source_integrity_ok,
            "automation_allowed": False,
            "manual_action_required": self.manual_action_required,
            "permitted_next_actions": list(self.permitted_next_actions),
            "invoice_not_sent": self.invoice_not_sent,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _deny(
    *,
    error_code: str,
    error_detail: str,
    invoice: InvoicePreparationRecord | None = None,
    permitted_next_actions: tuple[str, ...] = (),
) -> InvoiceServiceResult:
    return InvoiceServiceResult(
        ok=False,
        invoice=invoice,
        error_code=error_code,
        error_detail=error_detail,
        permitted_next_actions=permitted_next_actions,
        invoice_not_sent=invoice is None or invoice.sent_date is None,
    )


def _records(repo_root: Path) -> tuple[InvoicePreparationRecord, ...]:
    latest: dict[str, InvoicePreparationRecord] = {}
    for event in read_invoice_events(audit_log_path=invoice_audit_path(repo_root)):
        if not event.record:
            continue
        record = invoice_record_from_dict(event.record)
        latest[record.invoice_preparation_id] = record
    return tuple(latest[key] for key in sorted(latest))


def _find_record(repo_root: Path, invoice_preparation_id: str) -> InvoicePreparationRecord | None:
    for record in _records(repo_root):
        if record.invoice_preparation_id == invoice_preparation_id:
            return record
    return None


def _find_by_scope(repo_root: Path, commercial_scope_id: str) -> InvoicePreparationRecord | None:
    for record in _records(repo_root):
        if record.commercial_scope_id == commercial_scope_id:
            return record
    return None


def _permitted(status: str) -> tuple[str, ...]:
    return {
        INVOICE_DRAFT_PENDING: ("mark_ready",),
        READY_FOR_MANUAL_INVOICE: ("mark_sent",),
        PAYMENT_PENDING: ("follow_up_due", "overdue", "dispute", "cancel", "paid"),
        PAYMENT_FOLLOW_UP_DUE: ("overdue", "dispute", "cancel", "paid"),
        OVERDUE: ("dispute", "cancel", "paid"),
        DISPUTED: ("resolve_dispute", "cancel", "paid"),
        CANCELLED: (),
        PAID: (),
    }.get(status, ())


def verify_invoice_source_integrity(
    *, invoice_preparation_id: str, repo_root
) -> InvoiceServiceResult:
    repo = Path(repo_root)
    record = _find_record(repo, invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    source = get_closure(closure_id=record.delivery_closure_id, repo_root=repo)
    if not source.ok or source.closure is None:
        return _deny(error_code=source.error_code or ERR_NOT_FOUND, error_detail=source.error_detail or "closure not found", invoice=record)
    ok = source.closure.artifact_sha256 == record.artifact_sha256
    if not ok:
        return _deny(error_code=ERR_ARTIFACT_SHA_MISMATCH, error_detail="source closure artifact_sha256 mismatch", invoice=record)
    return InvoiceServiceResult(ok=True, invoice=record, source_integrity_ok=True, permitted_next_actions=_permitted(record.status), invoice_not_sent=record.sent_date is None)


def _build_record(
    *,
    closure: Any,
    customer_id: str,
    billing_scope_key: str,
    currency: str,
    payment_terms: str,
    line_items: tuple[InvoiceLineItem, ...],
    tax_amount: Decimal,
    discount_amount: Decimal,
    operator_id: str,
    recorded_at: str,
) -> InvoicePreparationRecord:
    subtotal = quantize_money(sum((line.amount for line in line_items), Decimal("0")), currency)
    tax = quantize_money(tax_amount, currency)
    discount = quantize_money(discount_amount, currency)
    total = quantize_money(subtotal + tax - discount, currency)
    commercial_scope_id = stable_commercial_scope_id(
        customer_id=customer_id,
        project_id=closure.project_id,
        delivery_record_id=closure.delivery_record_id,
        delivery_closure_id=closure.closure_id,
        artifact_sha256=closure.artifact_sha256,
        billing_scope_key=billing_scope_key,
    )
    invoice_id = stable_invoice_preparation_id(
        commercial_scope_id=commercial_scope_id,
        line_items=line_items,
        currency=currency,
        payment_terms=payment_terms,
        tax_amount=tax,
        discount_amount=discount,
    )
    return InvoicePreparationRecord(
        schema_version=INVOICE_PREPARATION_SCHEMA_VERSION,
        invoice_preparation_id=invoice_id,
        commercial_scope_id=commercial_scope_id,
        customer_id=customer_id,
        project_id=closure.project_id,
        delivery_closure_id=closure.closure_id,
        receipt_evidence_id=closure.receipt_evidence_id,
        delivery_record_id=closure.delivery_record_id,
        package_id=closure.package_id,
        approval_request_id=closure.approval_request_id,
        artifact_sha256=closure.artifact_sha256,
        billing_scope_key=billing_scope_key,
        currency=currency,
        payment_terms=payment_terms,
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=discount,
        total_amount=total,
        status=INVOICE_DRAFT_PENDING,
        operator_id=operator_id,
        invoice_number=None,
        sent_date=None,
        due_date=None,
        follow_up_date=None,
        paid_date=None,
        paid_amount=None,
        payment_reference=None,
        dispute_reason=None,
        cancellation_reason=None,
        resolution_note=None,
        manual_action_required=True,
        automation_allowed=False,
        invoice_created_by_scos=False,
        invoice_sent_by_scos=False,
        payment_confirmed_by_scos=False,
        customer_contact_executed_by_scos=False,
        revenue_recognized_by_scos=False,
        tax_calculated_by_scos=False,
        rounding_mode="ROUND_HALF_UP",
        recorded_at=recorded_at,
        updated_at=recorded_at,
        identity_inputs={
            "customer_id": customer_id,
            "project_id": closure.project_id,
            "delivery_record_id": closure.delivery_record_id,
            "delivery_closure_id": closure.closure_id,
            "artifact_sha256": closure.artifact_sha256,
            "billing_scope_key": billing_scope_key,
            "line_item_content_hash": stable_invoice_preparation_id(
                commercial_scope_id=commercial_scope_id,
                line_items=line_items,
                currency=currency,
                payment_terms=payment_terms,
                tax_amount=tax,
                discount_amount=discount,
            ),
        },
        audit_correlation={
            "package_id": closure.package_id,
            "approval_request_id": closure.approval_request_id,
            "receipt_evidence_id": closure.receipt_evidence_id,
            "delivery_record_id": closure.delivery_record_id,
            "closure_id": closure.closure_id,
            "artifact_sha256": closure.artifact_sha256,
        },
    )


def create_invoice_preparation(
    *,
    delivery_closure_id: str,
    repo_root,
    customer_id: str,
    line_items: list[dict[str, Any]],
    currency: str,
    payment_terms: str,
    operator_id: str,
    recorded_at: str,
    billing_scope_key: str | None = None,
    tax_amount: Any = "0",
    discount_amount: Any = "0",
) -> InvoiceServiceResult:
    repo = Path(repo_root)
    try:
        _require_nonempty("operator_id", operator_id)
        customer = _safe_optional_label("customer_id", customer_id, 160) or ""
        _require_nonempty("customer_id", customer)
        terms = _safe_optional_label("payment_terms", payment_terms, 240) or ""
        _require_nonempty("payment_terms", terms)
        cur = normalize_currency(currency)
        if not line_items:
            raise ValueError("at least one line item is required")
        lines = tuple(invoice_line_from_input(item, currency=cur) for item in line_items)
        scope_key = _safe_optional_label("billing_scope_key", billing_scope_key, 160) if billing_scope_key else None
        if not scope_key:
            scope_key = "|".join(sorted({line.billing_scope_key for line in lines}))
        _reject_sensitive_data(customer, terms, scope_key)
        tax = normalize_money(tax_amount, field="tax_amount", min_value=Decimal("0"))
        discount = normalize_money(discount_amount, field="discount_amount", min_value=Decimal("0"))
    except SensitiveDataError as exc:
        return _deny(error_code=ERR_SENSITIVE_DATA, error_detail=exc.category)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc))

    source = get_closure(closure_id=delivery_closure_id, repo_root=repo)
    if not source.ok or source.closure is None:
        return _deny(error_code=source.error_code or ERR_NOT_FOUND, error_detail=source.error_detail or "closure not found")
    closure = source.closure
    if closure.closure_status != CLOSURE_ACCEPTED or closure.accepted_by_customer is not True:
        return _deny(error_code=ERR_INELIGIBLE_CLOSURE, error_detail="closure must be ACCEPTED_AND_CLOSED and accepted_by_customer true")

    record = _build_record(
        closure=closure,
        customer_id=customer,
        billing_scope_key=scope_key,
        currency=cur,
        payment_terms=terms,
        line_items=lines,
        tax_amount=tax,
        discount_amount=discount,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
    )
    if closure.artifact_sha256 != record.artifact_sha256:
        return _deny(error_code=ERR_ARTIFACT_SHA_MISMATCH, error_detail="source closure artifact_sha256 mismatch")
    existing = _find_by_scope(repo, record.commercial_scope_id)
    if existing is not None:
        if existing.invoice_preparation_id == record.invoice_preparation_id:
            return InvoiceServiceResult(ok=True, invoice=existing, permitted_next_actions=_permitted(existing.status), invoice_not_sent=existing.sent_date is None)
        return _deny(error_code=ERR_DUPLICATE_COMMERCIAL_SCOPE, error_detail="commercial_scope_id already exists", invoice=existing)
    append_invoice_event(
        audit_log_path=invoice_audit_path(repo),
        event_type=EVT_INVOICE_PREPARATION_CREATED,
        invoice_preparation_id=record.invoice_preparation_id,
        commercial_scope_id=record.commercial_scope_id,
        delivery_closure_id=record.delivery_closure_id,
        resulting_status=record.status,
        operator_id=record.operator_id,
        recorded_at=recorded_at,
        record=record.to_dict(),
    )
    return InvoiceServiceResult(ok=True, invoice=record, permitted_next_actions=_permitted(record.status), invoice_not_sent=True)


def inspect_invoice_preparation(*, invoice_preparation_id: str, repo_root) -> InvoiceServiceResult:
    record = _find_record(Path(repo_root), invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    return InvoiceServiceResult(ok=True, invoice=record, permitted_next_actions=_permitted(record.status), invoice_not_sent=record.sent_date is None)


def _replace(record: InvoicePreparationRecord, **changes: Any) -> InvoicePreparationRecord:
    data = record.to_dict()
    data.update(changes)
    return invoice_record_from_dict(data)


def update_invoice_draft(
    *,
    invoice_preparation_id: str,
    repo_root,
    operator_id: str,
    recorded_at: str,
    line_items: list[dict[str, Any]] | None = None,
    payment_terms: str | None = None,
    tax_amount: Any | None = None,
    discount_amount: Any | None = None,
) -> InvoiceServiceResult:
    repo = Path(repo_root)
    record = _find_record(repo, invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    if record.status != INVOICE_DRAFT_PENDING:
        return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="only draft pending invoices can be updated", invoice=record)
    try:
        _require_nonempty("operator_id", operator_id)
        lines = record.line_items if line_items is None else tuple(invoice_line_from_input(item, currency=record.currency) for item in line_items)
        terms = record.payment_terms if payment_terms is None else (_safe_optional_label("payment_terms", payment_terms, 240) or "")
        _require_nonempty("payment_terms", terms)
        tax = record.tax_amount if tax_amount is None else normalize_money(tax_amount, field="tax_amount", min_value=Decimal("0"))
        discount = record.discount_amount if discount_amount is None else normalize_money(discount_amount, field="discount_amount", min_value=Decimal("0"))
        _reject_sensitive_data(terms)
    except SensitiveDataError as exc:
        return _deny(error_code=ERR_SENSITIVE_DATA, error_detail=exc.category, invoice=record)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc), invoice=record)
    source = get_closure(closure_id=record.delivery_closure_id, repo_root=repo)
    if not source.ok or source.closure is None or source.closure.artifact_sha256 != record.artifact_sha256:
        return _deny(error_code=ERR_ARTIFACT_SHA_MISMATCH, error_detail="source integrity failed", invoice=record)
    updated = _build_record(
        closure=source.closure,
        customer_id=record.customer_id,
        billing_scope_key=record.billing_scope_key,
        currency=record.currency,
        payment_terms=terms,
        line_items=lines,
        tax_amount=tax,
        discount_amount=discount,
        operator_id=_normalize_text(operator_id),
        recorded_at=record.recorded_at,
    )
    updated = _replace(updated, status=INVOICE_DRAFT_PENDING, updated_at=recorded_at)
    append_invoice_event(
        audit_log_path=invoice_audit_path(repo),
        event_type=EVT_INVOICE_DRAFT_UPDATED,
        invoice_preparation_id=updated.invoice_preparation_id,
        commercial_scope_id=updated.commercial_scope_id,
        delivery_closure_id=updated.delivery_closure_id,
        resulting_status=updated.status,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
        record=updated.to_dict(),
    )
    return InvoiceServiceResult(ok=True, invoice=updated, permitted_next_actions=_permitted(updated.status), invoice_not_sent=True)


def mark_invoice_ready(*, invoice_preparation_id: str, repo_root, operator_id: str, recorded_at: str) -> InvoiceServiceResult:
    repo = Path(repo_root)
    record = _find_record(repo, invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    if record.status != INVOICE_DRAFT_PENDING:
        return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="invoice must be INVOICE_DRAFT_PENDING", invoice=record)
    if not record.line_items or record.total_amount < Decimal("0"):
        return _deny(error_code=ERR_INVALID_INPUT, error_detail="invoice data is incomplete", invoice=record)
    try:
        _require_nonempty("operator_id", operator_id)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc), invoice=record)
    updated = _replace(record, status=READY_FOR_MANUAL_INVOICE, updated_at=recorded_at)
    append_invoice_event(
        audit_log_path=invoice_audit_path(repo),
        event_type=EVT_INVOICE_READY_FOR_MANUAL_INVOICE,
        invoice_preparation_id=updated.invoice_preparation_id,
        commercial_scope_id=updated.commercial_scope_id,
        delivery_closure_id=updated.delivery_closure_id,
        resulting_status=updated.status,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
        record=updated.to_dict(),
    )
    return InvoiceServiceResult(ok=True, invoice=updated, permitted_next_actions=_permitted(updated.status), invoice_not_sent=True)


def mark_invoice_sent(
    *,
    invoice_preparation_id: str,
    repo_root,
    operator_id: str,
    sent_date: str,
    invoice_number: str,
    recorded_at: str,
    due_date: str | None = None,
    follow_up_date: str | None = None,
) -> InvoiceServiceResult:
    repo = Path(repo_root)
    record = _find_record(repo, invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    if record.status != READY_FOR_MANUAL_INVOICE:
        return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="invoice must be READY_FOR_MANUAL_INVOICE", invoice=record)
    try:
        _require_nonempty("operator_id", operator_id)
        sent = _safe_optional_label("sent_date", sent_date, 64) or ""
        number = _safe_optional_label("invoice_number", invoice_number, 160) or ""
        _require_nonempty("sent_date", sent)
        _require_nonempty("invoice_number", number)
        due = _safe_optional_label("due_date", due_date, 64)
        follow = _safe_optional_label("follow_up_date", follow_up_date, 64)
        _reject_sensitive_data(number, due, follow)
    except SensitiveDataError as exc:
        return _deny(error_code=ERR_SENSITIVE_DATA, error_detail=exc.category, invoice=record)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc), invoice=record)
    updated = _replace(
        record,
        status=PAYMENT_PENDING,
        invoice_number=number,
        sent_date=sent,
        due_date=due,
        follow_up_date=follow,
        updated_at=recorded_at,
    )
    append_invoice_event(
        audit_log_path=invoice_audit_path(repo),
        event_type=EVT_INVOICE_MARKED_SENT,
        invoice_preparation_id=updated.invoice_preparation_id,
        commercial_scope_id=updated.commercial_scope_id,
        delivery_closure_id=updated.delivery_closure_id,
        resulting_status=PAYMENT_PENDING,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
        record=updated.to_dict(),
        reference=number,
    )
    return InvoiceServiceResult(ok=True, invoice=updated, permitted_next_actions=_permitted(updated.status), invoice_not_sent=False)


def inspect_payment_status(*, invoice_preparation_id: str, repo_root) -> InvoiceServiceResult:
    return inspect_invoice_preparation(invoice_preparation_id=invoice_preparation_id, repo_root=repo_root)


def _queue_status(record: InvoicePreparationRecord, as_of: str) -> str | None:
    # Terminal/closed states are never queued for follow-up.
    if record.status in (PAID, CANCELLED):
        return None
    if record.status == OVERDUE:
        return OVERDUE
    if record.due_date and record.due_date < as_of and record.status in (PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE):
        return OVERDUE
    if record.status == PAYMENT_FOLLOW_UP_DUE:
        return PAYMENT_FOLLOW_UP_DUE
    if record.follow_up_date and record.follow_up_date <= as_of and record.status == PAYMENT_PENDING:
        return PAYMENT_FOLLOW_UP_DUE
    # Still-pending or disputed items remain in the queue (due-soon / needs attention).
    if record.status in (PAYMENT_PENDING, DISPUTED):
        return record.status
    return None


def list_payment_follow_up_queue(*, repo_root, as_of: str) -> InvoiceServiceResult:
    items: list[PaymentFollowUpItem] = []
    for record in _records(Path(repo_root)):
        queue_status = _queue_status(record, as_of)
        if queue_status is None:
            continue
        items.append(
            PaymentFollowUpItem(
                invoice_preparation_id=record.invoice_preparation_id,
                commercial_scope_id=record.commercial_scope_id,
                customer_id=record.customer_id,
                project_id=record.project_id,
                status=record.status,
                queue_status=queue_status,
                total_amount=money_to_json(record.total_amount, record.currency),
                currency=record.currency,
                invoice_number=record.invoice_number,
                sent_date=record.sent_date,
                due_date=record.due_date,
                follow_up_date=record.follow_up_date,
                manual_action_required=True,
                automation_allowed=False,
                permitted_next_actions=_permitted(queue_status),
            )
        )
    items.sort(key=lambda item: (item.queue_status, item.due_date or "", item.invoice_preparation_id))
    return InvoiceServiceResult(ok=True, follow_up_queue=tuple(items), manual_action_required=bool(items))


def record_payment_status_decision(
    *,
    invoice_preparation_id: str,
    repo_root,
    decision: str,
    operator_id: str,
    recorded_at: str,
    reason: str | None = None,
    resolution_note: str | None = None,
    paid_date: str | None = None,
    paid_amount: Any | None = None,
    currency: str | None = None,
    payment_reference: str | None = None,
) -> InvoiceServiceResult:
    repo = Path(repo_root)
    record = _find_record(repo, invoice_preparation_id)
    if record is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="invoice preparation not found")
    try:
        _require_nonempty("operator_id", operator_id)
        dec = _normalize_text(decision).lower()
        note = _safe_optional_label("resolution_note", resolution_note, 512)
        why = _safe_optional_label("reason", reason, 512)
        ref = _safe_optional_label("payment_reference", payment_reference, 160)
        _reject_sensitive_data(why, note, ref)
    except SensitiveDataError as exc:
        return _deny(error_code=ERR_SENSITIVE_DATA, error_detail=exc.category, invoice=record)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc), invoice=record)

    changes: dict[str, Any] = {"updated_at": recorded_at}
    if dec == "follow_up_due":
        if record.status != PAYMENT_PENDING:
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="follow_up_due requires PAYMENT_PENDING", invoice=record)
        changes["status"] = PAYMENT_FOLLOW_UP_DUE
    elif dec == "overdue":
        if record.status not in (PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE):
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="overdue requires pending or follow-up due", invoice=record)
        changes["status"] = OVERDUE
    elif dec == "dispute":
        if record.status not in (PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE, OVERDUE):
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="dispute requires payment pending, follow-up due, or overdue", invoice=record)
        if not why:
            return _deny(error_code=ERR_INVALID_INPUT, error_detail="dispute reason is required", invoice=record)
        changes.update({"status": DISPUTED, "dispute_reason": why})
    elif dec == "cancel":
        if record.status not in (PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE, OVERDUE, DISPUTED):
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="cancel requires active payment status", invoice=record)
        if not why:
            return _deny(error_code=ERR_INVALID_INPUT, error_detail="cancellation reason is required", invoice=record)
        changes.update({"status": CANCELLED, "cancellation_reason": why})
    elif dec == "resolve_dispute":
        if record.status != DISPUTED:
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="resolve_dispute requires DISPUTED", invoice=record)
        if not note:
            return _deny(error_code=ERR_INVALID_INPUT, error_detail="resolution note is required", invoice=record)
        changes.update({"status": PAYMENT_PENDING, "resolution_note": note})
    elif dec == "paid":
        if record.status not in (PAYMENT_PENDING, PAYMENT_FOLLOW_UP_DUE, OVERDUE, DISPUTED):
            return _deny(error_code=ERR_INVALID_TRANSITION, error_detail="paid requires active payment status", invoice=record)
        if record.status == DISPUTED and not note:
            return _deny(error_code=ERR_INVALID_INPUT, error_detail="disputed payment requires resolution note", invoice=record)
        try:
            paid_cur = normalize_currency(currency)
            paid = normalize_money(paid_amount, field="paid_amount", min_value=Decimal("0"))
            paid_on = _safe_optional_label("paid_date", paid_date, 64) or ""
            _require_nonempty("paid_date", paid_on)
            _require_nonempty("payment_reference", ref)
        except ValueError as exc:
            return _deny(error_code=ERR_INVALID_INPUT, error_detail=str(exc), invoice=record)
        if paid_cur != record.currency:
            return _deny(error_code=ERR_CURRENCY_MISMATCH, error_detail="payment currency does not match invoice currency", invoice=record)
        paid = quantize_money(paid, record.currency)
        if paid < record.total_amount:
            return _deny(error_code=ERR_PARTIAL_PAYMENT_UNSUPPORTED, error_detail="partial payments are not supported", invoice=record)
        changes.update(
            {
                "status": PAID,
                "paid_date": paid_on,
                "paid_amount": money_to_json(paid, record.currency),
                "payment_reference": ref,
                "resolution_note": note,
            }
        )
    else:
        return _deny(error_code=ERR_INVALID_INPUT, error_detail="unsupported payment decision", invoice=record)

    updated = _replace(record, **changes)
    append_invoice_event(
        audit_log_path=invoice_audit_path(repo),
        event_type=EVT_PAYMENT_STATUS_DECISION_RECORDED,
        invoice_preparation_id=updated.invoice_preparation_id,
        commercial_scope_id=updated.commercial_scope_id,
        delivery_closure_id=updated.delivery_closure_id,
        resulting_status=updated.status,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
        record=updated.to_dict(),
        decision=dec,
        reference=ref,
    )
    return InvoiceServiceResult(ok=True, invoice=updated, permitted_next_actions=_permitted(updated.status), invoice_not_sent=updated.sent_date is None)
