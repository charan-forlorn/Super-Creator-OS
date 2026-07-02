"""test_delivery_package.py - SCOS Stage 4.2 Local Delivery Package suite.

Plain-assert script (project convention, not pytest). Builds a seeded Stage 4.1
CommercialReport and verifies the deterministic local delivery package
generator over it.

Run: python scos/commercial/tests/test_delivery_package.py
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from delivery_package import create_delivery_package  # noqa: E402
from package_models import (  # noqa: E402
    DELIVERY_PACKAGE_SCHEMA_VERSION,
    DeliveryPackageError,
    DeliveryPackageManifest,
    DeliveryPackageResult,
)
from report_models import (  # noqa: E402
    COMMERCIAL_REPORT_SCHEMA_VERSION,
    CommercialReport,
    FrozenMap,
    ReportEvidence,
    ReportRisk,
)

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


_FIXED_NOW = "2026-07-03T00:00:00Z"


def _now():
    return _FIXED_NOW


def _seed_report(risks=(), recommendations=()):
    return CommercialReport(
        report_id="commercial:run_summary:run_a1",
        schema_version=COMMERCIAL_REPORT_SCHEMA_VERSION,
        report_type="run_summary",
        created_at="2026-07-02T00:00:00Z",
        source_run_id="run_a1",
        style_id="style_a",
        qa_status="PASS",
        summary="run_a1 rendered with style_a and passed QA.",
        evidence=(
            ReportEvidence("confidence", "coverage", "seed.confidence",
                           {"level": "high", "present": 4, "expected": 4}),
            ReportEvidence("run_id", "identifier", "seed.run", "run_a1"),
        ),
        recommendations=tuple(recommendations),
        risks=tuple(risks),
        metadata=FrozenMap.from_mapping({"seed": True}),
    )


def _package(tmp: Path, name="out", **kwargs):
    return create_delivery_package(
        commercial_report=kwargs.pop("report", _seed_report()),
        output_dir=tmp / name,
        now_fn=_now,
        **kwargs,
    )


def test_create_package(tmp: Path):
    print("\n[1] create package from seeded report")
    result = _package(tmp)
    check("returns DeliveryPackageResult", isinstance(result, DeliveryPackageResult))
    check("ok is True", result.ok is True)
    check("deterministic delivery_id",
          result.delivery_id == "delivery:run_summary:run_a1")
    out = Path(result.output_dir)
    check("package folder is fs-safe child",
          out.name == "delivery_run_summary_run_a1")
    for name in ("manifest.json", "report.json", "report.md",
                 "qa_summary.md", "improvement_plan.md"):
        check(f"{name} exists", (out / name).is_file())
    check("manifest schema_version == 1",
          result.manifest.schema_version == DELIVERY_PACKAGE_SCHEMA_VERSION == 1)
    check("package_status complete", result.manifest.package_status == "complete")
    check("created_at from injected now_fn",
          result.manifest.created_at == _FIXED_NOW)


def test_deterministic_manifest(tmp: Path):
    print("\n[2] deterministic manifest with fixed now_fn")
    a = _package(tmp, "det_a")
    b = _package(tmp, "det_b")
    check("manifests serialize identically",
          json.dumps(a.manifest.to_dict(), sort_keys=True)
          == json.dumps(b.manifest.to_dict(), sort_keys=True))
    check("manifest key order stable", tuple(a.manifest.to_dict().keys()) == (
        "delivery_id", "schema_version", "created_at", "source_run_id",
        "style_id", "report_id", "package_status", "files", "checksums",
        "metadata"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_deterministic_files(tmp: Path):
    print("\n[3-6] deterministic report.json / report.md / qa_summary.md / improvement_plan.md")
    a = Path(_package(tmp, "files_a").output_dir)
    b = Path(_package(tmp, "files_b").output_dir)
    for name in ("report.json", "report.md", "qa_summary.md", "improvement_plan.md"):
        check(f"{name} deterministic", _read(a / name) == _read(b / name))
    report_json = json.loads(_read(a / "report.json"))
    check("report.json equals report.to_dict()",
          json.dumps(report_json, sort_keys=True)
          == json.dumps(_seed_report().to_dict(), sort_keys=True))
    check("empty risks fallback line",
          "No evidence-backed risks available." in _read(a / "improvement_plan.md"))
    check("empty recommendations fallback line",
          "No evidence-backed recommendations available."
          in _read(a / "improvement_plan.md"))
    md = _read(a / "report.md")
    check("report.md carries report fields",
          "commercial:run_summary:run_a1" in md and "style_a" in md)


def test_checksums(tmp: Path):
    print("\n[7] SHA256 checksums stable and correct")
    a = _package(tmp, "sum_a")
    b = _package(tmp, "sum_b")
    sums = a.manifest.checksums.to_dict()
    check("checksums identical across builds",
          sums == b.manifest.checksums.to_dict())
    out = Path(a.output_dir)
    ok = all(
        hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
        for rel, digest in sums.items()
    )
    check("checksums match file bytes", ok and len(sums) >= 4)
    check("manifest.json not self-checksummed", "manifest.json" not in sums)


def test_already_exists(tmp: Path):
    print("\n[8] existing package dir returns PACKAGE_ALREADY_EXISTS")
    _package(tmp, "dup")
    again = _package(tmp, "dup")
    check("returns DeliveryPackageError", isinstance(again, DeliveryPackageError))
    check("error_kind PACKAGE_ALREADY_EXISTS",
          getattr(again, "error_kind", None) == "PACKAGE_ALREADY_EXISTS")
    check("ok is False", again.ok is False)


def test_overwrite(tmp: Path):
    print("\n[9] overwrite=True replaces only package dir")
    first = _package(tmp, "ow")
    pkg = Path(first.output_dir)
    (pkg / "stale.txt").write_text("stale", encoding="utf-8")
    sibling = pkg.parent / "sibling.txt"
    sibling.write_text("keep me", encoding="utf-8")
    second = _package(tmp, "ow", overwrite=True)
    check("overwrite succeeds", isinstance(second, DeliveryPackageResult))
    check("stale file removed", not (pkg / "stale.txt").exists())
    check("sibling outside package dir untouched",
          sibling.read_text(encoding="utf-8") == "keep me")
    check("required files regenerated", (pkg / "manifest.json").is_file())


def test_missing_video(tmp: Path):
    print("\n[10] explicit missing video_path fails deterministically")
    missing = _package(tmp, "vid_missing", video_path=tmp / "ghost.mp4")
    check("returns DeliveryPackageError", isinstance(missing, DeliveryPackageError))
    check("error_kind SOURCE_VIDEO_NOT_FOUND",
          getattr(missing, "error_kind", None) == "SOURCE_VIDEO_NOT_FOUND")
    not_a_file = tmp / "vid_dir.mp4"
    not_a_file.mkdir()
    dir_err = _package(tmp, "vid_dir_case", video_path=not_a_file)
    check("directory video_path also SOURCE_VIDEO_NOT_FOUND",
          isinstance(dir_err, DeliveryPackageError)
          and dir_err.error_kind == "SOURCE_VIDEO_NOT_FOUND")


def test_optional_video_absent(tmp: Path):
    print("\n[11] absent optional video_path does not fail")
    result = _package(tmp, "no_vid")
    check("succeeds without video", isinstance(result, DeliveryPackageResult))
    check("no assets folder created",
          not (Path(result.output_dir) / "assets").exists())
    check("no video file entry",
          all(f.kind != "video" for f in result.manifest.files))


def test_source_manifest_copied(tmp: Path):
    print("\n[12] source_manifest_path copied when present")
    src = tmp / "source_manifest.json"
    src.write_text('{"source": "job_1"}', encoding="utf-8")
    video = tmp / "video.mp4"
    video.write_bytes(b"\x00fakevideo")
    result = _package(tmp, "assets", source_manifest_path=src, video_path=video)
    check("succeeds with assets", isinstance(result, DeliveryPackageResult))
    out = Path(result.output_dir)
    check("source_manifest copied",
          (out / "assets" / "source_manifest.json").read_text(encoding="utf-8")
          == '{"source": "job_1"}')
    check("video copied",
          (out / "assets" / "video.mp4").read_bytes() == b"\x00fakevideo")
    check("source files untouched", src.is_file() and video.is_file())
    kinds = {f.path: (f.kind, f.required) for f in result.manifest.files}
    check("asset entries optional in manifest",
          kinds.get("assets/video.mp4") == ("video", False)
          and kinds.get("assets/source_manifest.json") == ("source_manifest", False))


def test_stable_file_ordering(tmp: Path):
    print("\n[13] manifest uses stable file ordering")
    src = tmp / "sm.json"
    src.write_text("{}", encoding="utf-8")
    video = tmp / "v.mp4"
    video.write_bytes(b"v")
    result = _package(tmp, "order", source_manifest_path=src, video_path=video)
    paths = [f.path for f in result.manifest.files]
    check("files sorted by path", paths == sorted(paths))
    check("relative forward-slash paths",
          all(("\\" not in p and not Path(p).is_absolute()) for p in paths))


def test_frozen_immutability(tmp: Path):
    print("\n[14] frozen dataclass immutability")
    result = _package(tmp, "frozen")
    frozen_count = 0
    for target, field, value in (
        (result, "delivery_id", "x"),
        (result.manifest, "package_status", "hacked"),
        (result.manifest.files[0], "path", "evil"),
    ):
        try:
            setattr(target, field, value)
        except FrozenInstanceError:
            frozen_count += 1
    check("result, manifest, file entries frozen", frozen_count == 3)
    err = _package(tmp, "frozen")  # duplicate -> error object
    try:
        err.error_kind = "changed"
        err_frozen = False
    except FrozenInstanceError:
        err_frozen = True
    check("error object frozen", err_frozen)


def test_no_mutable_leakage(tmp: Path):
    print("\n[15] no mutable nested leakage")
    manifest = _package(tmp, "leak").manifest
    check("files is tuple", isinstance(manifest.files, tuple))
    check("checksums is FrozenMap", isinstance(manifest.checksums, FrozenMap))
    check("metadata is FrozenMap", isinstance(manifest.metadata, FrozenMap))
    first = json.dumps(manifest.to_dict(), sort_keys=True)
    thawed = manifest.to_dict()
    thawed["checksums"]["report.json"] = "tampered"
    check("to_dict returns copies, not internal state",
          json.dumps(manifest.to_dict(), sort_keys=True) == first)


def test_no_lower_layer_imports():
    print("\n[16-17] static dependency check")
    source = (_COMMERCIAL / "delivery_package.py").read_text(encoding="utf-8")
    forbidden = (
        "KnowledgeIndex",
        "KnowledgeQueryEngine",
        "KnowledgeExplainEngine",
        "KnowledgeInsightEngine",
        "knowledge_service",
        "knowledge_index",
        "query_engine",
        "explain_engine",
        "insight_engine",
        "query_models",
        "explain_models",
        "insight_models",
        "requests",
        "httpx",
        "urllib",
        "boto3",
        "socket",
        "http.client",
        "aiohttp",
    )
    for token in forbidden:
        check(f"no '{token}'", token not in source)
    check("imports only commercial models",
          "from report_models import CommercialReport" in source
          and "from package_models import" in source)
    check("commercial code does not mutate sys.path", "sys.path" not in source)


def test_no_raw_payload_leakage(tmp: Path):
    print("\n[18] no raw lower-layer payload leakage")
    result = _package(tmp, "payload")
    out = Path(result.output_dir)
    blob = json.dumps(result.manifest.to_dict(), sort_keys=True)
    blob += _read(out / "qa_summary.md") + _read(out / "improvement_plan.md")
    forbidden_payload_keys = ("replay", "feedback", "audit", "style_version",
                              "timeline_ref")
    check("no raw provenance payload keys",
          all(key not in blob for key in forbidden_payload_keys))
    check("manifest is JSON-safe", blob.startswith("{"))


def test_expected_errors_not_exceptions(tmp: Path):
    print("\n[19] expected errors return DeliveryPackageError")
    bad_report = _package(tmp, "bad", report={"not": "a report"})
    check("invalid report -> INVALID_REPORT",
          isinstance(bad_report, DeliveryPackageError)
          and bad_report.error_kind == "INVALID_REPORT")
    file_as_dir = tmp / "not_a_dir"
    file_as_dir.write_text("x", encoding="utf-8")
    bad_dir = _package(tmp, "not_a_dir")
    check("file output_dir -> INVALID_OUTPUT_DIR",
          isinstance(bad_dir, DeliveryPackageError)
          and bad_dir.error_kind == "INVALID_OUTPUT_DIR")
    hostile = _package(tmp, "hostile", delivery_id="../escape")
    check("path traversal delivery_id -> INVALID_OUTPUT_DIR",
          isinstance(hostile, DeliveryPackageError)
          and hostile.error_kind == "INVALID_OUTPUT_DIR")
    check("nothing written outside output_dir",
          not (tmp / "escape").exists())
    missing_sm = _package(tmp, "sm_missing", source_manifest_path=tmp / "ghost.json")
    check("missing source manifest -> SOURCE_MANIFEST_NOT_FOUND",
          isinstance(missing_sm, DeliveryPackageError)
          and missing_sm.error_kind == "SOURCE_MANIFEST_NOT_FOUND")
    check("errors serialize deterministically",
          json.dumps(missing_sm.to_dict(), sort_keys=True)
          == json.dumps(_package(tmp, "sm_missing",
                                 source_manifest_path=tmp / "ghost.json").to_dict(),
                        sort_keys=True))
    check("no traceback leakage",
          "Traceback" not in json.dumps(missing_sm.to_dict(), sort_keys=True))


def test_package_re_readable(tmp: Path):
    print("\n[20] generated package is re-readable from disk")
    result = _package(tmp, "reread")
    out = Path(result.output_dir)
    manifest_data = json.loads(_read(out / "manifest.json"))
    reread = DeliveryPackageManifest.from_dict(manifest_data)
    check("manifest round-trips from disk",
          json.dumps(reread.to_dict(), sort_keys=True)
          == json.dumps(result.manifest.to_dict(), sort_keys=True))
    ok = all(
        hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
        for rel, digest in manifest_data["checksums"].items()
    )
    check("re-read checksums verify", ok)
    report = json.loads(_read(out / "report.json"))
    check("re-read report keeps run id", report["source_run_id"] == "run_a1")


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_create_package(tmp)
        test_deterministic_manifest(tmp)
        test_deterministic_files(tmp)
        test_checksums(tmp)
        test_already_exists(tmp)
        test_overwrite(tmp)
        test_missing_video(tmp)
        test_optional_video_absent(tmp)
        test_source_manifest_copied(tmp)
        test_stable_file_ordering(tmp)
        test_frozen_immutability(tmp)
        test_no_mutable_leakage(tmp)
        test_no_lower_layer_imports()
        test_no_raw_payload_leakage(tmp)
        test_expected_errors_not_exceptions(tmp)
        test_package_re_readable(tmp)

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
