"""Focused backend tests — SCOS Cohort 10I paid-pilot operational audit.

Local, deterministic, hermetic. Exercises: append-only logging, event-id
idempotency, read-back, tamper-evidence hash, redaction (no paths/secrets),
invalid event type rejection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center.hvs_paid_pilot_audit import (
    DELIVERY_AUDIT_SCHEMA_VERSION,
    append_audit_event,
    compute_audit_hash,
    read_audit_events,
    verify_audit_integrity,
)


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "paid-pilot-audit.jsonl"


def test_append_and_read(audit_path: Path):
    ev = append_audit_event(
        audit_log_path=audit_path,
        event_type="RIGHTS_REVIEWED",
        delivery_id="scos-hvs-pp-delivery-test1",
        actor="op",
        transition="RIGHTS_NOT_REVIEWED->RIGHTS_APPROVED",
        previous_state="RIGHTS_NOT_REVIEWED",
        new_state="RIGHTS_APPROVED",
        result="SUCCESS",
        correlation_key="corr-1",
        recorded_at="2026-07-27T00:00:00Z",
    )
    assert ev.event_type == "RIGHTS_REVIEWED"
    assert ev.delivery_id == "scos-hvs-pp-delivery-test1"
    events = read_audit_events(audit_log_path=audit_path)
    assert len(events) == 1
    assert events[0].event_id == ev.event_id
    assert events[0].actor == "op"


def test_event_id_is_content_derived(audit_path: Path):
    """Same inputs produce the same event id (deterministic)."""
    ev1 = append_audit_event(
        audit_log_path=audit_path,
        event_type="PACKAGE_CREATED",
        delivery_id="d1",
        actor="op",
        transition="APPROVED->PACKAGE_READY",
        previous_state="DELIVERY_APPROVED",
        new_state="DELIVERY_PACKAGE_READY",
        result="SUCCESS",
        correlation_key="corr-1",
        recorded_at="2026-07-27T00:00:00Z",
    )
    # Append the same event again — same id, but two lines in the log.
    ev2 = append_audit_event(
        audit_log_path=audit_path,
        event_type="PACKAGE_CREATED",
        delivery_id="d1",
        actor="op",
        transition="APPROVED->PACKAGE_READY",
        previous_state="DELIVERY_APPROVED",
        new_state="DELIVERY_PACKAGE_READY",
        result="SUCCESS",
        correlation_key="corr-1",
        recorded_at="2026-07-27T00:00:00Z",
    )
    assert ev1.event_id == ev2.event_id
    events = read_audit_events(audit_log_path=audit_path)
    assert len(events) == 2  # both lines preserved


def test_invalid_event_type_rejected(audit_path: Path):
    with pytest.raises(ValueError, match="INVALID_EVENT_TYPE"):
        append_audit_event(
            audit_log_path=audit_path,
            event_type="INVALID_EVENT",
            delivery_id="d1",
            actor="op",
            transition="x->y",
            previous_state="x",
            new_state="y",
            result="SUCCESS",
            correlation_key="c",
            recorded_at="2026-07-27T00:00:00Z",
        )


def test_audit_hash_tamper_evidence(audit_path: Path):
    append_audit_event(
        audit_log_path=audit_path,
        event_type="BACKUP_FINALIZED",
        delivery_id="d1",
        actor="op",
        transition="PACKAGE_READY->BACKUP_READY",
        previous_state="DELIVERY_PACKAGE_READY",
        new_state="DELIVERY_BACKUP_READY",
        result="SUCCESS",
        correlation_key="c",
        recorded_at="2026-07-27T00:00:00Z",
    )
    h1 = compute_audit_hash(audit_log_path=audit_path)
    # Tamper: append a corrupt line.
    audit_path.write_text(audit_path.read_text() + "{corrupt line}\n")
    ok, msg = verify_audit_integrity(audit_log_path=audit_path)
    assert ok is False
    assert "INVALID_AUDIT_LINE" in msg
    h2 = compute_audit_hash(audit_log_path=audit_path)
    assert h1 != h2


def test_audit_redaction_no_paths_or_secrets(audit_path: Path):
    """Audit events must not contain absolute paths, secrets, or env values."""
    ev = append_audit_event(
        audit_log_path=audit_path,
        event_type="HANDOFF_READY",
        delivery_id="d1",
        actor="op",
        transition="BACKUP_READY->HANDOFF_READY",
        previous_state="DELIVERY_BACKUP_READY",
        new_state="DELIVERY_READY_FOR_MANUAL_HANDOFF",
        result="SUCCESS",
        correlation_key="c",
        recorded_at="2026-07-27T00:00:00Z",
        detail="handoff ready",
    )
    serialized = json.dumps(ev.to_dict())
    assert "C:\\" not in serialized
    assert "/workspace/" not in serialized.lower()
    assert "secret" not in serialized.lower()
    assert "password" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_empty_audit_is_valid(audit_path: Path):
    ok, msg = verify_audit_integrity(audit_log_path=audit_path)
    assert ok is True
    assert msg == "EMPTY"
    events = read_audit_events(audit_log_path=audit_path)
    assert len(events) == 0
