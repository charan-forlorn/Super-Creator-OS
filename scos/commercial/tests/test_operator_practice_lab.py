"""test_operator_practice_lab.py - SCOS Stage 4.10 practice lab suite."""

from __future__ import annotations

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

from operator_practice_lab import (  # noqa: E402
    available_practice_scenarios,
    run_operator_practice_scenario,
)
from practice_models import (  # noqa: E402
    OPERATOR_PRACTICE_SCHEMA_VERSION,
    OperatorPracticeError,
    OperatorPracticeResult,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T06:00:00Z"
_SCENARIO_IDS = (
    "clinic-ready",
    "clinic-missing-offer",
    "spa-low-content",
    "creator-video-audit",
    "restaurant-local-promo",
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _run(tmp: Path, scenario_id: str = "clinic-ready", **kwargs):
    return run_operator_practice_scenario(
        scenario_id=scenario_id,
        output_dir=tmp / "practice",
        checked_at=_NOW,
        **kwargs,
    )


def _read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _snapshot(paths: tuple[str | Path, ...]) -> dict[str, str]:
    return {Path(path).name: _read(path) for path in paths}


def _contains_sensitive_key(value) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("phone", "email", "address")):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def test_success_and_outputs(tmp: Path):
    print("\n[1-14] clinic-ready success and output files")
    res = _run(tmp)
    check("returns OperatorPracticeResult", isinstance(res, OperatorPracticeResult))
    check("ok True", res.ok is True)
    check("schema version", res.schema_version == OPERATOR_PRACTICE_SCHEMA_VERSION == 1)
    check("clinic-ready PASS", res.practice_status == "PASS")
    check("dry_run folder created", (tmp / "practice" / "clinic-ready" / "dry_run").is_dir())
    check("launch_certification folder created",
          (tmp / "practice" / "clinic-ready" / "launch_certification").is_dir())
    for attr in (
        "practice_summary_path",
        "practice_walkthrough_path",
        "customer_facing_files_path",
        "internal_evidence_files_path",
        "operator_observations_path",
    ):
        path = Path(getattr(res, attr))
        check(f"{path.name} written", path.is_file())
        check(f"{path.name} under output_dir",
              str(path.resolve()).startswith(str((tmp / "practice").resolve())))
    summary = _read_json(res.practice_summary_path)
    check("practice_summary schema", summary["schema_version"] == 1)
    check("summary records scenario", summary["scenario_id"] == "clinic-ready")
    check("summary records status", summary["practice_status"] == res.practice_status)


def test_all_scenarios_available_and_run(tmp: Path):
    print("\n[15-20] predefined scenarios available and executable")
    scenarios = available_practice_scenarios()
    ids = tuple(item.scenario_id for item in scenarios)
    check("all five predefined scenarios are available", ids == tuple(sorted(_SCENARIO_IDS)))
    for scenario_id in _SCENARIO_IDS:
        res = run_operator_practice_scenario(
            scenario_id=scenario_id,
            output_dir=tmp / f"practice_{scenario_id}",
            checked_at=_NOW,
        )
        check(f"{scenario_id} returns result", isinstance(res, OperatorPracticeResult))
        check(f"{scenario_id} deterministic id", getattr(res, "practice_id", "") == f"operator-practice-{scenario_id}")


def test_input_errors(tmp: Path):
    print("\n[21-25] input validation errors")
    unknown = _run(tmp, "unknown-scenario")
    check("unknown scenario UNKNOWN_SCENARIO", isinstance(unknown, OperatorPracticeError)
          and unknown.error_kind == "UNKNOWN_SCENARIO")
    missing_id = run_operator_practice_scenario(
        scenario_id="", output_dir=tmp / "practice_missing_id", checked_at=_NOW)
    check("missing scenario_id INVALID_ARGUMENTS", isinstance(missing_id, OperatorPracticeError)
          and missing_id.error_kind == "INVALID_ARGUMENTS")
    missing_out = run_operator_practice_scenario(
        scenario_id="clinic-ready", output_dir="", checked_at=_NOW)
    check("missing output_dir INVALID_ARGUMENTS", isinstance(missing_out, OperatorPracticeError)
          and missing_out.error_kind == "INVALID_ARGUMENTS")
    missing_time = run_operator_practice_scenario(
        scenario_id="clinic-ready", output_dir=tmp / "practice_missing_time", checked_at="")
    check("missing checked_at INVALID_ARGUMENTS", isinstance(missing_time, OperatorPracticeError)
          and missing_time.error_kind == "INVALID_ARGUMENTS")
    url_out = run_operator_practice_scenario(
        scenario_id="clinic-ready", output_dir="https://example.test/practice", checked_at=_NOW)
    check("URL output_dir rejected", isinstance(url_out, OperatorPracticeError)
          and url_out.error_kind == "INVALID_ARGUMENTS")


def test_file_separation_and_plain_language(tmp: Path):
    print("\n[26-34] file separation and operator-readable markdown")
    res = _run(tmp, overwrite=True)
    customer = _read(res.customer_facing_files_path)
    internal = _read(res.internal_evidence_files_path)
    walkthrough = _read(res.practice_walkthrough_path)
    observations = _read(res.operator_observations_path)
    for name in (
        "report.md",
        "qa_summary.md",
        "improvement_plan.md",
        "customer_intake_checklist.md",
        "delivery_handoff.md",
        "acceptance_certificate.md",
        "pricing_offer_checklist.md",
    ):
        check(f"{name} marked synthetic/practice", f"Synthetic/practice only: `{name}`" in customer)
    check("customer-facing list excludes raw JSON evidence", ".json" not in customer)
    check("internal evidence includes manifests", "manifest" in internal.lower())
    check("internal evidence includes JSON evidence", ".json" in internal)
    check("internal evidence warns not to send by default",
          "do not send raw JSON files, manifests, blockers, or internal evidence to customers by default" in internal)
    for token in ("PASS", "CONDITIONAL", "FAIL"):
        check(f"walkthrough explains {token}", token in walkthrough)
    check("walkthrough is non-developer readable", "What happened" in walkthrough and "Where to inspect" in walkthrough)
    check("observations include manual checklist", "Manual checklist after each run" in observations)
    check("observations ask key question", "Is the report understandable?" in observations)
    lowered = "\n".join([customer, walkthrough, observations]).lower()
    for phrase in ("send this message", "ready-to-send", "copy and paste", "automated outreach"):
        check(f"no ready outreach phrase: {phrase}", phrase not in lowered)


def test_determinism_and_overwrite(tmp: Path):
    print("\n[35-39] deterministic outputs and overwrite behavior")
    out = tmp / "practice_det"
    first = run_operator_practice_scenario(
        scenario_id="clinic-ready",
        output_dir=out,
        checked_at=_NOW,
    )
    second = run_operator_practice_scenario(
        scenario_id="clinic-ready",
        output_dir=out,
        checked_at=_NOW,
    )
    check("overwrite False fails if scenario output exists", isinstance(second, OperatorPracticeError)
          and second.error_kind == "OUTPUT_ALREADY_EXISTS")
    files = (
        first.practice_summary_path,
        first.practice_walkthrough_path,
        first.customer_facing_files_path,
        first.internal_evidence_files_path,
        first.operator_observations_path,
    )
    before = _snapshot(files)
    over = run_operator_practice_scenario(
        scenario_id="clinic-ready",
        output_dir=out,
        checked_at=_NOW,
        overwrite=True,
    )
    check("overwrite True succeeds", isinstance(over, OperatorPracticeResult))
    after = _snapshot((
        over.practice_summary_path,
        over.practice_walkthrough_path,
        over.customer_facing_files_path,
        over.internal_evidence_files_path,
        over.operator_observations_path,
    ))
    check("fixed checked_at deterministic practice_summary.json",
          before["practice_summary.json"] == after["practice_summary.json"])
    check("fixed checked_at deterministic markdown",
          {k: v for k, v in before.items() if k != "practice_summary.json"}
          == {k: v for k, v in after.items() if k != "practice_summary.json"})
    check("result.to_dict deterministic",
          json.dumps(over.to_dict(), sort_keys=True) == json.dumps(over.to_dict(), sort_keys=True))
    err1 = run_operator_practice_scenario(scenario_id="", output_dir=tmp / "a", checked_at=_NOW)
    err2 = run_operator_practice_scenario(scenario_id="", output_dir=tmp / "b", checked_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(err1.to_dict(), sort_keys=True) == json.dumps(err2.to_dict(), sort_keys=True))


def test_no_pii_and_static_boundaries():
    print("\n[40-43] no PII and static boundary scans")
    scenarios = available_practice_scenarios()
    for scenario in scenarios:
        data = scenario.to_dict()
        check(f"{scenario.scenario_id} no PII-like keys", not _contains_sensitive_key(data))
    source = (_COMMERCIAL / "operator_practice_lab.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "payment", "auth", "CRM", "invoice"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeService", "KnowledgeIndex", "KnowledgeQueryEngine",
                  "KnowledgeExplainEngine", "KnowledgeInsightEngine", "query_engine",
                  "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("build_commercial_report", "create_delivery_package",
                  "run_commercial_delivery", "certify_commercial_run",
                  "generate_first_customer_kit", "review_monetization_readiness"):
        check(f"no direct earlier-stage token '{token}'", token not in source)
    check("uses Stage 4.8 public boundary", "run_first_paid_customer_dry_run" in source)
    check("uses actual Stage 4.9 public boundary", "create_commercial_launch_certification_pack" in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success_and_outputs(tmp)
        test_all_scenarios_available_and_run(tmp)
        test_input_errors(tmp)
        test_file_separation_and_plain_language(tmp)
        test_determinism_and_overwrite(tmp)
    test_no_pii_and_static_boundaries()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
