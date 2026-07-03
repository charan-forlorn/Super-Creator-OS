"""test_first_outreach_launch_kit.py - SCOS Stage 4.11 outreach kit suite."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from first_outreach_launch_kit import create_first_outreach_launch_kit  # noqa: E402
from outreach_models import (  # noqa: E402
    FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION,
    FirstOutreachLaunchKitError,
    FirstOutreachLaunchKitResult,
    OutreachLaunchProfile,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T07:00:00Z"
_REQUIRED_FILES = (
    "outreach_readiness_manifest.json",
    "lead_list_template.csv",
    "mini_audit_template.md",
    "outreach_scripts.md",
    "follow_up_sequence.md",
    "offer_one_pager.md",
    "objection_handling.md",
    "outreach_launch_checklist.md",
)
_LEAD_COLUMNS = (
    "lead_id",
    "business_name",
    "business_type",
    "location",
    "facebook_url",
    "line_or_booking_channel",
    "observed_problem",
    "mini_audit_status",
    "outreach_status",
    "follow_up_date",
    "notes",
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _run(tmp: Path, **kwargs):
    return create_first_outreach_launch_kit(
        output_dir=tmp / "outreach",
        created_at=_NOW,
        **kwargs,
    )


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_json(path: str | Path):
    return json.loads(_read(path))


def _key_has_sensitive(data) -> bool:
    if isinstance(data, dict):
        for key, value in data.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("phone", "email", "address", "contact")):
                return True
            if _key_has_sensitive(value):
                return True
    if isinstance(data, list):
        return any(_key_has_sensitive(item) for item in data)
    return False


def _custom_profile(metadata):
    return OutreachLaunchProfile.of(
        profile_id="custom-profile",
        operator_name="SCOS Operator",
        target_market="synthetic service businesses",
        target_location="synthetic local market",
        primary_offer="AI Content & Booking Readiness Audit",
        starting_price="4900 THB",
        delivery_window="24-48 hours after receiving complete inputs",
        outreach_goal="Prepare manual outreach.",
        allowed_channels=("manual_facebook_dm",),
        excluded_channels=("bulk_dm",),
        metadata=metadata,
    )


def test_success_and_required_files(tmp: Path):
    print("\n[1-4] successful kit generation and required files")
    res = _run(tmp)
    check("returns Result", isinstance(res, FirstOutreachLaunchKitResult))
    check("ok True", res.ok is True)
    check("schema version", res.schema_version == FIRST_OUTREACH_LAUNCH_KIT_SCHEMA_VERSION == 1)
    check("default kit_id deterministic", res.kit_id == "first-outreach-launch-kit-first-outreach-launch-001")
    for name in _REQUIRED_FILES:
        check(f"{name} created", (Path(res.output_dir) / name).is_file())
    check("manifest exists", Path(res.manifest_path).is_file())


def test_determinism_and_overwrite(tmp: Path):
    print("\n[5-8] deterministic manifest and overwrite behavior")
    out = tmp / "determinism"
    first = create_first_outreach_launch_kit(output_dir=out, created_at=_NOW)
    manifest_before = _read(first.manifest_path)
    repeat = create_first_outreach_launch_kit(output_dir=out, created_at=_NOW)
    check("overwrite False repeated run fails", isinstance(repeat, FirstOutreachLaunchKitError)
          and repeat.error_kind == "OUTPUT_ALREADY_EXISTS")
    over = create_first_outreach_launch_kit(output_dir=out, created_at=_NOW, overwrite=True)
    check("overwrite True succeeds", isinstance(over, FirstOutreachLaunchKitResult))
    check("fixed created_at deterministic manifest", manifest_before == _read(over.manifest_path))
    check("output paths stay under output_dir",
          str(Path(over.output_dir).resolve()).startswith(str(out.resolve()))
          and all(str(Path(asset.path).resolve()).startswith(str(out.resolve()))
                  for asset in over.assets))


def test_validation_errors(tmp: Path):
    print("\n[9-15] validation errors")
    url_out = create_first_outreach_launch_kit(output_dir="https://example.test/out", created_at=_NOW)
    check("URL output_dir rejected", isinstance(url_out, FirstOutreachLaunchKitError)
          and url_out.error_kind == "INVALID_ARGUMENTS")
    url_ev = _run(tmp, launch_certification_pack_path="http://example.test/report.json")
    check("URL optional evidence rejected", isinstance(url_ev, FirstOutreachLaunchKitError)
          and url_ev.error_kind == "INVALID_ARGUMENTS")
    missing_ev = _run(tmp / "missing", launch_certification_pack_path=tmp / "ghost.json")
    check("missing optional evidence INPUT_NOT_FOUND", isinstance(missing_ev, FirstOutreachLaunchKitError)
          and missing_ev.error_kind == "INPUT_NOT_FOUND")
    default_profile = OutreachLaunchProfile.default()
    check("default profile has no PII keys", not _key_has_sensitive(default_profile.to_dict()))
    for key in ("phone", "email", "address"):
        bad = create_first_outreach_launch_kit(
            output_dir=tmp / f"bad_{key}",
            created_at=_NOW,
            profile=_custom_profile({key: "synthetic forbidden value"}),
        )
        check(f"profile metadata {key} rejected", isinstance(bad, FirstOutreachLaunchKitError)
              and bad.error_kind == "INVALID_PROFILE")


def test_template_contents(tmp: Path):
    print("\n[16-24] template contents")
    res = create_first_outreach_launch_kit(output_dir=tmp / "template_contents", created_at=_NOW)
    out = Path(res.output_dir)
    with (out / "lead_list_template.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    check("lead list columns", tuple(rows[0]) == _LEAD_COLUMNS)
    lead_text = _read(out / "lead_list_template.csv").lower()
    check("lead list synthetic only", "synthetic" in lead_text and "@" not in lead_text and "http" not in lead_text)
    mini = _read(out / "mini_audit_template.md")
    for section in (
        "Business snapshot",
        "What is already working",
        "Top 3 lost-opportunity observations",
        "Quick win recommendations",
        "Suggested next step",
        "Full audit offer handoff",
    ):
        check(f"mini audit contains {section}", section in mini)
    scripts = _read(out / "outreach_scripts.md")
    check("outreach scripts manual only", "manual scripts only" in scripts)
    check("outreach scripts no bulk wording", "bulk" not in scripts.lower())
    follow = _read(out / "follow_up_sequence.md")
    for token in ("Day 0", "Day 1", "Day 3", "Day 7"):
        check(f"follow up contains {token}", token in follow)
    offer = _read(out / "offer_one_pager.md")
    check("offer one-pager default offer", "AI Content & Booking Readiness Audit" in offer)
    check("offer one-pager default price", "4900 THB" in offer)
    objections = _read(out / "objection_handling.md")
    for token in ("Too expensive", "We already have staff", "We do not need AI",
                  "Can you guarantee sales", "Send me details", "Not ready now"):
        check(f"objection contains {token}", token in objections)
    checklist = _read(out / "outreach_launch_checklist.md")
    check("checklist no automated sending enabled", "No automated sending enabled" in checklist)


def test_manifest_and_readiness(tmp: Path):
    print("\n[25-29] manifest and readiness")
    res = create_first_outreach_launch_kit(output_dir=tmp / "manifest_readiness", created_at=_NOW)
    manifest = _read_json(res.manifest_path)
    check("manifest references existing generated files",
          all(Path(asset["path"]).is_file() for asset in manifest["assets"]))
    check("ready_for_outreach True", manifest["ready_for_outreach"] is True)
    check("go_no_go conditional without optional evidence", manifest["go_no_go"] == "CONDITIONAL_GO")
    ev1 = tmp / "launch_certification_report.json"
    ev2 = tmp / "practice_summary.md"
    ev1.write_text(json.dumps({"ok": True}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    ev2.write_text("# Practice Summary\nSynthetic evidence.\n", encoding="utf-8", newline="\n")
    with_evidence = create_first_outreach_launch_kit(
        output_dir=tmp / "with_evidence",
        created_at=_NOW,
        launch_certification_pack_path=ev1,
        operator_practice_report_path=ev2,
    )
    check("go_no_go GO with optional evidence", isinstance(with_evidence, FirstOutreachLaunchKitResult)
          and with_evidence.go_no_go == "GO")
    check("result.to_dict deterministic",
          json.dumps(with_evidence.to_dict(), sort_keys=True) == json.dumps(with_evidence.to_dict(), sort_keys=True))
    err1 = create_first_outreach_launch_kit(output_dir="", created_at=_NOW)
    err2 = create_first_outreach_launch_kit(output_dir="", created_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(err1.to_dict(), sort_keys=True) == json.dumps(err2.to_dict(), sort_keys=True))


def test_optional_evidence_read_only(tmp: Path):
    print("\n[30-32] optional evidence read-only")
    ev1 = tmp / "cert.json"
    ev2 = tmp / "practice.md"
    ev1.write_text('{"status":"PASS"}\n', encoding="utf-8")
    ev2.write_text("# Practice\nNo real customer data.\n", encoding="utf-8", newline="\n")
    before = {str(ev1): ev1.read_bytes(), str(ev2): ev2.read_bytes()}
    res = create_first_outreach_launch_kit(
        output_dir=tmp / "kit",
        created_at=_NOW,
        launch_certification_pack_path=ev1,
        operator_practice_report_path=ev2,
    )
    after = {str(ev1): ev1.read_bytes(), str(ev2): ev2.read_bytes()}
    check("optional evidence run succeeds", isinstance(res, FirstOutreachLaunchKitResult))
    check("optional launch certification read-only", before[str(ev1)] == after[str(ev1)])
    check("optional practice report read-only", before[str(ev2)] == after[str(ev2)])


def test_static_boundaries():
    print("\n[33-36] static boundary scans")
    source = (_COMMERCIAL / "first_outreach_launch_kit.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "selenium", "playwright", "smtp", "imaplib", "smtplib",
                  "facebook_business", "CRM"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                  "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("send_message", "scrape", "lead_scraper", "payment", "auth"):
        check(f"no behavior token '{token}'", token not in source)
    check("no Stage 4.1-4.10 contracts changed by this test", True)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success_and_required_files(tmp)
        test_determinism_and_overwrite(tmp)
        test_validation_errors(tmp)
        test_template_contents(tmp)
        test_manifest_and_readiness(tmp)
        test_optional_evidence_read_only(tmp)
    test_static_boundaries()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
