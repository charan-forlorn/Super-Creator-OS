"""test_first_customer_conversion_handoff.py - SCOS Stage 4.17 handoff suite.

Plain executable script (no pytest). Builds genuine Stage 4.12 -> 4.16 artifacts
by chaining the real upstream stage functions, then patches the resulting Stage
4.16 outcome-review JSON on disk to construct edge-case inputs. Never mutates any
committed artifact; every file lives under a TemporaryDirectory.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent
_ROOT = _HERE.parents[2]

sys.path.insert(0, str(_COMMERCIAL))

from first_customer_conversion_handoff import (  # noqa: E402
    create_first_customer_conversion_handoff,
)
from conversion_handoff_models import (  # noqa: E402
    FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
    FirstCustomerConversionHandoffError,
    FirstCustomerConversionHandoffResult,
)
from first_prospect_outcome_review import review_first_prospect_outcome  # noqa: E402
from first_prospect_mini_audit_delivery_log import (  # noqa: E402
    record_first_prospect_mini_audit_delivery,
)
from first_prospect_mini_audit_handoff import (  # noqa: E402
    create_first_prospect_mini_audit_handoff,
)
from first_prospect_follow_up_decision import decide_first_prospect_follow_up  # noqa: E402
from first_prospect_execution_log import record_first_prospect_execution  # noqa: E402
from prospect_models import (  # noqa: E402
    ProspectOutreachAction,
    ProspectProfile,
    ProspectResponseStatus,
)

_PASS, _FAIL = 0, 0
_NOW = "2026-07-04T07:00:00Z"
_COUNTER = [0]

_DELIVERY_NAME = "first_prospect_mini_audit_delivery_log.json"
_OUTCOME_NAME = "first_prospect_outcome_review.json"
_MANIFEST_NAME = "first_customer_conversion_handoff_manifest.json"
_EVIDENCE_NAME = "evidence_summary.json"
_EXPECTED_FILES = (
    _MANIFEST_NAME,
    "scope_confirmation.md",
    "offer_summary.md",
    "pricing_confirmation.md",
    "manual_close_checklist.md",
    "next_step_script.md",
    "operator_review.md",
    _EVIDENCE_NAME,
)


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _make_delivery(tmp: Path, *, response="interested") -> Path:
    """Chain real 4.12 -> 4.13 -> 4.14 -> 4.15 and return the delivery-log path."""
    _COUNTER[0] += 1
    n = _COUNTER[0]
    log_dir = tmp / f"log{n}"
    prospect = ProspectProfile.of(
        prospect_id="prospect-001", display_name="Synthetic Clinic Alias",
        business_type="clinic", channel="manual_facebook_dm",
        source="manual_local_observation", manual_context="Observed unclear booking path.")
    action = ProspectOutreachAction.of(
        action_id="action-001", action_type="manual_dm",
        message_summary="Sent a short manual note offering a mini-audit.",
        performed_at=_NOW, performed_by="SCOS Operator")
    response_status = ProspectResponseStatus.of(
        status=response, response_summary="Owner replied with mild interest.",
        next_action="Prepare a manual mini-audit.")
    rec = record_first_prospect_execution(
        output_dir=log_dir, checked_at=_NOW, prospect=prospect,
        outreach_action=action, response_status=response_status)
    dec_path = tmp / f"decision{n}.json"
    decide_first_prospect_follow_up(
        execution_log_path=rec.execution_log_path, checked_at=_NOW, output_path=dec_path)
    hout = tmp / f"handoff{n}"
    hr = create_first_prospect_mini_audit_handoff(
        decision_path=dec_path, checked_at=_NOW, output_dir=hout)
    dl_dir = tmp / f"dl{n}"
    record_first_prospect_mini_audit_delivery(
        output_path=dl_dir, handoff_manifest_path=Path(hr.manifest_path), checked_at=_NOW,
        operator_review_status="approved_for_manual_send", manual_send_status="sent_manually",
        prospect_response_status="interested", sent_at=_NOW, response_received_at=_NOW)
    return dl_dir / _DELIVERY_NAME


def _base_outcome(tmp: Path) -> Path:
    """A genuine, unpatched conversion-ready Stage 4.16 outcome review."""
    dl = _make_delivery(tmp)
    n = _COUNTER[0]
    o_dir = tmp / f"outcome{n}"
    review_first_prospect_outcome(delivery_log_path=dl, checked_at=_NOW, output_path=o_dir)
    return o_dir / _OUTCOME_NAME


def _patched(tmp: Path, mutate, label="patched") -> Path:
    base = _base_outcome(tmp)
    data = json.loads(base.read_text(encoding="utf-8"))
    mutate(data)
    n = _COUNTER[0]
    out = tmp / f"{label}{n}.json"
    _write_json(out, data)
    return out


def test_happy_path(tmp: Path):
    print("\n[01-08] valid conversion-ready outcome -> full handoff package")
    src = _base_outcome(tmp)
    out = tmp / "out_happy"
    r = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW)
    check("returns Result", isinstance(r, FirstCustomerConversionHandoffResult))
    check("accepted is True", getattr(r, "accepted", False) is True)
    check("ok is True", getattr(r, "ok", False) is True)
    check("schema_version == 1", r.schema_version == FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION == 1)
    hd = Path(r.handoff_dir)
    check("handoff_dir exists", hd.is_dir())
    present = all((hd / name).is_file() for name in _EXPECTED_FILES)
    check("all 8 artifacts exist on disk", present)
    check("artifacts tuple has 8 entries", len(r.artifacts) == 8)
    check("artifact paths all exist", all(Path(a.path).exists() for a in r.artifacts))


def test_manifest_and_evidence(tmp: Path):
    print("\n[09-13] manifest + evidence integrity")
    src = _base_outcome(tmp)
    out = tmp / "out_manifest"
    r = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW)
    manifest = json.loads(Path(r.manifest_path).read_text(encoding="utf-8"))
    check("manifest schema_version == 1", manifest.get("schema_version") == 1)
    check("manifest handoff_id matches result", manifest.get("handoff_id") == r.handoff_id)
    check("manifest references real artifact paths",
          all(Path(a["path"]).exists() for a in manifest.get("artifacts", [])))
    ev = json.loads((Path(r.handoff_dir) / _EVIDENCE_NAME).read_text(encoding="utf-8"))
    check("evidence_summary has source review id + prospect",
          ev.get("outcome_review_id") == r.outcome_review_id
          and ev.get("prospect_id") == r.prospect_id
          and ev.get("checked_at") == _NOW)
    check("evidence_summary records action + readiness",
          ev.get("action") == "REQUEST_SCOPE_CONFIRMATION" and ev.get("ready_for_handoff") is True)


def test_handoff_id(tmp: Path):
    print("\n[14-17] deterministic + explicit handoff id")
    src = _base_outcome(tmp)
    r1 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=tmp / "hid_a", checked_at=_NOW)
    r2 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=tmp / "hid_b", checked_at=_NOW)
    check("derived handoff_id deterministic", r1.handoff_id == r2.handoff_id)
    check("derived handoff_id has deterministic prefix",
          r1.handoff_id.startswith("first-customer-conversion-"))
    r3 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=tmp / "hid_c", checked_at=_NOW,
        handoff_id="My Handoff!! 001")
    check("explicit handoff_id sanitized", r3.handoff_id == "my-handoff-001")
    check("explicit handoff_id dir used", Path(r3.handoff_dir).name == "my-handoff-001")


def test_overwrite(tmp: Path):
    print("\n[18-21] overwrite semantics + byte determinism")
    src = _base_outcome(tmp)
    out = tmp / "out_over"
    r1 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW)
    first_manifest = Path(r1.manifest_path).read_text(encoding="utf-8")
    first_evidence = (Path(r1.handoff_dir) / _EVIDENCE_NAME).read_text(encoding="utf-8")
    r2 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW)
    check("repeat without overwrite -> OUTPUT_EXISTS",
          isinstance(r2, FirstCustomerConversionHandoffError) and r2.error_kind == "OUTPUT_EXISTS")
    r3 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW, overwrite=True)
    check("repeat with overwrite -> Result", isinstance(r3, FirstCustomerConversionHandoffResult))
    second_manifest = Path(r3.manifest_path).read_text(encoding="utf-8")
    second_evidence = (Path(r3.handoff_dir) / _EVIDENCE_NAME).read_text(encoding="utf-8")
    check("manifest byte-identical across overwrite", first_manifest == second_manifest)
    check("evidence_summary byte-identical across overwrite", first_evidence == second_evidence)


def test_input_errors(tmp: Path):
    print("\n[22-27] input + contract errors")
    r = create_first_customer_conversion_handoff(
        outcome_review_path="https://x.test/o.json", output_dir=tmp / "u1", checked_at=_NOW)
    check("URL outcome_review_path -> INVALID_ARGUMENTS",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INVALID_ARGUMENTS")
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_base_outcome(tmp), output_dir="https://x.test/out", checked_at=_NOW)
    check("URL output_dir -> INVALID_ARGUMENTS",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INVALID_ARGUMENTS")
    r = create_first_customer_conversion_handoff(
        outcome_review_path=tmp / "ghost.json", output_dir=tmp / "u2", checked_at=_NOW)
    check("missing outcome_review_path -> INPUT_NOT_FOUND",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INPUT_NOT_FOUND")
    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = create_first_customer_conversion_handoff(
        outcome_review_path=bad, output_dir=tmp / "u3", checked_at=_NOW)
    check("invalid JSON -> INVALID_OUTCOME_REVIEW",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INVALID_OUTCOME_REVIEW")

    def drop_prospect(data):
        data.pop("prospect_id", None)
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, drop_prospect, "missing"),
        output_dir=tmp / "u4", checked_at=_NOW)
    check("missing required field -> INVALID_OUTCOME_REVIEW",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INVALID_OUTCOME_REVIEW")
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_base_outcome(tmp), output_dir=tmp / "u5", checked_at="")
    check("empty checked_at -> INVALID_ARGUMENTS",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "INVALID_ARGUMENTS")


def test_readiness_gates(tmp: Path):
    print("\n[28-33] conversion readiness gates")

    def wait(data):
        data["action"]["action"] = "WAIT_FOR_RESPONSE"
        data["conversion_ready"] = False
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, wait, "wait"), output_dir=tmp / "g1", checked_at=_NOW)
    check("non-ready action -> CONVERSION_NOT_READY",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "CONVERSION_NOT_READY")

    def close(data):
        data["action"]["action"] = "CLOSE_NO_GO"
        data["conversion_ready"] = False
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, close, "close"), output_dir=tmp / "g2", checked_at=_NOW)
    check("CLOSE_NO_GO default -> not accepted (CONVERSION_NOT_READY)",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "CONVERSION_NOT_READY")

    def blocked(data):
        data["action"]["action"] = "BLOCKED"
        data["accepted"] = False
        data["conversion_ready"] = False
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, blocked, "blocked"), output_dir=tmp / "g3", checked_at=_NOW)
    check("BLOCKED default -> not accepted (CONVERSION_NOT_READY)",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "CONVERSION_NOT_READY")

    # require_conversion_ready=False -> package generated but accepted=False with blocker
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, close, "close2"), output_dir=tmp / "g4",
        checked_at=_NOW, require_conversion_ready=False)
    check("require_conversion_ready=False -> Result, accepted False",
          isinstance(r, FirstCustomerConversionHandoffResult) and r.accepted is False)
    check("not-ready package records a critical blocker",
          any(b.severity == "critical" for b in getattr(r, "blockers", ())))
    # human-review-off downgrades acceptance even for a ready action
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_base_outcome(tmp), output_dir=tmp / "g5",
        checked_at=_NOW, require_human_review=False)
    check("require_human_review=False -> accepted False",
          isinstance(r, FirstCustomerConversionHandoffResult) and r.accepted is False)


def test_manual_only_and_sensitive(tmp: Path):
    print("\n[34-35] manual-only + sensitive metadata rejection")

    def inject_auto(data):
        data.setdefault("metadata", {})["auto_send"] = True
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, inject_auto, "auto"), output_dir=tmp / "m1", checked_at=_NOW)
    check("manual-only violation -> MANUAL_ONLY_VIOLATION",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "MANUAL_ONLY_VIOLATION")

    def inject_pii(data):
        data.setdefault("prospect", {})["email"] = "owner@example.test"
    r = create_first_customer_conversion_handoff(
        outcome_review_path=_patched(tmp, inject_pii, "pii"), output_dir=tmp / "m2", checked_at=_NOW)
    check("sensitive field -> SENSITIVE_METADATA_REJECTED",
          isinstance(r, FirstCustomerConversionHandoffError) and r.error_kind == "SENSITIVE_METADATA_REJECTED")


def test_no_mutation(tmp: Path):
    print("\n[36] source Stage 4.16 artifact is never mutated")
    src = _base_outcome(tmp)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=tmp / "nm", checked_at=_NOW)
    after = hashlib.sha256(src.read_bytes()).hexdigest()
    check("outcome review bytes unchanged", before == after)


def test_determinism(tmp: Path):
    print("\n[37-39] determinism (no clock/random/uuid)")
    src = _base_outcome(tmp)
    out = tmp / "det"
    r1 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW)
    r2 = create_first_customer_conversion_handoff(
        outcome_review_path=src, output_dir=out, checked_at=_NOW, overwrite=True)
    check("result.to_dict deterministic",
          json.dumps(r1.to_dict(), sort_keys=True) == json.dumps(r2.to_dict(), sort_keys=True))
    e1 = create_first_customer_conversion_handoff(
        outcome_review_path=tmp / "ghost.json", output_dir=tmp / "de1", checked_at=_NOW)
    e2 = create_first_customer_conversion_handoff(
        outcome_review_path=tmp / "ghost.json", output_dir=tmp / "de2", checked_at=_NOW)
    check("error.to_dict deterministic",
          json.dumps(e1.to_dict(), sort_keys=True) == json.dumps(e2.to_dict(), sort_keys=True))
    check("error is INPUT_NOT_FOUND", e1.error_kind == "INPUT_NOT_FOUND")


def test_static_boundaries():
    print("\n[40-43] static boundary scans (executable source only)")
    source = (_COMMERCIAL / "first_customer_conversion_handoff.py").read_text(encoding="utf-8")
    source += (_COMMERCIAL / "conversion_handoff_models.py").read_text(encoding="utf-8")
    for token in ("requests", "httpx", "urllib.request", "boto3", "socket",
                  "http.client", "openai", "anthropic", "stripe", "paypal",
                  "selenium", "playwright", "smtp", "imaplib", "smtplib", "subprocess"):
        check(f"no network/service token '{token}'", token not in source)
    for token in ("KnowledgeService", "KnowledgeIndex", "KnowledgeQueryEngine",
                  "query_engine", "explain_engine", "insight_engine"):
        check(f"no lower knowledge token '{token}'", token not in source)
    for token in ("send_email", "send_message", "auto_dm", "scrape", "scraper",
                  "sales" + "force", "hub" + "spot", "send" + "grid",
                  _CRM_LIT, _INVOICE_LIT, "check" + "out"):
        check(f"no auto-message/service token '{token}'", token not in source)
    for token in (_PAY_LIT, _BILL_LIT, "uuid.uuid4", "random.", "datetime.now",
                  "date.today", "time.time"):
        check(f"no billing/non-determinism token '{token}'", token not in source)


def test_existing_suites():
    print("\n[44+] existing lower-stage + knowledge suites still pass")
    suites = [
        _HERE / "test_first_prospect_outcome_review.py",
        _HERE / "test_first_prospect_mini_audit_delivery_log.py",
        _HERE / "test_first_prospect_mini_audit_handoff.py",
        _HERE / "test_first_prospect_follow_up_decision.py",
        _HERE / "test_first_prospect_execution_log.py",
        _HERE / "test_first_outreach_launch_kit.py",
        _ROOT / "scos" / "knowledge" / "tests" / "test_knowledge_service.py",
    ]
    for suite in suites:
        proc = subprocess.run([sys.executable, str(suite)], capture_output=True, text=True)
        check(f"suite passes: {suite.name}", proc.returncode == 0)


def test_package_import_safe():
    print("\n[import] __init__ lazy export is package-import safe")
    code = (
        "import sys\n"
        "import scos.commercial as c\n"
        "assert callable(c.create_first_customer_conversion_handoff)\n"
        "assert c.FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION == 1\n"
        "assert not any(m.startswith('scos.knowledge') for m in sys.modules), 'knowledge imported eagerly'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(_ROOT))
    check("import scos.commercial exposes Stage 4.17 lazily w/o knowledge",
          proc.returncode == 0)


# Literal boundary tokens for the static scan, assembled from fragments so this
# test file itself stays free of the raw tokens even under a whole-tree scan.
_PAY_LIT = "pay" + "ment"
_INVOICE_LIT = "in" + "voice"
_BILL_LIT = "bil" + "ling"
_CRM_LIT = "CR" + "M"


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_happy_path(tmp)
        test_manifest_and_evidence(tmp)
        test_handoff_id(tmp)
        test_overwrite(tmp)
        test_input_errors(tmp)
        test_readiness_gates(tmp)
        test_manual_only_and_sensitive(tmp)
        test_no_mutation(tmp)
        test_determinism(tmp)
    test_static_boundaries()
    test_package_import_safe()
    test_existing_suites()
    print(f"\nRESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
