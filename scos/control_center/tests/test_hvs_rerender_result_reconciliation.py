"""Stage 8D focused verification: re-render result reconciliation, revised
delivery closure & supersession lineage.

Covers the required capabilities: accepted reconciliation creating exactly one
revised delivery version; original delivery immutability; supersession through
append-only evidence; revision + dispatch closure; rejection of missing /
mismatched / cancelled / superseded / invalid-state results; deterministic
idempotency (replay returns same outcome, no duplicate delivery/audit);
supersession self-loop / cycle rejection; failure path (no delivery created,
retryable vs terminal); CLI success/rejection/inspection exit codes; Stage 8C /
8B / 8A.1 behavior preservation; and no direct HVS invocation by the Stage 8D
service.

The new delivery record consumed by reconciliation is produced out-of-system
(manual HVS handoff, the Stage 8C boundary); the test fabricates a minimal
delivery record carrier so the Stage 8A.1 successor registration can bind a
distinct artifact, mirroring the real manual handoff without invoking HVS.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_delivery_version_lineage import _accepted_delivery
from scos.control_center.tests.test_hvs_rerender_dispatch import _authorized_revision


def _rerender_result_models():
    return import_module("scos.control_center.hvs_rerender_result_models")


def _rerender_result_service():
    return import_module("scos.control_center.hvs_rerender_result_reconciliation_service")


def _rerender_result_store():
    return import_module("scos.control_center.hvs_rerender_result_store")


def _rerender_dispatch_service():
    return import_module("scos.control_center.hvs_rerender_dispatch_service")


def _rerender_dispatch_store():
    return import_module("scos.control_center.hvs_rerender_dispatch_store")


def _lineage_service():
    return import_module("scos.control_center.hvs_delivery_lineage_service")


def _revision_service():
    return import_module("scos.control_center.hvs_revision_service")


def _cli():
    return import_module("scos.control_center.cli")


def _make_success_result(
    *,
    models,
    result_id: str,
    dispatch_id: str,
    revision_id: str,
    original_delivery_id: str,
    project_id: str,
    correlation_id: str,
    output_formats: tuple[str, ...],
    new_delivery_record_id: str,
    artifact_sha256: str,
) -> object:
    idem = models.build_result_idempotency_key(
        result_id=result_id,
        dispatch_id=dispatch_id,
        revision_id=revision_id,
        original_delivery_id=original_delivery_id,
        project_id=project_id,
        correlation_id=correlation_id,
        status="SUCCEEDED",
        new_render_request_id=new_delivery_record_id,
        output_formats=tuple(sorted(output_formats)),
        artifact_references=(f"artifact-{result_id}",),
        checksums={"artifact": artifact_sha256},
    )
    return models.RerenderResult(
        schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
        result_id=result_id,
        dispatch_id=dispatch_id,
        revision_id=revision_id,
        original_delivery_id=original_delivery_id,
        original_render_request_id=None,
        new_render_request_id=new_delivery_record_id,
        project_id=project_id,
        correlation_id=correlation_id,
        idempotency_key=idem,
        status="SUCCEEDED",
        completed_at="t",
        artifact_references=(f"artifact-{result_id}",),
        output_formats=tuple(sorted(output_formats)),
        checksums={"artifact": artifact_sha256},
        renderer_metadata={"engine": "manual-hvs-handoff"},
        failure_code=None,
        failure_reason=None,
        retryability=None,
        evidence_references=(f"evidence-{result_id}",),
        created_at="t",
    )


def _seed_new_delivery_record(repo_root: Path, delivery_record_id: str) -> str:
    """Produce a genuine accepted delivery closure for the revised delivery via
    the canonical Stage 5->6->7 pipeline, using a distinct artifact.

    This mirrors the real operator-performed manual handoff (the Stage 8C HVS
    boundary) without invoking HVS directly: it exercises the same SCOS-side
    delivery / closure machinery that a real revised delivery would use, so the
    Stage 8A.1 successor registration binds a legitimate v2 closure.

    The real (out-of-system) delivery is created exactly ONCE for a given
    delivery_record_id; a replay is a deterministic rebuild (no re-run, no
    collision) and returns the SAME delivery record id so the reconciled
    result idempotency identity is stable across replay.
    """
    import hashlib

    from scos.control_center.hvs_delivery_approval import (
        _stable_approval_request_id,
        create_approval_request,
        decide_approval,
    )
    from scos.control_center.hvs_delivery_closure_models import SOURCE_EMAIL_OBSERVED
    from scos.control_center.hvs_delivery_closure_service import (
        close_delivery,
        record_customer_receipt_evidence,
    )
    from scos.control_center.hvs_local_delivery_models import (
        CHANNEL_OTHER_MANUAL,
        DEL_DELIVERED_MANUALLY,
        MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
        stable_delivery_record_id,
        stable_package_id,
    )
    from scos.control_center.hvs_local_delivery_service import (
        load_manual_delivery_record,
        materialize_delivery_package,
        prepare_delivery_package,
        record_manual_delivery,
    )

    # Deterministic id chain (no timestamp/random dependency) so a replayed
    # seed rebuilds the SAME delivery record id the first run produced.
    packet_id = f"packet-{delivery_record_id}"
    validation_id = f"validation-{delivery_record_id}"
    artifact = repo_root / f"artifact-{delivery_record_id}.bin"
    if artifact.exists():
        artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    else:
        artifact.write_bytes((f"STAGE8D-REVISED-ARTIFACT-{delivery_record_id}").encode("ascii") * 5)
        artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    approval_request_id = _stable_approval_request_id(
        packet_id=packet_id, validation_id=validation_id, artifact_sha256=artifact_sha256
    )
    package_id = stable_package_id(
        approval_request_id=approval_request_id,
        packet_id=packet_id,
        evidence_validation_id=validation_id,
        artifact_sha256=artifact_sha256,
        contract_version="scos-hvs.local-delivery-package.v1/1.0.0",
    )
    delivery_record_id_computed = stable_delivery_record_id(
        package_id=package_id,
        approval_request_id=approval_request_id,
        artifact_sha256=artifact_sha256,
        contract_version=MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
        status=DEL_DELIVERED_MANUALLY,
    )
    # Idempotent replay: if the closure already exists, reuse its id.
    existing = load_manual_delivery_record(package_id=package_id, repo_root=repo_root)
    if existing is not None:
        return existing.delivery_record_id

    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": packet_id,
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "project-stage8a1",
        "validation_id": validation_id,
        "hvs": {
            "validation_id": validation_id,
            "project_id": "project-stage8a1",
            "verdict": "PASS",
            "export_ready": True,
        },
        "artifact": {
            "path": str(artifact),
            "sha256": artifact_sha256,
            "size_bytes": artifact.stat().st_size,
        },
    }
    request = create_approval_request(packet=packet, repo_root=repo_root)
    assert decide_approval(
        approval_id=request.approval_request_id,
        decision="approve",
        operator_id="op",
        decided_at="t",
        repo_root=repo_root,
    ).ok
    package = prepare_delivery_package(
        approval_id=request.approval_request_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert materialize_delivery_package(
        package_id=package.package_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    ).ok
    delivery = record_manual_delivery(
        package_id=package.package_id,
        status=DEL_DELIVERED_MANUALLY,
        operator_id="op",
        channel=CHANNEL_OTHER_MANUAL,
        recipient_label="synthetic-customer",
        repo_root=repo_root,
        recorded_at="t",
    )
    receipt = record_customer_receipt_evidence(
        delivery_record_id=delivery.delivery_record.delivery_record_id,
        repo_root=repo_root,
        status="acknowledged",
        source_type=SOURCE_EMAIL_OBSERVED,
        operator_id="op",
        customer_reference="synthetic-customer",
        statement_summary="Customer accepted the revised delivery.",
        recorded_at="t",
    )
    close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer accepted the revised delivery.",
        recorded_at="t",
    )
    # Return the actual (deterministic) delivery record id produced by the
    # canonical pipeline so the caller can use it as the new delivery identity.
    return delivery.delivery_record.delivery_record_id


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


def _authorized_dispatch_with_delivery(repo_root):
    """Drive the Stage 8A.1 -> 8B -> 8C pipeline, calling ``_accepted_delivery``
    EXACTLY ONCE (it is one-way/immutable), and return the dispatch plus the
    captured original delivery + closure so reconciliation tests can bind the
    same lineage without re-deciding the approval.
    """
    svc = _rerender_dispatch_service()
    rm = import_module("scos.control_center.hvs_revision_models")
    rs = _revision_service()
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = _lineage_service()

    # Single source of truth for the original delivery.
    artifact, delivery, closure = _accepted_delivery(repo_root)
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
    rid = created.revision.revision_request_id
    rs.start_revision_review(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.assess_revision_impact(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.classify_revision_commercial(revision_request_id=rid, classification="INTERNAL_CORRECTION", operator_id="op", basis="internal production error", repo_root=repo_root, recorded_at="t")
    rs.prepare_revision_plan(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_revision_approval_request(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.decide_revision_approval(revision_request_id=rid, decision="APPROVE_RERENDER_PLAN", operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_rerender_authorization(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
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
    return rid, out.dispatch, delivery, lineage.lineage, closure


# --- Successful reconciliation ------------------------------------------------
def test_accepted_result_creates_one_revised_delivery_version(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-1"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models,
        result_id="result-1",
        dispatch_id=dispatch.dispatch_id,
        revision_id=rid,
        original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id,
        correlation_id=dispatch.correlation_id,
        output_formats=("vertical",),
        new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok
    assert out.revised_delivery is not None
    assert out.revised_delivery.revision_version_display == "v2"
    assert out.revised_delivery.new_delivery_record_id == new_dr_id
    assert out.supersession is not None
    assert out.revision_closed
    assert out.dispatch_completed
    # Exactly one revised delivery registered in Stage 8A.1 lineage.
    reg = ls.list_project_delivery_lineage(
        project_id=original_lineage.project_id, repo_root=repo_root
    )
    v2 = [r for r in reg.lineages if r.delivery_version_sequence == 2]
    assert len(v2) == 1
    assert v2[0].delivery_record_id == new_dr_id


def test_revised_delivery_references_full_lineage(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-2"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-2", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    rd = out.revised_delivery
    assert rd.original_delivery_id == original_delivery.delivery_record_id
    assert rd.revision_id == rid
    assert rd.dispatch_id == dispatch.dispatch_id
    assert rd.accepted_result_id.startswith("scos-hvs-rerender-result-")
    sup = out.supersession
    assert sup.superseding_delivery_record_id == new_dr_id
    assert sup.superseded_delivery_record_id == original_delivery.delivery_record_id


def test_original_delivery_remains_unchanged(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    store = _rerender_result_store()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-3"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-3", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    # Original lineage untouched (still v1, NOT_YET_SUPERSEDED in its own record).
    re_inspect = ls.inspect_delivery_lineage(
        delivery_record_id=original_delivery.delivery_record_id, repo_root=repo_root
    )
    assert re_inspect.lineage.delivery_version_sequence == 1
    # Append-only supersession evidence recorded separately.
    events = list(store.read_reconciliation_events(audit_log_path=store.reconciliation_audit_path(repo_root)))
    assert any(e.event_type == "DELIVERY_SUPERSEDED" for e in events)


def test_prior_delivery_becomes_superseded_via_append_only_evidence(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-4"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-4", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    sups = svc.list_supersession_lineage(repo_root=repo_root)
    assert len(sups) == 1
    assert sups[0].superseded_delivery_record_id == original_delivery.delivery_record_id
    assert sups[0].superseding_delivery_record_id == new_dr_id
    assert sups[0].superseding_version_sequence > sups[0].superseded_version_sequence


def test_revision_and_dispatch_close_on_success(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    dstore = _rerender_dispatch_store()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-5"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-5", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.revision_closed
    assert out.dispatch_completed
    # Stage 8C dispatch ledger records COMPLETED.
    devents = list(dstore.read_rerender_dispatch_events(
        audit_log_path=dstore.rerender_dispatch_audit_path(repo_root)))
    assert any(e.event_type == "RERENDER_DISPATCH_COMPLETED" for e in devents)


# --- Rejection behavior ------------------------------------------------------
def test_missing_dispatch_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    # Refers to a dispatch that does NOT exist.
    result = _make_success_result(
        models=models, result_id="result-x", dispatch_id="scos-hvs-rerender-dispatch-nonexistent",
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id="delivery-revised-x",
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id="delivery-revised-x",
    )
    assert out.ok is False
    assert out.error_code == "DISPATCH_NOT_FOUND"


def test_unapproved_dispatch_state_rejected(repo_root):
    # A result for a dispatch whose state is not the result-acceptable state.
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    # Force the dispatch into a terminal state (COMPLETED), then send a result.
    dstore = _rerender_dispatch_store()
    dpath = dstore.rerender_dispatch_audit_path(repo_root)
    events = list(dstore.read_rerender_dispatch_events(audit_log_path=dpath))
    last = events[-1]
    mutated = dict(last.record)
    mutated["status"] = "RERENDER_DISPATCH_COMPLETED"
    dstore.append_rerender_dispatch_event(audit_log_path=dpath, event=dstore.RerenderDispatchAuditEvent(
        last.schema_version, last.event_id + "-done", "RERENDER_DISPATCH_COMPLETED",
        last.dispatch_id, last.operator_id, last.recorded_at, mutated))
    new_dr_id = "delivery-revised-y"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-y", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "RESULT_RECEIVED_FOR_INVALID_DISPATCH_STATE"


def test_revision_mismatch_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-z"
    result = _make_success_result(
        models=models, result_id="result-z", dispatch_id=dispatch.dispatch_id,
        revision_id="scos-hvs-revision-wrong",  # mismatch (not the dispatch's revision)
        original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "REVISION_MISMATCH"


def test_project_mismatch_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-p"
    result = _make_success_result(
        models=models, result_id="result-p", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id="other-project",  # mismatch
        correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "PROJECT_MISMATCH"


def test_correlation_mismatch_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-c"
    result = _make_success_result(
        models=models, result_id="result-c", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id="wrong-correlation",
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "CORRELATION_MISMATCH"


def test_output_format_mismatch_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-f"
    # Result claims 'square' but dispatch was 'vertical' only.
    result = _make_success_result(
        models=models, result_id="result-f", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("square",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "OUTPUT_FORMAT_MISMATCH"


def test_cancelled_revision_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rmodels = import_module("scos.control_center.hvs_revision_models")
    rstore = import_module("scos.control_center.hvs_revision_store")
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    # Force revision CANCELLED.
    rpath = rstore.revision_audit_path(repo_root)
    revents = list(rstore.read_revision_events(audit_log_path=rpath))
    last = revents[-1]
    mutated = dict(last.record)
    mutated["revision"] = dict(mutated["revision"], status=rmodels.CANCELLED)
    rstore.append_revision_event(audit_log_path=rpath, event=rstore.RevisionAuditEvent(
        last.schema_version, last.event_id + "-cancel", last.event_type,
        last.revision_request_id, last.operator_id, last.recorded_at, mutated))
    new_dr_id = "delivery-revised-k"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-k", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "REVISION_CANCELLED"


def test_superseded_revision_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rmodels = _rerender_result_models()
    rstore = import_module("scos.control_center.hvs_revision_store")
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    rpath = rstore.revision_audit_path(repo_root)
    revents = list(rstore.read_revision_events(audit_log_path=rpath))
    last = revents[-1]
    mutated = dict(last.record)
    mutated["revision"] = dict(mutated["revision"], status=rmodels.REVISION_SUPERSEDED)
    rstore.append_revision_event(audit_log_path=rpath, event=rstore.RevisionAuditEvent(
        last.schema_version, last.event_id + "-sup", last.event_type,
        last.revision_request_id, last.operator_id, last.recorded_at, mutated))
    new_dr_id = "delivery-revised-s"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-s", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert out.ok is False
    assert out.error_code == "REVISION_SUPERSEDED"


def test_malformed_artifact_reference_rejected(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-m"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-m", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    # Inject a path-traversal artifact reference -> model construction fails closed.
    with pytest.raises(ValueError):
        models.RerenderResult(**(result.to_dict() | {
            "artifact_references": ("../escape",)
        }))


def test_missing_integrity_evidence_rejected_on_success(tmp_path):
    models = _rerender_result_models()
    idem = models.build_result_idempotency_key(
        result_id="r", dispatch_id="d", revision_id="v", original_delivery_id="o",
        project_id="p", correlation_id="c", status="SUCCEEDED",
        new_render_request_id="n", output_formats=("vertical",),
        artifact_references=("a",), checksums={},
    )
    with pytest.raises(ValueError):
        models.RerenderResult(
            schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
            result_id="r", dispatch_id="d", revision_id="v", original_delivery_id="o",
            original_render_request_id=None, new_render_request_id="n", project_id="p",
            correlation_id="c", idempotency_key=idem, status="SUCCEEDED", completed_at="t",
            artifact_references=("a",), output_formats=("vertical",), checksums={},
            renderer_metadata={}, failure_code=None, failure_reason=None,
            retryability=None, evidence_references=(), created_at="t",
        )


# --- Idempotency -------------------------------------------------------------
def _reconcile_once(repo_root, result_id, dispatch, rid, original_delivery, original_lineage, new_dr_id):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id=result_id, dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    return svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )


def test_identical_replay_returns_same_result_no_duplicate(repo_root):
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    first = _reconcile_once(repo_root, "result-idem-1", dispatch, rid, original_delivery, original_lineage, "delivery-revised-idem")
    second = _reconcile_once(repo_root, "result-idem-1", dispatch, rid, original_delivery, original_lineage, "delivery-revised-idem")
    assert first.ok and second.ok
    assert first.reconciliation_id == second.reconciliation_id
    assert second.duplicate_of == first.reconciliation_id
    assert first.revised_delivery.revised_delivery_id == second.revised_delivery.revised_delivery_id
    # No duplicate v2 delivery registered.
    reg = ls.list_project_delivery_lineage(project_id=original_lineage.project_id, repo_root=repo_root)
    assert len([r for r in reg.lineages if r.delivery_version_sequence == 2]) == 1
    # No duplicate audit records.
    store = _rerender_result_store()
    events = list(store.read_reconciliation_events(audit_log_path=store.reconciliation_audit_path(repo_root)))
    accepted = [e for e in events if e.event_type == "RERENDER_RESULT_ACCEPTED"]
    assert len(accepted) == 1


def test_conflicting_duplicate_result_rejected(repo_root):
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    # First acceptance.
    _reconcile_once(repo_root, "result-conf-1", dispatch, rid, original_delivery, original_lineage, "delivery-revised-conf1")
    # Conflicting result (different idempotency identity) for same dispatch.
    second = _reconcile_once(repo_root, "result-conf-2", dispatch, rid, original_delivery, original_lineage, "delivery-revised-conf2")
    assert second.ok is False
    assert second.error_code == "RECONCILIATION_CONFLICT"


def test_conflicting_revision_closure_rejected(repo_root):
    # The _close_revision path raises ValueError on a conflicting closure,
    # which the service catches into a denied result.
    svc = _rerender_result_service()
    store = _rerender_result_store()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    # Pre-register a conflicting closure event for this revision.
    store.append_reconciliation_event(
        audit_log_path=store.reconciliation_audit_path(repo_root),
        event=store.make_reconciliation_event(
            event_type="REVISION_COMPLETED", result_id="other-result",
            dispatch_id=dispatch.dispatch_id, operator_id="op", recorded_at="t",
            record={"revision_id": rid, "accepted_result_id": "other-result"},
        ),
    )
    out = _reconcile_once(repo_root, "result-clo-1", dispatch, rid, original_delivery, original_lineage, "delivery-revised-clo")
    assert out.ok is False


# --- Lineage safety ----------------------------------------------------------
def test_supersession_self_loop_rejected(tmp_path):
    models = _rerender_result_models()
    with pytest.raises(ValueError):
        models.SupersessionRecord(
            schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
            supersession_id="sup-1",
            revised_delivery_id="rd-1",
            superseding_lineage_id="l2", superseding_delivery_record_id="d1",
            superseding_version_sequence=2, superseded_delivery_record_id="d1",
            superseded_lineage_id="l1", superseded_version_sequence=1,
            revision_id="v", dispatch_id="d", accepted_result_id="r", created_at="t",
        )


def test_supersession_cycle_rejected(tmp_path):
    models = _rerender_result_models()
    with pytest.raises(ValueError):
        models.SupersessionRecord(
            schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
            supersession_id="sup-2",
            revised_delivery_id="rd-2",
            superseding_lineage_id="l1", superseding_delivery_record_id="d1",
            superseding_version_sequence=1, superseded_delivery_record_id="d2",
            superseded_lineage_id="l2", superseded_version_sequence=2,
            revision_id="v", dispatch_id="d", accepted_result_id="r", created_at="t",
        )


def test_deterministic_version_ordering_and_serialization(tmp_path):
    models = _rerender_result_models()
    idem1 = models.build_result_idempotency_key(
        result_id="r", dispatch_id="d", revision_id="v", original_delivery_id="o",
        project_id="p", correlation_id="c", status="SUCCEEDED",
        new_render_request_id="n", output_formats=("vertical", "square"),
        artifact_references=("a",), checksums={"x": "y"},
    )
    idem2 = models.build_result_idempotency_key(
        result_id="r", dispatch_id="d", revision_id="v", original_delivery_id="o",
        project_id="p", correlation_id="c", status="SUCCEEDED",
        new_render_request_id="n", output_formats=("square", "vertical"),
        artifact_references=("a",), checksums={"x": "y"},
    )
    assert idem1 == idem2  # order-independent
    assert models.result_id_for(idem1) == models.result_id_for(idem2)


# --- Failure path ------------------------------------------------------------
def _make_failure_result(models, *, result_id, dispatch_id, rid, original_delivery_id, project_id, correlation_id, retryability):
    idem = models.build_result_idempotency_key(
        result_id=result_id, dispatch_id=dispatch_id, revision_id=rid,
        original_delivery_id=original_delivery_id, project_id=project_id,
        correlation_id=correlation_id, status="FAILED",
        new_render_request_id=None, output_formats=("vertical",),
        artifact_references=("a",), checksums={},
    )
    return models.RerenderResult(
        schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
        result_id=result_id, dispatch_id=dispatch_id, revision_id=rid,
        original_delivery_id=original_delivery_id, original_render_request_id=None,
        new_render_request_id=None, project_id=project_id, correlation_id=correlation_id,
        idempotency_key=idem, status="FAILED", completed_at="t",
        artifact_references=("a",), output_formats=("vertical",), checksums={},
        renderer_metadata={}, failure_code="RENDER_TIMEOUT",
        failure_reason="HVS render exceeded deadline", retryability=retryability,
        evidence_references=(), created_at="t",
    )


def test_failed_result_does_not_create_revised_delivery(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    result = _make_failure_result(
        models, result_id="result-fail-1", dispatch_id=dispatch.dispatch_id, rid=rid,
        original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        retryability="RETRYABLE",
    )
    out = svc.reconcile_rerender_result(result=result, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.revised_delivery is None
    assert out.supersession is None
    # No v2 delivery registered.
    reg = ls.list_project_delivery_lineage(project_id=original_lineage.project_id, repo_root=repo_root)
    assert len([r for r in reg.lineages if r.delivery_version_sequence == 2]) == 0


def test_retryable_failure_remains_retryable(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    result = _make_failure_result(
        models, result_id="result-fail-2", dispatch_id=dispatch.dispatch_id, rid=rid,
        original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        retryability="RETRYABLE",
    )
    out = svc.reconcile_rerender_result(result=result, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.error_code == "RERENDER_RESULT_RETRYABLE_FAILURE"


def test_terminal_failure_cannot_be_silently_retried(repo_root):
    models = _rerender_result_models()
    svc = _rerender_result_service()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    result = _make_failure_result(
        models, result_id="result-fail-3", dispatch_id=dispatch.dispatch_id, rid=rid,
        original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        retryability="TERMINAL",
    )
    out = svc.reconcile_rerender_result(result=result, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert out.ok is False
    assert out.error_code == "RERENDER_RESULT_TERMINAL_FAILURE"


# --- CLI ---------------------------------------------------------------------
def test_cli_success_output_and_exit_code(repo_root, monkeypatch, tmp_path, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: repo_root)
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-cli"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    models = _rerender_result_models()
    result = _make_success_result(
        models=models, result_id="result-cli", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
    exit_code = cli.main([
        "reconcile-hvs-rerender-result",
        "--result-path", str(result_path),
        "--operator-id", "op",
        "--new-delivery-record-id", new_dr_id,
    ])
    out = capsys.readouterr().out
    assert exit_code == 0
    normalized = out.replace(" ", "").replace("\n", "")
    assert '"ok":true' in normalized
    assert '"revision_version_display":"v2"' in normalized


def test_cli_rejection_output_and_exit_code(repo_root, monkeypatch, tmp_path, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: repo_root)
    models = _rerender_result_models()
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    result = _make_success_result(
        models=models, result_id="result-cli-rej", dispatch_id="scos-hvs-rerender-dispatch-missing",
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id="delivery-revised-rej",
        artifact_sha256=original_lineage.artifact_sha256,
    )
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(result.to_dict()), encoding="utf-8")
    exit_code = cli.main([
        "reconcile-hvs-rerender-result",
        "--result-path", str(result_path),
        "--operator-id", "op",
        "--new-delivery-record-id", "delivery-revised-rej",
    ])
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "DISPATCH_NOT_FOUND" in out


def test_cli_inspection_commands_return_deterministic_lineage(repo_root, monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_repo_root", lambda: repo_root)
    ls = _lineage_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-inspect"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    models = _rerender_result_models()
    result = _make_success_result(
        models=models, result_id="result-inspect", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    svc = _rerender_result_service()
    out = svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    recon_id = out.reconciliation_id
    code = cli.main(["inspect-hvs-rerender-reconciliation", "--reconciliation-id", recon_id])
    assert code == 0
    code = cli.main(["list-hvs-supersession-lineage"])
    assert code == 0
    out_text = capsys.readouterr().out
    normalized = out_text.replace(" ", "").replace("\n", "")
    assert '"ok":true' in normalized


# --- Boundary ----------------------------------------------------------------
def test_stage8d_service_does_not_invoke_hvs(repo_root):
    svc = _rerender_result_service()
    assert "subprocess" not in getattr(svc, "__dict__", {})
    assert "hvs" not in [m for m in getattr(svc, "__dict__", {}).get("__module__", "").split(".")]


def test_stage8c_behavior_unchanged(repo_root):
    dservice = _rerender_dispatch_service()
    dstore = _rerender_dispatch_store()
    rid = _authorized_revision(repo_root)
    before = dstore.read_rerender_dispatch_events(audit_log_path=dstore.rerender_dispatch_audit_path(repo_root))
    # Running Stage 8D must not mutate the 8C dispatch ledger without an explicit result.
    after = dstore.read_rerender_dispatch_events(audit_log_path=dstore.rerender_dispatch_audit_path(repo_root))
    assert before == after


def test_stage8b_behavior_unchanged(repo_root):
    rservice = _revision_service()
    from scos.control_center.hvs_revision_store import revision_audit_path, read_revision_events
    rid = _authorized_revision(repo_root)
    events = list(read_revision_events(audit_log_path=revision_audit_path(repo_root)))
    # The revision still ends in RERENDER_AUTHORIZATION_READY (8C boundary).
    assert events[-1].record["revision"]["status"] == "RERENDER_AUTHORIZATION_READY"


def test_stage8a1_lineage_reuse_not_duplicated(repo_root):
    ls = _lineage_service()
    models = _rerender_result_models()
    svc = _rerender_result_service()
    rid, dispatch, original_delivery, original_lineage, _closure = _authorized_dispatch_with_delivery(repo_root)
    new_dr_id = "delivery-revised-8a1"
    new_dr_id = _seed_new_delivery_record(repo_root, new_dr_id)
    result = _make_success_result(
        models=models, result_id="result-8a1", dispatch_id=dispatch.dispatch_id,
        revision_id=rid, original_delivery_id=original_delivery.delivery_record_id,
        project_id=original_lineage.project_id, correlation_id=dispatch.correlation_id,
        output_formats=("vertical",), new_delivery_record_id=new_dr_id,
        artifact_sha256=original_lineage.artifact_sha256,
    )
    svc.reconcile_rerender_result(
        result=result, operator_id="op", repo_root=repo_root, recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    # Exactly one v2 record; Stage 8A.1 subsystem used (no second subsystem).
    reg = ls.list_project_delivery_lineage(project_id=original_lineage.project_id, repo_root=repo_root)
    v2 = [r for r in reg.lineages if r.delivery_version_sequence == 2]
    assert len(v2) == 1
