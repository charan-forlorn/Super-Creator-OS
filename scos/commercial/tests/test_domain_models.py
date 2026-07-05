"""test_domain_models.py - SCOS Stage 4.18 shared domain model suite.

Plain executable script (no pytest). Covers construction, of() factories,
to_dict() key order and serialization, immutability, invalid enum rejection,
FrozenMap handling, and determinism.

Run: python scos/commercial/tests/test_domain_models.py
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from domain_models import (  # noqa: E402
    BLOCKER_SEVERITIES,
    CHECK_SEVERITIES,
    CHECK_STATUSES,
    COMMERCIAL_DOMAIN_SCHEMA_VERSION,
    MANUAL_ACTION_PRIORITIES,
    CommercialArtifactReference,
    CommercialBlocker,
    CommercialCheck,
    CommercialManualAction,
)
from report_models import FrozenMap  # noqa: E402

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


def _raises_value_error(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def test_schema_version() -> None:
    print("\n[1] schema version + allowed vocabularies")
    check("schema version is 1", COMMERCIAL_DOMAIN_SCHEMA_VERSION == 1)
    check("check statuses", CHECK_STATUSES == ("success", "failure", "skipped"))
    check("check severities", CHECK_SEVERITIES == ("info", "warning", "error", "critical"))
    check("blocker severities", BLOCKER_SEVERITIES == ("warning", "error", "critical"))
    check("priorities", MANUAL_ACTION_PRIORITIES == ("low", "normal", "high", "urgent"))


def test_commercial_check() -> None:
    print("\n[2] CommercialCheck")
    item = CommercialCheck.of(
        "artifact_exists",
        "success",
        "info",
        artifact_path="out/manifest.json",
        metadata={"b": 2, "a": 1},
    )
    check("of() returns CommercialCheck", isinstance(item, CommercialCheck))
    check("metadata is FrozenMap", isinstance(item.metadata, FrozenMap))
    data = item.to_dict()
    check(
        "to_dict key order is explicit",
        list(data) == [
            "check_name", "status", "severity", "artifact_path",
            "error_kind", "error_detail", "metadata",
        ],
    )
    check("metadata serialized as plain dict", data["metadata"] == {"a": 1, "b": 2})
    check("optional fields default to None", data["error_kind"] is None and data["error_detail"] is None)
    check("invalid status raises ValueError",
          _raises_value_error(lambda: CommercialCheck.of("x", "ok")))
    check("invalid severity raises ValueError",
          _raises_value_error(lambda: CommercialCheck.of("x", "success", "fatal")))
    check("frozen: field assignment rejected",
          _raises(lambda: setattr(item, "status", "failure"), FrozenInstanceError))
    check("metadata dict coerced to FrozenMap via constructor",
          isinstance(
              CommercialCheck(
                  check_name="n", status="skipped", severity="warning",
                  artifact_path=None, error_kind=None, error_detail=None,
                  metadata={"k": "v"},
              ).metadata,
              FrozenMap,
          ))


def _raises(fn, exc_type) -> bool:
    try:
        fn()
    except exc_type:
        return True
    except Exception:
        return False
    return False


def test_commercial_blocker() -> None:
    print("\n[3] CommercialBlocker")
    item = CommercialBlocker.of(
        "B-001", "integrity", "critical", "Manifest missing",
        "The manifest file was not found.", "Re-run the packaging step.",
        "manifest_tools", {"path": "out/manifest.json"},
    )
    check("of() returns CommercialBlocker", isinstance(item, CommercialBlocker))
    data = item.to_dict()
    check(
        "to_dict key order is explicit",
        list(data) == [
            "blocker_id", "category", "severity", "title", "detail",
            "recommended_action", "source", "metadata",
        ],
    )
    check("severity 'info' rejected for blockers",
          _raises_value_error(lambda: CommercialBlocker.of(
              "B-002", "c", "info", "t", "d", "a", "s")))
    check("frozen: field assignment rejected",
          _raises(lambda: setattr(item, "severity", "warning"), FrozenInstanceError))


def test_artifact_reference(tmp: Path) -> None:
    print("\n[4] CommercialArtifactReference")
    item = CommercialArtifactReference.of(
        "A-001", "manifest", str(tmp / "manifest.json"),
        sha256=None, required=True, metadata={"stage": "4.18"},
    )
    check("of() returns CommercialArtifactReference", isinstance(item, CommercialArtifactReference))
    data = item.to_dict()
    check(
        "to_dict key order is explicit",
        list(data) == ["artifact_id", "artifact_type", "path", "sha256", "required", "metadata"],
    )
    check("required coerced to bool", data["required"] is True)
    check("sha256 optional", data["sha256"] is None)
    with_sha = CommercialArtifactReference.of("A-002", "report", "r.json", sha256="ab" * 32)
    check("sha256 stored as str", with_sha.to_dict()["sha256"] == "ab" * 32)


def test_manual_action() -> None:
    print("\n[5] CommercialManualAction")
    item = CommercialManualAction.of(
        "Review the handoff summary", "Human confirmation required before send.",
        "high", due_at="2026-07-06T00:00:00Z",
    )
    check("of() returns CommercialManualAction", isinstance(item, CommercialManualAction))
    data = item.to_dict()
    check(
        "to_dict key order is explicit",
        list(data) == [
            "action", "reason", "priority", "due_at",
            "requires_human_review", "metadata",
        ],
    )
    check("requires_human_review defaults True", data["requires_human_review"] is True)
    check("due_at optional",
          CommercialManualAction.of("a", "r").to_dict()["due_at"] is None)
    check("invalid priority raises ValueError",
          _raises_value_error(lambda: CommercialManualAction.of("a", "r", "asap")))


def test_determinism() -> None:
    print("\n[6] determinism")
    def build():
        return CommercialCheck.of(
            "c", "failure", "error",
            error_kind="INPUT_NOT_FOUND", error_detail="missing",
            metadata={"z": [1, 2], "a": {"nested": True}},
        ).to_dict()
    check("identical builds produce identical dicts", build() == build())
    first = build()
    check("tuples serialized as lists", isinstance(
        CommercialCheck.of("c", "success", metadata={"seq": (1, 2)}).to_dict()["metadata"]["seq"],
        list,
    ))
    check("nested metadata thawed to plain dict", first["metadata"] == {"a": {"nested": True}, "z": [1, 2]})


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_schema_version()
        test_commercial_check()
        test_commercial_blocker()
        test_artifact_reference(tmp)
        test_manual_action()
        test_determinism()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
