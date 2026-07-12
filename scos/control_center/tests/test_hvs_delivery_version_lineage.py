from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import create_approval_request, decide_approval
from scos.control_center.hvs_delivery_closure_models import SOURCE_EMAIL_OBSERVED
from scos.control_center.hvs_delivery_closure_service import (
    close_delivery,
    record_customer_receipt_evidence,
)
from scos.control_center.hvs_local_delivery_models import (
    CHANNEL_OTHER_MANUAL,
    DEL_DELIVERED_MANUALLY,
)
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


def _accepted_delivery(repo_root: Path, label: str = "one"):
    artifact = repo_root / f"artifact-{label}.bin"
    artifact.write_bytes((f"STAGE8A1-LINEAGE-ARTIFACT-{label}").encode("ascii") * 5)
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": f"packet-{repo_root.name}-{label}",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "project-stage8a1",
        "validation_id": f"validation-{repo_root.name}-{label}",
        "hvs": {
            "validation_id": f"validation-{repo_root.name}-{label}",
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
        statement_summary="Customer accepted the delivery.",
        recorded_at="t",
    )
    closure = close_delivery(
        receipt_evidence_id=receipt.receipt_evidence.receipt_evidence_id,
        repo_root=repo_root,
        operator_id="op",
        decision="accept",
        reason="Customer accepted the delivery.",
        recorded_at="t",
    )
    assert closure.ok
    return artifact, delivery.delivery_record, closure.closure


def test_legacy_completed_delivery_reports_unknown_lineage_without_inferred_version(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    service = import_module("scos.control_center.hvs_delivery_lineage_service")

    result = service.inspect_delivery_lineage(
        delivery_record_id=delivery.delivery_record_id,
        repo_root=repo_root,
    )

    assert result.ok is True
    assert result.lineage_status == "UNKNOWN"
    assert result.registered_version is None
    assert result.successor_planning_eligible is False
    assert result.blocking_reason == "DELIVERY_VERSION_UNKNOWN"
    assert result.to_dict()["registered_version"] is None


def test_unknown_lineage_blocks_successor_planning_without_persistence(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    service = import_module("scos.control_center.hvs_delivery_lineage_service")
    store = import_module("scos.control_center.hvs_delivery_lineage_store")

    planned = service.plan_successor_version(
        delivery_record_id=delivery.delivery_record_id,
        repo_root=repo_root,
    )

    assert planned.ok is False
    assert planned.error_code == "DELIVERY_VERSION_UNKNOWN"
    assert store.read_lineage_events(audit_log_path=store.lineage_audit_path(repo_root)) == ()


def test_delivery_version_rejects_non_positive_decimal_and_float_values():
    models = import_module("scos.control_center.hvs_delivery_lineage_models")

    assert models.DeliveryVersion.parse("v12").sequence == 12
    assert models.DeliveryVersion.parse("12").display == "v12"
    for value in (0, -1, 1.0, "1.0", "01", "v0", "v-1"):
        with pytest.raises(ValueError):
            models.DeliveryVersion.parse(value)


def test_registration_requires_operator_and_explicit_legacy_confirmation(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    service = import_module("scos.control_center.hvs_delivery_lineage_service")

    no_operator = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    unconfirmed = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=False,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    assert no_operator.error_code == "MISSING_OPERATOR_ID"
    assert unconfirmed.error_code == "LEGACY_VERSION_CONFIRMATION_REQUIRED"


def test_explicit_original_registration_is_idempotent_and_successor_planning_is_read_only(repo_root):
    artifact, delivery, closure = _accepted_delivery(repo_root)
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    service = import_module("scos.control_center.hvs_delivery_lineage_service")
    store = import_module("scos.control_center.hvs_delivery_lineage_store")
    request = models.DeliveryLineageRegistrationRequest(
        delivery_record_id=delivery.delivery_record_id,
        delivery_version=models.DeliveryVersion(1),
        operator_id="op",
        registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
        confirm_legacy_version=True,
    )
    before_delivery = delivery.to_dict()
    before_closure = closure.to_dict()
    before_artifact = artifact.read_bytes()

    first = service.register_delivery_lineage(request=request, repo_root=repo_root, recorded_at="t1")
    replay = service.register_delivery_lineage(request=request, repo_root=repo_root, recorded_at="t2")
    before_plan_events = store.read_lineage_events(audit_log_path=store.lineage_audit_path(repo_root))
    planned = service.plan_successor_version(delivery_record_id=delivery.delivery_record_id, repo_root=repo_root)

    assert first.ok and replay.ok
    assert first.lineage.lineage_id == replay.lineage.lineage_id
    assert first.lineage.delivery_version_display == "v1"
    assert first.lineage.supersession_status == "NOT_YET_SUPERSEDED"
    assert planned.ok and planned.successor_plan.planned_successor_version.display == "v2"
    assert planned.successor_plan.persistence_performed is False
    assert planned.successor_plan.rerender_started is False
    assert store.read_lineage_events(audit_log_path=store.lineage_audit_path(repo_root)) == before_plan_events
    assert delivery.to_dict() == before_delivery
    assert closure.to_dict() == before_closure
    assert artifact.read_bytes() == before_artifact


def test_conflicting_delivery_version_and_artifact_reuse_are_rejected(repo_root):
    _, first_delivery, _ = _accepted_delivery(repo_root, "first")
    _, second_delivery, _ = _accepted_delivery(repo_root, "second")
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    service = import_module("scos.control_center.hvs_delivery_lineage_service")
    first = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=first_delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    conflict = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=second_delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    assert first.ok
    assert conflict.ok is False
    assert conflict.error_code == "LINEAGE_CONFLICT"


def test_successor_registration_requires_parent_and_immediate_next_version(repo_root):
    _, first_delivery, _ = _accepted_delivery(repo_root, "first")
    _, second_delivery, _ = _accepted_delivery(repo_root, "second")
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    service = import_module("scos.control_center.hvs_delivery_lineage_service")
    first = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=first_delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    missing_parent = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=second_delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(2),
            operator_id="op",
            registration_basis=models.BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    successor = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=second_delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(2),
            operator_id="op",
            registration_basis=models.BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
            confirm_legacy_version=True,
            parent_lineage_id=first.lineage.lineage_id,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    assert missing_parent.error_code == "PARENT_LINEAGE_REQUIRED"
    assert successor.ok
    assert successor.lineage.parent_lineage_id == first.lineage.lineage_id
    assert successor.lineage.parent_delivery_version_sequence == 1


def test_store_rejects_path_traversal_and_malformed_or_duplicate_event_ids(repo_root):
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    store = import_module("scos.control_center.hvs_delivery_lineage_store")
    event = models.DeliveryLineageEvent(
        schema_version=models.DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION,
        event_id="event-1",
        event_type=models.EVT_LINEAGE_REGISTRATION_REJECTED,
        delivery_record_id="delivery-1",
        lineage_id=None,
        resulting_status="REJECTED",
        operator_id="op",
        recorded_at="t",
        automation_allowed=False,
        detail="test",
    )
    with pytest.raises(ValueError):
        store.read_lineage_events(audit_log_path=repo_root / ".." / "escape.jsonl")
    path = store.lineage_audit_path(repo_root)
    store.append_lineage_event(audit_log_path=path, event=event)
    assert store.append_lineage_event(audit_log_path=path, event=event) == event
    changed = models.DeliveryLineageEvent(**(event.to_dict() | {"detail": "different"}))
    with pytest.raises(ValueError):
        store.append_lineage_event(audit_log_path=path, event=changed)


def test_cli_inspect_registration_confirmation_and_successor_exit_codes(repo_root, monkeypatch, capsys):
    _, delivery, _ = _accepted_delivery(repo_root)
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    inspect_exit = cli_mod.main([
        "inspect-hvs-delivery-lineage",
        "--delivery-record-id", delivery.delivery_record_id,
    ])
    inspect_payload = capsys.readouterr().out
    unconfirmed_exit = cli_mod.main([
        "register-hvs-delivery-lineage",
        "--delivery-record-id", delivery.delivery_record_id,
        "--delivery-version", "1",
        "--registration-basis", "original_delivery_confirmed",
        "--operator-id", "op",
    ])
    unconfirmed_payload = capsys.readouterr().out
    planned_exit = cli_mod.main([
        "plan-hvs-successor-version",
        "--delivery-record-id", delivery.delivery_record_id,
    ])
    planned_payload = capsys.readouterr().out

    assert inspect_exit == 0
    assert '"lineage_status": "UNKNOWN"' in inspect_payload
    assert unconfirmed_exit == 1
    assert "LEGACY_VERSION_CONFIRMATION_REQUIRED" in unconfirmed_payload
    assert planned_exit == 1
    assert "DELIVERY_VERSION_UNKNOWN" in planned_payload


def test_verify_lineage_integrity_revalidates_registered_delivery(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    models = import_module("scos.control_center.hvs_delivery_lineage_models")
    service = import_module("scos.control_center.hvs_delivery_lineage_service")
    registered = service.register_delivery_lineage(
        request=models.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    verified = service.verify_lineage_integrity(
        lineage_id=registered.lineage.lineage_id,
        repo_root=repo_root,
    )

    assert verified.ok
    assert verified.lineage.lineage_id == registered.lineage.lineage_id
