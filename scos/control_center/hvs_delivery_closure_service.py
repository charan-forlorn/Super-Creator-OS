"""SCOS <-> HVS Stage 7 delivery closure service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_delivery_closure_audit import (
    EVT_CUSTOMER_DELIVERY_REJECTED,
    EVT_CUSTOMER_RECEIPT_ACKNOWLEDGED,
    EVT_CUSTOMER_RECEIPT_UNCONFIRMED,
    EVT_CUSTOMER_REVISION_REQUESTED,
    EVT_DELIVERY_ACCEPTED_AND_CLOSED,
    EVT_DELIVERY_CLOSED_WITHOUT_CONFIRMATION,
    EVT_DELIVERY_CLOSURE_REJECTED,
    EVT_DELIVERY_REJECTED_AND_CLOSED,
    EVT_DELIVERY_REVISION_OPEN,
    EVT_INTEGRITY_REVALIDATION_FAILED,
    EVT_REVENUE_AUDIT_SUMMARY_BLOCKED,
    EVT_REVENUE_AUDIT_SUMMARY_CREATED,
    EVT_REVISION_REQUEST_OPENED,
    append_closure_event,
)
from .hvs_delivery_closure_models import (
    ALLOWED_EVIDENCE_SOURCE_TYPES,
    CLOSURE_ACCEPTED,
    CLOSURE_CANCELLED,
    CLOSURE_REJECTED,
    CLOSURE_REVISION_OPEN,
    CLOSURE_WITHOUT_CONFIRMATION,
    CUSTOMER_RECEIPT_EVIDENCE_SCHEMA_VERSION,
    DELIVERY_CLOSURE_SCHEMA_VERSION,
    DELIVERY_REVISION_REQUEST_SCHEMA_VERSION,
    HVSCustomerReceiptEvidence,
    HVSDeliveryClosure,
    HVSDeliveryRevisionRequest,
    REC_ACKNOWLEDGED,
    REC_DELIVERY_REJECTED,
    REC_REVISION_REQUESTED,
    REC_UNCONFIRMED,
    SOURCE_NONE_AVAILABLE,
    _normalize_text,
    _safe_optional_label,
    _safe_short_label,
    _safe_summary,
    normalize_categories,
    stable_closure_id,
    stable_receipt_evidence_id,
    stable_revision_request_id,
)
from .hvs_local_delivery_models import (
    DEL_DELIVERED_MANUALLY,
    PKG_MATERIALIZED,
    _require_allowed,
    _require_nonempty,
)
from .hvs_local_delivery_service import (
    _assert_safe_relative_name,
    _runtime_root,
    _sha256_stream,
    inspect_delivery_package,
    load_manual_delivery_record,
)
from .hvs_revenue_audit import (
    ALLOWED_CURRENCIES,
    AMOUNT_OPERATOR_PROVIDED,
    HVSRevenueReadyAuditSummary,
    INV_BLOCKED_BY_MISSING_COMMERCIAL,
    INV_BLOCKED_BY_REJECTION,
    INV_BLOCKED_BY_REVISION,
    INV_BLOCKED_BY_UNCONFIRMED,
    INV_NOT_READY,
    INV_READY_FOR_MANUAL_REVIEW,
    REVENUE_READY_AUDIT_SUMMARY_SCHEMA_VERSION,
    stable_revenue_summary_id,
)

ERR_INTEGRITY = "integrity_revalidation_failed"
ERR_NOT_FOUND = "record_not_found"
ERR_CONFLICT = "record_conflict"
ERR_INVALID = "invalid_input"


@dataclass(frozen=True)
class ClosureServiceResult:
    ok: bool
    package_id: str | None = None
    delivery_record_id: str | None = None
    receipt_evidence: HVSCustomerReceiptEvidence | None = None
    revision_request: HVSDeliveryRevisionRequest | None = None
    closure: HVSDeliveryClosure | None = None
    revenue_summary: HVSRevenueReadyAuditSummary | None = None
    error_code: str | None = None
    error_detail: str | None = None
    next_manual_action: str = "review_result"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "package_id": self.package_id,
            "delivery_record_id": self.delivery_record_id,
            "receipt_evidence": (
                self.receipt_evidence.to_dict() if self.receipt_evidence else None
            ),
            "revision_request": (
                self.revision_request.to_dict() if self.revision_request else None
            ),
            "closure": self.closure.to_dict() if self.closure else None,
            "revenue_summary": (
                self.revenue_summary.to_dict() if self.revenue_summary else None
            ),
            "operator_asserted": True,
            "externally_verified_by_scos": False,
            "external_delivery_executed_by_scos": False,
            "customer_contact_executed_by_scos": False,
            "payment_confirmed_by_scos": False,
            "invoice_created_by_scos": False,
            "revenue_recognized_by_scos": False,
            "automation_allowed": False,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "next_manual_action": self.next_manual_action,
        }


class _IntegrityError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class _Context:
    repo_root: Path
    package_dir: Path
    manifest: Any
    delivery_record: Any
    artifact_path: Path
    artifact_sha256: str


def _deny(
    *,
    error_code: str,
    error_detail: str,
    package_id: str | None = None,
    delivery_record_id: str | None = None,
    next_manual_action: str = "operator_review_required",
) -> ClosureServiceResult:
    return ClosureServiceResult(
        ok=False,
        package_id=package_id,
        delivery_record_id=delivery_record_id,
        error_code=error_code,
        error_detail=error_detail,
        next_manual_action=next_manual_action,
    )


def record_customer_receipt_evidence(
    *,
    delivery_record_id: str,
    repo_root,
    status: str,
    source_type: str,
    operator_id: str,
    customer_reference: str,
    statement_summary: str,
    revision_summary: str | None = None,
    rejection_reason: str | None = None,
    external_reference: str | None = None,
    operator_note: str | None = None,
    recorded_at: str,
) -> ClosureServiceResult:
    try:
        ctx = _context_for_delivery_record(
            delivery_record_id=delivery_record_id, repo_root=Path(repo_root)
        )
        _require_nonempty("operator_id", operator_id)
        status_full = _normalize_receipt_status(status)
        _require_allowed("source_type", source_type, ALLOWED_EVIDENCE_SOURCE_TYPES)
        customer_label = _safe_short_label("customer_reference", customer_reference)
        statement = _receipt_statement_for_status(
            status=status_full,
            statement_summary=statement_summary,
            operator_note=operator_note,
        )
        rev = _safe_summary("revision_summary", revision_summary) if status_full == REC_REVISION_REQUESTED else None
        rej = _safe_summary("rejection_reason", rejection_reason) if status_full == REC_DELIVERY_REJECTED else None
        if status_full == REC_ACKNOWLEDGED and source_type == SOURCE_NONE_AVAILABLE:
            raise ValueError("acknowledgment requires a positive evidence source type")
        ext_ref = _safe_optional_label("external_reference", external_reference)
    except (ValueError, _IntegrityError) as exc:
        detail = getattr(exc, "detail", str(exc))
        code = getattr(exc, "code", ERR_INVALID)
        return _deny(
            error_code=code,
            error_detail=detail,
            delivery_record_id=delivery_record_id,
        )

    receipt_id = stable_receipt_evidence_id(
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        package_id=ctx.manifest.package_id,
        artifact_sha256=ctx.artifact_sha256,
        receipt_status=status_full,
        evidence_source_type=source_type,
        statement_text=statement,
    )
    record = HVSCustomerReceiptEvidence(
        schema_version=CUSTOMER_RECEIPT_EVIDENCE_SCHEMA_VERSION,
        receipt_evidence_id=receipt_id,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        approval_request_id=ctx.manifest.approval_request_id,
        packet_id=ctx.manifest.packet_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        receipt_status=status_full,
        evidence_source_type=source_type,
        operator_id=_normalize_text(operator_id),
        customer_reference_label=customer_label,
        customer_statement_summary=statement,
        revision_summary=rev,
        rejection_reason=rej,
        external_reference=ext_ref,
        evidence_observed_at=recorded_at,
        recorded_at=recorded_at,
        operator_asserted=True,
        externally_verified_by_scos=False,
        customer_contact_executed_by_scos=False,
        automation_allowed=False,
        identity_inputs={
            "delivery_record_id": ctx.delivery_record.delivery_record_id,
            "package_id": ctx.manifest.package_id,
            "artifact_sha256": ctx.artifact_sha256,
            "receipt_status": status_full,
            "evidence_source_type": source_type,
            "statement_summary_hash": stable_receipt_evidence_id(
                delivery_record_id="",
                package_id="",
                artifact_sha256="",
                receipt_status="",
                evidence_source_type="",
                statement_text=statement,
            ),
            "contract_version": CUSTOMER_RECEIPT_EVIDENCE_SCHEMA_VERSION,
        },
        audit_correlation=_audit_correlation(ctx),
    )
    existing = _receipts_for_package(ctx.package_dir)
    for seen in existing:
        if seen.receipt_evidence_id == receipt_id:
            return ClosureServiceResult(
                ok=True,
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
                receipt_evidence=seen,
                next_manual_action=_next_after_receipt(seen.receipt_status),
            )
        if seen.delivery_record_id == ctx.delivery_record.delivery_record_id:
            return _deny(
                error_code=ERR_CONFLICT,
                error_detail="conflicting receipt evidence already exists",
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
            )
    _write_json_atomic(record.to_dict(), ctx.package_dir / f"receipt_evidence_{receipt_id}.json")
    append_closure_event(
        audit_log_path=_closure_audit_path(ctx.repo_root),
        event_type=_receipt_event(status_full),
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        resulting_status=status_full,
        operator_id=record.operator_id,
        recorded_at=recorded_at,
        receipt_evidence_id=receipt_id,
    )
    return ClosureServiceResult(
        ok=True,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        receipt_evidence=record,
        next_manual_action=_next_after_receipt(status_full),
    )


def get_receipt_evidence(*, receipt_evidence_id: str, repo_root) -> ClosureServiceResult:
    receipt = load_receipt_evidence(receipt_evidence_id=receipt_evidence_id, repo_root=repo_root)
    if receipt is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="receipt evidence not found")
    try:
        _context_for_delivery_record(
            delivery_record_id=receipt.delivery_record_id, repo_root=Path(repo_root)
        )
    except _IntegrityError as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            package_id=receipt.package_id,
            delivery_record_id=receipt.delivery_record_id,
        )
    return ClosureServiceResult(
        ok=True,
        package_id=receipt.package_id,
        delivery_record_id=receipt.delivery_record_id,
        receipt_evidence=receipt,
        next_manual_action=_next_after_receipt(receipt.receipt_status),
    )


def load_receipt_evidence(*, receipt_evidence_id: str, repo_root):
    for path in _runtime_root(Path(repo_root)).glob("*/receipt_evidence_*.json"):
        data = _read_json(path)
        if data.get("receipt_evidence_id") == receipt_evidence_id:
            return _receipt_from_dict(data)
    return None


def open_revision_request(
    *,
    receipt_evidence_id: str,
    repo_root,
    operator_id: str,
    revision_summary: str,
    change_categories: list[str],
    priority: str,
    due_date: str | None = None,
    recorded_at: str,
) -> ClosureServiceResult:
    try:
        receipt = _require_receipt(receipt_evidence_id, repo_root)
        ctx = _context_for_delivery_record(
            delivery_record_id=receipt.delivery_record_id, repo_root=Path(repo_root)
        )
        if receipt.receipt_status != REC_REVISION_REQUESTED:
            raise ValueError("revision can only open from REVISION_REQUESTED evidence")
        _require_nonempty("operator_id", operator_id)
        summary = _safe_summary("revision_summary", revision_summary)
        categories = normalize_categories(tuple(change_categories))
        prio = _safe_optional_label("priority", priority, 64) or "normal"
        due = _safe_optional_label("due_date", due_date, 64)
    except (ValueError, _IntegrityError) as exc:
        return _deny(
            error_code=getattr(exc, "code", ERR_INVALID),
            error_detail=getattr(exc, "detail", str(exc)),
        )

    existing = _revisions_for_package(ctx.package_dir, receipt_evidence_id=receipt_evidence_id)
    for rev in existing:
        if (
            rev.revision_summary == summary
            and tuple(sorted(rev.requested_change_categories)) == categories
            and rev.status == "OPEN"
        ):
            return ClosureServiceResult(
                ok=True,
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
                revision_request=rev,
                next_manual_action="operator_review_revision_request",
            )
    if existing:
        return _deny(
            error_code=ERR_CONFLICT,
            error_detail="conflicting revision request already exists for this evidence",
            package_id=ctx.manifest.package_id,
            delivery_record_id=ctx.delivery_record.delivery_record_id,
        )
    revision_round = len([r for r in existing if r.status == "OPEN"]) + 1
    revision_id = stable_revision_request_id(
        receipt_evidence_id=receipt_evidence_id,
        package_id=ctx.manifest.package_id,
        artifact_sha256=ctx.artifact_sha256,
        revision_summary=summary,
        requested_change_categories=categories,
        revision_round=revision_round,
    )
    record = HVSDeliveryRevisionRequest(
        schema_version=DELIVERY_REVISION_REQUEST_SCHEMA_VERSION,
        revision_request_id=revision_id,
        receipt_evidence_id=receipt_evidence_id,
        package_id=ctx.manifest.package_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        operator_id=_normalize_text(operator_id),
        revision_summary=summary,
        requested_change_categories=list(categories),
        priority=prio,
        due_date=due,
        revision_round=revision_round,
        status="OPEN",
        rendering_not_started=True,
        automation_allowed=False,
        recorded_at=recorded_at,
        audit_correlation=_audit_correlation(ctx) | {"receipt_evidence_id": receipt_evidence_id},
    )
    _write_json_atomic(record.to_dict(), ctx.package_dir / f"revision_request_{revision_id}.json")
    append_closure_event(
        audit_log_path=_closure_audit_path(ctx.repo_root),
        event_type=EVT_REVISION_REQUEST_OPENED,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        resulting_status="OPEN",
        operator_id=record.operator_id,
        recorded_at=recorded_at,
        receipt_evidence_id=receipt_evidence_id,
        revision_request_id=revision_id,
    )
    return ClosureServiceResult(
        ok=True,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        revision_request=record,
        next_manual_action="operator_review_revision_request",
    )


def close_delivery(
    *,
    receipt_evidence_id: str,
    repo_root,
    operator_id: str,
    decision: str,
    reason: str,
    recorded_at: str,
) -> ClosureServiceResult:
    try:
        receipt = _require_receipt(receipt_evidence_id, repo_root)
        ctx = _context_for_delivery_record(
            delivery_record_id=receipt.delivery_record_id, repo_root=Path(repo_root)
        )
        _require_nonempty("operator_id", operator_id)
        closure_status = _closure_status_for_decision(decision, receipt, ctx.package_dir)
        reason_text = _safe_summary("reason", reason)
    except (ValueError, _IntegrityError) as exc:
        return _deny(
            error_code=getattr(exc, "code", ERR_INVALID),
            error_detail=getattr(exc, "detail", str(exc)),
        )

    open_revision_id = None
    if closure_status == CLOSURE_REVISION_OPEN:
        revisions = _revisions_for_package(ctx.package_dir, receipt_evidence_id=receipt_evidence_id)
        open_revision_id = revisions[0].revision_request_id if revisions else None
        if not open_revision_id:
            return _deny(
                error_code=ERR_INVALID,
                error_detail="REVISION_OPEN requires an OPEN revision request",
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
            )
    closure_id = stable_closure_id(
        receipt_evidence_id=receipt_evidence_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        package_id=ctx.manifest.package_id,
        artifact_sha256=ctx.artifact_sha256,
        closure_status=closure_status,
    )
    record = HVSDeliveryClosure(
        schema_version=DELIVERY_CLOSURE_SCHEMA_VERSION,
        closure_id=closure_id,
        receipt_evidence_id=receipt_evidence_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        package_id=ctx.manifest.package_id,
        approval_request_id=ctx.manifest.approval_request_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        closure_status=closure_status,
        operator_id=_normalize_text(operator_id),
        closure_reason=reason_text,
        accepted_by_customer=closure_status == CLOSURE_ACCEPTED,
        payment_confirmed=False,
        revenue_recognized_by_scos=False,
        invoice_created_by_scos=False,
        customer_contact_executed_by_scos=False,
        automation_allowed=False,
        manual_follow_up_required=closure_status in (CLOSURE_REVISION_OPEN, CLOSURE_WITHOUT_CONFIRMATION),
        open_revision_request_id=open_revision_id,
        recorded_at=recorded_at,
        identity_inputs={
            "receipt_evidence_id": receipt_evidence_id,
            "delivery_record_id": ctx.delivery_record.delivery_record_id,
            "package_id": ctx.manifest.package_id,
            "artifact_sha256": ctx.artifact_sha256,
            "closure_status": closure_status,
            "contract_version": DELIVERY_CLOSURE_SCHEMA_VERSION,
        },
        audit_correlation=_audit_correlation(ctx) | {"receipt_evidence_id": receipt_evidence_id},
    )
    existing = _closures_for_package(ctx.package_dir)
    for seen in existing:
        if seen.closure_id == closure_id:
            return ClosureServiceResult(
                ok=True,
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
                closure=seen,
                next_manual_action=_next_after_closure(seen.closure_status),
            )
        if seen.receipt_evidence_id == receipt_evidence_id:
            append_closure_event(
                audit_log_path=_closure_audit_path(ctx.repo_root),
                event_type=EVT_DELIVERY_CLOSURE_REJECTED,
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
                project_id=ctx.manifest.source_project_id,
                artifact_sha256=ctx.artifact_sha256,
                resulting_status=seen.closure_status,
                operator_id=_normalize_text(operator_id),
                recorded_at=recorded_at,
                receipt_evidence_id=receipt_evidence_id,
                closure_id=seen.closure_id,
            )
            return _deny(
                error_code=ERR_CONFLICT,
                error_detail="conflicting final closure already exists",
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
            )
    _write_json_atomic(record.to_dict(), ctx.package_dir / f"delivery_closure_{closure_id}.json")
    append_closure_event(
        audit_log_path=_closure_audit_path(ctx.repo_root),
        event_type=_closure_event(closure_status),
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        resulting_status=closure_status,
        operator_id=record.operator_id,
        recorded_at=recorded_at,
        receipt_evidence_id=receipt_evidence_id,
        closure_id=closure_id,
        revision_request_id=open_revision_id,
    )
    return ClosureServiceResult(
        ok=True,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        closure=record,
        next_manual_action=_next_after_closure(closure_status),
    )


def get_closure(*, closure_id: str, repo_root) -> ClosureServiceResult:
    closure = _load_closure(closure_id=closure_id, repo_root=Path(repo_root))
    if closure is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="closure not found")
    try:
        _context_for_delivery_record(
            delivery_record_id=closure.delivery_record_id, repo_root=Path(repo_root)
        )
    except _IntegrityError as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            package_id=closure.package_id,
            delivery_record_id=closure.delivery_record_id,
        )
    return ClosureServiceResult(
        ok=True,
        package_id=closure.package_id,
        delivery_record_id=closure.delivery_record_id,
        closure=closure,
        next_manual_action=_next_after_closure(closure.closure_status),
    )


def create_revenue_audit_summary(
    *,
    closure_id: str,
    repo_root,
    operator_id: str,
    commercial_reference: str,
    agreed_amount_minor: int | None = None,
    currency: str | None = None,
    recorded_at: str,
) -> ClosureServiceResult:
    try:
        closure = _require_closure(closure_id, repo_root)
        receipt = _require_receipt(closure.receipt_evidence_id, repo_root)
        ctx = _context_for_delivery_record(
            delivery_record_id=closure.delivery_record_id, repo_root=Path(repo_root)
        )
        _require_nonempty("operator_id", operator_id)
        commercial_ref = _safe_optional_label("commercial_reference", commercial_reference, 160) or ""
        if agreed_amount_minor is not None and not isinstance(agreed_amount_minor, int):
            raise ValueError("agreed_amount_minor must be an integer minor-unit value")
        cur = _normalize_text(currency).upper() if currency is not None else None
        if cur is not None:
            _require_allowed("currency", cur, ALLOWED_CURRENCIES)
    except (ValueError, _IntegrityError) as exc:
        return _deny(
            error_code=getattr(exc, "code", ERR_INVALID),
            error_detail=getattr(exc, "detail", str(exc)),
        )

    blockers, warnings, readiness, next_action = _revenue_readiness(
        closure=closure,
        receipt=receipt,
        has_revision=bool(_revisions_for_package(ctx.package_dir, receipt_evidence_id=receipt.receipt_evidence_id)),
        commercial_reference=commercial_ref,
        agreed_amount_minor=agreed_amount_minor,
        currency=cur,
    )
    summary_id = stable_revenue_summary_id(
        closure_id=closure.closure_id,
        receipt_evidence_id=receipt.receipt_evidence_id,
        package_id=ctx.manifest.package_id,
        artifact_sha256=ctx.artifact_sha256,
        closure_status=closure.closure_status,
        commercial_reference=commercial_ref,
        currency=cur,
        agreed_amount_minor=agreed_amount_minor,
    )
    summary = HVSRevenueReadyAuditSummary(
        schema_version=REVENUE_READY_AUDIT_SUMMARY_SCHEMA_VERSION,
        summary_id=summary_id,
        project_id=ctx.manifest.source_project_id,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        receipt_evidence_id=receipt.receipt_evidence_id,
        closure_id=closure.closure_id,
        artifact_sha256=ctx.artifact_sha256,
        delivery_status=ctx.delivery_record.final_status,
        receipt_status=receipt.receipt_status,
        closure_status=closure.closure_status,
        revision_status="OPEN" if closure.closure_status == CLOSURE_REVISION_OPEN else "NONE",
        commercial_reference=commercial_ref,
        agreed_amount_minor=agreed_amount_minor,
        currency=cur,
        amount_source=AMOUNT_OPERATOR_PROVIDED,
        amount_verified_by_scos=False,
        invoice_readiness=readiness,
        accounting_review_required=True,
        payment_status="NOT_VERIFIED",
        payment_confirmed_by_scos=False,
        invoice_created_by_scos=False,
        revenue_recognized_by_scos=False,
        tax_calculated_by_scos=False,
        customer_contact_executed_by_scos=False,
        automation_allowed=False,
        blockers=blockers,
        warnings=warnings,
        next_manual_action=next_action,
        evidence_chain_ids={
            "approval_request_id": ctx.manifest.approval_request_id,
            "packet_id": ctx.manifest.packet_id,
            "package_id": ctx.manifest.package_id,
            "delivery_record_id": ctx.delivery_record.delivery_record_id,
            "receipt_evidence_id": receipt.receipt_evidence_id,
            "closure_id": closure.closure_id,
        },
        audit_correlation=_audit_correlation(ctx)
        | {"receipt_evidence_id": receipt.receipt_evidence_id, "closure_id": closure.closure_id},
        recorded_at=recorded_at,
    )
    existing = _summaries_for_package(ctx.package_dir)
    for seen in existing:
        if seen.summary_id == summary_id:
            return ClosureServiceResult(
                ok=True,
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
                revenue_summary=seen,
                next_manual_action=seen.next_manual_action,
            )
        if seen.closure_id == closure_id:
            return _deny(
                error_code=ERR_CONFLICT,
                error_detail="conflicting revenue audit summary already exists",
                package_id=ctx.manifest.package_id,
                delivery_record_id=ctx.delivery_record.delivery_record_id,
            )
    _write_json_atomic(summary.to_dict(), ctx.package_dir / f"revenue_audit_summary_{summary_id}.json")
    append_closure_event(
        audit_log_path=_closure_audit_path(ctx.repo_root),
        event_type=(
            EVT_REVENUE_AUDIT_SUMMARY_CREATED
            if readiness == INV_READY_FOR_MANUAL_REVIEW
            else EVT_REVENUE_AUDIT_SUMMARY_BLOCKED
        ),
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        project_id=ctx.manifest.source_project_id,
        artifact_sha256=ctx.artifact_sha256,
        resulting_status=readiness,
        operator_id=_normalize_text(operator_id),
        recorded_at=recorded_at,
        receipt_evidence_id=receipt.receipt_evidence_id,
        closure_id=closure.closure_id,
        summary_id=summary_id,
    )
    return ClosureServiceResult(
        ok=True,
        package_id=ctx.manifest.package_id,
        delivery_record_id=ctx.delivery_record.delivery_record_id,
        revenue_summary=summary,
        next_manual_action=next_action,
    )


def get_revenue_audit_summary(*, summary_id: str, repo_root) -> ClosureServiceResult:
    summary = _load_summary(summary_id=summary_id, repo_root=Path(repo_root))
    if summary is None:
        return _deny(error_code=ERR_NOT_FOUND, error_detail="revenue audit summary not found")
    try:
        _context_for_delivery_record(
            delivery_record_id=summary.delivery_record_id, repo_root=Path(repo_root)
        )
    except _IntegrityError as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            package_id=summary.package_id,
            delivery_record_id=summary.delivery_record_id,
        )
    return ClosureServiceResult(
        ok=True,
        package_id=summary.package_id,
        delivery_record_id=summary.delivery_record_id,
        revenue_summary=summary,
        next_manual_action=summary.next_manual_action,
    )


def _context_for_delivery_record(*, delivery_record_id: str, repo_root: Path) -> _Context:
    runtime = _runtime_root(repo_root)
    for path in runtime.glob("*/manual_delivery_record.json"):
        data = _read_json(path)
        if data.get("delivery_record_id") != delivery_record_id:
            continue
        package_id = data.get("package_id", "")
        return _context_for_package(package_id=package_id, repo_root=repo_root, expected_delivery_id=delivery_record_id)
    raise _IntegrityError(ERR_NOT_FOUND, "manual delivery record not found")


def _context_for_package(*, package_id: str, repo_root: Path, expected_delivery_id: str | None = None) -> _Context:
    try:
        _assert_safe_relative_name(package_id)
    except ValueError as exc:
        raise _IntegrityError("unsafe_path", str(exc))
    pkg_dir = _runtime_root(repo_root) / package_id
    try:
        pkg_dir.resolve().relative_to(_runtime_root(repo_root).resolve())
    except (ValueError, OSError) as exc:
        raise _IntegrityError("unsafe_path", str(exc))
    inspected = inspect_delivery_package(package_id=package_id, repo_root=repo_root)
    if not inspected.ok or inspected.manifest is None:
        raise _IntegrityError(inspected.error_code or ERR_INTEGRITY, inspected.error_detail or "package missing")
    manifest = inspected.manifest
    if manifest.package_status != PKG_MATERIALIZED:
        raise _IntegrityError("not_materialized", "package must be MATERIALIZED")
    record = load_manual_delivery_record(package_id=package_id, repo_root=repo_root)
    if record is None:
        raise _IntegrityError("delivery_record_not_found", "manual delivery record missing")
    if expected_delivery_id is not None and record.delivery_record_id != expected_delivery_id:
        raise _IntegrityError(ERR_INTEGRITY, "delivery record identity mismatch")
    if record.final_status != DEL_DELIVERED_MANUALLY:
        raise _IntegrityError("not_delivered_manually", "manual delivery final status is not DELIVERED_MANUALLY")
    if record.manual_delivery_performed is not True:
        raise _IntegrityError(ERR_INTEGRITY, "manual delivery was not performed")
    if record.delivery_was_external_to_scos is not True:
        raise _IntegrityError(ERR_INTEGRITY, "delivery external-to-SCOS flag is invalid")
    if record.automation_allowed is not False or manifest.automation_allowed is not False:
        raise _IntegrityError(ERR_INTEGRITY, "automation_allowed must remain false")
    if not manifest.packaged_artifact_relative_path:
        raise _IntegrityError("artifact_missing", "materialized artifact path missing")
    try:
        _assert_safe_relative_name(manifest.packaged_artifact_relative_path)
    except ValueError as exc:
        raise _IntegrityError("unsafe_path", str(exc))
    artifact_path = pkg_dir / manifest.packaged_artifact_relative_path
    try:
        artifact_path.resolve().relative_to(pkg_dir.resolve())
        artifact_path.resolve().relative_to(_runtime_root(repo_root).resolve())
    except (ValueError, OSError) as exc:
        _append_integrity_failure(repo_root, manifest, record, str(exc))
        raise _IntegrityError("unsafe_path", "materialized artifact escapes runtime root")
    if not artifact_path.is_file() or artifact_path.is_symlink():
        _append_integrity_failure(repo_root, manifest, record, "artifact not regular")
        raise _IntegrityError("artifact_missing", "materialized artifact is missing or not regular")
    if artifact_path.stat().st_size <= 0:
        _append_integrity_failure(repo_root, manifest, record, "artifact zero byte")
        raise _IntegrityError("artifact_zero_byte", "materialized artifact is zero bytes")
    live_sha = _sha256_stream(artifact_path)
    expected_sha = str(manifest.packaged_artifact_sha256 or manifest.source_artifact_sha256)
    if live_sha.lower() != expected_sha.lower():
        _append_integrity_failure(repo_root, manifest, record, "artifact SHA mismatch")
        raise _IntegrityError("artifact_sha_mismatch", "materialized artifact SHA mismatch")
    for value in (
        manifest.source_artifact_sha256,
        manifest.packaged_artifact_sha256,
        record.artifact_sha256,
    ):
        if str(value or "").lower() != live_sha.lower():
            raise _IntegrityError("artifact_sha_mismatch", "artifact identity chain mismatch")
    if record.package_id != manifest.package_id or record.approval_request_id != manifest.approval_request_id:
        raise _IntegrityError(ERR_INTEGRITY, "Stage 6 package and delivery record linkage mismatch")
    return _Context(
        repo_root=repo_root,
        package_dir=pkg_dir,
        manifest=manifest,
        delivery_record=record,
        artifact_path=artifact_path,
        artifact_sha256=live_sha,
    )


def _require_receipt(receipt_evidence_id: str, repo_root) -> HVSCustomerReceiptEvidence:
    receipt = load_receipt_evidence(receipt_evidence_id=receipt_evidence_id, repo_root=repo_root)
    if receipt is None:
        raise _IntegrityError(ERR_NOT_FOUND, "receipt evidence not found")
    return receipt


def _require_closure(closure_id: str, repo_root) -> HVSDeliveryClosure:
    closure = _load_closure(closure_id=closure_id, repo_root=Path(repo_root))
    if closure is None:
        raise _IntegrityError(ERR_NOT_FOUND, "closure not found")
    return closure


def _receipt_statement_for_status(
    *, status: str, statement_summary: str | None, operator_note: str | None
) -> str:
    if status == REC_ACKNOWLEDGED:
        return _safe_summary("customer_statement_summary", statement_summary)
    if status == REC_REVISION_REQUESTED:
        return _safe_summary("customer_statement_summary", statement_summary)
    if status == REC_DELIVERY_REJECTED:
        return _safe_summary("customer_statement_summary", statement_summary)
    if status == REC_UNCONFIRMED:
        return _safe_summary("operator_note", operator_note or statement_summary)
    raise ValueError("unsupported receipt status")


def _normalize_receipt_status(status: str) -> str:
    status_map = {
        "acknowledged": REC_ACKNOWLEDGED,
        "revision-requested": REC_REVISION_REQUESTED,
        "revision_requested": REC_REVISION_REQUESTED,
        "rejected": REC_DELIVERY_REJECTED,
        "unconfirmed": REC_UNCONFIRMED,
    }
    full = status_map.get(status, status)
    if full not in (REC_ACKNOWLEDGED, REC_REVISION_REQUESTED, REC_DELIVERY_REJECTED, REC_UNCONFIRMED):
        raise ValueError("unsupported receipt status")
    return full


def _closure_status_for_decision(decision: str, receipt: HVSCustomerReceiptEvidence, package_dir: Path) -> str:
    if decision == "accept":
        if receipt.receipt_status != REC_ACKNOWLEDGED:
            raise ValueError("accept requires RECEIPT_ACKNOWLEDGED evidence")
        return CLOSURE_ACCEPTED
    if decision == "revision_open":
        if receipt.receipt_status != REC_REVISION_REQUESTED:
            raise ValueError("revision_open requires REVISION_REQUESTED evidence")
        if not _revisions_for_package(package_dir, receipt_evidence_id=receipt.receipt_evidence_id):
            raise ValueError("revision_open requires an OPEN revision request")
        return CLOSURE_REVISION_OPEN
    if decision == "reject":
        if receipt.receipt_status != REC_DELIVERY_REJECTED:
            raise ValueError("reject requires DELIVERY_REJECTED evidence")
        return CLOSURE_REJECTED
    if decision == "close_without_confirmation":
        if receipt.receipt_status != REC_UNCONFIRMED:
            raise ValueError("close_without_confirmation requires RECEIPT_UNCONFIRMED evidence")
        return CLOSURE_WITHOUT_CONFIRMATION
    if decision == "cancel":
        return CLOSURE_CANCELLED
    raise ValueError("unsupported closure decision")


def _revenue_readiness(
    *,
    closure: HVSDeliveryClosure,
    receipt: HVSCustomerReceiptEvidence,
    has_revision: bool,
    commercial_reference: str,
    agreed_amount_minor: int | None,
    currency: str | None,
) -> tuple[list[str], list[str], str, str]:
    blockers: list[str] = []
    warnings: list[str] = []
    if closure.artifact_sha256 != receipt.artifact_sha256:
        blockers.append("artifact_sha_mismatch")
    if closure.closure_status == CLOSURE_REVISION_OPEN or has_revision:
        blockers.append("open_revision")
        return blockers, warnings, INV_BLOCKED_BY_REVISION, "resolve_open_revision_manually"
    if closure.closure_status == CLOSURE_REJECTED:
        blockers.append("delivery_rejected")
        return blockers, warnings, INV_BLOCKED_BY_REJECTION, "review_rejection_manually"
    if closure.closure_status == CLOSURE_WITHOUT_CONFIRMATION:
        blockers.append("receipt_unconfirmed")
        return blockers, warnings, INV_BLOCKED_BY_UNCONFIRMED, "perform_manual_follow_up"
    if closure.closure_status != CLOSURE_ACCEPTED or receipt.receipt_status != REC_ACKNOWLEDGED:
        blockers.append("not_accepted_by_customer")
    if not commercial_reference or agreed_amount_minor is None or currency is None:
        blockers.append("missing_commercial_data")
        return blockers, warnings, INV_BLOCKED_BY_MISSING_COMMERCIAL, "provide_manual_commercial_data"
    if blockers:
        return blockers, warnings, INV_NOT_READY, "review_blockers_manually"
    warnings.append("amount_operator_provided_not_verified_by_scos")
    return blockers, warnings, INV_READY_FOR_MANUAL_REVIEW, "manual_invoice_review"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _receipts_for_package(package_dir: Path) -> list[HVSCustomerReceiptEvidence]:
    return [_receipt_from_dict(_read_json(path)) for path in sorted(package_dir.glob("receipt_evidence_*.json"))]


def _revisions_for_package(package_dir: Path, *, receipt_evidence_id: str | None = None) -> list[HVSDeliveryRevisionRequest]:
    records = [_revision_from_dict(_read_json(path)) for path in sorted(package_dir.glob("revision_request_*.json"))]
    if receipt_evidence_id is not None:
        records = [r for r in records if r.receipt_evidence_id == receipt_evidence_id and r.status == "OPEN"]
    return records


def _closures_for_package(package_dir: Path) -> list[HVSDeliveryClosure]:
    return [_closure_from_dict(_read_json(path)) for path in sorted(package_dir.glob("delivery_closure_*.json"))]


def _summaries_for_package(package_dir: Path) -> list[HVSRevenueReadyAuditSummary]:
    return [_summary_from_dict(_read_json(path)) for path in sorted(package_dir.glob("revenue_audit_summary_*.json"))]


def _load_closure(*, closure_id: str, repo_root: Path):
    for path in _runtime_root(repo_root).glob("*/delivery_closure_*.json"):
        data = _read_json(path)
        if data.get("closure_id") == closure_id:
            return _closure_from_dict(data)
    return None


def _load_summary(*, summary_id: str, repo_root: Path):
    for path in _runtime_root(repo_root).glob("*/revenue_audit_summary_*.json"):
        data = _read_json(path)
        if data.get("summary_id") == summary_id:
            return _summary_from_dict(data)
    return None


def _receipt_from_dict(d: dict[str, Any]) -> HVSCustomerReceiptEvidence:
    return HVSCustomerReceiptEvidence(**d)


def _revision_from_dict(d: dict[str, Any]) -> HVSDeliveryRevisionRequest:
    return HVSDeliveryRevisionRequest(**d)


def _closure_from_dict(d: dict[str, Any]) -> HVSDeliveryClosure:
    return HVSDeliveryClosure(**d)


def _summary_from_dict(d: dict[str, Any]) -> HVSRevenueReadyAuditSummary:
    return HVSRevenueReadyAuditSummary(**d)


def _audit_correlation(ctx: _Context) -> dict[str, Any]:
    return {
        "package_id": ctx.manifest.package_id,
        "approval_request_id": ctx.manifest.approval_request_id,
        "packet_id": ctx.manifest.packet_id,
        "delivery_record_id": ctx.delivery_record.delivery_record_id,
        "artifact_sha256": ctx.artifact_sha256,
    }


def _closure_audit_path(repo_root: Path) -> Path:
    return _runtime_root(repo_root) / "delivery_closure_audit.jsonl"


def _append_integrity_failure(repo_root: Path, manifest: Any, record: Any, detail: str) -> None:
    append_closure_event(
        audit_log_path=_closure_audit_path(repo_root),
        event_type=EVT_INTEGRITY_REVALIDATION_FAILED,
        package_id=getattr(manifest, "package_id", ""),
        delivery_record_id=getattr(record, "delivery_record_id", ""),
        project_id=getattr(manifest, "source_project_id", None),
        artifact_sha256=getattr(record, "artifact_sha256", ""),
        resulting_status=detail[:80],
        operator_id="system",
        recorded_at="integrity-check",
    )


def _receipt_event(status: str) -> str:
    return {
        REC_ACKNOWLEDGED: EVT_CUSTOMER_RECEIPT_ACKNOWLEDGED,
        REC_REVISION_REQUESTED: EVT_CUSTOMER_REVISION_REQUESTED,
        REC_DELIVERY_REJECTED: EVT_CUSTOMER_DELIVERY_REJECTED,
        REC_UNCONFIRMED: EVT_CUSTOMER_RECEIPT_UNCONFIRMED,
    }[status]


def _closure_event(status: str) -> str:
    return {
        CLOSURE_ACCEPTED: EVT_DELIVERY_ACCEPTED_AND_CLOSED,
        CLOSURE_REVISION_OPEN: EVT_DELIVERY_REVISION_OPEN,
        CLOSURE_REJECTED: EVT_DELIVERY_REJECTED_AND_CLOSED,
        CLOSURE_WITHOUT_CONFIRMATION: EVT_DELIVERY_CLOSED_WITHOUT_CONFIRMATION,
        CLOSURE_CANCELLED: EVT_DELIVERY_CLOSURE_REJECTED,
    }[status]


def _next_after_receipt(status: str) -> str:
    return {
        REC_ACKNOWLEDGED: "close_delivery_accept_or_review",
        REC_REVISION_REQUESTED: "open_manual_revision_request",
        REC_DELIVERY_REJECTED: "close_delivery_rejected_or_review",
        REC_UNCONFIRMED: "manual_follow_up_or_close_without_confirmation",
    }[status]


def _next_after_closure(status: str) -> str:
    return {
        CLOSURE_ACCEPTED: "manual_invoice_review",
        CLOSURE_REVISION_OPEN: "resolve_open_revision_manually",
        CLOSURE_REJECTED: "review_rejection_manually",
        CLOSURE_WITHOUT_CONFIRMATION: "manual_follow_up_required",
        CLOSURE_CANCELLED: "operator_review_required",
    }[status]
