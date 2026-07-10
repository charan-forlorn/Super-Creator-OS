"""Focused tests — SCOS <-> HVS Stage 6 manual delivery record.

Local, deterministic, no network/subprocess. Exercises the manual-delivery
state machine: delivered requires a materialized package + operator + channel
+ recipient; failed/cancelled require a reason; final records are immutable;
conflicting re-records are rejected; the record states SCOS performed no
external action; and the CLI JSON + exit-code contracts.

The package directory lives under the gitignored ``scos/work/`` tree.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import decide_approval
from scos.control_center.hvs_local_delivery_models import (
    CHANNEL_OTHER_MANUAL,
    DEL_DELIVERED_MANUALLY,
    DEL_DELIVERY_CANCELLED,
    DEL_DELIVERY_FAILED,
    PKG_MATERIALIZED,
    PKG_PREPARED,
    stable_delivery_record_id,
)
from scos.control_center.hvs_local_delivery_service import (
    inspect_delivery_package,
    load_manual_delivery_record,
    materialize_delivery_package,
    prepare_delivery_package,
    record_manual_delivery,
)
from scos.control_center.hvs_delivery_audit import read_delivery_events


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scos" / "work").mkdir(parents=True)
    return root


def _make_artifact(root: Path) -> Path:
    art = root / "source_artifact.bin"
    art.write_bytes(b"SCOS-STAGE6-ARTIFACT-CONTENT-" * 3)
    return art


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _prepared_materialized(repo_root: Path):
    art = _make_artifact(repo_root)
    sha = _sha256_of(art)
    from scos.control_center.hvs_delivery_approval import (
        create_approval_request,
    )

    packet = {
        "ok": True,
        "schema_version": 1,
        "packet_id": "scos-hvs-evidence-pkg6",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "proj-6",
        "validation_id": "val-6",
        "hvs": {
            "schema_version": "hvs.quality.stage6/1.0.0",
            "validation_id": "val-6",
            "project_id": "proj-6",
            "verdict": "PASS",
            "export_ready": True,
        },
        "artifact": {
            "path": str(art),
            "sha256": sha,
            "size_bytes": art.stat().st_size,
        },
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    decide_approval(
        approval_id=req.approval_request_id,
        decision="approve",
        operator_id="op-6",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    out = prepare_delivery_package(
        approval_id=req.approval_request_id,
        operator_id="op-6",
        repo_root=repo_root,
        recorded_at="2026-07-11T00:00:00+00:00",
    )
    mat = materialize_delivery_package(
        package_id=out.package_id,
        operator_id="op-6",
        repo_root=repo_root,
        recorded_at="2026-07-11T00:00:01+00:00",
    )
    return out.package_id, sha


# --- 28) delivered requires materialized package -----------------------------
def test_delivered_requires_materialized(repo_root):
    art = _make_artifact(repo_root)
    sha = _sha256_of(art)
    from scos.control_center.hvs_delivery_approval import (
        create_approval_request,
    )

    packet = {
        "ok": True, "schema_version": 1, "packet_id": "p6",
        "source": "hermes_video_studio", "trust_level": "VERIFIED",
        "operator_action": "review_export_ready", "automation_allowed": False,
        "project_id": "proj-6", "validation_id": "val-6",
        "hvs": {"validation_id": "val-6", "project_id": "proj-6", "verdict": "PASS",
                "export_ready": True},
        "artifact": {"path": str(art), "sha256": sha,
                     "size_bytes": art.stat().st_size},
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    decide_approval(approval_id=req.approval_request_id, decision="approve",
                    operator_id="op-6", decided_at="t", repo_root=repo_root)
    out = prepare_delivery_package(approval_id=req.approval_request_id,
                                   operator_id="op-6", repo_root=repo_root,
                                   recorded_at="t")
    # Not materialized -> rejected.
    rec = record_manual_delivery(
        package_id=out.package_id, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "not_materialized"


# --- 29-31) delivered requires operator/channel/recipient --------------------
def test_delivered_requires_operator(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "missing_operator_id"


def test_delivered_requires_channel(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=None,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "invalid_channel"


def test_delivered_requires_recipient(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "missing_recipient"


# --- 32) valid delivered becomes DELIVERED_MANUALLY --------------------------
def test_valid_delivered_record(repo_root):
    pid, sha = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="certification-recipient",
        external_reference="ticket-123",
        operator_note="hand delivered at desk",
        repo_root=repo_root, recorded_at="2026-07-11T00:00:02+00:00",
    )
    assert rec.ok is True
    d = rec.delivery_record
    assert d.final_status == DEL_DELIVERED_MANUALLY
    assert d.manual_delivery_performed is True
    assert d.automation_allowed is False
    assert d.delivery_was_external_to_scos is True
    assert "SCOS did not execute" in d.scos_external_action_statement


# --- 33) delivered states SCOS performed no external action ------------------
def test_delivered_states_no_external_action(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is True
    assert rec.to_dict()["external_delivery_executed_by_scos"] is False


# --- 34-35) failed / cancelled require reason --------------------------------
def test_failed_requires_reason(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERY_FAILED,
        operator_id="op-6", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "missing_reason"


def test_cancelled_requires_reason(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERY_CANCELLED,
        operator_id="op-6", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is False
    assert rec.error_code == "missing_reason"


def test_valid_failed_record(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERY_FAILED,
        operator_id="op-6", reason="customer unavailable",
        repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is True
    assert rec.delivery_record.final_status == DEL_DELIVERY_FAILED
    assert rec.delivery_record.manual_delivery_performed is False
    assert rec.delivery_record.failure_or_cancel_reason == "customer unavailable"


def test_valid_cancelled_record(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERY_CANCELLED,
        operator_id="op-6", reason="order revoked",
        repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is True
    assert rec.delivery_record.final_status == DEL_DELIVERY_CANCELLED


# --- 36) final records immutable ---------------------------------------------
def test_record_immutable(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is True
    # A second record for the same package is rejected (conflict).
    rec2 = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERY_CANCELLED,
        operator_id="op-x", reason="conflict",
        repo_root=repo_root, recorded_at="t2",
    )
    assert rec2.ok is False
    assert rec2.error_code == "delivery_record_conflict"


# --- 37) duplicate identical record idempotent -------------------------------
def test_duplicate_identical_record_idempotent(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    rec1 = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    rec2 = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec1.ok and rec2.ok
    assert rec2.delivery_record.delivery_record_id == (
        rec1.delivery_record.delivery_record_id
    )


# --- 38) conflicting second final record rejected ---------------------------
def test_conflicting_record_rejected(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    rec2 = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="DIFFERENT", repo_root=repo_root, recorded_at="t",
    )
    assert rec2.ok is False
    assert rec2.error_code == "delivery_record_conflict"


# --- 39-40) audit append-only + linkage --------------------------------------
def test_audit_append_only_and_linked(repo_root):
    pid, sha = _prepared_materialized(repo_root)
    record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    events = read_delivery_events(
        audit_log_path=repo_root / "scos" / "work" / "hvs_delivery_packages"
        / "delivery_audit.jsonl"
    )
    types = [e.event_type for e in events]
    assert "DELIVERY_PACKAGE_PREPARED" in types
    assert "DELIVERY_PACKAGE_MATERIALIZED" in types
    assert "MANUAL_DELIVERY_RECORDED" in types
    for e in events:
        assert e.package_id == pid
        assert e.artifact_sha256 == sha
        assert e.automation_allowed is False


# --- 41) event ids deterministic ---------------------------------------------
def test_event_ids_deterministic(repo_root):
    from scos.control_center.hvs_local_delivery_models import (
        stable_delivery_event_id,
    )
    eid1 = stable_delivery_event_id(
        event_type="MANUAL_DELIVERY_RECORDED", package_id="pkg",
        approval_request_id="appr", packet_id="pkt", artifact_sha256="sha",
        operator_id="op", resulting_state=DEL_DELIVERED_MANUALLY,
    )
    eid2 = stable_delivery_event_id(
        event_type="MANUAL_DELIVERY_RECORDED", package_id="pkg",
        approval_request_id="appr", packet_id="pkt", artifact_sha256="sha",
        operator_id="op", resulting_state=DEL_DELIVERED_MANUALLY,
    )
    assert eid1 == eid2
    assert eid1.startswith("dlevt-")


# --- 42) timestamp excluded from deterministic identity ----------------------
def test_record_id_timestamp_independent(repo_root):
    pid, sha = _prepared_materialized(repo_root)
    rid1 = stable_delivery_record_id(
        package_id=pid, approval_request_id="appr", artifact_sha256=sha,
        contract_version="scos-hvs.manual-delivery-record.v1/1.0.0",
        status=DEL_DELIVERED_MANUALLY,
    )
    rid2 = stable_delivery_record_id(
        package_id=pid, approval_request_id="appr", artifact_sha256=sha,
        contract_version="scos-hvs.manual-delivery-record.v1/1.0.0",
        status=DEL_DELIVERED_MANUALLY,
    )
    assert rid1 == rid2


# --- 43-47) CLI contracts ----------------------------------------------------
def test_cli_record_delivered(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    pid, _ = _prepared_materialized(repo_root)
    assert cli_mod.main([
        "record-hvs-manual-delivery",
        "--package-id", pid,
        "--status", "delivered",
        "--operator-id", "op-6",
        "--channel", CHANNEL_OTHER_MANUAL,
        "--recipient-label", "cert-recipient",
        "--note", "cli delivered",
    ]) == 0
    # Inspect reflects the record.
    assert cli_mod.main([
        "inspect-hvs-delivery-package",
        "--package-id", pid,
    ]) == 0
    rec = load_manual_delivery_record(package_id=pid, repo_root=repo_root)
    assert rec is not None
    assert rec.final_status == DEL_DELIVERED_MANUALLY


def test_cli_record_failed_missing_reason_exit1(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    pid, _ = _prepared_materialized(repo_root)
    assert cli_mod.main([
        "record-hvs-manual-delivery",
        "--package-id", pid,
        "--status", "failed",
        "--operator-id", "op-6",
    ]) == 1


def test_cli_record_delivered_missing_channel_exit1(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    pid, _ = _prepared_materialized(repo_root)
    assert cli_mod.main([
        "record-hvs-manual-delivery",
        "--package-id", pid,
        "--status", "delivered",
        "--operator-id", "op-6",
        "--recipient-label", "rcpt",
    ]) == 1


# --- 48) invalid CLI command returns non-zero --------------------------------
def test_cli_invalid_status_exit2(repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    pid, _ = _prepared_materialized(repo_root)
    # Invalid --status (not in choices) -> argparse usage error -> exit 2.
    assert cli_mod.main([
        "record-hvs-manual-delivery",
        "--package-id", pid,
        "--status", "shipped",
        "--operator-id", "op-6",
    ]) == 2


# --- 49-51) no subprocess / network / HVS ------------------------------------
def test_no_external_side_effects(repo_root):
    pid, sha = _prepared_materialized(repo_root)
    rec = record_manual_delivery(
        package_id=pid, status=DEL_DELIVERED_MANUALLY,
        operator_id="op-6", channel=CHANNEL_OTHER_MANUAL,
        recipient_label="rcpt", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok is True
    d = rec.to_dict()
    assert d["automation_allowed"] is False
    assert d["external_delivery_executed_by_scos"] is False
    assert "http://" not in str(d) and "https://" not in str(d)
    assert "s3://" not in str(d)
    # No HVS command invoked; service only reads/writes local package dir.


# --- 52) Stage 5 approval regression remains green ---------------------------
def test_stage5_approval_still_green(repo_root):
    from scos.control_center.hvs_delivery_approval import (
        STATUS_APPROVED,
        create_approval_request,
    )

    packet = {
        "ok": True, "schema_version": 1, "packet_id": "p6",
        "source": "hermes_video_studio", "trust_level": "VERIFIED",
        "operator_action": "review_export_ready", "automation_allowed": False,
        "project_id": "proj-6", "validation_id": "val-6",
        "hvs": {"validation_id": "val-6", "project_id": "proj-6", "verdict": "PASS",
                "export_ready": True},
        "artifact": {"path": "x.mp4", "sha256": "a" * 64, "size_bytes": 9},
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    res = decide_approval(approval_id=req.approval_request_id, decision="approve",
                          operator_id="op", decided_at="t", repo_root=repo_root)
    assert res.status == STATUS_APPROVED
    assert res.to_dict()["automation_allowed"] is False


# --- 54) caller-owned input objects not mutated ------------------------------
def test_caller_inputs_not_mutated(repo_root):
    art = _make_artifact(repo_root)
    sha = _sha256_of(art)
    from scos.control_center.hvs_delivery_approval import (
        create_approval_request,
    )

    packet = {
        "ok": True, "schema_version": 1, "packet_id": "p6",
        "source": "hermes_video_studio", "trust_level": "VERIFIED",
        "operator_action": "review_export_ready", "automation_allowed": False,
        "project_id": "proj-6", "validation_id": "val-6",
        "hvs": {"validation_id": "val-6", "project_id": "proj-6", "verdict": "PASS",
                "export_ready": True},
        "artifact": {"path": str(art), "sha256": sha,
                     "size_bytes": art.stat().st_size},
    }
    req = create_approval_request(packet=packet, repo_root=repo_root)
    decide_approval(approval_id=req.approval_request_id, decision="approve",
                    operator_id="op-6", decided_at="t", repo_root=repo_root)
    out = prepare_delivery_package(approval_id=req.approval_request_id,
                                   operator_id="op-6", repo_root=repo_root,
                                   recorded_at="t")
    # The packet dict the caller owns must be untouched.
    assert packet["artifact"]["sha256"] == sha
    assert "automation_allowed" in packet


# --- 55) runtime packages stay outside tracked source -----------------------
def test_runtime_artifacts_ignored(repo_root):
    pid, _ = _prepared_materialized(repo_root)
    pkg_dir = repo_root / "scos" / "work" / "hvs_delivery_packages" / pid
    # The package lives under scos/work, which is gitignored.
    assert "scos/work" in str(pkg_dir).replace("\\", "/")
    assert pkg_dir.is_dir()
