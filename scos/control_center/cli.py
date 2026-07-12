"""SCOS <-> Hermes Video Studio (HVS) — Stage 3 Evidence CLI.

Local-only, deterministic ``argparse`` front-end over
``scos.control_center.hvs_evidence_intake.intake_hvs_render_evidence``.
It emits a structured JSON decision packet and returns:

* exit 0  — only for a VERIFIED export-ready packet
* exit 1  — invalid / failed / untrusted evidence
* exit 2  — argparse usage error

It does NOT auto-trigger any downstream command, does NOT write
evidence, and does NOT import or invoke HVS.

Entry point::

    python -m scos.control_center.cli inspect-hvs-render-evidence \
        --evidence-path <path> [--no-verify-artifact]

Boundary: the intake module is imported lazily; this file only
knows the explicit command surface.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

COMMNAD_NAME = "inspect-hvs-render-evidence"
CLI_SCHEMA_VERSION = 1

# Exit codes (stable, machine-readable).
EXIT_OK = 0
EXIT_REJECT = 1
EXIT_USAGE = 2


class _CliError(Exception):
    """Expected, deterministic failure. Rendered as failure JSON, exit 1."""

    def __init__(
        self,
        error_kind: str,
        error_detail: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_detail)
        self.error_kind = error_kind
        self.error_detail = error_detail
        self.metadata = dict(metadata or {})


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False))


def _reject_url(*paths: Any) -> None:
    for path in paths:
        if path is None:
            continue
        text = str(path)
        if text.startswith("http://") or text.startswith("https://"):
            raise _CliError(
                "INVALID_ARGUMENTS",
                "paths must be local filesystem paths, not URLs",
                {"path": text},
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scos.control_center.cli",
        description="SCOS Stage 3 HVS render-evidence intake CLI "
        "(local-only, deterministic).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        COMMNAD_NAME,
        help="Ingest an HVS Stage 6 render-validation evidence file "
        "and emit a deterministic operator decision packet.",
    )
    p.add_argument("--evidence-path", required=True)
    p.add_argument(
        "--no-verify-artifact",
        action="store_true",
        help="Do NOT re-check the artifact's SHA-256 against the evidence "
        "(degrades trust to PARTIAL; never falsely VERIFIED).",
    )
    p.set_defaults(func=_cmd_inspect)

    # --- Stage 5: operator delivery approval handoff -------------------------
    a = sub.add_parser(
        "create-hvs-delivery-approval",
        help="Create a PENDING delivery-approval request from a VERIFIED "
        "HVS render-evidence packet.",
    )
    a.add_argument("--evidence-path", required=True)
    a.set_defaults(func=_cmd_create_approval)

    i = sub.add_parser(
        "inspect-hvs-delivery-approval",
        help="Inspect the current state of an approval request by id.",
    )
    i.add_argument("--approval-id", required=True)
    i.set_defaults(func=_cmd_inspect_approval)

    d = sub.add_parser(
        "decide-hvs-delivery-approval",
        help="Approve or reject a PENDING delivery-approval request "
        "(operator-controlled; manual delivery only).",
    )
    d.add_argument("--approval-id", required=True)
    d.add_argument(
        "--decision",
        required=True,
        choices=["approve", "reject"],
        help="approve = APPROVED_FOR_MANUAL_DELIVERY; "
        "reject = REJECTED_FOR_MANUAL_DELIVERY",
    )
    d.add_argument("--operator-id", required=True)
    d.add_argument("--note", default=None)
    d.add_argument(
        "--reason",
        default=None,
        help="required when --decision reject",
    )
    d.add_argument(
        "--decided-at",
        default=None,
        help="informational ISO timestamp (not used in deterministic ids); "
        "defaults to current UTC time",
    )
    d.set_defaults(func=_cmd_decide_approval)

    # --- Stage 6: local delivery package preparation + manual delivery -------
    p6 = sub.add_parser(
        "prepare-hvs-delivery-package",
        help="Prepare a deterministic local delivery package from an "
        "APPROVED_FOR_MANUAL_DELIVERY approval (no media copied).",
    )
    p6.add_argument("--approval-id", required=True)
    p6.add_argument("--operator-id", required=True)
    p6.add_argument(
        "--recorded-at",
        default=None,
        help="informational ISO timestamp (not used in deterministic ids); "
        "defaults to current UTC time",
    )
    p6.set_defaults(func=_cmd_prepare_package)

    m6 = sub.add_parser(
        "materialize-hvs-delivery-package",
        help="Explicitly copy the approved artifact into the local package "
        "(operator-authorized; source never modified).",
    )
    m6.add_argument("--package-id", required=True)
    m6.add_argument("--operator-id", required=True)
    m6.add_argument("--recorded-at", default=None)
    m6.set_defaults(func=_cmd_materialize_package)

    i6 = sub.add_parser(
        "inspect-hvs-delivery-package",
        help="Inspect a prepared/materialized local delivery package.",
    )
    i6.add_argument("--package-id", required=True)
    i6.set_defaults(func=_cmd_inspect_package)

    r6 = sub.add_parser(
        "record-hvs-manual-delivery",
        help="Record a human-performed manual delivery (or failure/cancel). "
        "SCOS performs no external action.",
    )
    r6.add_argument("--package-id", required=True)
    r6.add_argument(
        "--status",
        required=True,
        choices=["delivered", "failed", "cancelled"],
        help="delivered = DELIVERED_MANUALLY; failed = DELIVERY_FAILED; "
        "cancelled = DELIVERY_CANCELLED",
    )
    r6.add_argument("--operator-id", required=True)
    r6.add_argument(
        "--channel",
        default=None,
        help="required for delivered; one of the bounded manual channels",
    )
    r6.add_argument("--recipient-label", default=None)
    r6.add_argument("--external-reference", default=None)
    r6.add_argument("--note", default=None)
    r6.add_argument(
        "--reason",
        default=None,
        help="required for failed/cancelled",
    )
    r6.add_argument("--recorded-at", default=None)
    r6.set_defaults(func=_cmd_record_delivery)

    # --- Stage 7: customer receipt, closure, and revenue audit ---------------
    rec7 = sub.add_parser(
        "record-hvs-customer-receipt",
        help="Record operator-observed customer receipt evidence; SCOS performs no customer contact.",
    )
    rec7.add_argument("--delivery-record-id", required=True)
    rec7.add_argument(
        "--status",
        required=True,
        choices=["acknowledged", "revision-requested", "rejected", "unconfirmed"],
    )
    rec7.add_argument("--source-type", required=True)
    rec7.add_argument("--operator-id", required=True)
    rec7.add_argument("--customer-reference", required=True)
    rec7.add_argument("--statement-summary", required=True)
    rec7.add_argument("--revision-summary", default=None)
    rec7.add_argument("--rejection-reason", default=None)
    rec7.add_argument("--external-reference", default=None)
    rec7.add_argument("--operator-note", default=None)
    rec7.add_argument("--recorded-at", default=None)
    rec7.set_defaults(func=_cmd_record_customer_receipt)

    insp_rec7 = sub.add_parser(
        "inspect-hvs-customer-receipt",
        help="Inspect Stage 7 customer receipt evidence by id.",
    )
    insp_rec7.add_argument("--receipt-evidence-id", required=True)
    insp_rec7.set_defaults(func=_cmd_inspect_customer_receipt)

    rev7 = sub.add_parser(
        "open-hvs-delivery-revision",
        help="Open a manual revision request from revision-requested receipt evidence.",
    )
    rev7.add_argument("--receipt-evidence-id", required=True)
    rev7.add_argument("--operator-id", required=True)
    rev7.add_argument("--revision-summary", required=True)
    rev7.add_argument("--change-category", required=True, action="append")
    rev7.add_argument("--priority", default="normal")
    rev7.add_argument("--due-date", default=None)
    rev7.add_argument("--recorded-at", default=None)
    rev7.set_defaults(func=_cmd_open_delivery_revision)

    close7 = sub.add_parser(
        "close-hvs-delivery",
        help="Close a delivered HVS package from Stage 7 receipt evidence.",
    )
    close7.add_argument("--receipt-evidence-id", required=True)
    close7.add_argument("--operator-id", required=True)
    close7.add_argument(
        "--decision",
        required=True,
        choices=["accept", "revision_open", "reject", "close_without_confirmation", "cancel"],
    )
    close7.add_argument("--reason", required=True)
    close7.add_argument("--recorded-at", default=None)
    close7.set_defaults(func=_cmd_close_delivery)

    insp_close7 = sub.add_parser(
        "inspect-hvs-delivery-closure",
        help="Inspect Stage 7 delivery closure by id.",
    )
    insp_close7.add_argument("--closure-id", required=True)
    insp_close7.set_defaults(func=_cmd_inspect_delivery_closure)

    revsum7 = sub.add_parser(
        "create-hvs-revenue-audit-summary",
        help="Create local revenue-ready audit summary for manual invoice review.",
    )
    revsum7.add_argument("--closure-id", required=True)
    revsum7.add_argument("--operator-id", required=True)
    revsum7.add_argument("--commercial-reference", required=True)
    revsum7.add_argument("--amount-minor", type=int, default=None)
    revsum7.add_argument("--currency", default=None)
    revsum7.add_argument("--recorded-at", default=None)
    revsum7.set_defaults(func=_cmd_create_revenue_audit_summary)

    insp_revsum7 = sub.add_parser(
        "inspect-hvs-revenue-audit-summary",
        help="Inspect Stage 7 revenue audit summary by id.",
    )
    insp_revsum7.add_argument("--summary-id", required=True)
    insp_revsum7.set_defaults(func=_cmd_inspect_revenue_audit_summary)

    # --- Stage 8A: manual invoice preparation and payment follow-up ----------
    inv8 = sub.add_parser(
        "create-hvs-invoice-preparation",
        help="Create a manual invoice preparation record from an accepted delivery closure.",
    )
    inv8.add_argument("--closure-id", required=True)
    inv8.add_argument("--customer-id", required=True)
    inv8.add_argument("--billing-scope-key", default=None)
    inv8.add_argument("--currency", required=True)
    inv8.add_argument("--payment-terms", required=True)
    inv8.add_argument("--operator-id", required=True)
    inv8.add_argument("--line-description", required=True)
    inv8.add_argument("--line-quantity", required=True)
    inv8.add_argument("--line-unit-price", required=True)
    inv8.add_argument("--line-billing-scope-key", default=None)
    inv8.add_argument("--tax-amount", default="0")
    inv8.add_argument("--discount-amount", default="0")
    inv8.add_argument("--recorded-at", default=None)
    inv8.set_defaults(func=_cmd_create_invoice_preparation)

    insp_inv8 = sub.add_parser(
        "inspect-hvs-invoice-preparation",
        help="Inspect a Stage 8A invoice preparation record.",
    )
    insp_inv8.add_argument("--invoice-preparation-id", required=True)
    insp_inv8.set_defaults(func=_cmd_inspect_invoice_preparation)

    ready8 = sub.add_parser(
        "mark-hvs-invoice-ready",
        help="Mark a draft invoice preparation as ready for manual invoice creation.",
    )
    ready8.add_argument("--invoice-preparation-id", required=True)
    ready8.add_argument("--operator-id", required=True)
    ready8.add_argument("--recorded-at", default=None)
    ready8.set_defaults(func=_cmd_mark_invoice_ready)

    sent8 = sub.add_parser(
        "mark-hvs-invoice-sent",
        help="Record that a human operator marked the manual invoice sent.",
    )
    sent8.add_argument("--invoice-preparation-id", required=True)
    sent8.add_argument("--operator-id", required=True)
    sent8.add_argument("--sent-date", required=True)
    sent8.add_argument("--invoice-number", required=True)
    sent8.add_argument("--due-date", default=None)
    sent8.add_argument("--follow-up-date", default=None)
    sent8.add_argument("--recorded-at", default=None)
    sent8.set_defaults(func=_cmd_mark_invoice_sent)

    queue8 = sub.add_parser(
        "list-hvs-payment-follow-ups",
        help="List manual payment follow-up queue items without mutating records.",
    )
    queue8.add_argument("--as-of", required=True)
    queue8.set_defaults(func=_cmd_list_payment_follow_ups)

    pay8 = sub.add_parser(
        "record-hvs-payment-status",
        help="Record an explicit manual payment status decision.",
    )
    pay8.add_argument("--invoice-preparation-id", required=True)
    pay8.add_argument("--decision", required=True, choices=["follow_up_due", "overdue", "dispute", "cancel", "resolve_dispute", "paid"])
    pay8.add_argument("--operator-id", required=True)
    pay8.add_argument("--reason", default=None)
    pay8.add_argument("--resolution-note", default=None)
    pay8.add_argument("--paid-date", default=None)
    pay8.add_argument("--paid-amount", default=None)
    pay8.add_argument("--currency", default=None)
    pay8.add_argument("--payment-reference", default=None)
    pay8.add_argument("--recorded-at", default=None)
    pay8.set_defaults(func=_cmd_record_payment_status)

    insp_pay8 = sub.add_parser(
        "inspect-hvs-payment-status",
        help="Inspect current manual payment status for an invoice preparation.",
    )
    insp_pay8.add_argument("--invoice-preparation-id", required=True)
    insp_pay8.set_defaults(func=_cmd_inspect_payment_status)

    # --- Stage 8A.1: immutable delivery version lineage ---------------------
    lineage_inspect = sub.add_parser(
        "inspect-hvs-delivery-lineage",
        help="Inspect derived HVS delivery-version lineage without mutating delivery records.",
    )
    lineage_inspect.add_argument("--delivery-record-id", required=True)
    lineage_inspect.set_defaults(func=_cmd_inspect_delivery_lineage)

    lineage_register = sub.add_parser(
        "register-hvs-delivery-lineage",
        help="Explicitly register immutable historical delivery lineage; no HVS action occurs.",
    )
    lineage_register.add_argument("--delivery-record-id", required=True)
    lineage_register.add_argument("--delivery-version", required=True)
    lineage_register.add_argument(
        "--registration-basis",
        required=True,
        choices=[
            "original_delivery_confirmed",
            "existing_external_version_record",
            "operator_historical_reconciliation",
            "imported_certified_lineage",
            "successor_of_registered_delivery",
        ],
    )
    lineage_register.add_argument("--operator-id", required=True)
    lineage_register.add_argument("--evidence-reference", default=None)
    lineage_register.add_argument("--registration-reason", default=None)
    lineage_register.add_argument("--parent-lineage-id", default=None)
    lineage_register.add_argument("--confirm-legacy-version", action="store_true")
    lineage_register.add_argument("--recorded-at", default=None)
    lineage_register.set_defaults(func=_cmd_register_delivery_lineage)

    lineage_plan = sub.add_parser(
        "plan-hvs-successor-version",
        help="Derive a successor delivery version without persistence, revision, render, or HVS action.",
    )
    lineage_plan.add_argument("--delivery-record-id", required=True)
    lineage_plan.set_defaults(func=_cmd_plan_hvs_successor_version)

    lineage_list = sub.add_parser(
        "list-hvs-delivery-lineage",
        help="List registered immutable delivery lineage for one project.",
    )
    lineage_list.add_argument("--project-id", required=True)
    lineage_list.set_defaults(func=_cmd_list_delivery_lineage)

    revision_create = sub.add_parser("create-hvs-revision-request", help="Create a local revision request from registered delivery lineage.")
    revision_create.add_argument("--delivery-record-id", required=True); revision_create.add_argument("--requested-by-id", required=True); revision_create.add_argument("--operator-id", required=True)
    revision_create.add_argument("--item-category", required=True); revision_create.add_argument("--item-description", required=True); revision_create.add_argument("--target-type", required=True); revision_create.add_argument("--target-id", required=True); revision_create.add_argument("--acceptance-requirement", required=True); revision_create.add_argument("--scene-id", default=None); revision_create.add_argument("--asset-id", default=None); revision_create.add_argument("--format", default=None); revision_create.add_argument("--recorded-at", default=None); revision_create.set_defaults(func=_cmd_create_revision_request)
    for command, handler, argument in (("start-hvs-revision-review", _cmd_start_revision_review, None), ("assess-hvs-revision-impact", _cmd_assess_revision_impact, None), ("prepare-hvs-revision-plan", _cmd_prepare_revision_plan, None), ("create-hvs-revision-approval", _cmd_create_revision_approval, None), ("create-hvs-rerender-authorization", _cmd_create_rerender_authorization, None)):
        item = sub.add_parser(command); item.add_argument("--revision-request-id", required=True); item.add_argument("--operator-id", required=True); item.add_argument("--recorded-at", default=None); item.set_defaults(func=handler)
    commercial = sub.add_parser("classify-hvs-revision-commercial"); commercial.add_argument("--revision-request-id", required=True); commercial.add_argument("--classification", required=True); commercial.add_argument("--basis", required=True); commercial.add_argument("--operator-id", required=True); commercial.add_argument("--amount", default=None); commercial.add_argument("--currency", default=None); commercial.add_argument("--tax", default=None); commercial.add_argument("--discount", default=None); commercial.add_argument("--recorded-at", default=None); commercial.set_defaults(func=_cmd_classify_revision_commercial)
    decision = sub.add_parser("decide-hvs-revision-approval"); decision.add_argument("--revision-request-id", required=True); decision.add_argument("--decision", required=True, choices=["APPROVE_RERENDER_PLAN", "REJECT_RERENDER_PLAN"]); decision.add_argument("--operator-id", required=True); decision.add_argument("--reason", default=None); decision.add_argument("--recorded-at", default=None); decision.set_defaults(func=_cmd_decide_revision_approval)

    # --- Stage 8C: approval-gated revision re-render dispatch -----------------
    dispatch = sub.add_parser(
        "request-hvs-rerender-dispatch",
        help="Convert an APPROVED Stage 8B revision into an immutable, "
        "lineage-preserving re-render dispatch request (manual HVS handoff; no HVS invocation).",
    )
    dispatch.add_argument("--revision-request-id", required=True)
    dispatch.add_argument("--operator-id", required=True)
    dispatch.add_argument(
        "--target-format",
        required=True,
        action="append",
        dest="target_formats",
        choices=["vertical", "square", "horizontal", "captions", "thumbnail", "raw_master"],
        help="requested delivery variant; repeatable; bounded to allowed formats",
    )
    dispatch.add_argument(
        "--change-category",
        action="append",
        dest="change_categories",
        default=[],
        choices=[
            "TEXT_CHANGE", "CAPTION_CHANGE", "TIMING_CHANGE", "ASSET_REPLACEMENT",
            "AUDIO_CHANGE", "MUSIC_CHANGE", "VOICE_CHANGE", "LAYOUT_CHANGE",
            "BRANDING_CHANGE", "FORMAT_CHANGE", "DURATION_CHANGE",
            "COMPLIANCE_CHANGE", "TECHNICAL_CORRECTION",
        ],
        help="optional bounded requested-change category; repeatable",
    )
    dispatch.add_argument("--change-description", default=None)
    dispatch.add_argument("--reason", required=True)
    dispatch.add_argument("--requested-by", default=None)
    dispatch.add_argument("--approved-by", default=None)
    dispatch.add_argument("--recorded-at", default=None)
    dispatch.set_defaults(func=_cmd_request_rerender_dispatch)

    inspect_dispatch = sub.add_parser(
        "inspect-hvs-rerender-dispatch",
        help="Inspect a Stage 8C re-render dispatch request by id (no mutation).",
    )
    inspect_dispatch.add_argument("--dispatch-id", required=True)
    inspect_dispatch.set_defaults(func=_cmd_inspect_rerender_dispatch)

    # --- Stage 8D: re-render result reconciliation -------------------------
    recon = sub.add_parser(
        "reconcile-hvs-rerender-result",
        help="Reconcile a Stage 8C re-render result into SCOS delivery + revision "
        "lineage (no HVS invocation; manual HVS handoff boundary).\n\n"
        "INPUT is a JSON file path containing the re-render result evidence "
        "contract. The result must bind the same dispatch, revision, delivery, "
        "project, and correlation lineage as the approved Stage 8C dispatch.",
    )
    recon.add_argument("--result-path", required=True, help="path to the re-render result JSON evidence file")
    recon.add_argument("--operator-id", required=True)
    recon.add_argument(
        "--new-delivery-record-id",
        default=None,
        help="identifier of the new delivery record produced by the re-render; "
        "required to register the revised delivery version",
    )
    recon.add_argument("--recorded-at", default=None)
    recon.set_defaults(func=_cmd_reconcile_rerender_result)

    recon_inspect = sub.add_parser(
        "inspect-hvs-rerender-reconciliation",
        help="Inspect a Stage 8D reconciliation by id (no mutation).",
    )
    recon_inspect.add_argument("--reconciliation-id", required=True)
    recon_inspect.set_defaults(func=_cmd_inspect_rerender_reconciliation)

    recon_rev = sub.add_parser(
        "list-hvs-revised-delivery-lineage",
        help="List the revised-delivery lineage for a project (read-only).",
    )
    recon_rev.add_argument("--project-id", required=True)
    recon_rev.set_defaults(func=_cmd_list_revised_delivery_lineage)

    recon_sup = sub.add_parser(
        "list-hvs-supersession-lineage",
        help="List all append-only supersession evidence (read-only).",
    )
    recon_sup.set_defaults(func=_cmd_list_supersession_lineage)
    return parser


def _repo_root() -> Path:
    # cli.py lives at <repo>/scos/control_center/cli.py
    return Path(__file__).resolve().parents[2]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _cmd_inspect(args: argparse.Namespace) -> int:
    command = COMMNAD_NAME
    _reject_url(args.evidence_path)
    from .hvs_evidence_intake import intake_hvs_render_evidence

    verify_artifact = not args.no_verify_artifact
    result = intake_hvs_render_evidence(
        evidence_path=args.evidence_path,
        verify_artifact=verify_artifact,
    )
    _emit(result.to_dict())
    # exit 0 ONLY for a verified export-ready packet.
    if result.ok and result.trust_level == "VERIFIED":
        return EXIT_OK
    return EXIT_REJECT


def _cmd_create_approval(args: argparse.Namespace) -> int:
    command = "create-hvs-delivery-approval"
    _reject_url(args.evidence_path)
    from .hvs_delivery_approval import (
        HVSDeliveryApprovalRequest,
        create_approval_request,
    )
    from .hvs_evidence_intake import intake_hvs_render_evidence

    packet = intake_hvs_render_evidence(
        evidence_path=args.evidence_path, verify_artifact=True
    )
    outcome = create_approval_request(
        packet=packet.to_dict(), repo_root=_repo_root()
    )
    _emit(outcome.to_dict())
    if isinstance(outcome, HVSDeliveryApprovalRequest):
        return EXIT_OK
    # Ineligible packet (unverified / not ready / already decided) -> reject.
    return EXIT_REJECT


def _cmd_inspect_approval(args: argparse.Namespace) -> int:
    command = "inspect-hvs-delivery-approval"
    from .hvs_delivery_approval import get_approval_request

    outcome = get_approval_request(
        approval_id=args.approval_id, repo_root=_repo_root()
    )
    _emit(outcome.to_dict())
    return EXIT_OK


def _cmd_decide_approval(args: argparse.Namespace) -> int:
    command = "decide-hvs-delivery-approval"
    from .hvs_delivery_approval import decide_approval

    decided_at = args.decided_at or _now_iso()
    outcome = decide_approval(
        approval_id=args.approval_id,
        decision=args.decision,
        operator_id=args.operator_id,
        decided_at=decided_at,
        reason=getattr(args, "reason", None),
        note=getattr(args, "note", None),
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_prepare_package(args: argparse.Namespace) -> int:
    command = "prepare-hvs-delivery-package"
    from .hvs_local_delivery_service import prepare_delivery_package

    recorded_at = args.recorded_at or _now_iso()
    outcome = prepare_delivery_package(
        approval_id=args.approval_id,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=recorded_at,
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_materialize_package(args: argparse.Namespace) -> int:
    command = "materialize-hvs-delivery-package"
    from .hvs_local_delivery_service import materialize_delivery_package

    recorded_at = args.recorded_at or _now_iso()
    outcome = materialize_delivery_package(
        package_id=args.package_id,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=recorded_at,
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_package(args: argparse.Namespace) -> int:
    command = "inspect-hvs-delivery-package"
    from .hvs_local_delivery_service import inspect_delivery_package

    outcome = inspect_delivery_package(
        package_id=args.package_id, repo_root=_repo_root()
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_record_delivery(args: argparse.Namespace) -> int:
    command = "record-hvs-manual-delivery"
    from .hvs_local_delivery_models import (
        DEL_DELIVERED_MANUALLY,
        DEL_DELIVERY_CANCELLED,
        DEL_DELIVERY_FAILED,
    )
    from .hvs_local_delivery_service import record_manual_delivery

    status_map = {
        "delivered": DEL_DELIVERED_MANUALLY,
        "failed": DEL_DELIVERY_FAILED,
        "cancelled": DEL_DELIVERY_CANCELLED,
    }
    recorded_at = args.recorded_at or _now_iso()
    outcome = record_manual_delivery(
        package_id=args.package_id,
        status=status_map[args.status],
        operator_id=args.operator_id,
        channel=getattr(args, "channel", None),
        recipient_label=getattr(args, "recipient_label", None),
        external_reference=getattr(args, "external_reference", None),
        operator_note=getattr(args, "note", None),
        reason=getattr(args, "reason", None),
        repo_root=_repo_root(),
        recorded_at=recorded_at,
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_record_customer_receipt(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import record_customer_receipt_evidence

    outcome = record_customer_receipt_evidence(
        delivery_record_id=args.delivery_record_id,
        repo_root=_repo_root(),
        status=args.status,
        source_type=args.source_type,
        operator_id=args.operator_id,
        customer_reference=args.customer_reference,
        statement_summary=args.statement_summary,
        revision_summary=args.revision_summary,
        rejection_reason=args.rejection_reason,
        external_reference=args.external_reference,
        operator_note=args.operator_note,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_customer_receipt(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import get_receipt_evidence

    outcome = get_receipt_evidence(
        receipt_evidence_id=args.receipt_evidence_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_open_delivery_revision(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import open_revision_request

    outcome = open_revision_request(
        receipt_evidence_id=args.receipt_evidence_id,
        repo_root=_repo_root(),
        operator_id=args.operator_id,
        revision_summary=args.revision_summary,
        change_categories=args.change_category,
        priority=args.priority,
        due_date=args.due_date,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_close_delivery(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import close_delivery

    outcome = close_delivery(
        receipt_evidence_id=args.receipt_evidence_id,
        repo_root=_repo_root(),
        operator_id=args.operator_id,
        decision=args.decision,
        reason=args.reason,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_delivery_closure(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import get_closure

    outcome = get_closure(closure_id=args.closure_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_create_revenue_audit_summary(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import create_revenue_audit_summary

    outcome = create_revenue_audit_summary(
        closure_id=args.closure_id,
        repo_root=_repo_root(),
        operator_id=args.operator_id,
        commercial_reference=args.commercial_reference,
        agreed_amount_minor=args.amount_minor,
        currency=args.currency,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_revenue_audit_summary(args: argparse.Namespace) -> int:
    from .hvs_delivery_closure_service import get_revenue_audit_summary

    outcome = get_revenue_audit_summary(
        summary_id=args.summary_id, repo_root=_repo_root()
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_create_invoice_preparation(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import create_invoice_preparation

    line_scope = args.line_billing_scope_key or args.billing_scope_key or "default"
    outcome = create_invoice_preparation(
        delivery_closure_id=args.closure_id,
        repo_root=_repo_root(),
        customer_id=args.customer_id,
        billing_scope_key=args.billing_scope_key,
        currency=args.currency,
        payment_terms=args.payment_terms,
        operator_id=args.operator_id,
        line_items=[
            {
                "description": args.line_description,
                "quantity": args.line_quantity,
                "unit_price": args.line_unit_price,
                "billing_scope_key": line_scope,
            }
        ],
        tax_amount=args.tax_amount,
        discount_amount=args.discount_amount,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_invoice_preparation(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import inspect_invoice_preparation

    outcome = inspect_invoice_preparation(
        invoice_preparation_id=args.invoice_preparation_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_mark_invoice_ready(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import mark_invoice_ready

    outcome = mark_invoice_ready(
        invoice_preparation_id=args.invoice_preparation_id,
        repo_root=_repo_root(),
        operator_id=args.operator_id,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_mark_invoice_sent(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import mark_invoice_sent

    outcome = mark_invoice_sent(
        invoice_preparation_id=args.invoice_preparation_id,
        repo_root=_repo_root(),
        operator_id=args.operator_id,
        sent_date=args.sent_date,
        invoice_number=args.invoice_number,
        due_date=args.due_date,
        follow_up_date=args.follow_up_date,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_list_payment_follow_ups(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import list_payment_follow_up_queue

    outcome = list_payment_follow_up_queue(repo_root=_repo_root(), as_of=args.as_of)
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_record_payment_status(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import record_payment_status_decision

    outcome = record_payment_status_decision(
        invoice_preparation_id=args.invoice_preparation_id,
        repo_root=_repo_root(),
        decision=args.decision,
        operator_id=args.operator_id,
        reason=args.reason,
        resolution_note=args.resolution_note,
        paid_date=args.paid_date,
        paid_amount=args.paid_amount,
        currency=args.currency,
        payment_reference=args.payment_reference,
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_payment_status(args: argparse.Namespace) -> int:
    from .hvs_invoice_service import inspect_payment_status

    outcome = inspect_payment_status(
        invoice_preparation_id=args.invoice_preparation_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_delivery_lineage(args: argparse.Namespace) -> int:
    from .hvs_delivery_lineage_service import inspect_delivery_lineage

    outcome = inspect_delivery_lineage(
        delivery_record_id=args.delivery_record_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_register_delivery_lineage(args: argparse.Namespace) -> int:
    from .hvs_delivery_lineage_models import DeliveryLineageRegistrationRequest, DeliveryVersion
    from .hvs_delivery_lineage_service import register_delivery_lineage

    try:
        version = DeliveryVersion.parse(args.delivery_version)
    except ValueError as exc:
        raise _CliError("INVALID_DELIVERY_VERSION", str(exc)) from exc
    basis = args.registration_basis.upper()
    outcome = register_delivery_lineage(
        request=DeliveryLineageRegistrationRequest(
            delivery_record_id=args.delivery_record_id,
            delivery_version=version,
            operator_id=args.operator_id,
            registration_basis=basis,
            confirm_legacy_version=args.confirm_legacy_version,
            evidence_reference=args.evidence_reference,
            registration_reason=args.registration_reason,
            parent_lineage_id=args.parent_lineage_id,
        ),
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_plan_hvs_successor_version(args: argparse.Namespace) -> int:
    from .hvs_delivery_lineage_service import plan_successor_version

    outcome = plan_successor_version(
        delivery_record_id=args.delivery_record_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_list_delivery_lineage(args: argparse.Namespace) -> int:
    from .hvs_delivery_lineage_service import list_project_delivery_lineage

    outcome = list_project_delivery_lineage(project_id=args.project_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _revision_result(call, args: argparse.Namespace) -> int:
    outcome = call(recorded_at=args.recorded_at or _now_iso())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_create_revision_request(args: argparse.Namespace) -> int:
    from .hvs_delivery_lineage_service import inspect_delivery_lineage
    from .hvs_revision_models import RevisionItem
    from .hvs_revision_service import create_revision_request
    lineage = inspect_delivery_lineage(delivery_record_id=args.delivery_record_id, repo_root=_repo_root())
    if not lineage.ok or not lineage.lineage:
        _emit(lineage.to_dict()); return EXIT_REJECT
    item = RevisionItem.create(category=args.item_category, description=args.item_description, target_type=args.target_type, target_id=args.target_id, scene_id=args.scene_id, asset_id=args.asset_id, format=args.format, priority="normal", acceptance_requirement=args.acceptance_requirement, requested_by_id=args.requested_by_id, source_artifact_sha256=lineage.lineage.artifact_sha256)
    return _revision_result(lambda **kw: create_revision_request(delivery_record_id=args.delivery_record_id, requested_by_id=args.requested_by_id, operator_id=args.operator_id, revision_items=(item,), repo_root=_repo_root(), **kw), args)


def _cmd_start_revision_review(args: argparse.Namespace) -> int:
    from .hvs_revision_service import start_revision_review
    return _revision_result(lambda **kw: start_revision_review(revision_request_id=args.revision_request_id, operator_id=args.operator_id, repo_root=_repo_root(), **kw), args)
def _cmd_assess_revision_impact(args: argparse.Namespace) -> int:
    from .hvs_revision_service import assess_revision_impact
    return _revision_result(lambda **kw: assess_revision_impact(revision_request_id=args.revision_request_id, operator_id=args.operator_id, repo_root=_repo_root(), **kw), args)
def _cmd_classify_revision_commercial(args: argparse.Namespace) -> int:
    from .hvs_revision_service import classify_revision_commercial
    return _revision_result(lambda **kw: classify_revision_commercial(revision_request_id=args.revision_request_id, classification=args.classification, operator_id=args.operator_id, basis=args.basis, amount=args.amount, currency=args.currency, tax=args.tax, discount=args.discount, repo_root=_repo_root(), **kw), args)
def _cmd_prepare_revision_plan(args: argparse.Namespace) -> int:
    from .hvs_revision_service import prepare_revision_plan
    return _revision_result(lambda **kw: prepare_revision_plan(revision_request_id=args.revision_request_id, operator_id=args.operator_id, repo_root=_repo_root(), **kw), args)
def _cmd_create_revision_approval(args: argparse.Namespace) -> int:
    from .hvs_revision_service import create_revision_approval_request
    return _revision_result(lambda **kw: create_revision_approval_request(revision_request_id=args.revision_request_id, operator_id=args.operator_id, repo_root=_repo_root(), **kw), args)
def _cmd_decide_revision_approval(args: argparse.Namespace) -> int:
    from .hvs_revision_service import decide_revision_approval
    return _revision_result(lambda **kw: decide_revision_approval(revision_request_id=args.revision_request_id, decision=args.decision, operator_id=args.operator_id, reason=args.reason, repo_root=_repo_root(), **kw), args)
def _cmd_create_rerender_authorization(args: argparse.Namespace) -> int:
    from .hvs_revision_service import create_rerender_authorization
    return _revision_result(lambda **kw: create_rerender_authorization(revision_request_id=args.revision_request_id, operator_id=args.operator_id, repo_root=_repo_root(), **kw), args)


def _cmd_request_rerender_dispatch(args: argparse.Namespace) -> int:
    from .hvs_rerender_dispatch_models import RequestedChange
    from .hvs_rerender_dispatch_service import request_rerender_dispatch

    changes = ()
    if getattr(args, "change_categories", None):
        description = args.change_description or "Operator-requested revision change."
        changes = tuple(
            RequestedChange(
                category=cat,
                description=description,
                target_format=None,
                target_id=None,
            )
            for cat in args.change_categories
        )
    outcome = request_rerender_dispatch(
        revision_request_id=args.revision_request_id,
        operator_id=args.operator_id,
        target_formats=tuple(args.target_formats),
        requested_changes=changes,
        reason=args.reason,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
        requested_by=getattr(args, "requested_by", None),
        approved_by=getattr(args, "approved_by", None),
    )
    _emit(outcome.to_dict())
    if outcome.ok:
        return EXIT_OK
    # Rejections (policy / validation) and not-found both surface as exit 1.
    return EXIT_REJECT


def _cmd_inspect_rerender_dispatch(args: argparse.Namespace) -> int:
    from .hvs_rerender_dispatch_service import inspect_rerender_dispatch

    outcome = inspect_rerender_dispatch(dispatch_id=args.dispatch_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_reconcile_rerender_result(args: argparse.Namespace) -> int:
    from .hvs_rerender_result_models import RerenderResult
    from .hvs_rerender_result_reconciliation_service import reconcile_rerender_result

    _reject_url(args.result_path)
    path = Path(args.result_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        _emit({"ok": False, "error_kind": "INVALID_ARGUMENTS", "error_detail": "unsafe result path"})
        return EXIT_REJECT
    if not path.is_file():
        _emit({"ok": False, "error_kind": "INVALID_ARGUMENTS", "error_detail": "result file not found"})
        return EXIT_REJECT
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = RerenderResult(**payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error_kind": "INVALID_RESULT_PAYLOAD", "error_detail": str(exc)})
        return EXIT_REJECT
    outcome = reconcile_rerender_result(
        result=result,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
        new_delivery_record_id=getattr(args, "new_delivery_record_id", None),
    )
    _emit(outcome.to_dict())
    if outcome.ok:
        return EXIT_OK
    # Validation/policy/lint rejections surface as exit 1.
    return EXIT_REJECT


def _cmd_inspect_rerender_reconciliation(args: argparse.Namespace) -> int:
    from .hvs_rerender_result_reconciliation_service import inspect_reconciliation

    outcome = inspect_reconciliation(reconciliation_id=args.reconciliation_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_list_revised_delivery_lineage(args: argparse.Namespace) -> int:
    from .hvs_rerender_result_reconciliation_service import list_revised_delivery_lineage

    records = list_revised_delivery_lineage(project_id=args.project_id, repo_root=_repo_root())
    _emit({
        "ok": True,
        "project_id": args.project_id,
        "count": len(records),
        "revised_deliveries": [r.to_dict() for r in records],
    })
    return EXIT_OK


def _cmd_list_supersession_lineage(args: argparse.Namespace) -> int:
    from .hvs_rerender_result_reconciliation_service import list_supersession_lineage

    records = list_supersession_lineage(repo_root=_repo_root())
    _emit({
        "ok": True,
        "count": len(records),
        "supersessions": [r.to_dict() for r in records],
    })
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    import argparse as _argparse

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)  # argparse errors raise ArgumentError / SystemExit(2)
    except (_argparse.ArgumentError, SystemExit) as exc:
        detail = str(exc) if not isinstance(exc, SystemExit) else "invalid command or arguments"
        _emit({
            "ok": False,
            "command": None,
            "schema_version": CLI_SCHEMA_VERSION,
            "error_kind": "INVALID_COMMAND",
            "error_detail": detail,
        })
        return EXIT_USAGE
    func = getattr(args, "func", None)
    if func is None:
        _emit({
            "ok": False,
            "command": getattr(args, "command", None),
            "schema_version": CLI_SCHEMA_VERSION,
            "error_kind": "INVALID_COMMAND",
            "error_detail": "unknown or unsupported command",
        })
        return EXIT_REJECT
    try:
        return func(args)
    except _CliError as exc:
        _emit({
            "ok": False,
            "command": getattr(args, "command", None),
            "schema_version": CLI_SCHEMA_VERSION,
            "error_kind": exc.error_kind,
            "error_detail": exc.error_detail,
            "metadata": exc.metadata,
        })
        return EXIT_REJECT


if __name__ == "__main__":
    sys.exit(main())
