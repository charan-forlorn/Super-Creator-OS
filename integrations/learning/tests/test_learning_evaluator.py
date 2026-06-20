"""test_learning_evaluator.py — proves the learning loop CLOSES.

Isolated temp stores only. Constructs ONE complete causal chain (a provenance record
with predicted retention + a matching observed telemetry row) and asserts the evaluator
turns the gap into knowledge that changes the future benchmark. This is a UNIT test of
the loop mechanics on controlled inputs — it does NOT fabricate production data.

Run: python integrations/learning/tests/test_learning_evaluator.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
import learning_evaluator as LE  # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


def _record(loop_run_id, niche, predicted):
    return {"project_name": "P", "product_niche": niche, "hook_successful": "h",
            "editing_specs": "e", "retention_score": predicted, "lesson_learned": "l",
            "created_at": "2026-06-20T00:00:00.000Z",
            "provenance": {"loop_run_id": loop_run_id,
                           "decided": {"hooks_actually_used": ["Double Kill"]}}}


def _telem(loop_run_id, pct, collected="2026-06-23T00:00:00Z"):
    return {"loop_run_id": loop_run_id, "project_name": "P", "platform": "tiktok",
            "collected_at": collected, "source": "manual", "avg_watch_pct": pct}


def test_no_observed_no_learning():
    print("\n[1] honesty — no observed data => no learning (cannot fake)")
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "db.json"; tel = Path(d) / "tel.json"
        db.write_text(json.dumps([_record("k::p", "Gaming (MOBA)", 84)]), encoding="utf-8")
        tel.write_text("[]", encoding="utf-8")
        rep = LE.evaluate(db, tel)
        check("has_learning is False with empty telemetry", rep["has_learning"] is False)
        check("calibrated_benchmark returns default (no knowledge yet)",
              LE.calibrated_benchmark("Gaming (MOBA)", default=84, db_path=db, telemetry_path=tel) == 84)


def test_loop_closes():
    print("\n[2] LOOP CLOSES — observed turns into a knowledge correction")
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "db.json"; tel = Path(d) / "tel.json"
        db.write_text(json.dumps([_record("k::p", "Gaming (MOBA)", 84)]), encoding="utf-8")
        tel.write_text(json.dumps([_telem("k::p", 46)]), encoding="utf-8")
        rep = LE.evaluate(db, tel)
        check("a learning event is produced", rep["has_learning"] and len(rep["learning_events"]) == 1)
        ev = rep["learning_events"][0]
        check("prediction error computed (84 - 46 = 38)", ev["prediction_error"] == 38.0)
        cal = rep["calibration"]["Gaming (MOBA)"]
        check("niche bias = +38 (system over-predicts)", cal["bias"] == 38.0)
        check("observed_benchmark = 46 (the real number)", cal["observed_benchmark"] == 46.0)
        # THE PROOF: the future benchmark is now the OBSERVED value, not the predicted guess
        nb = LE.calibrated_benchmark("Gaming (MOBA)", default=84, db_path=db, telemetry_path=tel)
        check("future benchmark CHANGED 84 -> 46 from observation (loop closed)", nb == 46.0)


def test_latest_snapshot_wins():
    print("\n[3] multiple snapshots — latest observed wins")
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "db.json"; tel = Path(d) / "tel.json"
        db.write_text(json.dumps([_record("k::p", "Gaming (MOBA)", 84)]), encoding="utf-8")
        tel.write_text(json.dumps([_telem("k::p", 40, "2026-06-21T00:00:00Z"),
                                   _telem("k::p", 52, "2026-06-27T00:00:00Z")]), encoding="utf-8")
        ev = LE.evaluate(db, tel)["learning_events"][0]
        check("uses latest snapshot (52, not 40)", ev["observed_avg_watch_pct"] == 52.0)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" LEARNING EVALUATOR — LOOP-CLOSURE TEST"); print("=" * 60)
    test_no_observed_no_learning(); test_loop_closes(); test_latest_snapshot_wins()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
