"""test_cli.py - SCOS Stage 4.3 Local Commercial CLI suite.

Plain-assert script (project convention, not pytest). Exercises the local
argparse CLI over the Stage 4.1 report builder and Stage 4.2 delivery package
generator, verifying deterministic JSON, exit codes, boundary rules, and
local-only restrictions.

Run: python scos/commercial/tests/test_cli.py
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent
_SCOS = _COMMERCIAL.parent
_KNOWLEDGE = _SCOS / "knowledge"

sys.path.insert(0, str(_COMMERCIAL))
sys.path.insert(0, str(_KNOWLEDGE))

import cli  # noqa: E402
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


def run_cli(argv):
    """Invoke cli.main(argv), capturing stdout and the resulting exit code."""
    buf = io.StringIO()
    code = None
    with contextlib.redirect_stdout(buf):
        try:
            code = cli.main(argv)
        except SystemExit as exc:  # argparse usage errors
            code = exc.code
    return code, buf.getvalue()


def _seed_report_dict():
    report = CommercialReport(
        report_id="commercial:run_summary:run_a1",
        schema_version=COMMERCIAL_REPORT_SCHEMA_VERSION,
        report_type="run_summary",
        created_at="2026-07-02T00:00:00Z",
        source_run_id="run_a1",
        style_id="style_a",
        qa_status="PASS",
        summary="run_a1 rendered with style_a and passed QA.",
        evidence=(
            ReportEvidence("run_id", "identifier", "seed.run", "run_a1"),
            ReportEvidence("style_id", "identifier", "seed.provenance", "style_a"),
        ),
        recommendations=(),
        risks=(ReportRisk("r1", "explicit", "seed", "seeded risk detail"),),
        metadata=FrozenMap.from_mapping({"seed": True}),
    )
    return report.to_dict()


def _write_report_json(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_seed_report_dict(), sort_keys=True, indent=2), encoding="utf-8")
    return path


def _cli_src():
    return (_COMMERCIAL / "cli.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
def test_version(tmp: Path):
    print("\n[1] version command")
    code, out = run_cli(["version"])
    data = json.loads(out)
    check("version exit 0", code == 0)
    check("version ok true", data["ok"] is True)
    check("version cli_schema_version == 1", data["cli_schema_version"] == 1)
    check("version supported_commands sorted", data["supported_commands"] == ["package", "report", "validate", "version"])
    check("version stdout is sorted-key indented JSON", out == json.dumps(data, sort_keys=True, indent=2) + "\n")


def test_invalid_command(tmp: Path):
    print("\n[2] invalid command exits non-zero deterministically")
    code_a, out_a = run_cli(["bogus"])
    code_b, out_b = run_cli(["bogus"])
    check("invalid command non-zero exit", code_a != 0)
    check("invalid command exit is deterministic", code_a == code_b)
    check("invalid command argparse exit code 2", code_a == 2)
    check("invalid command writes nothing to stdout", out_a == "" and out_b == "")


def test_validate_missing_report_json(tmp: Path):
    print("\n[3] validate rejects missing report-json")
    missing = tmp / "nope.json"
    out_dir = tmp / "deliveries"
    code, out = run_cli(["validate", "--report-json", str(missing), "--output-dir", str(out_dir), "--created-at", "T"])
    data = json.loads(out)
    check("validate missing report exit 1", code == 1)
    check("validate missing report ok false", data["ok"] is False)
    check("validate missing report kind VALIDATION_FAILED", data["error_kind"] == "VALIDATION_FAILED")


def test_validate_does_not_create_output_dir(tmp: Path):
    print("\n[4] validate does not create output directory")
    report = _write_report_json(tmp / "in" / "report.json")
    out_dir = tmp / "deliveries_x"  # does not exist yet; parent (tmp) exists
    code, out = run_cli(["validate", "--report-json", str(report), "--output-dir", str(out_dir), "--created-at", "T"])
    data = json.loads(out)
    check("validate success exit 0", code == 0)
    check("validate reports would_write plan", "would_write" in data["metadata"])
    check("validate did NOT create output-dir", not out_dir.exists())
    folder = out_dir / "delivery_run_summary_run_a1"
    check("validate did NOT create package dir", not folder.exists())


def test_package_missing_report_json(tmp: Path):
    print("\n[5] package rejects missing report-json")
    code, out = run_cli(["package", "--report-json", str(tmp / "gone.json"), "--output-dir", str(tmp / "d"), "--created-at", "T"])
    data = json.loads(out)
    check("package missing report exit 1", code == 1)
    check("package missing report kind INPUT_NOT_FOUND", data["error_kind"] == "INPUT_NOT_FOUND")


def test_package_invalid_report_json(tmp: Path):
    print("\n[6] package rejects invalid report-json")
    bad = tmp / "bad.json"
    bad.write_text("this is not json {", encoding="utf-8")
    code, out = run_cli(["package", "--report-json", str(bad), "--output-dir", str(tmp / "d2"), "--created-at", "T"])
    data = json.loads(out)
    check("package invalid report exit 1", code == 1)
    check("package invalid report kind INVALID_REPORT_JSON", data["error_kind"] == "INVALID_REPORT_JSON")


def test_package_creates_delivery(tmp: Path):
    print("\n[7] package creates delivery package from seeded report JSON")
    report = _write_report_json(tmp / "in7" / "report.json")
    out_dir = tmp / "out7"
    code, out = run_cli(["package", "--report-json", str(report), "--output-dir", str(out_dir), "--created-at", "2026-07-02T00:00:00Z"])
    data = json.loads(out)
    check("package exit 0", code == 0)
    check("package ok true", data["ok"] is True)
    pkg = Path(data["output_path"])
    check("package output_path exists", pkg.exists() and pkg.is_dir())
    check("package wrote report.json", (pkg / "report.json").is_file())
    check("package wrote manifest.json", (pkg / "manifest.json").is_file())
    check("package report_id surfaced", data["report_id"] == "commercial:run_summary:run_a1")


def test_package_stdout_is_deterministic_json(tmp: Path):
    print("\n[8] package stdout is deterministic JSON")
    report = _write_report_json(tmp / "in8" / "report.json")
    a_code, a_out = run_cli(["package", "--report-json", str(report), "--output-dir", str(tmp / "o8a"), "--created-at", "2026-07-02T00:00:00Z"])
    b_code, b_out = run_cli(["package", "--report-json", str(report), "--output-dir", str(tmp / "o8b"), "--created-at", "2026-07-02T00:00:00Z"])
    a = json.loads(a_out)
    b = json.loads(b_out)
    check("both succeed", a_code == 0 and b_code == 0)
    check("stdout is sorted-key indented JSON", a_out == json.dumps(a, sort_keys=True, indent=2) + "\n")
    # output_path differs only by the chosen output-dir; manifest determinism covered in [9].
    a.pop("output_path"), b.pop("output_path")
    check("stdout payloads identical apart from output_path", a == b)


def test_package_deterministic_manifest(tmp: Path):
    print("\n[9] package with fixed created-at produces deterministic manifest")
    report = _write_report_json(tmp / "in9" / "report.json")
    run_cli(["package", "--report-json", str(report), "--output-dir", str(tmp / "m9a"), "--created-at", "2026-07-02T00:00:00Z"])
    run_cli(["package", "--report-json", str(report), "--output-dir", str(tmp / "m9b"), "--created-at", "2026-07-02T00:00:00Z"])
    man_a = (tmp / "m9a" / "delivery_run_summary_run_a1" / "manifest.json").read_text(encoding="utf-8")
    man_b = (tmp / "m9b" / "delivery_run_summary_run_a1" / "manifest.json").read_text(encoding="utf-8")
    check("manifests are byte-identical across runs", man_a == man_b)


def test_package_copies_optional_video(tmp: Path):
    print("\n[10] package with optional video copies asset through Stage 4.2")
    report = _write_report_json(tmp / "in10" / "report.json")
    video = tmp / "clip.mp4"
    video.write_bytes(b"\x00\x01FAKEVIDEO")
    out_dir = tmp / "out10"
    code, out = run_cli([
        "package", "--report-json", str(report), "--output-dir", str(out_dir),
        "--created-at", "2026-07-02T00:00:00Z", "--video-path", str(video),
    ])
    data = json.loads(out)
    check("package w/ video exit 0", code == 0)
    copied = Path(data["output_path"]) / "assets" / "video.mp4"
    check("video copied into package assets", copied.is_file())
    check("copied bytes match source", copied.read_bytes() == b"\x00\x01FAKEVIDEO")


def test_package_missing_explicit_video(tmp: Path):
    print("\n[11] package with missing explicit video returns deterministic error")
    report = _write_report_json(tmp / "in11" / "report.json")
    ghost = tmp / "missing_clip.mp4"
    argv = [
        "package", "--report-json", str(report), "--output-dir", str(tmp / "out11"),
        "--created-at", "2026-07-02T00:00:00Z", "--video-path", str(ghost),
    ]
    code_a, out_a = run_cli(argv)
    code_b, out_b = run_cli(argv)
    data = json.loads(out_a)
    check("missing video exit 1", code_a == 1)
    check("missing video kind PACKAGE_BUILD_FAILED", data["error_kind"] == "PACKAGE_BUILD_FAILED")
    check("original 4.2 error_kind carried in metadata", data["metadata"].get("error_kind") == "SOURCE_VIDEO_NOT_FOUND")
    check("missing video error is deterministic", out_a == out_b)


def test_report_rejects_missing_index(tmp: Path):
    print("\n[12] report command rejects missing index path")
    code, out = run_cli([
        "report", "--index-path", str(tmp / "no_index.json"),
        "--report-type", "run_summary", "--output", str(tmp / "r.json"),
        "--created-at", "T", "--run-id", "run_a1",
    ])
    data = json.loads(out)
    check("report missing index exit 1", code == 1)
    check("report missing index kind INVALID_INDEX_PATH", data["error_kind"] == "INVALID_INDEX_PATH")
    check("report missing index wrote no output", not (tmp / "r.json").exists())


def test_report_boundary(tmp: Path):
    print("\n[13] report uses only KnowledgeService/public report builder boundary")
    src = inspect.getsource(cli._cmd_report)
    check("report uses KnowledgeService boundary", "KnowledgeService" in src)
    check("report uses public build_commercial_report", "build_commercial_report" in src)
    check("report uses IndexStore persistence boundary", "IndexStore" in src)
    lower = ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
             "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine")
    check("report avoids lower-layer engine tokens", all(tok not in src for tok in lower))


def test_report_type_unsupported(tmp: Path):
    print("\n[13b] unsupported report-type rejected as INVALID_ARGUMENTS")
    for rtype in ("style_summary", "portfolio", "system"):
        code, out = run_cli([
            "report", "--index-path", str(tmp / "x.json"), "--report-type", rtype,
            "--output", str(tmp / "o.json"), "--created-at", "T", "--run-id", "r",
        ])
        data = json.loads(out)
        check(f"{rtype} exit 1", code == 1)
        check(f"{rtype} kind INVALID_ARGUMENTS", data["error_kind"] == "INVALID_ARGUMENTS")
        check(f"{rtype} detail is Stage 4.1 message", data["error_detail"] == "report-type not supported by Stage 4.1 builder")


def test_no_traceback_on_expected_errors(tmp: Path):
    print("\n[14] stdout never contains traceback for expected errors")
    outs = []
    outs.append(run_cli(["package", "--report-json", str(tmp / "x.json"), "--output-dir", str(tmp / "d"), "--created-at", "T"])[1])
    bad = tmp / "b.json"
    bad.write_text("{", encoding="utf-8")
    outs.append(run_cli(["package", "--report-json", str(bad), "--output-dir", str(tmp / "d"), "--created-at", "T"])[1])
    outs.append(run_cli(["validate", "--report-json", str(tmp / "x.json"), "--output-dir", str(tmp / "d"), "--created-at", "T"])[1])
    outs.append(run_cli(["report", "--index-path", str(tmp / "x.json"), "--report-type", "run_summary", "--output", str(tmp / "o.json"), "--created-at", "T", "--run-id", "r"])[1])
    check("no 'Traceback' in any expected-error stdout", all("Traceback" not in o for o in outs))
    check("every expected error is valid JSON", all(json.loads(o)["ok"] is False for o in outs))


def test_rejects_url_paths(tmp: Path):
    print("\n[15] CLI rejects http:// and https:// paths")
    c1, o1 = run_cli(["package", "--report-json", "http://evil/report.json", "--output-dir", str(tmp / "d"), "--created-at", "T"])
    c2, o2 = run_cli(["validate", "--report-json", "https://evil/report.json", "--output-dir", str(tmp / "d"), "--created-at", "T"])
    d1, d2 = json.loads(o1), json.loads(o2)
    check("http package exit 1", c1 == 1 and d1["error_kind"] == "INVALID_ARGUMENTS")
    check("https validate exit 1", c2 == 1 and d2["error_kind"] == "INVALID_ARGUMENTS")


def test_no_network_cloud_imports(tmp: Path):
    print("\n[16] no network/cloud imports in cli.py")
    src = _cli_src()
    forbidden = ("requests", "httpx", "urllib.request", "boto3", "socket", "http.client", "openai", "anthropic")
    for tok in forbidden:
        check(f"cli.py free of '{tok}'", tok not in src)


def test_no_lower_layer_engine_imports(tmp: Path):
    print("\n[17] no lower-layer knowledge engine imports in cli.py")
    src = _cli_src()
    forbidden = ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                 "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine")
    for tok in forbidden:
        check(f"cli.py free of '{tok}'", tok not in src)


def test_package_does_not_touch_knowledge(tmp: Path):
    print("\n[18] package command does not import or invoke KnowledgeService directly")
    src = inspect.getsource(cli._cmd_package)
    check("_cmd_package free of KnowledgeService", "KnowledgeService" not in src)
    check("_cmd_package free of build_commercial_report", "build_commercial_report" not in src)
    check("_cmd_package free of IndexStore", "IndexStore" not in src)


def test_overwrite_passthrough(tmp: Path):
    print("\n[19] --overwrite passes through to Stage 4.2")
    report = _write_report_json(tmp / "in19" / "report.json")
    out_dir = tmp / "out19"
    base = ["package", "--report-json", str(report), "--output-dir", str(out_dir), "--created-at", "2026-07-02T00:00:00Z"]
    c1, _ = run_cli(base)
    c2, o2 = run_cli(base)  # second run without overwrite must fail
    c3, o3 = run_cli(base + ["--overwrite"])  # with overwrite must succeed
    d2 = json.loads(o2)
    check("first package succeeds", c1 == 0)
    check("second package without overwrite fails", c2 == 1 and d2["error_kind"] == "PACKAGE_BUILD_FAILED")
    check("stage 4.2 reported PACKAGE_ALREADY_EXISTS", d2["metadata"].get("error_kind") == "PACKAGE_ALREADY_EXISTS")
    check("third package with --overwrite succeeds", c3 == 0 and json.loads(o3)["ok"] is True)


def test_validate_writes_nothing(tmp: Path):
    print("\n[20] no writes occur during validate command")
    report = _write_report_json(tmp / "in20" / "report.json")
    before = report.read_bytes()
    out_dir = tmp / "out20"
    video = tmp / "v20.mp4"
    video.write_bytes(b"vid")
    code, out = run_cli([
        "validate", "--report-json", str(report), "--output-dir", str(out_dir),
        "--created-at", "T", "--video-path", str(video),
    ])
    check("validate exit 0", code == 0)
    check("output-dir not created", not out_dir.exists())
    check("report.json unchanged", report.read_bytes() == before)


def test_forbidden_token_static_scan(tmp: Path):
    print("\n[static] cli.py forbidden-token scan")
    src = _cli_src()
    forbidden = (
        "KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
        "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine",
        "requests", "httpx", "urllib.request", "boto3", "socket", "http.client",
        "openai", "anthropic",
    )
    check("cli.py contains no forbidden tokens", all(tok not in src for tok in forbidden))


def main():
    with tempfile.TemporaryDirectory() as d:
        for fn in (
            test_version,
            test_invalid_command,
            test_validate_missing_report_json,
            test_validate_does_not_create_output_dir,
            test_package_missing_report_json,
            test_package_invalid_report_json,
            test_package_creates_delivery,
            test_package_stdout_is_deterministic_json,
            test_package_deterministic_manifest,
            test_package_copies_optional_video,
            test_package_missing_explicit_video,
            test_report_rejects_missing_index,
            test_report_boundary,
            test_report_type_unsupported,
            test_no_traceback_on_expected_errors,
            test_rejects_url_paths,
            test_no_network_cloud_imports,
            test_no_lower_layer_engine_imports,
            test_package_does_not_touch_knowledge,
            test_overwrite_passthrough,
            test_validate_writes_nothing,
            test_forbidden_token_static_scan,
        ):
            with tempfile.TemporaryDirectory() as sub:
                fn(Path(sub))

    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
