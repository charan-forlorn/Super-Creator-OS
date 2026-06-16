"""test_dq_report.py — validation suite for DQ Report fixes F1-F5.

No pytest dependency: run directly ->
    python integrations/learning/tests/test_dq_report.py
Exits 0 if all pass, 1 otherwise. Uses tempfile only; never touches production data.
Covers Positive / Negative (old bug closed) / Regression (existing behavior intact).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))          # integrations/learning

import dq_report as dq                          # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _record(niche="Gaming (MOBA)", run="r1", watch=None, with_prov=True, adoption="adopted"):
    rec = {"project_name": run, "product_niche": niche, "hook_successful": "h",
           "editing_specs": "e", "retention_score": 80, "lesson_learned": "l",
           "created_at": "2026-06-16T00:00:00.000Z", "render_success": True}
    if with_prov:
        rec["schema_version"] = "v3"
        rec["provenance"] = {
            "schema": "provenance/v3", "loop_run_id": f"2026-06-16T00:00:00.000Z::{run}",
            "recommended": {"recommendation_id": f"rec_{run}", "match_quality": "exact",
                            "suggested_hooks": ["Double Kill"]},
            "decided": {"hooks_actually_used": ["Double Kill"], "hook_adoption": adoption},
            "linkage": {"recommendation_available": True, "is_cold_start": False}}
    return rec


# ---------------------------------------------------------------------------
def test_F1_protected_paths():
    print("\n[F1] read-only contract — --json-out must reject every input path")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db = d / "mydb.json"; db.write_text("[]", encoding="utf-8")
        tel = d / "tel.json"; tel.write_text("[]", encoding="utf-8")
        ev = d / "ev.jsonl"; ev.write_text("", encoding="utf-8")
        lib = d / "lib.json"; lib.write_text("{}", encoding="utf-8")
        safe = d / "report.json"

        # NEGATIVE: each input path is protected
        check("rejects --json-out == --db",
              dq._is_protected_path(db, db=str(db), telemetry=str(tel), events=str(ev), lib_path=str(lib)))
        check("rejects --json-out == --lib-path",
              dq._is_protected_path(lib, db=str(db), telemetry=str(tel), events=str(ev), lib_path=str(lib)))
        check("rejects --json-out == --telemetry",
              dq._is_protected_path(tel, db=str(db), telemetry=str(tel), events=str(ev), lib_path=str(lib)))
        check("rejects --json-out == --events",
              dq._is_protected_path(ev, db=str(db), telemetry=str(tel), events=str(ev), lib_path=str(lib)))
        # POSITIVE: a non-input path is allowed
        check("allows --json-out to a fresh path",
              not dq._is_protected_path(safe, db=str(db), telemetry=str(tel), events=str(ev), lib_path=str(lib)))

        # END-TO-END: main() must REFUSE and NOT overwrite the db
        db.write_text('[{"x":1}]', encoding="utf-8")
        before = db.read_bytes()
        argv = ["dq", "--db", str(db), "--telemetry", str(tel), "--events", str(ev),
                "--lib-path", str(lib), "--json-out", str(db), "--quiet"]
        old = sys.argv
        try:
            sys.argv = argv
            rc = dq.main()
        finally:
            sys.argv = old
        check("main() returns 2 (refused)", rc == 2)
        check("db file NOT overwritten (bytes identical)", db.read_bytes() == before)


def test_F2_variance():
    print("\n[F2] flat data must not satisfy niche_at_M2")
    # 30 records, all observed watch == 50 (zero variance)
    recs = [_record(run=f"r{i}") for i in range(30)]
    chain = [{"product_niche": "Gaming (MOBA)", "loop_run_id": f"r{i}", "has_observed": True,
              "predicted_retention_score": 80, "observed": [{"avg_watch_pct": 50,
              "collected_at": "2026-06-19T00:00:00Z"}]} for i in range(30)]
    nd = dq.niche_distribution(recs, chain)
    hf = nd["hit_flop_per_niche"]["Gaming (MOBA)"]
    check("flat niche: hits == 0", hf["hits"] == 0)
    check("flat niche: flops == 0", hf["flops"] == 0)
    check("flat niche: eligible == False", hf["eligible"] is False)
    check("flat niche: reason == insufficient_variance", hf.get("reason") == "insufficient_variance")
    rdy = dq.readiness(
        {"coverage_pct_raw": 100, "orphan_rendered": []},
        {"with_provenance_pct_raw": 100}, {"recorded_pct_raw": 100},
        {"fill_rate_pct_raw": 100}, nd, 100)
    check("flat niche: niche_at_M2 gate FALSE", rdy["gates"]["niche_at_M2"] is False)

    # POSITIVE: varied data with clear spread IS eligible
    vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    chain2 = [{"product_niche": "N", "loop_run_id": f"v{i}", "has_observed": True,
               "predicted_retention_score": 80, "observed": [{"avg_watch_pct": v,
               "collected_at": "2026-06-19T00:00:00Z"}]} for i, v in enumerate(vals)]
    hf2 = dq.niche_distribution([{"product_niche": "N"}] * 10, chain2)["hit_flop_per_niche"]["N"]
    check("varied niche: eligible == True", hf2["eligible"] is True)
    check("varied niche: hits > 0 and flops > 0", hf2["hits"] > 0 and hf2["flops"] > 0)


def test_F3_rounding():
    print("\n[F3] gate uses RAW value, not rounded")
    check("_ratio(1999,2000) == 99.95 (raw)", abs(dq._ratio(1999, 2000) - 99.95) < 1e-9)
    check("_pct(1999,2000) == 100.0 (display rounds)", dq._pct(1999, 2000) == 100.0)
    cov = {"coverage_pct_raw": dq._ratio(1999, 2000), "orphan_rendered": ["x"]}
    rdy = dq.readiness(cov, {"with_provenance_pct_raw": 100}, {"recorded_pct_raw": 100},
                       {"fill_rate_pct_raw": 100}, {"canonical_violations": [],
                       "hit_flop_per_niche": {}, "records_per_niche": {}}, 100)
    check("99.95% coverage -> coverage_100 FALSE", rdy["gates"]["coverage_100"] is False)
    cov2 = {"coverage_pct_raw": dq._ratio(2000, 2000), "orphan_rendered": []}
    rdy2 = dq.readiness(cov2, {"with_provenance_pct_raw": 100}, {"recorded_pct_raw": 100},
                        {"fill_rate_pct_raw": 100}, {"canonical_violations": [],
                        "hit_flop_per_niche": {}, "records_per_niche": {}}, 100)
    check("100.0% coverage -> coverage_100 TRUE", rdy2["gates"]["coverage_100"] is True)


def test_F4_latest_snapshot():
    print("\n[F4] latest snapshot chosen by collected_at, not file order")
    # rows OUT OF ORDER in the list: newest (72h=46) appears BEFORE older (24h=80)
    rows = [
        {"avg_watch_pct": 46, "collected_at": "2026-06-21T00:00:00Z"},  # latest, listed first
        {"avg_watch_pct": 80, "collected_at": "2026-06-19T00:00:00Z"},  # older, listed last
    ]
    check("picks 46 (newest by ts) not 80 (last in list)", dq._observed_watch(rows) == 46)
    check("empty rows -> None", dq._observed_watch([]) is None)
    check("ignores rows missing avg_watch_pct",
          dq._observed_watch([{"collected_at": "2026-06-22T00:00:00Z"},
                              {"avg_watch_pct": 30, "collected_at": "2026-06-20T00:00:00Z"}]) == 30)


def test_F5_event_robustness():
    print("\n[F5] malformed event lines are skipped, no crash")
    events = [
        {"event_type": "PROJECT_RENDERED", "project_id": "p1"},
        {"event_type": "PROJECT_COMPLETE", "project_id": "p1"},
        {"event_type": "PROJECT_RENDERED"},          # missing project_id
        {"project_id": "p2"},                        # missing event_type
        {},                                          # empty
        "not-a-dict",                                # wrong type
    ]
    try:
        cov = dq.coverage_metrics([], events)
        crashed = False
    except Exception as e:                            # noqa: BLE001
        crashed, cov = True, {"error": str(e)}
    check("coverage_metrics does not crash on malformed events", not crashed)
    check("counts only well-formed rendered (1)", cov.get("events_rendered") == 1)
    check("counts only well-formed complete (1)", cov.get("events_complete") == 1)


def _m2_dataset(d: Path):
    """Write a temp db+telemetry where EVERY non-coverage gate passes (30-record
    niche with real variance + full observed). Returns (db, tel, run_ids)."""
    db = d / "db.json"
    tel = d / "tel.json"
    recs, tels, run_ids = [], [], []
    for i in range(30):
        run = f"p{i}"
        run_ids.append(run)
        recs.append(_record(run=run))
        watch = 10 + (i % 10) * 9          # spread 10..91 -> real variance
        tels.append({"loop_run_id": f"2026-06-16T00:00:00.000Z::{run}",
                     "project_name": run, "platform": "tiktok",
                     "collected_at": "2026-06-19T00:00:00Z",
                     "avg_watch_pct": watch, "views": 1000})
    db.write_text(json.dumps(recs), encoding="utf-8")
    tel.write_text(json.dumps(tels), encoding="utf-8")
    return db, tel, run_ids


def test_F6_tristate():
    print("\n[F6] tri-state coverage gate (PASS / FAIL / UNKNOWN)")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db, tel, run_ids = _m2_dataset(d)

        # --- UNKNOWN: no events.jsonl, but every other gate passes ---
        rep = dq.build_report(db=str(db), telemetry=str(tel), events=str(d / "nope.jsonl"))
        cov, rdy = rep["coverage"], rep["readiness"]
        check("no events -> coverage_state UNKNOWN", cov["coverage_state"] == "UNKNOWN")
        check("no events -> reason coverage_evidence_missing",
              cov["coverage_reason"] == "coverage_evidence_missing")
        check("UNKNOWN -> coverage_100 gate is False (not counted as pass)",
              rdy["gates"]["coverage_100"] is False)
        check("UNKNOWN + others pass -> status 'blocked'", rdy["status"] == "blocked")
        check("UNKNOWN -> ready is False", rdy["ready"] is False)

        # --- UNKNOWN variant: events exist but none are PROJECT_RENDERED ---
        ev2 = d / "ev2.jsonl"
        ev2.write_text(json.dumps({"event_type": "BRIEF_RECEIVED", "project_id": "p0"}) + "\n",
                       encoding="utf-8")
        rep2 = dq.build_report(db=str(db), telemetry=str(tel), events=str(ev2))
        check("events present but no RENDERED -> coverage_unavailable",
              rep2["coverage"]["coverage_reason"] == "coverage_unavailable"
              and rep2["coverage"]["coverage_state"] == "UNKNOWN")

        # --- PASS: full coverage events for all 30 -> READY, status ready ---
        evp = d / "evp.jsonl"
        lines = []
        for run in run_ids:
            lines.append(json.dumps({"event_type": "PROJECT_RENDERED", "project_id": run}))
            lines.append(json.dumps({"event_type": "PROJECT_COMPLETE", "project_id": run}))
        evp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rep3 = dq.build_report(db=str(db), telemetry=str(tel), events=str(evp))
        check("full coverage -> coverage_state PASS", rep3["coverage"]["coverage_state"] == "PASS")
        check("PASS + all gates -> status ready", rep3["readiness"]["status"] == "ready")
        check("PASS -> ready True", rep3["readiness"]["ready"] is True)

        # --- FAIL: one rendered project has no terminal event (orphan) ---
        evf = d / "evf.jsonl"
        lines_f = []
        for j, run in enumerate(run_ids):
            lines_f.append(json.dumps({"event_type": "PROJECT_RENDERED", "project_id": run}))
            if j > 0:                                   # p0 left as orphan
                lines_f.append(json.dumps({"event_type": "PROJECT_COMPLETE", "project_id": run}))
        evf.write_text("\n".join(lines_f) + "\n", encoding="utf-8")
        rep4 = dq.build_report(db=str(db), telemetry=str(tel), events=str(evf))
        check("orphan present -> coverage_state FAIL", rep4["coverage"]["coverage_state"] == "FAIL")
        check("FAIL -> status fail", rep4["readiness"]["status"] == "fail")

        # --- EXIT CODES via main(): UNKNOWN=3, PASS=0, FAIL=1 ---
        def run_main(events_path):
            argv = ["dq", "--db", str(db), "--telemetry", str(tel),
                    "--events", str(events_path), "--quiet"]
            old = sys.argv
            try:
                sys.argv = argv
                return dq.main()
            finally:
                sys.argv = old
        check("exit code 3 when UNKNOWN", run_main(d / "nope.jsonl") == 3)
        check("exit code 0 when READY", run_main(evp) == 0)
        check("exit code 1 when FAIL", run_main(evf) == 1)


def test_regression_readonly_and_metrics():
    print("\n[REGRESSION] existing metrics intact + read-only on real run")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db = d / "db.json"
        tel = d / "tel.json"
        recs = [_record(run="ra"), _record(run="rb", adoption="rejected")]
        db.write_text(json.dumps(recs), encoding="utf-8")
        tel.write_text(json.dumps([{"loop_run_id": "2026-06-16T00:00:00.000Z::ra",
                                    "project_name": "ra", "platform": "tiktok",
                                    "collected_at": "2026-06-19T00:00:00Z",
                                    "avg_watch_pct": 46, "views": 1000}]), encoding="utf-8")
        before_db = db.read_bytes()
        before_tel = tel.read_bytes()

        rep = dq.build_report(db=str(db), telemetry=str(tel), events=str(d / "none.jsonl"))

        # read-only: inputs unchanged
        check("db unchanged after build_report", db.read_bytes() == before_db)
        check("telemetry unchanged after build_report", tel.read_bytes() == before_tel)
        # metric shape intact
        check("provenance 2/2 = 100%", rep["provenance_quality"]["with_provenance_pct"] == 100.0)
        check("hook adoption has adopted+rejected",
              rep["hook_adoption"]["adoption_distribution"].get("adopted") == 1
              and rep["hook_adoption"]["adoption_distribution"].get("rejected") == 1)
        check("ground truth fill = 50% (1 of 2 has observed)",
              rep["ground_truth_fill"]["fill_rate_pct"] == 50.0)
        check("calibration MAE present (predicted 80 vs observed 46)",
              rep["prediction_calibration"]["mae"] == 34.0)
        check("telemetry health: 1 row, no dup, no orphan",
              rep["telemetry_health"]["total_rows"] == 1
              and rep["telemetry_health"]["duplicate_keys"] == []
              and rep["telemetry_health"]["orphan_loop_run_ids"] == [])
        check("readiness NOT ready (small data) with blockers",
              rep["readiness"]["ready"] is False and len(rep["readiness"]["blockers"]) > 0)
        check("render_text does not crash", isinstance(dq.render_text(rep), str))


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 60)
    print(" DQ REPORT — VALIDATION SUITE (F1-F5 + regression)")
    print("=" * 60)
    test_F1_protected_paths()
    test_F2_variance()
    test_F3_rounding()
    test_F4_latest_snapshot()
    test_F5_event_robustness()
    test_F6_tristate()
    test_regression_readonly_and_metrics()
    print("\n" + "=" * 60)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
