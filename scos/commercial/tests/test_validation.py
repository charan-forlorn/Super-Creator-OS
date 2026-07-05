"""test_validation.py - SCOS Stage 4.18 unified validation helper suite.

Plain executable script (no pytest). Covers required-key ordering, URL
rejection, local path checks, sensitive-metadata scanning (including
business-alias non-rejection), manual-only flag detection, path containment,
and safe JSON loading. Boundary flag literals are assembled from fragments so
this file's own text stays free of forbidden tokens.

Run: python scos/commercial/tests/test_validation.py
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COMMERCIAL = _HERE.parent

sys.path.insert(0, str(_COMMERCIAL))

from validation import (  # noqa: E402
    COMMERCIAL_VALIDATION_SCHEMA_VERSION,
    DEFAULT_SENSITIVE_METADATA_KEYS,
    MANUAL_ONLY_FORBIDDEN_FLAGS,
    load_json_object,
    validate_existing_dir,
    validate_existing_file,
    validate_local_path_string,
    validate_manual_only_flags,
    validate_no_sensitive_metadata,
    validate_no_url_path,
    validate_path_containment,
    validate_required_keys,
)
from report_models import FrozenMap  # noqa: E402

_PASS = 0
_FAIL = 0

# Boundary flag names assembled from fragments (repo static-scan convention).
_F_PAY_CAPTURE = "pay" + "ment_capture"
_F_REL_SYNC = "cr" + "m_sync"
_F_BIL_SYNC = "bil" + "ling_sync"
_F_AUTO_DM = "auto_" + "dm"


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def test_schema_version() -> None:
    print("\n[1] schema version + constants")
    check("schema version is 1", COMMERCIAL_VALIDATION_SCHEMA_VERSION == 1)
    check("default sensitive keys count", len(DEFAULT_SENSITIVE_METADATA_KEYS) == 9)
    check("manual-only flag count", len(MANUAL_ONLY_FORBIDDEN_FLAGS) == 10)


def test_required_keys() -> None:
    print("\n[2] validate_required_keys")
    payload = {"b": 1, "d": 2}
    missing = validate_required_keys(payload, ("a", "b", "c", "d"))
    check("returns tuple", isinstance(missing, tuple))
    check("missing keys in required order", missing == ("a", "c"))
    check("empty when all present", validate_required_keys({"a": 1}, ("a",)) == ())
    check("all missing preserves order", validate_required_keys({}, ("z", "a")) == ("z", "a"))


def test_url_and_path_strings() -> None:
    print("\n[3] URL / local path strings")
    check("http rejected", validate_no_url_path("http://example.com/x") is False)
    check("https rejected", validate_no_url_path("https://example.com/x") is False)
    check("local path accepted", validate_no_url_path("output/report.json") is True)
    check("windows path accepted", validate_no_url_path("C:\\work\\report.json") is True)
    check("local string accepted", validate_local_path_string("output/report.json") is True)
    check("windows drive accepted", validate_local_path_string("C:\\work\\x.json") is True)
    check("relative dot path accepted", validate_local_path_string("./x.json") is True)
    check("empty rejected", validate_local_path_string("") is False)
    check("whitespace rejected", validate_local_path_string("   ") is False)
    check("http rejected", validate_local_path_string("http://example.com/a.json") is False)
    check("https rejected", validate_local_path_string("HTTPS://example.com/a.json") is False)
    check("other scheme rejected", validate_local_path_string("ftp://host/a.json") is False)
    check("non-str rejected", validate_local_path_string(123) is False)
    check("does not require existence", validate_local_path_string("no/such/file.json") is True)


def test_existing_file_dir(tmp: Path) -> None:
    print("\n[4] validate_existing_file / validate_existing_dir")
    file_path = tmp / "a.json"
    file_path.write_text("{}", encoding="utf-8")
    check("existing file -> True", validate_existing_file(file_path) is True)
    check("existing file str -> True", validate_existing_file(str(file_path)) is True)
    check("dir is not file", validate_existing_file(tmp) is False)
    check("missing file -> False", validate_existing_file(tmp / "missing.json") is False)
    check("url string -> False", validate_existing_file("https://example.com/a") is False)
    check("existing dir -> True", validate_existing_dir(tmp) is True)
    check("file is not dir", validate_existing_dir(file_path) is False)
    check("missing dir -> False", validate_existing_dir(tmp / "nope") is False)


def test_sensitive_metadata() -> None:
    print("\n[5] validate_no_sensitive_metadata")
    clean = {"display_name": "SCOS", "business_address_note": "see contract", "summary": "ok"}
    check("business/display aliases not rejected", validate_no_sensitive_metadata(clean) == ())
    flagged = validate_no_sensitive_metadata({"contact": {"email": "x"}, "phone": "y"})
    check("nested + top-level keys found", flagged == ("contact.email", "phone"))
    listed = validate_no_sensitive_metadata({"entries": [{"tax_id": "z"}]})
    check("list traversal path", listed == ("entries.0.tax_id",))
    frozen = FrozenMap.from_mapping({"card_number": "0000"})
    check("FrozenMap scanned", validate_no_sensitive_metadata(frozen) == ("card_number",))
    check("custom forbidden keys honored",
          validate_no_sensitive_metadata({"secret_token": 1}, ("secret_token",)) == ("secret_token",))
    check("default keys not applied with custom set",
          validate_no_sensitive_metadata({"email": "x"}, ("secret_token",)) == ())
    check("case-normalized key match (Email)",
          validate_no_sensitive_metadata({"Email": "x"}) == ("Email",))
    original = {"contact": {"email": "x"}, "items": [1, 2]}
    snapshot = copy.deepcopy(original)
    validate_no_sensitive_metadata(original)
    check("input not mutated", original == snapshot)
    check("deterministic across calls",
          validate_no_sensitive_metadata({"phone": 1, "address": 2})
          == validate_no_sensitive_metadata({"address": 2, "phone": 1}))


def test_manual_only_flags() -> None:
    print("\n[6] validate_manual_only_flags")
    check("clean payload passes", validate_manual_only_flags({"manual_review": True}) == ())
    check("auto_send True flagged", validate_manual_only_flags({"auto_send": True}) == ("auto_send",))
    check("string 'true' flagged",
          validate_manual_only_flags({_F_REL_SYNC: "true"}) == (_F_REL_SYNC,))
    check("string 'enabled' flagged",
          validate_manual_only_flags({_F_PAY_CAPTURE: "enabled"}) == (_F_PAY_CAPTURE,))
    check("int 1 flagged", validate_manual_only_flags({"network_enabled": 1}) == ("network_enabled",))
    check("disabled flag passes", validate_manual_only_flags({"auto_send": False}) == ())
    check("string 'false' passes", validate_manual_only_flags({_F_BIL_SYNC: "false"}) == ())
    nested = {"config": {_F_AUTO_DM: "yes"}}
    check("nested flag path", validate_manual_only_flags(nested) == (f"config.{_F_AUTO_DM}",))
    check("saas flag flagged", validate_manual_only_flags({"saas_enabled": "on"}) == ("saas_enabled",))
    every = {flag: True for flag in MANUAL_ONLY_FORBIDDEN_FLAGS}
    check("all ten flags detected", len(validate_manual_only_flags(every)) == 10)


def test_path_containment(tmp: Path) -> None:
    print("\n[7] validate_path_containment")
    parent = tmp / "package"
    parent.mkdir()
    inside = parent / "sub" / "file.json"
    check("child under parent -> True", validate_path_containment(inside, parent) is True)
    check("equal paths -> True", validate_path_containment(parent, parent) is True)
    check("sibling rejected", validate_path_containment(tmp / "other", parent) is False)
    escape = parent / ".." / "escape.json"
    check("traversal escape rejected", validate_path_containment(escape, parent) is False)
    deep_escape = parent / "sub" / ".." / ".." / "escape.json"
    check("deep traversal escape rejected", validate_path_containment(deep_escape, parent) is False)
    check("traversal that stays inside accepted",
          validate_path_containment(parent / "sub" / ".." / "ok.json", parent) is True)


def test_load_json_object(tmp: Path) -> None:
    print("\n[8] load_json_object")
    good = tmp / "good.json"
    good.write_text('{"a": 1}\n', encoding="utf-8")
    payload, error = load_json_object(good)
    check("valid object loads", payload == {"a": 1} and error is None)

    payload, error = load_json_object(tmp / "missing.json")
    check("missing file -> FILE_NOT_FOUND",
          payload is None and isinstance(error, str) and error.startswith("FILE_NOT_FOUND"))

    bad = tmp / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    payload, error = load_json_object(bad)
    check("invalid JSON -> INVALID_JSON",
          payload is None and isinstance(error, str) and error.startswith("INVALID_JSON"))

    array = tmp / "array.json"
    array.write_text("[1, 2]", encoding="utf-8")
    payload, error = load_json_object(array)
    check("non-object -> NOT_A_JSON_OBJECT",
          payload is None and isinstance(error, str) and error.startswith("NOT_A_JSON_OBJECT"))

    check("directory path -> error, no raise", load_json_object(tmp)[0] is None)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_schema_version()
        test_required_keys()
        test_url_and_path_strings()
        test_existing_file_dir(tmp)
        test_sensitive_metadata()
        test_manual_only_flags()
        test_path_containment(tmp)
        test_load_json_object(tmp)
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
