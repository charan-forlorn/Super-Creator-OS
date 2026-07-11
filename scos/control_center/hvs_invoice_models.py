"""SCOS <-> HVS Stage 8A manual invoice preparation models.

Local-only, deterministic, manual accounting handoff. These models never
create invoices in an external system, never contact customers, and never
confirm payment automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .hvs_delivery_closure_models import _normalize_text, _safe_optional_label
from .hvs_local_delivery_models import _require_allowed, _require_nonempty, _sha256_hex16
from .hvs_revenue_audit import ALLOWED_CURRENCIES

INVOICE_PREPARATION_SCHEMA_VERSION = "scos-hvs.invoice-preparation.v1/1.0.0"
INVOICE_AUDIT_SCHEMA_VERSION = "scos-hvs.invoice-audit-event.v1/1.0.0"

DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
INVOICE_DRAFT_PENDING = "INVOICE_DRAFT_PENDING"
READY_FOR_MANUAL_INVOICE = "READY_FOR_MANUAL_INVOICE"
INVOICE_MARKED_SENT = "INVOICE_MARKED_SENT"
PAYMENT_PENDING = "PAYMENT_PENDING"
PAYMENT_FOLLOW_UP_DUE = "PAYMENT_FOLLOW_UP_DUE"
OVERDUE = "OVERDUE"
DISPUTED = "DISPUTED"
CANCELLED = "CANCELLED"
PAID = "PAID"
ALLOWED_INVOICE_STATUSES = (
    DELIVERY_CONFIRMED,
    INVOICE_DRAFT_PENDING,
    READY_FOR_MANUAL_INVOICE,
    INVOICE_MARKED_SENT,
    PAYMENT_PENDING,
    PAYMENT_FOLLOW_UP_DUE,
    OVERDUE,
    DISPUTED,
    CANCELLED,
    PAID,
)

EVT_INVOICE_PREPARATION_CREATED = "INVOICE_PREPARATION_CREATED"
EVT_INVOICE_DRAFT_UPDATED = "INVOICE_DRAFT_UPDATED"
EVT_INVOICE_READY_FOR_MANUAL_INVOICE = "INVOICE_READY_FOR_MANUAL_INVOICE"
EVT_INVOICE_MARKED_SENT = "INVOICE_MARKED_SENT"
EVT_PAYMENT_STATUS_DECISION_RECORDED = "PAYMENT_STATUS_DECISION_RECORDED"
EVT_INVOICE_PREPARATION_REJECTED = "INVOICE_PREPARATION_REJECTED"
ALLOWED_INVOICE_EVENT_TYPES = (
    EVT_INVOICE_PREPARATION_CREATED,
    EVT_INVOICE_DRAFT_UPDATED,
    EVT_INVOICE_READY_FOR_MANUAL_INVOICE,
    EVT_INVOICE_MARKED_SENT,
    EVT_PAYMENT_STATUS_DECISION_RECORDED,
    EVT_INVOICE_PREPARATION_REJECTED,
)

ERR_INVALID_INPUT = "INVALID_INPUT"
ERR_NOT_FOUND = "RECORD_NOT_FOUND"
ERR_CONFLICT = "RECORD_CONFLICT"
ERR_INELIGIBLE_CLOSURE = "INELIGIBLE_CLOSURE"
ERR_ARTIFACT_SHA_MISMATCH = "ARTIFACT_SHA_MISMATCH"
ERR_DUPLICATE_COMMERCIAL_SCOPE = "DUPLICATE_COMMERCIAL_SCOPE"
ERR_INVALID_TRANSITION = "INVALID_TRANSITION"
ERR_PARTIAL_PAYMENT_UNSUPPORTED = "PARTIAL_PAYMENT_UNSUPPORTED"
ERR_CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
ERR_SENSITIVE_DATA = "SENSITIVE_DATA_REJECTED"

_MINOR_UNITS = {
    "JPY": 0,
    "KRW": 0,
    "IDR": 0,
    "VND": 0,
}
_CARD_RE = re.compile(r"(?:\d[ -]?){13,19}")
_CVV_RE = re.compile(r"\b(?:cvv|cvc|security code)\s*[:= -]*\d{3,4}\b", re.IGNORECASE)
_PASSWORD_RE = re.compile(r"\b(?:password|banking password|account password)\s*[:=]", re.IGNORECASE)
_TOKEN_RE = re.compile(r"\b(?:access[_ -]?token|api[_ -]?key)\s*[:=]|Bearer\s+", re.IGNORECASE)
_SEED_RE = re.compile(r"\bseed phrase\b|\bmnemonic phrase\b", re.IGNORECASE)
_BEGIN = "-----" + "BEGIN"
_PRIVATE_KEY = "PRIVATE" + " KEY"


class SensitiveDataError(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _reject_sensitive_data(*fields: Any) -> None:
    for field in fields:
        if field is None:
            continue
        text = str(field)
        compact_digits = re.sub(r"\D", "", text)
        if _CARD_RE.search(text) and 13 <= len(compact_digits) <= 19:
            raise SensitiveDataError("payment_card")
        if _CVV_RE.search(text):
            raise SensitiveDataError("card_security_code")
        if _PASSWORD_RE.search(text):
            raise SensitiveDataError("credential")
        if _TOKEN_RE.search(text):
            raise SensitiveDataError("access_token")
        if _SEED_RE.search(text):
            raise SensitiveDataError("seed_phrase")
        if _BEGIN in text and _PRIVATE_KEY in text:
            raise SensitiveDataError("private_key")


def normalize_money(value: Any, *, field: str, min_value: Decimal | None = None) -> Decimal:
    if isinstance(value, float):
        raise ValueError(f"{field} must not be a float; use str, int, or Decimal")
    if value is None:
        raise ValueError(f"{field} is required")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a valid Decimal value") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    if min_value is not None and amount < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    return amount


def normalize_currency(currency: str | None) -> str:
    text = _normalize_text(currency).upper()
    _require_nonempty("currency", text)
    _require_allowed("currency", text, ALLOWED_CURRENCIES)
    return text


def currency_minor_precision(currency: str) -> int:
    return _MINOR_UNITS.get(currency, 2)


def quantize_money(value: Decimal, currency: str) -> Decimal:
    precision = currency_minor_precision(currency)
    quantum = Decimal("1") if precision == 0 else Decimal("1").scaleb(-precision)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def money_to_json(value: Decimal, currency: str) -> str:
    return str(quantize_money(value, currency))


def _line_content_hash(line_items: tuple["InvoiceLineItem", ...]) -> str:
    canon = "|".join(
        [
            "::".join(
                [
                    item.line_item_id,
                    item.description.lower(),
                    str(item.quantity),
                    str(item.unit_price),
                    item.billing_scope_key.lower(),
                    item.note or "",
                ]
            )
            for item in line_items
        ]
    )
    return _sha256_hex16(canon)


def stable_line_item_id(*, description: str, quantity: Decimal, unit_price: Decimal, billing_scope_key: str) -> str:
    canon = "|".join(["invoice-line", description.lower(), str(quantity), str(unit_price), billing_scope_key.lower()])
    return "scos-hvs-inv-line-" + _sha256_hex16(canon)


def stable_commercial_scope_id(
    *,
    customer_id: str,
    project_id: str | None,
    delivery_record_id: str,
    delivery_closure_id: str,
    artifact_sha256: str,
    billing_scope_key: str,
) -> str:
    canon = "|".join(
        [
            "commercial-scope",
            _normalize_text(customer_id).lower(),
            project_id or "",
            delivery_record_id,
            delivery_closure_id,
            artifact_sha256,
            _normalize_text(billing_scope_key).lower(),
            INVOICE_PREPARATION_SCHEMA_VERSION,
        ]
    )
    return "scos-hvs-commercial-" + _sha256_hex16(canon)


def stable_invoice_preparation_id(
    *,
    commercial_scope_id: str,
    line_items: tuple["InvoiceLineItem", ...],
    currency: str,
    payment_terms: str,
    tax_amount: Decimal,
    discount_amount: Decimal,
) -> str:
    canon = "|".join(
        [
            "invoice-preparation",
            commercial_scope_id,
            _line_content_hash(line_items),
            currency,
            _normalize_text(payment_terms).lower(),
            str(tax_amount),
            str(discount_amount),
            INVOICE_PREPARATION_SCHEMA_VERSION,
        ]
    )
    return "scos-hvs-invoice-" + _sha256_hex16(canon)


def stable_invoice_event_id(
    *,
    event_type: str,
    invoice_preparation_id: str | None,
    commercial_scope_id: str | None,
    resulting_status: str,
    operator_id: str | None,
    decision: str | None = None,
    reference: str | None = None,
) -> str:
    canon = "|".join(
        [
            event_type,
            invoice_preparation_id or "",
            commercial_scope_id or "",
            resulting_status,
            operator_id or "",
            decision or "",
            reference or "",
        ]
    )
    return "invevt-" + _sha256_hex16(canon)


@dataclass(frozen=True)
class InvoiceLineItem:
    line_item_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    billing_scope_key: str
    note: str | None = None

    def to_dict(self, *, currency: str) -> dict[str, Any]:
        return {
            "line_item_id": self.line_item_id,
            "description": self.description,
            "quantity": str(self.quantity),
            "unit_price": money_to_json(self.unit_price, currency),
            "amount": money_to_json(self.amount, currency),
            "billing_scope_key": self.billing_scope_key,
            "note": self.note,
        }


@dataclass(frozen=True)
class InvoicePreparationRecord:
    schema_version: str
    invoice_preparation_id: str
    commercial_scope_id: str
    customer_id: str
    project_id: str | None
    delivery_closure_id: str
    receipt_evidence_id: str
    delivery_record_id: str
    package_id: str
    approval_request_id: str
    artifact_sha256: str
    billing_scope_key: str
    currency: str
    payment_terms: str
    line_items: tuple[InvoiceLineItem, ...]
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    status: str
    operator_id: str
    invoice_number: str | None
    sent_date: str | None
    due_date: str | None
    follow_up_date: str | None
    paid_date: str | None
    paid_amount: Decimal | None
    payment_reference: str | None
    dispute_reason: str | None
    cancellation_reason: str | None
    resolution_note: str | None
    manual_action_required: bool
    automation_allowed: bool
    invoice_created_by_scos: bool
    invoice_sent_by_scos: bool
    payment_confirmed_by_scos: bool
    customer_contact_executed_by_scos: bool
    revenue_recognized_by_scos: bool
    tax_calculated_by_scos: bool
    rounding_mode: str
    recorded_at: str
    updated_at: str
    identity_inputs: dict[str, Any]
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "invoice_preparation_id": self.invoice_preparation_id,
            "commercial_scope_id": self.commercial_scope_id,
            "customer_id": self.customer_id,
            "project_id": self.project_id,
            "delivery_closure_id": self.delivery_closure_id,
            "receipt_evidence_id": self.receipt_evidence_id,
            "delivery_record_id": self.delivery_record_id,
            "package_id": self.package_id,
            "approval_request_id": self.approval_request_id,
            "artifact_sha256": self.artifact_sha256,
            "billing_scope_key": self.billing_scope_key,
            "currency": self.currency,
            "payment_terms": self.payment_terms,
            "line_items": [line.to_dict(currency=self.currency) for line in self.line_items],
            "subtotal": money_to_json(self.subtotal, self.currency),
            "tax_amount": money_to_json(self.tax_amount, self.currency),
            "discount_amount": money_to_json(self.discount_amount, self.currency),
            "total_amount": money_to_json(self.total_amount, self.currency),
            "status": self.status,
            "operator_id": self.operator_id,
            "invoice_number": self.invoice_number,
            "sent_date": self.sent_date,
            "due_date": self.due_date,
            "follow_up_date": self.follow_up_date,
            "paid_date": self.paid_date,
            "paid_amount": None if self.paid_amount is None else money_to_json(self.paid_amount, self.currency),
            "payment_reference": self.payment_reference,
            "dispute_reason": self.dispute_reason,
            "cancellation_reason": self.cancellation_reason,
            "resolution_note": self.resolution_note,
            "manual_action_required": self.manual_action_required,
            "automation_allowed": False,
            "invoice_created_by_scos": False,
            "invoice_sent_by_scos": False,
            "payment_confirmed_by_scos": False,
            "customer_contact_executed_by_scos": False,
            "revenue_recognized_by_scos": False,
            "tax_calculated_by_scos": False,
            "rounding_mode": self.rounding_mode,
            "recorded_at": self.recorded_at,
            "updated_at": self.updated_at,
            "identity_inputs": self.identity_inputs,
            "audit_correlation": self.audit_correlation,
        }


@dataclass(frozen=True)
class PaymentStatusEvent:
    schema_version: str
    event_id: str
    event_type: str
    invoice_preparation_id: str | None
    commercial_scope_id: str | None
    delivery_closure_id: str | None
    resulting_status: str
    operator_id: str | None
    recorded_at: str
    automation_allowed: bool
    record: dict[str, Any] | None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PaymentFollowUpItem:
    invoice_preparation_id: str
    commercial_scope_id: str
    customer_id: str
    project_id: str | None
    status: str
    queue_status: str
    total_amount: str
    currency: str
    invoice_number: str | None
    sent_date: str | None
    due_date: str | None
    follow_up_date: str | None
    manual_action_required: bool
    automation_allowed: bool
    permitted_next_actions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def invoice_line_from_input(data: dict[str, Any], *, currency: str) -> InvoiceLineItem:
    description = _normalize_text(data.get("description"))
    _require_nonempty("description", description)
    billing_scope_key = _safe_optional_label("billing_scope_key", data.get("billing_scope_key"), 160) or ""
    _require_nonempty("billing_scope_key", billing_scope_key)
    note = _safe_optional_label("note", data.get("note"), 512)
    _reject_sensitive_data(description, billing_scope_key, note, data.get("line_item_id"))
    quantity = normalize_money(data.get("quantity"), field="quantity", min_value=Decimal("0"))
    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    unit_price = normalize_money(data.get("unit_price"), field="unit_price", min_value=Decimal("0"))
    amount = quantize_money(quantity * unit_price, currency)
    line_id = _safe_optional_label("line_item_id", data.get("line_item_id"), 128)
    if not line_id:
        line_id = stable_line_item_id(
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            billing_scope_key=billing_scope_key,
        )
    return InvoiceLineItem(
        line_item_id=line_id,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        billing_scope_key=billing_scope_key,
        note=note,
    )


def invoice_line_from_dict(data: dict[str, Any]) -> InvoiceLineItem:
    return InvoiceLineItem(
        line_item_id=data["line_item_id"],
        description=data["description"],
        quantity=Decimal(str(data["quantity"])),
        unit_price=Decimal(str(data["unit_price"])),
        amount=Decimal(str(data["amount"])),
        billing_scope_key=data["billing_scope_key"],
        note=data.get("note"),
    )


def invoice_record_from_dict(data: dict[str, Any]) -> InvoicePreparationRecord:
    return InvoicePreparationRecord(
        schema_version=data["schema_version"],
        invoice_preparation_id=data["invoice_preparation_id"],
        commercial_scope_id=data["commercial_scope_id"],
        customer_id=data["customer_id"],
        project_id=data.get("project_id"),
        delivery_closure_id=data["delivery_closure_id"],
        receipt_evidence_id=data["receipt_evidence_id"],
        delivery_record_id=data["delivery_record_id"],
        package_id=data["package_id"],
        approval_request_id=data["approval_request_id"],
        artifact_sha256=data["artifact_sha256"],
        billing_scope_key=data["billing_scope_key"],
        currency=data["currency"],
        payment_terms=data["payment_terms"],
        line_items=tuple(invoice_line_from_dict(x) for x in data.get("line_items", ())),
        subtotal=Decimal(str(data["subtotal"])),
        tax_amount=Decimal(str(data["tax_amount"])),
        discount_amount=Decimal(str(data["discount_amount"])),
        total_amount=Decimal(str(data["total_amount"])),
        status=data["status"],
        operator_id=data["operator_id"],
        invoice_number=data.get("invoice_number"),
        sent_date=data.get("sent_date"),
        due_date=data.get("due_date"),
        follow_up_date=data.get("follow_up_date"),
        paid_date=data.get("paid_date"),
        paid_amount=None if data.get("paid_amount") is None else Decimal(str(data["paid_amount"])),
        payment_reference=data.get("payment_reference"),
        dispute_reason=data.get("dispute_reason"),
        cancellation_reason=data.get("cancellation_reason"),
        resolution_note=data.get("resolution_note"),
        manual_action_required=bool(data.get("manual_action_required", True)),
        automation_allowed=False,
        invoice_created_by_scos=False,
        invoice_sent_by_scos=False,
        payment_confirmed_by_scos=False,
        customer_contact_executed_by_scos=False,
        revenue_recognized_by_scos=False,
        tax_calculated_by_scos=False,
        rounding_mode=data.get("rounding_mode", "ROUND_HALF_UP"),
        recorded_at=data["recorded_at"],
        updated_at=data["updated_at"],
        identity_inputs=data.get("identity_inputs", {}),
        audit_correlation=data.get("audit_correlation", {}),
    )
