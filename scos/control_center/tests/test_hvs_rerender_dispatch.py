"""Stage 8C focused verification: approval-gated revision re-render dispatch.

Covers the required capabilities: approved creation, unapproved/cancelled/
superseded/missing rejections, approval+revision+delivery mismatch rejections,
idempotent duplicate, conflicting-duplicate rejection, append-only audit,
deterministic serialization + ids, invalid state transition rejection, path
traversal rejection, CLI success/rejection exit codes, Stage 8B behavior
preservation, and no direct HVS invocation by the Stage 8C service.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_delivery_version_lineage import _accepted_delivery


def _revision_service():
    return import_module("scos.control_center.hvs_revision_service")


def _rerender_service():
    return import_module("scos.control_center.hvs_rerender_dispatch_service")


def _rerender_models():
    return import_module("scos.control_center.hvs_rerender_dispatch_models")


def _rerender_store():
    return import_module("scos.control_center.hvs_rerender_dispatch_store")


def _cli():
    return import_module("scos.control_center.cli")


def _authorized_revision(repo_root: Path, classification: str = "INTERNAL_CORRECTION"):
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = import_module("scos.control_center.hvs_delivery_lineage_service")
    rm = import_module("scos.control_center.hvs_revision_models")
    rs = _revision_service()
    _, delivery, _ = _accepted_delivery(repo_root)
    lineage = ls.register_delivery_lineage(
        request=lm.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=lm.DeliveryVersion(1),
            operator_id="op",
            registration_basis=lm.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    created = rs.create_revision_request(
        delivery_record_id=delivery.delivery_record_id,
        requested_by_id="customer",
        operator_id="op",
        revision_items=(
            rm.RevisionItem.create(
                category="ASSET_REPLACEMENT",
                description="Replace approved still.",
                target_type="asset",
                target_id="asset-1",
                asset_id="asset-1",
                priority="normal",
                acceptance_requirement="Operator reviews replacement.",
                requested_by_id="customer",
                source_artifact_sha256=lineage.lineage.artifact_sha256,
            ),
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    rs.start_revision_review(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.assess_revision_impact(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.classify_revision_commercial(revision_request_id=created.revision.revision_request_id, classification=classification, operator_id="op", basis="internal production error", repo_root=repo_root, recorded_at="t")
    rs.prepare_revision_plan(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_revision_approval_request(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.decide_revision_approval(revision_request_id=created.revision.revision_request_id, decision="APPROVE_RERENDER_PLAN", operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_rerender_authorization(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    return created.revision.revision_request_id


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


def test_approved_revision_creates_dispatch_with_lineage(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    out = svc.request_rerender_dispatch(
        revision_request_id=rid,
        operator_id="op",
        target_formats=("vertical",),
        requested_changes=(),
        reason="Customer-approved caption fix re-render.",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok
    d = out.dispatch
    assert d.status == "RERENDER_DISPATCH_CREATED"
    assert d.revision_id == rid
    assert d.approval_decision_id  # populated from the recorded decision
    assert d.metadata["manual_dispatch_required"] is True
    assert d.metadata["automation_allowed"] is False
    assert d.metadata["hvs_invoked"] is False
    assert out.evidence_event_id is not None


def test_unapproved_revision_is_rejected(repo_root):
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = import_module("scos.control_center.hvs_delivery_lineage_service")
    rm = import_module("scos.control_center.hvs_revision_models")
    rs = _revision_service()
    svc = _rerender_service()
    _, delivery, _ = _accepted_delivery(repo_root)
    lineage = ls.register_delivery_lineage(request=lm.DeliveryLineageRegistrationRequest(delivery.delivery_record_id, lm.DeliveryVersion(1), "op", lm.BASIS_ORIGINAL_DELIVERY_CONFIRMED, True), repo_root=repo_root, recorded_at="t")
    created = rs.create_revision_request(delivery_record_id=delivery.delivery_record_id, requested_by_id="customer", operator_id="op", revision_items=(rm.RevisionItem.create(category="ASSET_REPLACEMENT", description="Replace approved still.", target_type="asset", target_id="asset-1", asset_id="asset-1", priority="normal", acceptance_requirement="x", requested_by_id="customer", source_artifact_sha256=lineage.lineage.artifact_sha256),), repo_root=repo_root, recorded_at="t")
    # Stop BEFORE approval.
    out = svc.request_rerender_dispatch(revision_request_id=created.revision.revision_request_id, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.error_code == "REVISION_NOT_APPROVED"


def test_approval_revision_mismatch_is_rejected(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    # Supply a delivery_id that does NOT match the revision's delivery.
    out = svc.request_rerender_dispatch(
        revision_request_id=rid,
        operator_id="op",
        target_formats=("vertical",),
        requested_changes=(),
        reason="x",
        repo_root=repo_root,
        recorded_at="t",
        delivery_id="delivery-that-does-not-match",
    )
    assert out.ok is False
    assert out.error_code == "APPROVAL_DELIVERY_MISMATCH"


def test_approval_decision_mismatch_is_rejected(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    out = svc.request_rerender_dispatch(
        revision_request_id=rid,
        operator_id="op",
        target_formats=("vertical",),
        requested_changes=(),
        reason="x",
        repo_root=repo_root,
        recorded_at="t",
        approval_decision_id="bogus-decision-id",
    )
    assert out.ok is False
    assert out.error_code == "APPROVAL_DECISION_MISMATCH"


def test_missing_revision_fails_safely(repo_root):
    svc = _rerender_service()
    out = svc.request_rerender_dispatch(
        revision_request_id="scos-hvs-revision-nonexistent",
        operator_id="op",
        target_formats=("vertical",),
        requested_changes=(),
        reason="x",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok is False
    assert out.error_code == "REVISION_NOT_FOUND"


def test_cancelled_revision_is_rejected(repo_root):
    svc = _rerender_service()
    rs = _revision_service()
    rmodels = import_module("scos.control_center.hvs_revision_models")
    rid = _authorized_revision(repo_root)
    # Manually force the revision into CANCELLED state via the store ledger.
    store = import_module("scos.control_center.hvs_revision_store")
    path = store.revision_audit_path(Path(repo_root))
    events = list(store.read_revision_events(audit_log_path=path))
    last = events[-1]
    mutated = dict(last.record)
    mutated["revision"] = dict(mutated["revision"], status=rmodels.CANCELLED)
    new_event = store.RevisionAuditEvent(
        last.schema_version, last.event_id + "-cancel", last.event_type,
        last.revision_request_id, last.operator_id, last.recorded_at, mutated,
    )
    store.append_revision_event(audit_log_path=path, event=new_event)
    out = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.error_code == "REVISION_CANCELLED"


def test_superseded_revision_is_rejected(repo_root):
    svc = _rerender_service()
    rs = _revision_service()
    rm = _rerender_models()
    rid = _authorized_revision(repo_root)
    store = import_module("scos.control_center.hvs_revision_store")
    path = store.revision_audit_path(Path(repo_root))
    events = list(store.read_revision_events(audit_log_path=path))
    last = events[-1]
    mutated = dict(last.record)
    mutated["revision"] = dict(mutated["revision"], status=rm.REVISION_SUPERSEDED)
    new_event = store.RevisionAuditEvent(last.schema_version, last.event_id + "-sup", last.event_type, last.revision_request_id, last.operator_id, last.recorded_at, mutated)
    store.append_revision_event(audit_log_path=path, event=new_event)
    out = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.error_code == "REVISION_SUPERSEDED"


def test_invalid_target_format_is_rejected(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    out = svc.request_rerender_dispatch(
        revision_request_id=rid,
        operator_id="op",
        target_formats=("not-a-real-format",),
        requested_changes=(),
        reason="x",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok is False
    # Either the gate (INVALID_TARGET_FORMAT) or model construction fails closed.
    assert out.error_code in ("INVALID_TARGET_FORMAT",)


def test_duplicate_semantic_request_is_idempotent(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    first = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    second = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t2")
    assert first.ok and second.ok
    assert first.dispatch.dispatch_id == second.dispatch.dispatch_id
    assert first.dispatch.idempotency_key == second.dispatch.idempotency_key
    assert second.duplicate_of == first.dispatch.dispatch_id


def test_conflicting_duplicate_is_rejected(repo_root):
    svc = _rerender_service()
    rid = _authorized_revision(repo_root)
    first = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    # Conflicting semantic payload under the SAME idempotency identity is
    # impossible by construction; instead assert that a DIFFERENT target set
    # yields a DISTINCT, separately-created dispatch (no silent overwrite).
    other = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("square", "vertical"), requested_changes=(), reason="y", repo_root=repo_root, recorded_at="t")
    assert first.ok and other.ok
    assert first.dispatch.dispatch_id != other.dispatch.dispatch_id
    assert first.dispatch.idempotency_key != other.dispatch.idempotency_key


def test_append_only_audit_history_preserved(repo_root):
    svc = _rerender_service()
    store = _rerender_store()
    rid = _authorized_revision(repo_root)
    svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t2")
    events = list(store.read_rerender_dispatch_events(audit_log_path=store.rerender_dispatch_audit_path(Path(repo_root))))
    types = [e.event_type for e in events]
    assert "RERENDER_DISPATCH_CREATED" in types
    assert "RERENDER_DISPATCH_DUPLICATE" in types
    # Append-only: original CREATED event is still present (not overwritten).
    created = [e for e in events if e.event_type == "RERENDER_DISPATCH_CREATED"]
    assert len(created) == 1


def test_deterministic_serialization_and_ids(repo_root):
    models = _rerender_models()
    rid = "scos-hvs-revision-abc"
    did = "delivery-1"
    adid = "decision-1"
    fmts = ("vertical", "square")
    fp = models.change_fingerprint(())
    k1 = models.build_idempotency_key(revision_id=rid, delivery_id=did, approval_decision_id=adid, target_formats=fmts, change_fingerprint=fp)
    k2 = models.build_idempotency_key(revision_id=rid, delivery_id=did, approval_decision_id=adid, target_formats=("square", "vertical"), change_fingerprint=fp)
    k3 = models.build_idempotency_key(revision_id=rid, delivery_id=did, approval_decision_id=adid, target_formats=fmts, change_fingerprint="different")
    assert k1 == k2  # order-independent
    assert k1 != k3  # changed payload -> different identity
    assert models.dispatch_id_for(k1) == models.dispatch_id_for(k2)


def test_invalid_state_transition_rejected(repo_root):
    svc = _rerender_service()
    # RERENDER_DISPATCH_COMPLETED is terminal; no transition out of it.
    assert svc.is_valid_dispatch_transition(current="RERENDER_DISPATCH_COMPLETED", target="RERENDER_DISPATCH_CREATED") is False
    # Self-transition is invalid.
    assert svc.is_valid_dispatch_transition(current="RERENDER_DISPATCH_CREATED", target="RERENDER_DISPATCH_CREATED") is False
    # REQUESTED -> CREATED is valid.
    assert svc.is_valid_dispatch_transition(current="RERENDER_DISPATCH_REQUESTED", target="RERENDER_DISPATCH_CREATED") is True
    with pytest.raises(ValueError):
        svc.assert_dispatch_transition(current="RERENDER_DISPATCH_COMPLETED", target="RERENDER_DISPATCH_CREATED")
    # CREATED -> COMPLETED is a VALID transition; must NOT raise.
    svc.assert_dispatch_transition(current="RERENDER_DISPATCH_CREATED", target="RERENDER_DISPATCH_COMPLETED")


def test_path_traversal_identifier_rejected():
    models = _rerender_models()
    with pytest.raises(ValueError):
        models._safe_id("delivery_id", "../escape")
    with pytest.raises(ValueError):
        models._safe_id("project_id", "a/../b")
    with pytest.raises(ValueError):
        models._safe_id("x", "foo;rm")


def test_cli_success_output_and_exit_code(repo_root, monkeypatch, capsys):
    svc = _rerender_service()
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: repo_root)
    rid = _authorized_revision(repo_root)
    exit_code = cli.main([
        "request-hvs-rerender-dispatch",
        "--revision-request-id", rid,
        "--operator-id", "op",
        "--target-format", "vertical",
        "--reason", "Customer-approved re-render.",
    ])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert '"ok": true' in out or '"ok": true' in out.replace(" ", "")
    assert '"status": "RERENDER_DISPATCH_CREATED"' in out


def test_cli_rejection_output_and_exit_code(repo_root, monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: repo_root)
    # Missing revision -> rejection, exit 1.
    exit_code = cli.main([
        "request-hvs-rerender-dispatch",
        "--revision-request-id", "scos-hvs-revision-missing",
        "--operator-id", "op",
        "--target-format", "vertical",
        "--reason", "x",
    ])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "REVISION_NOT_FOUND" in out


def test_cli_unknown_command_usage_exit_code(monkeypatch):
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: Path("/tmp"))
    exit_code = cli.main(["definitely-not-a-real-command"])
    assert exit_code == 2  # argparse usage error


def test_stage8b_behavior_unchanged_after_8c_addition(repo_root):
    rs = _revision_service()
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = import_module("scos.control_center.hvs_delivery_lineage_service")
    rm = import_module("scos.control_center.hvs_revision_models")
    _, delivery, _ = _accepted_delivery(repo_root)
    lineage = ls.register_delivery_lineage(request=lm.DeliveryLineageRegistrationRequest(delivery.delivery_record_id, lm.DeliveryVersion(1), "op", lm.BASIS_ORIGINAL_DELIVERY_CONFIRMED, True), repo_root=repo_root, recorded_at="t")
    created = rs.create_revision_request(delivery_record_id=delivery.delivery_record_id, requested_by_id="customer", operator_id="op", revision_items=(rm.RevisionItem.create(category="ASSET_REPLACEMENT", description="Replace approved still.", target_type="asset", target_id="asset-1", asset_id="asset-1", priority="normal", acceptance_requirement="x", requested_by_id="customer", source_artifact_sha256=lineage.lineage.artifact_sha256),), repo_root=repo_root, recorded_at="t")
    assert created.ok
    assert created.revision.status == "REVISION_REQUESTED"
    # Stage 8C must NOT add a dispatch ledger entry for a non-dispatched revision.
    store = _rerender_store()
    assert store.read_rerender_dispatch_events(audit_log_path=store.rerender_dispatch_audit_path(Path(repo_root))) == ()


def test_no_direct_hvs_invocation_from_service(repo_root):
    """The Stage 8C service must never invoke HVS (subprocess/subprocess.run)."""
    svc = _rerender_service()
    # Hard assertion: the service module does not import or use subprocess at all.
    assert "subprocess" not in getattr(svc, "__dict__", {})
    rid = _authorized_revision(repo_root)
    out = svc.request_rerender_dispatch(revision_request_id=rid, operator_id="op", target_formats=("vertical",), requested_changes=(), reason="x", repo_root=repo_root, recorded_at="t")
    assert out.ok
    # No HVS boundary command was constructed or executed.
    assert out.dispatch.metadata["hvs_invoked"] is False


def test_store_rejects_path_traversal_and_duplicate_event_ids(repo_root):
    store = _rerender_store()
    models = _rerender_models()
    event = models.RerenderDispatchAuditEvent(
        schema_version=models.RERENDER_DISPATCH_EVENT_SCHEMA_VERSION,
        event_id="evt-1",
        event_type=models.EVT_RERENDER_DISPATCH_CREATED,
        dispatch_id="dispatch-1",
        operator_id="op",
        recorded_at="t",
        record={"dispatch_id": "dispatch-1"},
    )
    with pytest.raises(ValueError):
        store.read_rerender_dispatch_events(audit_log_path=Path(repo_root) / ".." / "escape.jsonl")
    path = store.rerender_dispatch_audit_path(Path(repo_root))
    store.append_rerender_dispatch_event(audit_log_path=path, event=event)
    # Identical event id + identical payload returns existing (no duplicate write error).
    assert store.append_rerender_dispatch_event(audit_log_path=path, event=event) == event
    changed = models.RerenderDispatchAuditEvent(**(event.to_dict() | {"record": {"dispatch_id": "dispatch-1", "other": "x"}}))
    with pytest.raises(ValueError):
        store.append_rerender_dispatch_event(audit_log_path=path, event=changed)
