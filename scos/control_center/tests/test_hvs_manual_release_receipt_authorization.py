"""Stage 8F focused verification: manual release execution, customer receipt
confirmation, and post-delivery audit closure.

Covers: release recording + gates, receipt recording + gates, post-delivery
audit readiness + closure, deterministic idempotency, conflict rejection, audit
append-only evidence, lineage inspectability, HVS/outbound boundaries, and CLI
behavior.

The Stage 8E release-ready context is constructed by reusing the proven Stage 8E
test harness (_reconcile_revised_delivery / _authorized_context), so 8F is
exercised on exactly the same upstream evidence the 8E tests use.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_revised_delivery_release_authorization import (
    _authorized_context as _e8_authorized_context,
    _reconcile_revised_delivery as _e8_reconcile,
)
from scos.control_center.hvs_revised_delivery_release_service import (
    create_customer_release_authorization,
)
from scos.control_center.hvs_manual_release_receipt_service import (
    close_post_delivery_audit,
    evaluate_post_delivery_audit,
    inspect_customer_receipt,
    inspect_manual_release,
    inspect_post_delivery_lineage,
    record_customer_receipt,
    record_manual_release,
)
from scos.control_center.hvs_manual_release_receipt_store import (
    post_delivery_audit_path,
    read_post_delivery_events,
)
from scos.control_center.hvs_manual_release_receipt_models import (
    AUDIT_CLOSED,
    AUDIT_READY,
)


def _reconcile_revised_delivery(repo_root: Path) -> dict[str, str]:
    return _e8_reconcile(repo_root)


def _authorized_context(repo_root: Path):
    return _e8_authorized_context(repo_root)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


# ===========================================================================
# A. Manual release recording
# ===========================================================================
def test_record_manual_release_success(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id=auth.authorization_id,
        released_by="operator-1",
        release_channel="email_manual",
        released_formats=("vertical",),
        customer_reference="cust-1",
        release_method_reference="manual-share-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok and out.release is not None
    assert out.release.authorization_id == auth.authorization_id
    assert out.release.revision_id == ctx["revision_id"]
    assert out.release.revised_delivery_id == ctx["revised_delivery_id"]
    assert out.release.original_delivery_id == ctx["original_delivery_id"]
    assert out.release.project_id == ctx["project_id"]
    assert out.release.correlation_id == ctx["correlation_id"]
    assert out.release.status == "RECORDED"
    assert out.hvs_invoked is False


def test_record_manual_release_idempotent(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    first = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert first.ok
    second = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert second.ok and second.duplicate_of == first.release.release_id
    events = [e for e in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)) if e.event_type == "MANUAL_RELEASE_RECORDED"]
    assert len(events) == 1


def test_record_manual_release_missing_authorization_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id="scos-hvs-release-auth-missing",
        released_by="operator-1", release_channel="email_manual",
        released_formats=("vertical",), customer_reference="cust-1",
        release_method_reference="manual-share-1", operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "AUTHORIZATION_NOT_FOUND"


def test_record_manual_release_format_not_authorized_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("story",),  # not in approved
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_FORMAT_NOT_AUTHORIZED"


def test_record_manual_release_channel_not_authorized_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="ftp_manual", released_formats=("vertical",),  # not allowed
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_CHANNEL_NOT_AUTHORIZED"


def test_record_manual_release_customer_mismatch_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="other-customer", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "CUSTOMER_REFERENCE_MISMATCH"


def test_record_manual_release_path_traversal_customer_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="../escape", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code in ("RELEASE_VALIDATION", "CUSTOMER_REFERENCE_MISMATCH")


# ===========================================================================
# B. Customer receipt confirmation
# ===========================================================================
def _released_context(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    # Complete the Stage 8E final revision closure so the post-delivery audit
    # has a fully closed upstream lineage to evaluate against.
    from scos.control_center.hvs_revised_delivery_release_service import close_final_revision

    close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    rel = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert rel.ok
    return ctx, acc, auth, rel.release


def test_record_customer_receipt_success(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    out = record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1",
        receipt_status="CONFIRMED", received_formats=("vertical",),
        customer_reference="cust-1", confirmation_reference="ticket-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert out.ok and out.receipt is not None
    assert out.receipt.release_id == release.release_id
    assert out.receipt.revision_id == ctx["revision_id"]
    assert out.receipt.received_formats == ("vertical",)
    assert out.hvs_invoked is False


def test_record_customer_receipt_idempotent(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    first = record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert first.ok
    second = record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert second.ok and second.duplicate_of == first.receipt.receipt_id
    events = [e for e in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)) if e.event_type == "CUSTOMER_RECEIPT_CONFIRMED"]
    assert len(events) == 1


def test_record_customer_receipt_missing_release_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = record_customer_receipt(
        release_id="scos-hvs-manual-release-missing", confirmed_by="cs-1",
        receipt_status="CONFIRMED", received_formats=("vertical",),
        customer_reference="cust-1", confirmation_reference="ticket-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_NOT_FOUND"


def test_record_customer_receipt_format_not_released_rejected(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    out = record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("story",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "RECEIPT_FORMAT_NOT_RELEASED"


def test_record_customer_receipt_customer_mismatch_rejected(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    out = record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="other-customer",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "CUSTOMER_REFERENCE_MISMATCH"


# ===========================================================================
# C. Post-delivery audit readiness + closure
# ===========================================================================
def test_evaluate_post_delivery_audit_ready(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    out = evaluate_post_delivery_audit(
        authorization_id=auth.authorization_id, operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert out.ok and out.audit is not None
    assert out.audit.audit_ready is True
    assert out.audit.closure_decision == AUDIT_READY
    assert out.audit.release_id == release.release_id


def test_evaluate_post_delivery_audit_missing_release_not_ready(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    # No manual release recorded yet -> audit evaluation must fail closed.
    out = evaluate_post_delivery_audit(
        authorization_id=auth.authorization_id, operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_NOT_FOUND"


def test_close_post_delivery_audit_success(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    out = close_post_delivery_audit(
        authorization_id=auth.authorization_id, operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert out.ok and out.audit is not None
    assert out.audit.closure_decision == AUDIT_CLOSED
    assert out.audit.revision_id == ctx["revision_id"]


def test_close_post_delivery_audit_idempotent(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    first = close_post_delivery_audit(authorization_id=auth.authorization_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert first.ok
    second = close_post_delivery_audit(authorization_id=auth.authorization_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert second.ok and second.duplicate_of == first.audit.audit_id
    events = [e for e in read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root)) if e.event_type == "POST_DELIVERY_AUDIT_CLOSED"]
    assert len(events) == 1


def test_close_post_delivery_audit_not_ready_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    out = close_post_delivery_audit(authorization_id=auth.authorization_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert not out.ok and out.error_code == "AUDIT_NOT_READY"


def test_record_manual_release_conflict_rejected(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    # A second manual release for the same authorization with different
    # content must be rejected (exactly one recorded release per authorization).
    out = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-2",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="cust-1", release_method_reference="different-share",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert (not out.ok) and out.error_code == "CONFLICTING_RELEASE"
    # The audit closure remains idempotent for the original release.
    close = close_post_delivery_audit(
        authorization_id=auth.authorization_id, operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert close.ok and close.audit.release_id == release.release_id


# ===========================================================================
# D. Lineage inspectability
# ===========================================================================
def test_inspect_complete_lineage(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    out = inspect_post_delivery_lineage(project_id=ctx["project_id"], repo_root=repo_root)
    assert out["project_id"] == ctx["project_id"]
    assert len(out["releases"]) == 1
    assert len(out["receipts"]) == 1
    assert "stage8e_lineage" in out


def test_audit_evidence_append_only(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    close_post_delivery_audit(authorization_id=auth.authorization_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    events = read_post_delivery_events(audit_log_path=post_delivery_audit_path(repo_root))
    types = [e.event_type for e in events]
    assert "MANUAL_RELEASE_RECORDED" in types
    assert "CUSTOMER_RECEIPT_CONFIRMED" in types
    assert "POST_DELIVERY_AUDIT_CLOSED" in types


# ===========================================================================
# E. Boundary: no direct HVS invocation / no outbound in source
# ===========================================================================
def test_no_direct_hvs_invocation_in_source():
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent
    for fname in (
        "hvs_manual_release_receipt_models.py",
        "hvs_manual_release_receipt_service.py",
    ):
        text = (src / fname).read_text(encoding="utf-8")
        for banned in ("hvs.cli", "import hvs", "from hvs", "subprocess", "requests", "urllib", "socket", "smtp", "os.system", "shell=True"):
            assert banned not in text, f"forbidden token {banned!r} present in {fname}"


def test_no_secret_fields_serialized(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    blob = release.to_dict()
    for banned in ("token", "secret", "password", "api_key", "credential"):
        assert banned not in blob, f"possible secret field {banned!r} in release record"


# ===========================================================================
# F. CLI behavior
# ===========================================================================
def _cli():
    from scos.control_center import cli

    return cli


def _point_cli_at(repo_root):
    cli = _cli()
    cli._repo_root = lambda: repo_root  # type: ignore[attr-defined]
    return cli


def test_cli_record_manual_release_success_exit0(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    cli = _point_cli_at(repo_root)
    rc = cli.main([
        "record-manual-release",
        "--authorization-id", auth.authorization_id,
        "--released-by", "operator-1",
        "--release-channel", "email_manual",
        "--released-formats", "vertical",
        "--customer-reference", "cust-1",
        "--release-method-reference", "manual-share-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_record_manual_release_rejection_exit1(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    cli = _point_cli_at(repo_root)
    rc = cli.main([
        "record-manual-release",
        "--authorization-id", "scos-hvs-release-auth-missing",
        "--released-by", "operator-1",
        "--release-channel", "email_manual",
        "--released-formats", "vertical",
        "--customer-reference", "cust-1",
        "--release-method-reference", "manual-share-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 1


def test_cli_close_post_delivery_audit_success_exit0(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    cli = _point_cli_at(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    rc = cli.main([
        "close-post-delivery-audit",
        "--authorization-id", auth.authorization_id,
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_malformed_usage_exit2(repo_root):
    cli = _point_cli_at(repo_root)
    rc = cli.main(["record-manual-release", "--released-by", "operator-1"])
    assert rc == 2


def test_cli_record_and_inspect_customer_receipt_exit0(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    cli = _point_cli_at(repo_root)
    rc = cli.main([
        "record-customer-receipt",
        "--release-id", release.release_id,
        "--confirmed-by", "cs-1",
        "--receipt-status", "CONFIRMED",
        "--received-formats", "vertical",
        "--customer-reference", "cust-1",
        "--confirmation-reference", "ticket-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0
    rc2 = cli.main([
        "inspect-customer-receipt",
        "--release-id", release.release_id,
    ])
    assert rc2 == 0


def test_cli_inspect_manual_release_exit0(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    cli = _point_cli_at(repo_root)
    rc = cli.main([
        "inspect-manual-release",
        "--authorization-id", auth.authorization_id,
    ])
    assert rc == 0


def test_cli_inspect_complete_lineage_exit0(repo_root):
    ctx, acc, auth, release = _released_context(repo_root)
    cli = _point_cli_at(repo_root)
    record_customer_receipt(
        release_id=release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    rc = cli.main([
        "inspect-complete-lineage",
        "--project-id", ctx["project_id"],
    ])
    assert rc == 0
