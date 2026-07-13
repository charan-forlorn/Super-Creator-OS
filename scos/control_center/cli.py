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

    # --- Stage 8E: revised-delivery acceptance, release authorization, and
    #     final revision closure (evidence only; no HVS / outbound transport) --
    acc8e = sub.add_parser(
        "record-revised-delivery-acceptance",
        help="Record internal acceptance of a Stage 8D revised delivery "
        "(evidence only; no customer contact).",
    )
    acc8e.add_argument("--reconciliation-result-id", required=True)
    acc8e.add_argument("--revised-delivery-id", required=True)
    acc8e.add_argument("--reviewer-id", required=True)
    acc8e.add_argument("--accepted-formats", action="append", dest="accepted_formats", default=[],
                       choices=["vertical", "square", "horizontal", "captions", "thumbnail", "raw_master"])
    acc8e.add_argument("--rejected-formats", action="append", dest="rejected_formats", default=[],
                       choices=["vertical", "square", "horizontal", "captions", "thumbnail", "raw_master"])
    acc8e.add_argument("--quality-gate-reference", required=True)
    acc8e.add_argument("--artifact-integrity-reference", required=True)
    acc8e.add_argument("--acceptance-status", default="ACCEPTED",
                       choices=["ACCEPTED", "PARTIALLY_ACCEPTED", "REJECTED"])
    acc8e.add_argument("--rejection-codes", default=None,
                       help="comma-separated rejection codes (required when status is REJECTED)")
    acc8e.add_argument("--review-notes", default=None)
    acc8e.add_argument("--evidence-references", default=None,
                       help="comma-separated evidence reference tokens")
    acc8e.add_argument("--operator-id", required=True)
    acc8e.add_argument("--recorded-at", default=None)
    acc8e.set_defaults(func=_cmd_record_revised_delivery_acceptance)

    insp_acc8e = sub.add_parser(
        "inspect-revised-delivery-acceptance",
        help="Inspect a Stage 8E acceptance by id (no mutation).",
    )
    insp_acc8e.add_argument("--acceptance-id", required=True)
    insp_acc8e.set_defaults(func=_cmd_inspect_revised_delivery_acceptance)

    auth8e = sub.add_parser(
        "create-customer-release-authorization",
        help="Create explicit customer-release authorization evidence for an "
        "accepted revised delivery (evidence only; no delivery transport).",
    )
    auth8e.add_argument("--acceptance-id", required=True)
    auth8e.add_argument("--authorized-by", required=True)
    auth8e.add_argument("--authorization-scope", action="append", dest="authorization_scope", default=[],
                        choices=["vertical", "square", "horizontal", "captions", "thumbnail", "raw_master"])
    auth8e.add_argument("--approved-formats", action="append", dest="approved_formats", default=[],
                        choices=["vertical", "square", "horizontal", "captions", "thumbnail", "raw_master"])
    auth8e.add_argument("--allowed-delivery-channels", action="append", dest="allowed_delivery_channels", default=[],
                        choices=["in_person", "removable_media", "local_network_manual", "customer_portal_manual",
                                 "cloud_storage_manual", "email_manual", "messaging_manual", "other_manual"])
    auth8e.add_argument("--customer-reference", required=True)
    auth8e.add_argument("--approval-basis", required=True)
    auth8e.add_argument("--policy-version", required=True)
    auth8e.add_argument("--expiry-at", required=True)
    auth8e.add_argument("--evidence-references", default=None,
                        help="comma-separated evidence reference tokens")
    auth8e.add_argument("--operator-id", required=True)
    auth8e.add_argument("--recorded-at", default=None)
    auth8e.set_defaults(func=_cmd_create_customer_release_authorization)

    revoke8e = sub.add_parser(
        "revoke-customer-release-authorization",
        help="Revoke a Stage 8E customer-release authorization (append-only; "
        "the record is preserved).",
    )
    revoke8e.add_argument("--authorization-id", required=True)
    revoke8e.add_argument("--reason", default=None)
    revoke8e.add_argument("--operator-id", required=True)
    revoke8e.add_argument("--recorded-at", default=None)
    revoke8e.set_defaults(func=_cmd_revoke_customer_release_authorization)

    ready8e = sub.add_parser(
        "evaluate-revised-delivery-release-readiness",
        help="Evaluate deterministic release readiness for an acceptance "
        "(fail-closed; no outbound transport).",
    )
    ready8e.add_argument("--acceptance-id", required=True)
    ready8e.add_argument("--authorization-id", default=None)
    ready8e.add_argument("--recorded-at", default=None)
    ready8e.set_defaults(func=_cmd_evaluate_release_readiness)

    close8e = sub.add_parser(
        "close-final-revision",
        help="Close the final revision release gate for an acceptance "
        "(idempotent; conflict-rejected).",
    )
    close8e.add_argument("--acceptance-id", required=True)
    close8e.add_argument("--authorization-id", default=None)
    close8e.add_argument("--operator-id", required=True)
    close8e.add_argument("--recorded-at", default=None)
    close8e.set_defaults(func=_cmd_close_final_revision)

    insp_close8e = sub.add_parser(
        "inspect-final-revision-closure",
        help="Inspect the Stage 8E final revision closure by revision id.",
    )
    insp_close8e.add_argument("--revision-id", required=True)
    insp_close8e.set_defaults(func=_cmd_inspect_final_revision_closure)

    lineage8e = sub.add_parser(
        "inspect-revised-delivery-release-lineage",
        help="Inspect the complete revised-delivery release lineage (read-only).",
    )
    lineage8e.add_argument("--project-id", default=None)
    lineage8e.set_defaults(func=_cmd_inspect_release_lineage)

    # --- Stage 8F: manual release, receipt, post-delivery audit ------------
    rec_rel = sub.add_parser(
        "record-manual-release",
        help="Record that an authorized revised delivery was manually released "
        "(evidence only; no transport executed).",
    )
    rec_rel.add_argument("--authorization-id", required=True)
    rec_rel.add_argument("--released-by", required=True)
    rec_rel.add_argument("--release-channel", required=True)
    rec_rel.add_argument("--released-formats", required=True, help="comma-separated formats")
    rec_rel.add_argument("--customer-reference", required=True)
    rec_rel.add_argument("--release-method-reference", required=True)
    rec_rel.add_argument("--evidence-references", default="", help="comma-separated references")
    rec_rel.add_argument("--operator-id", required=True)
    rec_rel.add_argument("--recorded-at", default=None)
    rec_rel.set_defaults(func=_cmd_record_manual_release)

    ins_rel = sub.add_parser(
        "inspect-manual-release",
        help="Inspect a recorded manual release by authorization id.",
    )
    ins_rel.add_argument("--authorization-id", required=True)
    ins_rel.set_defaults(func=_cmd_inspect_manual_release)

    rec_rcpt = sub.add_parser(
        "record-customer-receipt",
        help="Record that the customer confirmed receipt (evidence only; no "
        "customer contact).",
    )
    rec_rcpt.add_argument("--release-id", required=True)
    rec_rcpt.add_argument("--confirmed-by", required=True)
    rec_rcpt.add_argument("--receipt-status", required=True, help="CONFIRMED|DECLINED|UNREACHABLE")
    rec_rcpt.add_argument("--received-formats", required=True, help="comma-separated formats")
    rec_rcpt.add_argument("--customer-reference", required=True)
    rec_rcpt.add_argument("--confirmation-reference", required=True)
    rec_rcpt.add_argument("--receipt-channel", default=None)
    rec_rcpt.add_argument("--receipt-notes", default=None)
    rec_rcpt.add_argument("--evidence-references", default="", help="comma-separated references")
    rec_rcpt.add_argument("--operator-id", required=True)
    rec_rcpt.add_argument("--recorded-at", default=None)
    rec_rcpt.set_defaults(func=_cmd_record_8f_customer_receipt)

    ins_rcpt = sub.add_parser(
        "inspect-customer-receipt",
        help="Inspect a recorded customer receipt by release id.",
    )
    ins_rcpt.add_argument("--release-id", required=True)
    ins_rcpt.set_defaults(func=_cmd_inspect_8f_customer_receipt)

    eval_audit = sub.add_parser(
        "evaluate-post-delivery-audit",
        help="Evaluate deterministic post-delivery audit readiness "
        "(fail-closed; no outbound transport).",
    )
    eval_audit.add_argument("--authorization-id", required=True)
    eval_audit.add_argument("--operator-id", required=True)
    eval_audit.add_argument("--recorded-at", default=None)
    eval_audit.set_defaults(func=_cmd_evaluate_post_delivery_audit)

    close_audit = sub.add_parser(
        "close-post-delivery-audit",
        help="Close the post-delivery audit (idempotent; conflict-rejected).",
    )
    close_audit.add_argument("--authorization-id", required=True)
    close_audit.add_argument("--operator-id", required=True)
    close_audit.add_argument("--recorded-at", default=None)
    close_audit.set_defaults(func=_cmd_close_post_delivery_audit)

    lineage8f = sub.add_parser(
        "inspect-complete-lineage",
        help="Inspect the complete post-delivery lineage (Stage 8F + 8E + 8D).",
    )
    lineage8f.add_argument("--project-id", default=None)
    lineage8f.set_defaults(func=_cmd_inspect_post_delivery_lineage)

    # --- Stage 8G: post-delivery support, dispute/reopen, commercial closure -
    sp = sub.add_parser("register-support-policy", help="Register a post-delivery support policy (explicit window).")
    sp.add_argument("--authorization-id", required=True)
    sp.add_argument("--support-window-start", required=True)
    sp.add_argument("--support-window-end", required=True)
    sp.add_argument("--policy-type", required=True)
    sp.add_argument("--included-issue-categories", required=True, help="comma-separated")
    sp.add_argument("--excluded-issue-categories", default="")
    sp.add_argument("--revision-allowance-reference", default=None)
    sp.add_argument("--commercial-terms-reference", default=None)
    sp.add_argument("--policy-version", required=True)
    sp.add_argument("--created-by-operator-id", required=True)
    sp.add_argument("--evidence-references", default="")
    sp.add_argument("--operator-id", default=None)
    sp.add_argument("--recorded-at", default=None)
    sp.set_defaults(func=_cmd_register_support_policy)

    isp = sub.add_parser("inspect-support-policy", help="Inspect a support policy by id.")
    isp.add_argument("--support-policy-id", required=True)
    isp.set_defaults(func=_cmd_inspect_support_policy)

    ri = sub.add_parser("record-issue", help="Record a post-delivery customer issue/dispute intake.")
    ri.add_argument("--support-policy-id", required=True)
    ri.add_argument("--issue-category", required=True)
    ri.add_argument("--issue-summary", required=True)
    ri.add_argument("--recorded-by-operator-id", required=True)
    ri.add_argument("--customer-reference", required=True)
    ri.add_argument("--affected-formats", required=True, help="comma-separated")
    ri.add_argument("--reported-at", required=True)
    ri.add_argument("--issue-details", default="")
    ri.add_argument("--affected-artifact-references", default="")
    ri.add_argument("--artifact-sha256", default="")
    ri.add_argument("--requested-resolution", default="")
    ri.add_argument("--evidence-references", default="")
    ri.add_argument("--operator-id", default=None)
    ri.add_argument("--recorded-at", default=None)
    ri.set_defaults(func=_cmd_record_issue)

    ii = sub.add_parser("inspect-issue", help="Inspect an issue by id.")
    ii.add_argument("--issue-id", required=True)
    ii.set_defaults(func=_cmd_inspect_issue)

    ci = sub.add_parser("classify-issue", help="Deterministically classify an issue (fail-closed).")
    ci.add_argument("--issue-id", required=True)
    ci.add_argument("--classified-by-operator-id", required=True)
    ci.add_argument("--operator-id", default=None)
    ci.add_argument("--recorded-at", default=None)
    ci.set_defaults(func=_cmd_classify_issue)

    od = sub.add_parser("open-dispute", help="Open a dispute for an issue (operator-gated).")
    od.add_argument("--issue-id", required=True)
    od.add_argument("--dispute-type", required=True)
    od.add_argument("--dispute-reason", required=True)
    od.add_argument("--opened-by-operator-id", required=True)
    od.add_argument("--disputed-artifact-references", default="")
    od.add_argument("--artifact-sha256", default="")
    od.add_argument("--evidence-references", default="")
    od.add_argument("--operator-id", default=None)
    od.add_argument("--recorded-at", default=None)
    od.set_defaults(func=_cmd_open_dispute)

    rd = sub.add_parser("resolve-dispute", help="Resolve a dispute (operator + reason required).")
    rd.add_argument("--dispute-id", required=True)
    rd.add_argument("--resolution-status", required=True)
    rd.add_argument("--resolved-by-operator-id", required=True)
    rd.add_argument("--resolution-reason", required=True)
    rd.add_argument("--resolution-reference", default=None)
    rd.add_argument("--operator-id", default=None)
    rd.add_argument("--recorded-at", default=None)
    rd.set_defaults(func=_cmd_resolve_dispute)

    idp = sub.add_parser("inspect-dispute", help="Inspect a dispute by id.")
    idp.add_argument("--dispute-id", required=True)
    idp.set_defaults(func=_cmd_inspect_dispute)

    rr = sub.add_parser("request-reopen", help="Request a case reopen (routing evidence only).")
    rr.add_argument("--issue-id", required=True)
    rr.add_argument("--target-workflow", required=True)
    rr.add_argument("--reopen-reason", required=True)
    rr.add_argument("--reopen-scope", required=True)
    rr.add_argument("--operator-id", default=None)
    rr.add_argument("--recorded-at", default=None)
    rr.set_defaults(func=_cmd_request_reopen)

    ar = sub.add_parser("approve-reopen", help="Approve a reopen (explicit operator approval).")
    ar.add_argument("--reopen-id", required=True)
    ar.add_argument("--approved-by-operator-id", required=True)
    ar.add_argument("--approval-reference", required=True)
    ar.add_argument("--operator-id", default=None)
    ar.add_argument("--recorded-at", default=None)
    ar.set_defaults(func=_cmd_approve_reopen)

    ec = sub.add_parser("evaluate-commercial-closure", help="Evaluate commercial-closure readiness (fail-closed).")
    ec.add_argument("--authorization-id", required=True)
    ec.add_argument("--closure-basis", required=True)
    ec.add_argument("--closed-by-operator-id", required=True)
    ec.add_argument("--invoice-state-reference", default=None)
    ec.add_argument("--payment-state-reference", default=None)
    ec.add_argument("--outstanding-actions", default="")
    ec.add_argument("--evidence-references", default="")
    ec.add_argument("--operator-id", default=None)
    ec.add_argument("--recorded-at", default=None)
    ec.set_defaults(func=_cmd_evaluate_commercial_closure)

    cc = sub.add_parser("create-commercial-closure", help="Record commercial closure (read-only invoice/payment refs).")
    cc.add_argument("--authorization-id", required=True)
    cc.add_argument("--closure-basis", required=True)
    cc.add_argument("--closed-by-operator-id", required=True)
    cc.add_argument("--invoice-state-reference", default=None)
    cc.add_argument("--payment-state-reference", default=None)
    cc.add_argument("--support-policy-id", default="")
    cc.add_argument("--outstanding-actions", default="")
    cc.add_argument("--evidence-references", default="")
    cc.add_argument("--operator-id", default=None)
    cc.add_argument("--recorded-at", default=None)
    cc.set_defaults(func=_cmd_create_commercial_closure)

    isl = sub.add_parser("inspect-post-delivery-support-lineage", help="Inspect full 8G support/dispute/reopen/closure lineage.")
    isl.add_argument("--project-id", default=None)
    isl.set_defaults(func=_cmd_inspect_post_delivery_support_lineage)

    # --- Stage 8H: customer-success evidence and manual opportunity queue ---
    outcome = sub.add_parser("record-customer-outcome", help="Record explicit customer outcome evidence; no contact occurs.")
    for name in ("commercial-closure-id", "customer-reference", "recorded-by-operator-id", "business-outcome-status", "business-outcome-summary"):
        outcome.add_argument("--" + name, required=True)
    for name in ("satisfaction-rating", "delivery-quality-rating", "communication-rating", "timeliness-rating"):
        outcome.add_argument("--" + name, required=True, type=int)
    outcome.add_argument("--measurable-outcomes-json", default="[]")
    outcome.add_argument("--unresolved-concerns", default="")
    outcome.add_argument("--evidence-references", default="")
    outcome.add_argument("--idempotency-key", default="")
    outcome.add_argument("--recorded-at", default=None)
    outcome.set_defaults(func=_cmd_record_customer_outcome)

    inspect_outcome = sub.add_parser("inspect-customer-outcome", help="Inspect immutable customer outcome evidence.")
    inspect_outcome.add_argument("--outcome-review-id", required=True)
    inspect_outcome.set_defaults(func=_cmd_inspect_customer_outcome)

    portfolio = sub.add_parser("record-portfolio-consent", help="Record explicit scoped portfolio consent; no publication occurs.")
    for name in ("outcome-review-id", "customer-reference", "consent-status", "consent-scope", "allowed-artifact-references", "allowed-formats", "allowed-usage-contexts", "recorded-by-operator-id", "consent-basis"):
        portfolio.add_argument("--" + name, required=True)
    for name in ("brand-name-usage", "logo-usage", "customer-name-usage", "performance-metric-usage", "anonymization-required"):
        portfolio.add_argument("--" + name, action="store_true")
    portfolio.add_argument("--anonymization-rules", default="")
    portfolio.add_argument("--attribution-requirement", default=None)
    portfolio.add_argument("--valid-from", default=None)
    portfolio.add_argument("--expires-at", default=None)
    portfolio.add_argument("--evidence-references", default="")
    portfolio.add_argument("--idempotency-key", default="")
    portfolio.add_argument("--recorded-at", default=None)
    portfolio.set_defaults(func=_cmd_record_portfolio_consent)

    rev_portfolio = sub.add_parser("revoke-portfolio-consent", help="Append portfolio-consent revocation evidence.")
    rev_portfolio.add_argument("--consent-id", required=True)
    rev_portfolio.add_argument("--revoked-by-operator-id", required=True)
    rev_portfolio.add_argument("--revocation-reason", required=True)
    rev_portfolio.add_argument("--evidence-references", default="")
    rev_portfolio.add_argument("--idempotency-key", default="")
    rev_portfolio.add_argument("--recorded-at", default=None)
    rev_portfolio.set_defaults(func=_cmd_revoke_portfolio_consent)

    portfolio_ready = sub.add_parser("inspect-portfolio-readiness", help="Inspect portfolio readiness; no publication occurs.")
    portfolio_ready.add_argument("--portfolio-consent-id", required=True)
    portfolio_ready.add_argument("--as-of", required=True)
    portfolio_ready.set_defaults(func=_cmd_inspect_portfolio_readiness)

    testimonial = sub.add_parser("record-testimonial-consent", help="Record exact-text testimonial consent; no publication occurs.")
    for name in ("outcome-review-id", "customer-reference", "testimonial-reference", "testimonial-text-hash", "consent-status", "approved-usage-contexts", "recorded-by-operator-id", "consent-basis"):
        testimonial.add_argument("--" + name, required=True)
    testimonial.add_argument("--approved-edits", default="")
    testimonial.add_argument("--testimonial-text-preview", default=None)
    testimonial.add_argument("--anonymization-required", action="store_true")
    testimonial.add_argument("--attribution-name", default=None)
    testimonial.add_argument("--attribution-role", default=None)
    testimonial.add_argument("--attribution-company", default=None)
    testimonial.add_argument("--valid-from", default=None)
    testimonial.add_argument("--expires-at", default=None)
    testimonial.add_argument("--evidence-references", default="")
    testimonial.add_argument("--idempotency-key", default="")
    testimonial.add_argument("--recorded-at", default=None)
    testimonial.set_defaults(func=_cmd_record_testimonial_consent)

    rev_testimonial = sub.add_parser("revoke-testimonial-consent", help="Append testimonial-consent revocation evidence.")
    rev_testimonial.add_argument("--consent-id", required=True)
    rev_testimonial.add_argument("--revoked-by-operator-id", required=True)
    rev_testimonial.add_argument("--revocation-reason", required=True)
    rev_testimonial.add_argument("--evidence-references", default="")
    rev_testimonial.add_argument("--idempotency-key", default="")
    rev_testimonial.add_argument("--recorded-at", default=None)
    rev_testimonial.set_defaults(func=_cmd_revoke_testimonial_consent)

    testimonial_ready = sub.add_parser("inspect-testimonial-readiness", help="Inspect testimonial readiness; no publication occurs.")
    testimonial_ready.add_argument("--testimonial-consent-id", required=True)
    testimonial_ready.add_argument("--testimonial-text-hash", required=True)
    testimonial_ready.add_argument("--requested-edit", default=None)
    testimonial_ready.add_argument("--as-of", required=True)
    testimonial_ready.set_defaults(func=_cmd_inspect_testimonial_readiness)

    opportunity = sub.add_parser("create-opportunity", help="Record a manual renewal, follow-on, upsell, referral, or support opportunity.")
    for name in ("opportunity-type", "commercial-closure-id", "outcome-review-id", "customer-reference", "opportunity-summary", "confidence-level", "urgency", "created-by-operator-id"):
        opportunity.add_argument("--" + name, required=True)
    opportunity.add_argument("--source-issue-ids", default="")
    opportunity.add_argument("--source-evidence-references", default="")
    opportunity.add_argument("--recommended-offer", default=None)
    opportunity.add_argument("--estimated-value", default=None)
    opportunity.add_argument("--currency", default=None)
    opportunity.add_argument("--target-follow-up-date", default=None)
    opportunity.add_argument("--assigned-operator-id", default=None)
    opportunity.add_argument("--idempotency-key", default="")
    opportunity.add_argument("--recorded-at", default=None)
    opportunity.set_defaults(func=_cmd_create_opportunity)

    qualify = sub.add_parser("qualify-opportunity", help="Append an explicit manual opportunity status decision.")
    qualify.add_argument("--opportunity-id", required=True)
    qualify.add_argument("--status", required=True)
    qualify.add_argument("--confirmed-by-operator-id", required=True)
    qualify.add_argument("--reason", required=True)
    qualify.add_argument("--operator-confirmation", action="store_true")
    qualify.add_argument("--idempotency-key", default="")
    qualify.add_argument("--recorded-at", default=None)
    qualify.set_defaults(func=_cmd_qualify_opportunity)

    inspect_opp = sub.add_parser("inspect-opportunity", help="Inspect manual opportunity readiness.")
    inspect_opp.add_argument("--opportunity-id", required=True)
    inspect_opp.set_defaults(func=_cmd_inspect_opportunity)

    priority = sub.add_parser("evaluate-opportunity-priority", help="Evaluate deterministic priority from explicit JSON inputs.")
    priority.add_argument("--inputs-json", required=True)
    priority.set_defaults(func=_cmd_evaluate_opportunity_priority)

    queue = sub.add_parser("list-manual-follow-up-queue", help="List deterministic manual follow-up queue; does not contact customers.")
    queue.add_argument("--as-of", required=True)
    queue.set_defaults(func=_cmd_list_manual_follow_up_queue)

    lineage8h = sub.add_parser("inspect-customer-success-lineage", help="Inspect complete Stage 8H customer-success lineage.")
    lineage8h.add_argument("--project-id", default=None)
    lineage8h.set_defaults(func=_cmd_inspect_customer_success_lineage)

    # --- Stage 8I: local commercial proposal preparation and handoff -------
    proposal_create = sub.add_parser("create-hvs-commercial-proposal", help="Create local commercial proposal preparation; no customer action occurs.")
    for name in ("opportunity-id", "delivery-lineage-id", "title", "objective", "scope-summary", "deliverables-json", "exclusions", "assumptions", "line-items-json", "currency", "tax-amount", "tax-treatment", "discount-amount", "payment-terms", "revision-terms", "validity-start-date", "validity-end-date", "operator-id"):
        proposal_create.add_argument("--" + name, required=True)
    proposal_create.add_argument("--estimated-start-date", default=None)
    proposal_create.add_argument("--estimated-completion-date", default=None)
    proposal_create.add_argument("--dependency-notes", default="")
    proposal_create.add_argument("--risk-notes", default="")
    proposal_create.add_argument("--commercial-recipient-reference", default=None)
    proposal_create.add_argument("--recorded-at", default=None)
    proposal_create.set_defaults(func=_cmd_create_commercial_proposal)

    proposal_inspect = sub.add_parser("inspect-hvs-commercial-proposal", help="Inspect a local Stage 8I proposal preparation; no customer action occurs.")
    proposal_inspect.add_argument("--proposal-preparation-id", required=True)
    proposal_inspect.set_defaults(func=_cmd_inspect_commercial_proposal)

    proposal_readiness = sub.add_parser("evaluate-hvs-commercial-proposal-readiness", help="Evaluate local proposal readiness; no customer action occurs.")
    proposal_readiness.add_argument("--proposal-preparation-id", required=True)
    proposal_readiness.add_argument("--as-of", required=True)
    proposal_readiness.set_defaults(func=_cmd_evaluate_commercial_proposal_readiness)

    proposal_review = sub.add_parser("request-hvs-commercial-proposal-review", help="Request internal review for a ready local proposal.")
    proposal_review.add_argument("--proposal-preparation-id", required=True)
    proposal_review.add_argument("--operator-id", required=True)
    proposal_review.add_argument("--recorded-at", default=None)
    proposal_review.set_defaults(func=_cmd_request_commercial_proposal_review)

    proposal_approve = sub.add_parser("approve-hvs-commercial-proposal", help="Approve a reviewed proposal for manual presentation only.")
    proposal_approve.add_argument("--proposal-preparation-id", required=True)
    proposal_approve.add_argument("--operator-id", required=True)
    proposal_approve.add_argument("--as-of", required=True)
    proposal_approve.add_argument("--recorded-at", default=None)
    proposal_approve.set_defaults(func=_cmd_approve_commercial_proposal)

    for command, handler in (("reject-hvs-commercial-proposal", _cmd_reject_commercial_proposal), ("cancel-hvs-commercial-proposal", _cmd_cancel_commercial_proposal)):
        proposal_decision = sub.add_parser(command, help="Record a local commercial proposal decision; no customer action occurs.")
        proposal_decision.add_argument("--proposal-preparation-id", required=True)
        proposal_decision.add_argument("--operator-id", required=True)
        proposal_decision.add_argument("--reason", required=True)
        proposal_decision.add_argument("--recorded-at", default=None)
        proposal_decision.set_defaults(func=handler)

    proposal_handoff = sub.add_parser("create-hvs-manual-commercial-handoff", help="Create a manual-only handoff from an approved local proposal.")
    proposal_handoff.add_argument("--proposal-preparation-id", required=True)
    proposal_handoff.add_argument("--operator-id", required=True)
    proposal_handoff.add_argument("--recorded-at", default=None)
    proposal_handoff.set_defaults(func=_cmd_create_manual_commercial_handoff)

    proposal_queue = sub.add_parser("list-hvs-commercial-proposal-review-queue", help="List deterministic local commercial proposal review work.")
    proposal_queue.add_argument("--as-of", required=True)
    proposal_queue.set_defaults(func=_cmd_list_commercial_proposal_review_queue)

    # --- Stage 8J: manual proposal presentation and commercial acceptance ---
    presentation = sub.add_parser("record-hvs-proposal-presentation", help="Record a human-performed proposal presentation; SCOS performs no communication.")
    presentation.add_argument("--proposal-id", "--proposal-preparation-id", dest="proposal_preparation_id", required=True)
    presentation.add_argument("--handoff-id", required=True)
    presentation.add_argument("--channel", required=True)
    presentation.add_argument("--presentation-date", required=True)
    presentation.add_argument("--operator-id", required=True)
    presentation.add_argument("--evidence-reference", default=None)
    presentation.add_argument("--customer-participant-reference", default=None)
    presentation.add_argument("--operator-note", default=None)
    presentation.add_argument("--recorded-at", default=None)
    presentation.add_argument("--confirm-manual-presentation", action="store_true")
    presentation.set_defaults(func=_cmd_record_hvs_proposal_presentation)

    decision8j = sub.add_parser("record-hvs-customer-commercial-decision", help="Record explicit operator-supplied customer commercial decision evidence.")
    decision8j.add_argument("--presentation-id", dest="presentation_record_id", required=True)
    decision8j.add_argument("--decision", required=True, choices=["accepted", "rejected", "negotiation", "negotiation-requested", "revision", "proposal-revision-requested", "no-response", "deferred"])
    decision8j.add_argument("--decision-date", required=True)
    decision8j.add_argument("--operator-id", required=True)
    decision8j.add_argument("--evidence-reference", required=True)
    decision8j.add_argument("--approved-proposal-content-hash", required=True)
    decision8j.add_argument("--customer-decision-reference", default=None)
    decision8j.add_argument("--accepted-total", default=None)
    decision8j.add_argument("--accepted-currency", default=None)
    decision8j.add_argument("--accepted-scope-hash", default=None)
    decision8j.add_argument("--accepted-payment-terms", default=None)
    decision8j.add_argument("--accepted-revision-terms", default=None)
    decision8j.add_argument("--accepted-tax", default=None)
    decision8j.add_argument("--accepted-discount", default=None)
    decision8j.add_argument("--requested-changes", default="")
    decision8j.add_argument("--rejection-reason", default=None)
    decision8j.add_argument("--follow-up-date", default=None)
    decision8j.add_argument("--deferred-reason", default=None)
    decision8j.add_argument("--recorded-at", default=None)
    decision8j.set_defaults(func=_cmd_record_hvs_customer_commercial_decision)

    inspect_decision8j = sub.add_parser("inspect-hvs-customer-commercial-decision", help="Inspect a local Stage 8J customer decision.")
    inspect_decision8j.add_argument("--decision-id", required=True)
    inspect_decision8j.set_defaults(func=_cmd_inspect_hvs_customer_commercial_decision)

    readiness8j = sub.add_parser("evaluate-hvs-commercial-acceptance-readiness", help="Evaluate future manual invoice and project-kickoff readiness without mutating records.")
    readiness8j.add_argument("--proposal-id", "--proposal-preparation-id", dest="proposal_preparation_id", required=True)
    readiness8j.add_argument("--evaluation-date", required=True)
    readiness8j.set_defaults(func=_cmd_evaluate_hvs_commercial_acceptance_readiness)

    inspect_acceptance8j = sub.add_parser("inspect-hvs-commercial-acceptance", help="Inspect a local Stage 8J commercial acceptance.")
    inspect_acceptance8j.add_argument("--acceptance-id", required=True)
    inspect_acceptance8j.set_defaults(func=_cmd_inspect_hvs_commercial_acceptance)

    queue8j = sub.add_parser("list-hvs-commercial-decision-queue", help="List deterministic local customer decision work.")
    queue8j.add_argument("--evaluation-date", required=True)
    queue8j.set_defaults(func=_cmd_list_hvs_commercial_decision_queue)
    return parser


def _cmd_inspect_post_delivery_support_lineage(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import inspect_post_delivery_support_lineage

    out = inspect_post_delivery_support_lineage(project_id=getattr(args, "project_id", None), repo_root=_repo_root())
    _emit(out)
    return EXIT_OK


def _cmd_register_support_policy(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import register_post_delivery_support_policy

    out = register_post_delivery_support_policy(
        authorization_id=args.authorization_id,
        support_window_start=args.support_window_start,
        support_window_end=args.support_window_end,
        policy_type=args.policy_type,
        included_issue_categories=_split_csv(args.included_issue_categories),
        excluded_issue_categories=_split_csv(args.excluded_issue_categories),
        created_by_operator_id=args.created_by_operator_id,
        policy_version=args.policy_version,
        revision_allowance_reference=args.revision_allowance_reference,
        commercial_terms_reference=args.commercial_terms_reference,
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_inspect_support_policy(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import _policies_by_id

    policy = _policies_by_id(repo_root=_repo_root()).get(args.support_policy_id)
    if policy is None:
        _emit({"ok": False, "error_code": "SUPPORT_POLICY_NOT_FOUND"})
        return EXIT_REJECT
    _emit(policy.to_dict())
    return EXIT_OK


def _cmd_record_issue(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import record_post_delivery_issue

    out = record_post_delivery_issue(
        support_policy_id=args.support_policy_id,
        issue_category=args.issue_category,
        issue_summary=args.issue_summary,
        recorded_by_operator_id=args.recorded_by_operator_id,
        customer_reference=args.customer_reference,
        affected_formats=_split_csv(args.affected_formats),
        reported_at=args.reported_at,
        issue_details=args.issue_details,
        affected_artifact_references=_split_csv(args.affected_artifact_references),
        artifact_sha256=args.artifact_sha256,
        requested_resolution=args.requested_resolution,
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_inspect_issue(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import _issues_by_id

    issue = _issues_by_id(repo_root=_repo_root()).get(args.issue_id)
    if issue is None:
        _emit({"ok": False, "error_code": "ISSUE_NOT_FOUND"})
        return EXIT_REJECT
    _emit(issue.to_dict())
    return EXIT_OK


def _cmd_classify_issue(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import classify_post_delivery_issue

    out = classify_post_delivery_issue(
        issue_id=args.issue_id,
        classified_by_operator_id=args.classified_by_operator_id,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_open_dispute(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import open_post_delivery_dispute

    out = open_post_delivery_dispute(
        issue_id=args.issue_id,
        dispute_type=args.dispute_type,
        dispute_reason=args.dispute_reason,
        opened_by_operator_id=args.opened_by_operator_id,
        disputed_artifact_references=_split_csv(args.disputed_artifact_references),
        artifact_sha256=args.artifact_sha256,
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_resolve_dispute(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import resolve_post_delivery_dispute

    out = resolve_post_delivery_dispute(
        dispute_id=args.dispute_id,
        resolution_status=args.resolution_status,
        resolved_by_operator_id=args.resolved_by_operator_id,
        resolution_reason=args.resolution_reason,
        resolution_reference=args.resolution_reference,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_inspect_dispute(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import _disputes_by_issue

    for lst in _disputes_by_issue(repo_root=_repo_root()).values():
        for d in lst:
            if d.dispute_id == args.dispute_id:
                _emit(d.to_dict())
                return EXIT_OK
    _emit({"ok": False, "error_code": "DISPUTE_NOT_FOUND"})
    return EXIT_REJECT


def _cmd_request_reopen(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import request_post_delivery_reopen

    out = request_post_delivery_reopen(
        issue_id=args.issue_id,
        target_workflow=args.target_workflow,
        reopen_reason=args.reopen_reason,
        reopen_scope=args.reopen_scope,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_approve_reopen(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import approve_post_delivery_reopen

    out = approve_post_delivery_reopen(
        reopen_id=args.reopen_id,
        approved_by_operator_id=args.approved_by_operator_id,
        approval_reference=args.approval_reference,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_evaluate_commercial_closure(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import evaluate_commercial_closure

    out = evaluate_commercial_closure(
        authorization_id=args.authorization_id,
        closure_basis=args.closure_basis,
        closed_by_operator_id=args.closed_by_operator_id,
        invoice_state_reference=args.invoice_state_reference,
        payment_state_reference=args.payment_state_reference,
        outstanding_actions=_split_csv(args.outstanding_actions),
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_create_commercial_closure(args: argparse.Namespace) -> int:
    from .hvs_post_delivery_support_service import record_commercial_closure

    out = record_commercial_closure(
        authorization_id=args.authorization_id,
        closure_basis=args.closure_basis,
        closed_by_operator_id=args.closed_by_operator_id,
        invoice_state_reference=args.invoice_state_reference,
        payment_state_reference=args.payment_state_reference,
        support_policy_id=args.support_policy_id,
        outstanding_actions=_split_csv(args.outstanding_actions),
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _customer_success_result(out: Any) -> int:
    _emit(out.to_dict())
    return EXIT_OK if out.ok else EXIT_REJECT


def _cmd_record_customer_outcome(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import record_customer_outcome
    try:
        outcomes = json.loads(args.measurable_outcomes_json)
        if not isinstance(outcomes, list):
            raise ValueError("measurable outcomes must be a JSON list")
    except (ValueError, json.JSONDecodeError) as exc:
        raise _CliError("INVALID_ARGUMENTS", str(exc)) from exc
    return _customer_success_result(record_customer_outcome(commercial_closure_id=args.commercial_closure_id, customer_reference=args.customer_reference, recorded_by_operator_id=args.recorded_by_operator_id, satisfaction_rating=args.satisfaction_rating, delivery_quality_rating=args.delivery_quality_rating, communication_rating=args.communication_rating, timeliness_rating=args.timeliness_rating, business_outcome_status=args.business_outcome_status, business_outcome_summary=args.business_outcome_summary, measurable_outcomes=tuple(outcomes), unresolved_concerns=_split_csv(args.unresolved_concerns), evidence_references=_split_csv(args.evidence_references), idempotency_key=args.idempotency_key, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()))


def _cmd_inspect_customer_outcome(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import _outcomes
    record = _outcomes(_repo_root()).get(args.outcome_review_id)
    if not record:
        _emit({"ok": False, "error_code": "OUTCOME_REVIEW_NOT_FOUND"})
        return EXIT_REJECT
    _emit(record.to_dict())
    return EXIT_OK


def _cmd_record_portfolio_consent(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import record_portfolio_consent
    return _customer_success_result(record_portfolio_consent(outcome_review_id=args.outcome_review_id, customer_reference=args.customer_reference, consent_status=args.consent_status, consent_scope=args.consent_scope, allowed_artifact_references=_split_csv(args.allowed_artifact_references), allowed_formats=_split_csv(args.allowed_formats), allowed_usage_contexts=_split_csv(args.allowed_usage_contexts), brand_name_usage=args.brand_name_usage, logo_usage=args.logo_usage, customer_name_usage=args.customer_name_usage, performance_metric_usage=args.performance_metric_usage, anonymization_required=args.anonymization_required, anonymization_rules=_split_csv(args.anonymization_rules), attribution_requirement=args.attribution_requirement, valid_from=args.valid_from or _now_iso(), expires_at=args.expires_at, recorded_by_operator_id=args.recorded_by_operator_id, consent_basis=args.consent_basis, evidence_references=_split_csv(args.evidence_references), idempotency_key=args.idempotency_key, repo_root=_repo_root(), created_at=args.recorded_at or _now_iso()))


def _cmd_revoke_portfolio_consent(args: argparse.Namespace) -> int:
    return _cmd_revoke_consent(args, "PORTFOLIO")


def _cmd_revoke_testimonial_consent(args: argparse.Namespace) -> int:
    return _cmd_revoke_consent(args, "TESTIMONIAL")


def _cmd_revoke_consent(args: argparse.Namespace, consent_type: str) -> int:
    from .hvs_customer_outcome_service import revoke_consent
    return _customer_success_result(revoke_consent(consent_type=consent_type, consent_id=args.consent_id, revoked_by_operator_id=args.revoked_by_operator_id, revocation_reason=args.revocation_reason, evidence_references=_split_csv(args.evidence_references), idempotency_key=args.idempotency_key, repo_root=_repo_root(), created_at=args.recorded_at or _now_iso()))


def _cmd_inspect_portfolio_readiness(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import portfolio_readiness
    _emit(portfolio_readiness(portfolio_consent_id=args.portfolio_consent_id, repo_root=_repo_root(), as_of=args.as_of))
    return EXIT_OK


def _cmd_record_testimonial_consent(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import record_testimonial_consent
    return _customer_success_result(record_testimonial_consent(outcome_review_id=args.outcome_review_id, customer_reference=args.customer_reference, testimonial_reference=args.testimonial_reference, testimonial_text_hash=args.testimonial_text_hash, testimonial_text_preview=args.testimonial_text_preview, consent_status=args.consent_status, approved_usage_contexts=_split_csv(args.approved_usage_contexts), approved_edits=_split_csv(args.approved_edits), attribution_name=args.attribution_name, attribution_role=args.attribution_role, attribution_company=args.attribution_company, anonymization_required=args.anonymization_required, valid_from=args.valid_from or _now_iso(), expires_at=args.expires_at, recorded_by_operator_id=args.recorded_by_operator_id, consent_basis=args.consent_basis, evidence_references=_split_csv(args.evidence_references), idempotency_key=args.idempotency_key, repo_root=_repo_root(), created_at=args.recorded_at or _now_iso()))


def _cmd_inspect_testimonial_readiness(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import testimonial_readiness
    _emit(testimonial_readiness(testimonial_consent_id=args.testimonial_consent_id, testimonial_text_hash=args.testimonial_text_hash, requested_edit=args.requested_edit, repo_root=_repo_root(), as_of=args.as_of))
    return EXIT_OK


def _cmd_create_opportunity(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import create_opportunity
    return _customer_success_result(create_opportunity(opportunity_type=args.opportunity_type, commercial_closure_id=args.commercial_closure_id, outcome_review_id=args.outcome_review_id, customer_reference=args.customer_reference, opportunity_summary=args.opportunity_summary, confidence_level=int(args.confidence_level), urgency=args.urgency, created_by_operator_id=args.created_by_operator_id, source_issue_ids=_split_csv(args.source_issue_ids), source_evidence_references=_split_csv(args.source_evidence_references), recommended_offer=args.recommended_offer, estimated_value=args.estimated_value, currency=args.currency, target_follow_up_date=args.target_follow_up_date, assigned_operator_id=args.assigned_operator_id, idempotency_key=args.idempotency_key, repo_root=_repo_root(), created_at=args.recorded_at or _now_iso()))


def _cmd_qualify_opportunity(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import qualify_opportunity
    return _customer_success_result(qualify_opportunity(opportunity_id=args.opportunity_id, status=args.status, confirmed_by_operator_id=args.confirmed_by_operator_id, reason=args.reason, operator_confirmation=args.operator_confirmation, idempotency_key=args.idempotency_key, repo_root=_repo_root(), created_at=args.recorded_at or _now_iso()))


def _cmd_inspect_opportunity(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import opportunity_readiness
    _emit(opportunity_readiness(opportunity_id=args.opportunity_id, repo_root=_repo_root()))
    return EXIT_OK


def _cmd_evaluate_opportunity_priority(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import evaluate_opportunity_priority
    try:
        inputs = json.loads(args.inputs_json)
        if not isinstance(inputs, dict):
            raise ValueError("priority inputs must be a JSON object")
    except (ValueError, json.JSONDecodeError) as exc:
        raise _CliError("INVALID_ARGUMENTS", str(exc)) from exc
    _emit(evaluate_opportunity_priority(**inputs))
    return EXIT_OK


def _cmd_list_manual_follow_up_queue(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import list_manual_follow_up_queue
    _emit({"items": list_manual_follow_up_queue(repo_root=_repo_root(), as_of=args.as_of), "automation_allowed": False})
    return EXIT_OK


def _cmd_inspect_customer_success_lineage(args: argparse.Namespace) -> int:
    from .hvs_customer_outcome_service import inspect_customer_success_lineage
    _emit(inspect_customer_success_lineage(project_id=args.project_id, repo_root=_repo_root()))
    return EXIT_OK


def _cmd_inspect_commercial_proposal(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import inspect_proposal_preparation

    outcome = inspect_proposal_preparation(
        proposal_preparation_id=args.proposal_preparation_id,
        repo_root=_repo_root(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _commercial_proposal_result(outcome: Any) -> int:
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _proposal_json_list(value: str, field: str) -> tuple[dict[str, Any], ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise _CliError("INVALID_ARGUMENTS", f"{field} must be a JSON list") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise _CliError("INVALID_ARGUMENTS", f"{field} must be a JSON list of objects")
    return tuple(parsed)


def _cmd_create_commercial_proposal(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import create_proposal_preparation

    return _commercial_proposal_result(create_proposal_preparation(
        opportunity_id=args.opportunity_id,
        delivery_lineage_id=args.delivery_lineage_id,
        title=args.title,
        objective=args.objective,
        scope_summary=args.scope_summary,
        deliverables=_proposal_json_list(args.deliverables_json, "deliverables_json"),
        exclusions=_split_csv(args.exclusions),
        assumptions=_split_csv(args.assumptions),
        line_items=_proposal_json_list(args.line_items_json, "line_items_json"),
        currency=args.currency,
        tax_amount=args.tax_amount,
        tax_treatment=args.tax_treatment,
        discount_amount=args.discount_amount,
        payment_terms=args.payment_terms,
        revision_terms=args.revision_terms,
        validity_start_date=args.validity_start_date,
        validity_end_date=args.validity_end_date,
        operator_id=args.operator_id,
        recorded_at=args.recorded_at or _now_iso()[:10],
        estimated_start_date=args.estimated_start_date,
        estimated_completion_date=args.estimated_completion_date,
        dependency_notes=_split_csv(args.dependency_notes),
        risk_notes=_split_csv(args.risk_notes),
        commercial_recipient_reference=args.commercial_recipient_reference,
        repo_root=_repo_root(),
    ))


def _cmd_evaluate_commercial_proposal_readiness(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import evaluate_proposal_readiness

    readiness = evaluate_proposal_readiness(proposal_preparation_id=args.proposal_preparation_id, repo_root=_repo_root(), as_of=args.as_of)
    _emit(readiness.to_dict())
    return EXIT_OK if readiness.state == "READY" else EXIT_REJECT


def _cmd_request_commercial_proposal_review(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import submit_for_internal_review

    return _commercial_proposal_result(submit_for_internal_review(proposal_preparation_id=args.proposal_preparation_id, operator_id=args.operator_id, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()[:10]))


def _cmd_approve_commercial_proposal(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import approve_for_manual_presentation

    return _commercial_proposal_result(approve_for_manual_presentation(proposal_preparation_id=args.proposal_preparation_id, operator_id=args.operator_id, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()[:10], as_of=args.as_of))


def _cmd_reject_commercial_proposal(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import reject_proposal

    return _commercial_proposal_result(reject_proposal(proposal_preparation_id=args.proposal_preparation_id, operator_id=args.operator_id, reason=args.reason, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()[:10]))


def _cmd_cancel_commercial_proposal(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import cancel_proposal

    return _commercial_proposal_result(cancel_proposal(proposal_preparation_id=args.proposal_preparation_id, operator_id=args.operator_id, reason=args.reason, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()[:10]))


def _cmd_create_manual_commercial_handoff(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import create_manual_commercial_handoff

    return _commercial_proposal_result(create_manual_commercial_handoff(proposal_preparation_id=args.proposal_preparation_id, operator_id=args.operator_id, repo_root=_repo_root(), recorded_at=args.recorded_at or _now_iso()[:10]))


def _cmd_list_commercial_proposal_review_queue(args: argparse.Namespace) -> int:
    from .hvs_commercial_proposal_service import list_proposal_review_queue

    _emit({"items": list_proposal_review_queue(repo_root=_repo_root(), as_of=args.as_of), "automation_allowed": False})
    return EXIT_OK


def _commercial_acceptance_result(outcome: Any) -> int:
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_record_hvs_proposal_presentation(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import record_manual_proposal_presentation

    return _commercial_acceptance_result(record_manual_proposal_presentation(
        proposal_preparation_id=args.proposal_preparation_id,
        commercial_handoff_package_id=args.handoff_id,
        presentation_channel=args.channel,
        presentation_date=args.presentation_date,
        presented_by_operator_id=args.operator_id,
        evidence_reference=args.evidence_reference,
        customer_participant_reference=args.customer_participant_reference,
        operator_note=args.operator_note,
        manual_action_confirmed=args.confirm_manual_presentation,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or args.presentation_date,
    ))


def _cmd_record_hvs_customer_commercial_decision(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import record_customer_commercial_decision

    return _commercial_acceptance_result(record_customer_commercial_decision(
        presentation_record_id=args.presentation_record_id,
        decision_type=args.decision,
        decision_date=args.decision_date,
        recorded_by_operator_id=args.operator_id,
        evidence_reference=args.evidence_reference,
        approved_proposal_content_hash=args.approved_proposal_content_hash,
        customer_decision_reference=args.customer_decision_reference,
        accepted_total=args.accepted_total,
        accepted_currency=args.accepted_currency,
        accepted_scope_hash=args.accepted_scope_hash,
        accepted_payment_terms=args.accepted_payment_terms,
        accepted_revision_terms=args.accepted_revision_terms,
        accepted_tax=args.accepted_tax,
        accepted_discount=args.accepted_discount,
        requested_changes=_split_csv(args.requested_changes),
        rejection_reason=args.rejection_reason,
        follow_up_date=args.follow_up_date,
        deferred_reason=args.deferred_reason,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or args.decision_date,
    ))


def _cmd_inspect_hvs_customer_commercial_decision(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import inspect_customer_commercial_decision

    return _commercial_acceptance_result(inspect_customer_commercial_decision(customer_decision_id=args.decision_id, repo_root=_repo_root()))


def _cmd_evaluate_hvs_commercial_acceptance_readiness(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import evaluate_commercial_acceptance_readiness

    readiness = evaluate_commercial_acceptance_readiness(proposal_preparation_id=args.proposal_preparation_id, repo_root=_repo_root(), evaluation_date=args.evaluation_date)
    _emit(readiness.to_dict())
    return EXIT_OK if readiness.readiness_status == "READY_FOR_MANUAL_INVOICE_AND_KICKOFF" else EXIT_REJECT


def _cmd_inspect_hvs_commercial_acceptance(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import inspect_commercial_acceptance

    return _commercial_acceptance_result(inspect_commercial_acceptance(commercial_acceptance_id=args.acceptance_id, repo_root=_repo_root()))


def _cmd_list_hvs_commercial_decision_queue(args: argparse.Namespace) -> int:
    from .hvs_commercial_acceptance_service import list_commercial_decision_queue

    _emit({"items": list_commercial_decision_queue(repo_root=_repo_root(), evaluation_date=args.evaluation_date), "automation_allowed": False})
    return EXIT_OK


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


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _cmd_record_revised_delivery_acceptance(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import record_revised_delivery_acceptance

    rejection_codes = _split_csv(getattr(args, "rejection_codes", None)) if args.acceptance_status == "REJECTED" else ()
    outcome = record_revised_delivery_acceptance(
        reconciliation_result_id=args.reconciliation_result_id,
        revised_delivery_id=args.revised_delivery_id,
        reviewer_id=args.reviewer_id,
        accepted_formats=tuple(args.accepted_formats),
        rejected_formats=tuple(args.rejected_formats),
        quality_gate_reference=args.quality_gate_reference,
        artifact_integrity_reference=args.artifact_integrity_reference,
        acceptance_status=args.acceptance_status,
        rejection_codes=rejection_codes,
        review_notes=getattr(args, "review_notes", None),
        evidence_references=_split_csv(getattr(args, "evidence_references", None)),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_revised_delivery_acceptance(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import inspect_acceptance

    outcome = inspect_acceptance(acceptance_id=args.acceptance_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_create_customer_release_authorization(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import create_customer_release_authorization

    outcome = create_customer_release_authorization(
        acceptance_id=args.acceptance_id,
        authorized_by=args.authorized_by,
        authorization_scope=tuple(args.authorization_scope),
        approved_formats=tuple(args.approved_formats),
        allowed_delivery_channels=tuple(args.allowed_delivery_channels),
        customer_reference=args.customer_reference,
        approval_basis=args.approval_basis,
        policy_version=args.policy_version,
        expiry_at=args.expiry_at,
        evidence_references=_split_csv(getattr(args, "evidence_references", None)),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_revoke_customer_release_authorization(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import revoke_customer_release_authorization

    outcome = revoke_customer_release_authorization(
        authorization_id=args.authorization_id,
        reason=getattr(args, "reason", None),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_evaluate_release_readiness(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import evaluate_release_readiness

    decision = evaluate_release_readiness(
        acceptance_id=args.acceptance_id,
        authorization_id=getattr(args, "authorization_id", None),
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(decision.to_dict())
    return EXIT_OK


def _cmd_close_final_revision(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import close_final_revision

    outcome = close_final_revision(
        acceptance_id=args.acceptance_id,
        authorization_id=getattr(args, "authorization_id", None),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_final_revision_closure(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import inspect_final_closure

    outcome = inspect_final_closure(revision_id=args.revision_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_release_lineage(args: argparse.Namespace) -> int:
    from .hvs_revised_delivery_release_service import inspect_release_lineage

    outcome = inspect_release_lineage(project_id=getattr(args, "project_id", None), repo_root=_repo_root())
    _emit(outcome)
    return EXIT_OK


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in (value or "").split(",") if v.strip())


def _cmd_record_manual_release(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import record_manual_release

    outcome = record_manual_release(
        authorization_id=args.authorization_id,
        released_by=args.released_by,
        release_channel=args.release_channel,
        released_formats=_split_csv(args.released_formats),
        customer_reference=args.customer_reference,
        release_method_reference=args.release_method_reference,
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_manual_release(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import inspect_manual_release

    outcome = inspect_manual_release(authorization_id=args.authorization_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_record_8f_customer_receipt(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import record_customer_receipt

    outcome = record_customer_receipt(
        release_id=args.release_id,
        confirmed_by=args.confirmed_by,
        receipt_status=args.receipt_status,
        received_formats=_split_csv(args.received_formats),
        customer_reference=args.customer_reference,
        confirmation_reference=args.confirmation_reference,
        receipt_channel=getattr(args, "receipt_channel", None),
        receipt_notes=getattr(args, "receipt_notes", None),
        evidence_references=_split_csv(args.evidence_references),
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_8f_customer_receipt(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import inspect_customer_receipt

    outcome = inspect_customer_receipt(release_id=args.release_id, repo_root=_repo_root())
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_evaluate_post_delivery_audit(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import evaluate_post_delivery_audit

    outcome = evaluate_post_delivery_audit(
        authorization_id=args.authorization_id,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_close_post_delivery_audit(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import close_post_delivery_audit

    outcome = close_post_delivery_audit(
        authorization_id=args.authorization_id,
        operator_id=args.operator_id,
        repo_root=_repo_root(),
        recorded_at=args.recorded_at or _now_iso(),
    )
    _emit(outcome.to_dict())
    return EXIT_OK if outcome.ok else EXIT_REJECT


def _cmd_inspect_post_delivery_lineage(args: argparse.Namespace) -> int:
    from .hvs_manual_release_receipt_service import inspect_post_delivery_lineage

    outcome = inspect_post_delivery_lineage(project_id=getattr(args, "project_id", None), repo_root=_repo_root())
    _emit(outcome)
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
