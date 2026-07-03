"""test_first_prospect_execution_log.py - SCOS Stage 4.12 execution log suite."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from first_prospect_execution_log import record_first_prospect_execution  # noqa: E402
from prospect_models import (  # noqa: E402
    FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION,
    FirstProspectExecutionLogError,
    FirstProspectExecutionLogResult,
    ProspectOutreachAction,
    ProspectProfile,
    ProspectResponseStatus,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-03T07:00:00Z"
_LOG_FILE = "prospect_execution_log.json"
_REQUIRED_CHECK_NAMES = (
    "validate_inputs",
    "validate_prospect_profile",
    "validate_outreach_action",
    "validate_response_status",
    "validate_outreach_launch_kit_reference",
    "write_execution_log",
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _profile(metadata=None, **overrides):
    fields = dict(
        prospect_id="prospect-001",
        display_name="Synthetic Clinic Alias",
        business_type="clinic",
        channel="manual_facebook_dm",
        source="manual_local_observation",
        manual_context="Observed unclear booking path in public content.",
        metadata=metadata,
    )
    fields.update(overrides)
    return ProspectProfile.of(**fields)


def _action(action_type="manual_dm", **overrides):
    fields = dict(
        action_id="action-001",
        action_type=action_type,
        message_summary="Sent a short manual note offering a mini-audit.",
        performed_at=_NOW,
        performed_by="SCOS Operator",
        outreach_asset_id="outreach_scripts",
        offered_mini_audit=True,
    )
    fields.update(overrides)
    return ProspectOutreachAction.of(**fields)


def _response(status="interested", **overrides):
    fields = dict(
        status=status,
        response_summary="Owner replied with mild interest.",
        next_action="Prepare a manual mini-audit and follow up.",
        follow_up_due="2026-07-06",
    )
    fields.update(overrides)
    return ProspectResponseStatus.of(**fields)


def _run(output_dir, **overrides):
    kwargs = dict(
        output_dir=output_dir,
        checked_at=_NOW,
        prospect=_profile(),
        outreach_action=_action(),
        response_status=_response(),
    )
    kwargs.update(overrides)
    return record_first_prospect_execution(**kwargs)


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def test_success_and_determinism(tmp: Path):
    print("\n[1-4] success, determinism, byte-identical, containment")
    out = tmp / "exec"
    res = _run(out)
    check("returns Result", isinstance(res, FirstProspectExecutionLogResult))
    check("ok True and logged", res.ok is True and res.logged is True)
    check("schema version", res.schema_version == FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION == 1)
    check("log file written", (out / _LOG_FILE).is_file())

    out2 = tmp / "exec2"
    res2 = _run(out2)
    check("fixed checked_at deterministic id", res.execution_log_id == res2.execution_log_id)
    first_bytes = _read(out / _LOG_FILE)
    res_again = _run(out, overwrite=True)
    check("byte-identical output for fixed inputs", first_bytes == _read(res_again.execution_log_path))
    check("output path stays under output_dir",
          str(Path(res.execution_log_path).resolve()).startswith(str(out.resolve())))


def test_input_validation(tmp: Path):
    print("\n[5-9] input validation")
    err_dir = record_first_prospect_execution(
        output_dir="", checked_at=_NOW, prospect=_profile(),
        outreach_action=_action(), response_status=_response())
    check("missing output_dir INVALID_ARGUMENTS",
          isinstance(err_dir, FirstProspectExecutionLogError) and err_dir.error_kind == "INVALID_ARGUMENTS")
    err_at = record_first_prospect_execution(
        output_dir=tmp / "a", checked_at="", prospect=_profile(),
        outreach_action=_action(), response_status=_response())
    check("missing checked_at INVALID_ARGUMENTS",
          isinstance(err_at, FirstProspectExecutionLogError) and err_at.error_kind == "INVALID_ARGUMENTS")
    err_url = _run("https://example.test/out")
    check("URL output_dir rejected",
          isinstance(err_url, FirstProspectExecutionLogError) and err_url.error_kind == "INVALID_ARGUMENTS")
    err_kit_url = _run(tmp / "b", outreach_launch_kit_path="http://example.test/kit.json")
    check("URL outreach_launch_kit_path rejected",
          isinstance(err_kit_url, FirstProspectExecutionLogError) and err_kit_url.error_kind == "INVALID_ARGUMENTS")
    err_missing = _run(tmp / "c", outreach_launch_kit_path=tmp / "ghost.json")
    check("missing outreach_launch_kit_path INPUT_NOT_FOUND",
          isinstance(err_missing, FirstProspectExecutionLogError) and err_missing.error_kind == "INPUT_NOT_FOUND")


def test_kit_reference(tmp: Path):
    print("\n[10] valid outreach_launch_kit referenced without mutation")
    kit = tmp / "outreach_readiness_manifest.json"
    kit.write_text(json.dumps({"ok": True}, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    before = kit.read_bytes()
    res = _run(tmp / "kit_ok", outreach_launch_kit_path=kit)
    after = kit.read_bytes()
    check("kit run succeeds", isinstance(res, FirstProspectExecutionLogResult))
    check("kit path referenced", res.outreach_launch_kit_path == str(kit))
    check("kit not mutated", before == after)


def test_prospect_validation(tmp: Path):
    print("\n[11-15] prospect validation and sensitive metadata")
    bad = _run(tmp / "no_biz", prospect=_profile(business_type=""))
    check("missing required field INVALID_PROSPECT",
          isinstance(bad, FirstProspectExecutionLogError) and bad.error_kind == "INVALID_PROSPECT")
    for key in ("phone", "email", "address", "token", "secret", "password"):
        rej = _run(tmp / f"pii_{key}", prospect=_profile(metadata={key: "synthetic forbidden value"}))
        check(f"metadata {key} rejected",
              isinstance(rej, FirstProspectExecutionLogError) and rej.error_kind == "SENSITIVE_DATA_REJECTED")


def test_action_and_response(tmp: Path):
    print("\n[16-19] action and response validation")
    no_summary = _run(tmp / "no_summary", outreach_action=_action(message_summary=""))
    check("missing message_summary INVALID_OUTREACH_ACTION",
          isinstance(no_summary, FirstProspectExecutionLogError) and no_summary.error_kind == "INVALID_OUTREACH_ACTION")
    bad_type = _run(tmp / "bad_type", outreach_action=_action(action_type="auto_broadcast"))
    check("invalid action_type INVALID_OUTREACH_ACTION",
          isinstance(bad_type, FirstProspectExecutionLogError) and bad_type.error_kind == "INVALID_OUTREACH_ACTION")
    bad_status = _run(tmp / "bad_status", response_status=_response(status="converted"))
    check("invalid status INVALID_RESPONSE_STATUS",
          isinstance(bad_status, FirstProspectExecutionLogError) and bad_status.error_kind == "INVALID_RESPONSE_STATUS")
    no_next = _run(tmp / "no_next", response_status=_response(status="follow_up_needed", next_action=""))
    check("follow_up_needed requires next_action",
          isinstance(no_next, FirstProspectExecutionLogError) and no_next.error_kind == "INVALID_RESPONSE_STATUS")
    not_contacted = _run(tmp / "not_contacted",
                         response_status=_response(status="not_contacted", next_action="", follow_up_due=None))
    check("not_contacted allows empty next_action", isinstance(not_contacted, FirstProspectExecutionLogResult))


def test_overwrite(tmp: Path):
    print("\n[20-21] overwrite behavior")
    out = tmp / "overwrite"
    first = _run(out)
    before = _read(first.execution_log_path)
    blocked = _run(out)
    check("overwrite False blocks existing OUTPUT_EXISTS",
          isinstance(blocked, FirstProspectExecutionLogError) and blocked.error_kind == "OUTPUT_EXISTS")
    replaced = _run(out, overwrite=True)
    check("overwrite True replaces", isinstance(replaced, FirstProspectExecutionLogResult))
    check("overwrite deterministic", before == _read(replaced.execution_log_path))


def test_serialization_and_checks(tmp: Path):
    print("\n[22-24] serialization and required checks")
    res = _run(tmp / "serialize")
    check("result.to_dict deterministic",
          json.dumps(res.to_dict(), sort_keys=True) == json.dumps(res.to_dict(), sort_keys=True))
    err1 = record_first_prospect_execution(
        output_dir="", checked_at=_NOW, prospect=_profile(),
        outreach_action=_action(), response_status=_response())
    err2 = record_first_prospect_execution(
        output_dir="", checked_at=_NOW, prospect=_profile(),
        outreach_action=_action(), response_status=_response())
    check("error.to_dict deterministic",
          json.dumps(err1.to_dict(), sort_keys=True) == json.dumps(err2.to_dict(), sort_keys=True))
    present = {chk.check_name for chk in res.checks}
    check("checks include all required names", all(name in present for name in _REQUIRED_CHECK_NAMES))


def test_static_boundaries():
    print("\n[25-29] static boundary scans")
    source = (_COMMERCIAL / "first_prospect_execution_log.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "selenium", "playwright", "smtp", "imaplib", "smtplib"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeIndex", "KnowledgeQueryEngine", "KnowledgeExplainEngine",
                  "KnowledgeInsightEngine", "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("send_email", "send_message", "auto_dm"):
        check(f"no auto-message token '{token}'", token not in source)
    for token in ("scrape", "scraper", "CRM", "selenium", "playwright"):
        check(f"no scraping/CRM token '{token}'", token not in source)
    for token in ("payment", "auth"):
        check(f"no payment/auth token '{token}'", token not in source)


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_success_and_determinism(tmp)
        test_input_validation(tmp)
        test_kit_reference(tmp)
        test_prospect_validation(tmp)
        test_action_and_response(tmp)
        test_overwrite(tmp)
        test_serialization_and_checks(tmp)
    test_static_boundaries()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
