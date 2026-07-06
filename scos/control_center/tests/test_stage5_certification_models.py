"""test_stage5_certification_models.py - SCOS Stage 5.10 certification models suite.

Plain executable script (no pytest). Covers immutability, deterministic
to_dict key order, allowed enum validation, FrozenMap round-tripping, and
the Stage5FinalCertificationResult stage_closed invariant.

Run: python scos/control_center/tests/test_stage5_certification_models.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from stage5_certification_models import (  # noqa: E402
    BLOCKER_SEVERITIES,
    CHECK_CATEGORIES,
    CHECK_SEVERITIES,
    CHECK_STATUSES,
    GO_NO_GO_VALUES,
    HANDOFF_PRIORITIES,
    READINESS_LEVELS,
    STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION,
    FrozenMap,
    Stage5CertificationBlocker,
    Stage5CertificationCheck,
    Stage5FinalCertificationError,
    Stage5FinalCertificationResult,
    Stage6HandoffItem,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-06T00:00:00Z"


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def test_check_model():
    print("\n[01] Stage5CertificationCheck")
    c = Stage5CertificationCheck.of(
        "c1", "success", "info", category="testing",
        artifact_path="a.json", metadata={"k": "v"})
    check("frozen (mutation raises)", _raises_frozen(lambda: setattr(c, "status", "failure")))
    d = c.to_dict()
    check("to_dict key order",
          list(d) == ["check_name", "status", "severity", "category", "artifact_path",
                      "error_kind", "error_detail", "metadata"])
    check("metadata round-trips", d["metadata"] == {"k": "v"})
    for bad_field, allowed, kwargs in (
        ("status", CHECK_STATUSES, {"status": "bogus"}),
        ("severity", CHECK_SEVERITIES, {"severity": "bogus"}),
        ("category", CHECK_CATEGORIES, {"category": "bogus"}),
    ):
        rejected = _raises_value_error(lambda kw=kwargs: Stage5CertificationCheck.of(
            "c", **{**{"status": "success", "category": "testing"}, **kw}))
        check(f"invalid {bad_field} rejected", rejected)


def test_blocker_model():
    print("\n[02] Stage5CertificationBlocker")
    b = Stage5CertificationBlocker.of(
        "b1", "testing", "warning", "title", "detail", "action", "c1", metadata={"n": 1})
    d = b.to_dict()
    check("to_dict key order",
          list(d) == ["blocker_id", "category", "severity", "title", "detail",
                      "recommended_action", "source_check", "metadata"])
    check("invalid severity rejected", _raises_value_error(
        lambda: Stage5CertificationBlocker.of("b", "testing", "bogus", "t", "d", "a", "c")))
    check("invalid category rejected", _raises_value_error(
        lambda: Stage5CertificationBlocker.of("b", "bogus", "warning", "t", "d", "a", "c")))


def test_handoff_item_model():
    print("\n[03] Stage6HandoffItem")
    item = Stage6HandoffItem.of(
        "stage6-001", "Title", "control_center_backend", "high",
        description="desc", source_stage5_evidence="e.md")
    d = item.to_dict()
    check("to_dict key order",
          list(d) == ["item_id", "title", "category", "priority", "description",
                      "stage6_owner", "source_stage5_evidence", "metadata"])
    check("invalid priority rejected", _raises_value_error(
        lambda: Stage6HandoffItem.of("i", "t", "c", "bogus")))


def test_frozen_map_round_trip():
    print("\n[04] FrozenMap round-trip")
    nested = {"b": [1, 2, {"z": 1, "a": 2}], "a": {"x": 1}}
    fm = FrozenMap.from_mapping(nested)
    check("round-trips nested dict/list", fm.to_dict() == nested)
    check("deterministic key order (sorted)",
          [key for key, _ in fm.items] == sorted(nested))


def test_result_model_serialization():
    print("\n[05] Stage5FinalCertificationResult serializes deterministically")
    def build():
        chk = Stage5CertificationCheck.of(
            "c1", "success", "info", category="testing", metadata={"k": "v"})
        blk = Stage5CertificationBlocker.of(
            "b1", "testing", "warning", "title", "detail", "action", "c1", metadata={"n": 1})
        item = Stage6HandoffItem.of(
            "stage6-001", "Title", "security", "high", description="desc")
        return Stage5FinalCertificationResult(
            ok=True, schema_version=STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION,
            accepted=True, certification_id="s5c-abc", checked_at=_NOW,
            stage="5", stage_closed=True, go_no_go="GO",
            readiness_level="certified", readiness_score=100,
            readiness_max_score=100, checks=(chk,), blockers=(),
            stage6_handoff_items=(item,), output_path=None,
            metadata={"b": 2, "a": 1})
    r1, r2 = build(), build()
    check("two builds serialize identically",
          json.dumps(r1.to_dict(), sort_keys=True) == json.dumps(r2.to_dict(), sort_keys=True))
    d = r1.to_dict()
    check("top-level key order is explicit",
          list(d) == ["ok", "schema_version", "accepted", "certification_id", "checked_at",
                      "stage", "stage_closed", "go_no_go", "readiness_level",
                      "readiness_score", "readiness_max_score", "checks", "blockers",
                      "stage6_handoff_items", "output_path", "metadata"])
    check("stage is literal '5'", d["stage"] == "5")
    check("schema version constant is 1", STAGE5_FINAL_CERTIFICATION_SCHEMA_VERSION == 1)
    check("allowed enums exposed",
          GO_NO_GO_VALUES == ("GO", "NO_GO") and len(READINESS_LEVELS) == 3
          and len(BLOCKER_SEVERITIES) == 3 and len(HANDOFF_PRIORITIES) == 4)


def test_stage_closed_invariant():
    print("\n[06] stage_closed invariant")
    def build(stage_closed, accepted, blockers=()):
        return Stage5FinalCertificationResult(
            ok=True, schema_version=1, accepted=accepted, certification_id="s5c-x",
            checked_at=_NOW, stage="5", stage_closed=stage_closed, go_no_go="GO",
            readiness_level="certified", readiness_score=100, readiness_max_score=100,
            checks=(), blockers=blockers, stage6_handoff_items=(), output_path=None,
            metadata={})
    check("stage_closed=True, accepted=True, no blockers -> ok",
          build(True, True) is not None)
    check("stage_closed=True, accepted=False -> rejected",
          _raises_value_error(lambda: build(True, False)))
    critical = (Stage5CertificationBlocker.of(
        "b1", "testing", "critical", "t", "d", "a", "c"),)
    check("stage_closed=True with critical blocker -> rejected",
          _raises_value_error(lambda: build(True, True, critical)))
    warning = (Stage5CertificationBlocker.of(
        "b2", "testing", "warning", "t", "d", "a", "c"),)
    check("stage_closed=True with only warning blocker -> ok",
          build(True, True, warning) is not None)


def test_error_model_serialization():
    print("\n[07] Stage5FinalCertificationError serializes deterministically")
    def build():
        return Stage5FinalCertificationError.of(
            "INVALID_ARGUMENTS", "detail", "validate_inputs",
            (Stage5CertificationCheck.of("validate_inputs", "failure", "error",
                                         category="preflight"),),
            (), {"z": 1})
    e1, e2 = build(), build()
    check("two builds serialize identically",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))
    d = e1.to_dict()
    check("error key order is explicit",
          list(d) == ["ok", "schema_version", "error_kind", "error_detail",
                      "failed_check", "checks", "blockers", "metadata"])
    check("ok is False and schema pinned", d["ok"] is False and d["schema_version"] == 1)


def test_no_nondeterminism_tokens():
    print("\n[08] no clock/random/uuid usage")
    text = (_PACKAGE / "stage5_certification_models.py").read_text(encoding="utf-8")
    for token in ("uuid.uuid4", "random.", "datetime.now", "date.today", "time.time"):
        check(f"no non-determinism token '{token}'", token not in text)


def _raises_frozen(thunk):
    try:
        thunk()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def _raises_value_error(thunk):
    try:
        thunk()
        return False
    except ValueError:
        return True


def main():
    test_check_model()
    test_blocker_model()
    test_handoff_item_model()
    test_frozen_map_round_trip()
    test_result_model_serialization()
    test_stage_closed_invariant()
    test_error_model_serialization()
    test_no_nondeterminism_tokens()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
