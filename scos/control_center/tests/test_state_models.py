"""test_state_models.py - SCOS Stage 6.3 durable state models suite.

Plain executable script (no pytest). Covers construction, allowed-value
enforcement, deterministic to_dict/from_dict round trips, and FrozenMap
metadata sorting for every Stage 6.3 durable state model.

Run: python scos/control_center/tests/test_state_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from state_models import (  # noqa: E402
    DurableApprovalRecord,
    DurableCommandRecord,
    DurableEventRecord,
    DurableResultRecord,
    DurableSessionRecord,
    DurableStateError,
    StateRecordRef,
    CONTROL_CENTER_STATE_SCHEMA_VERSION,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _raises(fn, exc_type=ValueError) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True


def test_1_schema_version_constant() -> None:
    check("schema version is 1", CONTROL_CENTER_STATE_SCHEMA_VERSION == 1)


def test_2_state_record_ref_round_trip() -> None:
    ref = StateRecordRef.of(
        "rec-1", "command", "2026-07-07T00:00:00Z", metadata={"b": "2", "a": "1"}
    )
    data = ref.to_dict()
    check("metadata sorted", list(data["metadata"].keys()) == ["a", "b"])
    restored = StateRecordRef.from_dict(data)
    check("round trip equal", restored.to_dict() == data)


def test_3_durable_command_record_status_validation() -> None:
    record = DurableCommandRecord.of(
        "cmd-1", "health_check", "draft", "2026-07-07T00:00:00Z"
    )
    check("status accepted", record.status == "draft")
    check(
        "invalid status rejected",
        _raises(lambda: DurableCommandRecord.of("cmd-2", "x", "nonsense", "t")),
    )
    restored = DurableCommandRecord.from_dict(record.to_dict())
    check("command round trip", restored.to_dict() == record.to_dict())


def test_4_durable_session_record_status_validation() -> None:
    record = DurableSessionRecord.of("sess-1", "planned", "2026-07-07T00:00:00Z")
    check("status accepted", record.status == "planned")
    check(
        "invalid status rejected",
        _raises(lambda: DurableSessionRecord.of("sess-2", "nonsense", "t")),
    )
    restored = DurableSessionRecord.from_dict(record.to_dict())
    check("session round trip", restored.to_dict() == record.to_dict())


def test_5_durable_event_record_sequence() -> None:
    record = DurableEventRecord.of(
        "evt-1", "command_state_changed", "control_center", "command", "cmd-1",
        "2026-07-07T00:00:00Z", 0,
    )
    check("sequence is int", record.sequence == 0)
    check(
        "negative sequence rejected",
        _raises(
            lambda: DurableEventRecord.of(
                "evt-2", "x", "s", "t", "i", "created", -1
            )
        ),
    )
    restored = DurableEventRecord.from_dict(record.to_dict())
    check("event round trip", restored.to_dict() == record.to_dict())


def test_6_durable_approval_record_decision_validation() -> None:
    record = DurableApprovalRecord.of(
        "appr-1", "command_approval", "command", "cmd-1", "approved",
        "operator", "2026-07-07T00:00:00Z",
    )
    check("decision accepted", record.decision == "approved")
    check(
        "invalid decision rejected",
        _raises(
            lambda: DurableApprovalRecord.of(
                "appr-2", "x", "t", "i", "nonsense", "op", "t"
            )
        ),
    )
    restored = DurableApprovalRecord.from_dict(record.to_dict())
    check("approval round trip", restored.to_dict() == record.to_dict())


def test_7_durable_result_record_verdict_validation() -> None:
    record = DurableResultRecord.of(
        "res-1", "verification", "command", "cmd-1", "pass",
        "2026-07-07T00:00:00Z",
    )
    check("verdict accepted", record.verdict == "pass")
    check(
        "invalid verdict rejected",
        _raises(
            lambda: DurableResultRecord.of("res-2", "x", "t", "i", "nonsense", "t")
        ),
    )
    restored = DurableResultRecord.from_dict(record.to_dict())
    check("result round trip", restored.to_dict() == record.to_dict())


def test_8_durable_state_error_allowed_kinds() -> None:
    error = DurableStateError.of("not_found", "missing record")
    check("ok is False", error.ok is False)
    check(
        "invalid error_kind rejected",
        _raises(lambda: DurableStateError.of("nonsense", "detail")),
    )
    restored = DurableStateError.from_dict(error.to_dict())
    check("error round trip", restored.to_dict() == error.to_dict())


def main() -> int:
    tests = [
        test_1_schema_version_constant,
        test_2_state_record_ref_round_trip,
        test_3_durable_command_record_status_validation,
        test_4_durable_session_record_status_validation,
        test_5_durable_event_record_sequence,
        test_6_durable_approval_record_decision_validation,
        test_7_durable_result_record_verdict_validation,
        test_8_durable_state_error_allowed_kinds,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
