"""test_telemetry_capture.py — WF-3 capture-layer tests.

100% ISOLATED: every write goes to a tempfile store via explicit paths. NEVER touches
production memory/telemetry.json or database.json. No fabricated production data.

Run: python integrations/learning/tests/test_telemetry_capture.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
import telemetry_capture as TC  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _row(**kw):
    base = {"loop_run_id": "k::p1", "project_name": "p1", "platform": "tiktok",
            "collected_at": "2026-06-20T08:00:00Z", "source": "manual",
            "views": 18400, "reach": 25100, "avg_watch_pct": 46, "likes": 1230,
            "saves": 410, "followers_gained": 37}
    base.update(kw)
    return base


def test_happy_path():
    print("\n[1] capture a valid observed row (new fields reach/followers_gained)")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "telemetry.json"
        res = TC.capture(_row(), telemetry_path=store)
        check("capture ok", res["ok"] is True)
        rows = json.loads(store.read_text())
        check("1 row persisted", len(rows) == 1)
        check("reach stored", rows[0].get("reach") == 25100)
        check("followers_gained stored", rows[0].get("followers_gained") == 37)
        check("rewatch_rate normalized to *_pct",
              "rewatch_rate" not in rows[0])


def test_integrity_predicted_rejected():
    print("\n[2] INTEGRITY — predicted metrics are REJECTED (the WF-3 mandate)")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        res = TC.capture(_row(retention_score=85), telemetry_path=store)
        check("retention_score injection rejected", res["ok"] is False
              and any("predicted" in e for e in res.get("errors", [])))
        check("nothing written on rejection", not store.exists()
              or json.loads(store.read_text()) == [])
        res2 = TC.capture(_row(score=90), telemetry_path=store)
        check("generic 'score' rejected too", res2["ok"] is False)


def test_source_enforced():
    print("\n[3] observed provenance — source is mandatory and constrained")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        bad = _row(); del bad["source"]
        check("missing source rejected", TC.capture(bad, telemetry_path=store)["ok"] is False)
        check("invalid source rejected",
              TC.capture(_row(source="guess"), telemetry_path=store)["ok"] is False)


def test_new_fields_validated():
    print("\n[4] reach / followers_gained validated (non-negative)")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        check("negative reach rejected",
              TC.capture(_row(reach=-5), telemetry_path=store)["ok"] is False)
        check("negative followers_gained rejected",
              TC.capture(_row(followers_gained=-1), telemetry_path=store)["ok"] is False)


def test_dedup_reused():
    print("\n[5] dedup is inherited from the safe storage path")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        TC.capture(_row(), telemetry_path=store)
        res2 = TC.capture(_row(), telemetry_path=store)
        check("duplicate (run+platform+collected_at) rejected", res2["ok"] is False)
        check("still 1 row", len(json.loads(store.read_text())) == 1)


def test_derive_observed_from_observed():
    print("\n[6] derive fills avg_watch_pct from observed watch_time/duration ONLY")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        r = _row(avg_watch_pct=None, avg_watch_time=15)
        res = TC.capture(r, output_duration_s=30, telemetry_path=store)
        check("capture ok", res["ok"])
        check("avg_watch_pct derived to 50.0 (15/30)",
              json.loads(store.read_text())[0]["avg_watch_pct"] == 50.0)


def test_orphan_vs_joined():
    print("\n[7] causal-chain linking — orphan (v1 record) vs joined (provenance record)")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "t.json"
        # v1 record (no provenance) -> telemetry cannot join -> orphan
        db_v1 = Path(d) / "db_v1.json"
        db_v1.write_text(json.dumps([{"project_name": "p1", "product_niche": "n",
            "hook_successful": "h", "editing_specs": "e", "retention_score": 80,
            "lesson_learned": "l", "created_at": "x"}]), encoding="utf-8")
        res = TC.capture(_row(loop_run_id="k::orphan"), telemetry_path=store, db_path=db_v1)
        check("v1 record -> orphan=True", res["ok"] and res["orphan"] is True)
        # record WITH provenance.loop_run_id -> joins
        store2 = Path(d) / "t2.json"
        db_p = Path(d) / "db_p.json"
        db_p.write_text(json.dumps([{"project_name": "p1", "product_niche": "n",
            "hook_successful": "h", "editing_specs": "e", "retention_score": 80,
            "lesson_learned": "l", "created_at": "x",
            "provenance": {"loop_run_id": "k::joined"}}]), encoding="utf-8")
        res2 = TC.capture(_row(loop_run_id="k::joined"), telemetry_path=store2, db_path=db_p)
        check("provenance record -> joined_to_record=True",
              res2["ok"] and res2["joined_to_record"] is True)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" WF-3 OBSERVED TELEMETRY CAPTURE — TEST SUITE"); print("=" * 60)
    test_happy_path(); test_integrity_predicted_rejected(); test_source_enforced()
    test_new_fields_validated(); test_dedup_reused(); test_derive_observed_from_observed()
    test_orphan_vs_joined()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
