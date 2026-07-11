"""SCOS <-> HVS Stage 7 revenue-ready audit summary model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .hvs_local_delivery_models import _sha256_hex16

REVENUE_READY_AUDIT_SUMMARY_SCHEMA_VERSION = (
    "scos-hvs.revenue-ready-audit-summary.v1/1.0.0"
)

INV_NOT_READY = "NOT_READY"
INV_READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_INVOICE_REVIEW"
INV_BLOCKED_BY_REVISION = "BLOCKED_BY_REVISION"
INV_BLOCKED_BY_REJECTION = "BLOCKED_BY_REJECTION"
INV_BLOCKED_BY_UNCONFIRMED = "BLOCKED_BY_UNCONFIRMED_RECEIPT"
INV_BLOCKED_BY_MISSING_COMMERCIAL = "BLOCKED_BY_MISSING_COMMERCIAL_DATA"
ALLOWED_INVOICE_READINESS = (
    INV_NOT_READY,
    INV_READY_FOR_MANUAL_REVIEW,
    INV_BLOCKED_BY_REVISION,
    INV_BLOCKED_BY_REJECTION,
    INV_BLOCKED_BY_UNCONFIRMED,
    INV_BLOCKED_BY_MISSING_COMMERCIAL,
)

AMOUNT_OPERATOR_PROVIDED = "OPERATOR_PROVIDED"
AMOUNT_EXISTING_VERIFIED_CONTRACT = "EXISTING_VERIFIED_CONTRACT"

ALLOWED_CURRENCIES = (
    "THB",
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "SGD",
    "AUD",
    "CNY",
    "HKD",
    "MYR",
    "IDR",
    "PHP",
    "VND",
    "KRW",
    "INR",
    "NZD",
    "CHF",
    "CAD",
)


def stable_revenue_summary_id(
    *,
    closure_id: str,
    receipt_evidence_id: str,
    package_id: str,
    artifact_sha256: str,
    closure_status: str,
    commercial_reference: str,
    currency: str | None,
    agreed_amount_minor: int | None,
    contract_version: str = REVENUE_READY_AUDIT_SUMMARY_SCHEMA_VERSION,
) -> str:
    canon = "|".join(
        [
            "revenue-ready-summary",
            closure_id,
            receipt_evidence_id,
            package_id,
            artifact_sha256,
            closure_status,
            " ".join(str(commercial_reference or "").split()).lower(),
            currency or "",
            "" if agreed_amount_minor is None else str(agreed_amount_minor),
            contract_version,
        ]
    )
    return "scos-hvs-revenue-" + _sha256_hex16(canon)


@dataclass(frozen=True)
class HVSRevenueReadyAuditSummary:
    schema_version: str
    summary_id: str
    project_id: str | None
    package_id: str
    delivery_record_id: str
    receipt_evidence_id: str
    closure_id: str
    artifact_sha256: str
    delivery_status: str
    receipt_status: str
    closure_status: str
    revision_status: str
    commercial_reference: str
    agreed_amount_minor: int | None
    currency: str | None
    amount_source: str
    amount_verified_by_scos: bool
    invoice_readiness: str
    accounting_review_required: bool
    payment_status: str
    payment_confirmed_by_scos: bool
    invoice_created_by_scos: bool
    revenue_recognized_by_scos: bool
    tax_calculated_by_scos: bool
    customer_contact_executed_by_scos: bool
    automation_allowed: bool
    blockers: list[str]
    warnings: list[str]
    next_manual_action: str
    evidence_chain_ids: dict[str, Any]
    audit_correlation: dict[str, Any]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
