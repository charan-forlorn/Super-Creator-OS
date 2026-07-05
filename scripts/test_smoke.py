"""SCOS smoke tier — fast import / API sanity for the local operator.

Stage 4.18 test-suite strategy tier 1 (see docs/testing/TEST_SUITE_STRATEGY.md).
Verifies that the commercial package imports lazily (no knowledge import), that
the Stage 4.18 shared helpers answer correctly on trivial inputs, and nothing
else. No artifact generation outside a TemporaryDirectory, no network, no
subprocess, no repo mutation.

Run: .venv\\Scripts\\python.exe scripts\\test_smoke.py
Exit: 0 on pass, 1 on fail. Output is deterministic.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

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


def main() -> int:
    print("SMOKE TIER - scos.commercial import + shared helper sanity")

    import scos.commercial as commercial

    check("package imports", commercial is not None)
    check("lazy import: knowledge layer untouched",
          not any(m.startswith("scos.knowledge") for m in sys.modules))

    check("report schema version exported", commercial.COMMERCIAL_REPORT_SCHEMA_VERSION == 1)
    check("domain schema version exported", commercial.COMMERCIAL_DOMAIN_SCHEMA_VERSION == 1)
    check("validation schema version exported", commercial.COMMERCIAL_VALIDATION_SCHEMA_VERSION == 1)
    check("manifest tools schema version exported",
          commercial.COMMERCIAL_MANIFEST_TOOLS_SCHEMA_VERSION == 1)
    # Only knowledge-free entry points here: resolving build_commercial_report
    # would import the Stage 3.9 knowledge layer, which smoke must not touch.
    check("existing Stage 4 entry points still exported",
          "build_commercial_report" in commercial.__all__
          and callable(commercial.create_delivery_package)
          and callable(commercial.create_first_customer_conversion_handoff))

    item = commercial.CommercialCheck.of("smoke", "success", metadata={"tier": "smoke"})
    check("domain model round-trip",
          item.to_dict()["metadata"] == {"tier": "smoke"} and item.status == "success")

    check("stable_json_dumps deterministic",
          commercial.stable_json_dumps({"b": 1, "a": 2})
          == commercial.stable_json_dumps({"a": 2, "b": 1}))
    check("sha256_text known vector",
          commercial.sha256_text("abc")
          == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    check("validate_required_keys",
          commercial.validate_required_keys({"a": 1}, ("a", "b")) == ("b",))
    check("validate_no_url_path rejects URL",
          commercial.validate_no_url_path("https://example.com") is False)
    check("validate_manual_only_flags clean payload",
          commercial.validate_manual_only_flags({"manual_review": True}) == ())

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        written = commercial.write_stable_json(tmp / "smoke.json", {"ok": True})
        payload, error = commercial.load_json_object(written)
        check("tempdir write + load_json_object round-trip",
              payload == {"ok": True} and error is None)
        check("sha256_file works", len(commercial.sha256_file(written)) == 64)

    check("lazy import: knowledge layer still untouched after use",
          not any(m.startswith("scos.knowledge") for m in sys.modules))

    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    print("SMOKE: " + ("PASS" if _FAIL == 0 else "FAIL"))
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
