"""run_suite.py — 6/10 integration test suite for the Super Creator OS learning layer.

Calibration (per the user's 1..10 scale):
    1/10  = `python -c "import dq_report"`         (does it import?)
    6/10  = THIS suite                              (every core module exercised in
            isolation with Positive / Negative / Regression checks + the DQ suite)
    10/10 = + pytest, coverage %, property-based + mutation testing, CI gate

What 6/10 means here:
  - Covers all CLI-bearing + pure modules: validators, event_bus, telemetry,
    recommendation_service, learning_manager, plus the existing dq_report suite.
  - Each module gets Positive (happy path), Negative (bad input rejected), and at
    least one Regression / contract check (v1 record, read-only, append-only).
  - 100% isolated: tempfile dirs + $SCOS_EVENTS / $SCOS_TELEMETRY redirection.
    NEVER reads or writes production memory (database.json / telemetry.json).

No pytest dependency. Run from anywhere:
    python integrations/learning/tests/run_suite.py
Exit 0 if all pass, 1 otherwise.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent                                  # integrations/learning
sys.path.insert(0, str(_PKG))

import validators as V                                # noqa: E402
import event_bus as EB                                # noqa: E402
import telemetry as TEL                               # noqa: E402
import recommendation_service as RS                   # noqa: E402
import learning_manager as LM                         # noqa: E402
import memory_writer as MW                            # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _good_record(run="r1"):
    return {"project_name": run, "product_niche": "Gaming (MOBA)",
            "hook_successful": "h", "editing_specs": "e", "retention_score": 80,
            "lesson_learned": "l", "created_at": "2026-06-16T00:00:00.000Z"}


# ---------------------------------------------------------------------------
def test_imports():
    print("\n[1] import smoke — all learning-layer modules load")
    mods = ["validators", "event_bus", "telemetry", "recommendation_service",
            "learning_manager", "seed_store", "anchor_library", "memory_writer",
            "archive_manager", "dq_report"]
    ok = True
    for m in mods:
        try:
            __import__(m)
        except Exception as e:                        # noqa: BLE001
            ok = False
            print(f"        ! {m}: {e}")
    check(f"all {len(mods)} modules import", ok)


def test_validators():
    print("\n[2] validators — pure schema contract (pos / neg / v1 regression)")
    # POSITIVE
    check("valid v1 record -> no errors", V.validate_record(_good_record()) == [])
    # NEGATIVE: missing field + out-of-range score
    bad = _good_record(); del bad["lesson_learned"]; bad["retention_score"] = 150
    errs = V.validate_record(bad)
    check("missing v1 field reported", any("lesson_learned" in e for e in errs))
    check("retention_score out of range reported", any("range" in e for e in errs))
    # REGRESSION: v1 contract list is intact (the never-break invariant)
    check("V1_REQUIRED still has all 7 fields", len(V.V1_REQUIRED) == 7)

    # provenance (optional block): None ok, cold_start rule enforced
    check("provenance None -> valid", V.validate_provenance(None) == [])
    check("cold_start + reference_project -> error",
          any("cold_start" in e for e in V.validate_provenance(
              {"recommended": {"match_quality": "cold_start",
                               "reference_project": "x"}})))
    check("bad match_quality rejected",
          any("match_quality" in e for e in V.validate_provenance(
              {"recommended": {"match_quality": "wat"}})))

    # telemetry row: platform enum + 0..100 range
    good_t = {"loop_run_id": "k::p", "project_name": "p", "platform": "tiktok",
              "collected_at": "2026-06-19T00:00:00Z", "avg_watch_pct": 50}
    check("valid telemetry row -> no errors", V.validate_telemetry(good_t) == [])
    check("bad platform rejected",
          any("platform" in e for e in V.validate_telemetry({**good_t, "platform": "vimeo"})))
    check("avg_watch_pct > 100 rejected",
          any("avg_watch_pct" in e for e in V.validate_telemetry({**good_t, "avg_watch_pct": 150})))

    # event: required fields + known type
    ev = {"event_type": "PROJECT_RENDERED", "project_id": "p1",
          "timestamp": "t", "metadata": {}}
    check("valid event -> no errors", V.validate_event(ev) == [])
    check("unknown event_type rejected",
          any("unknown event_type" in e for e in V.validate_event({**ev, "event_type": "NOPE"})))


def test_event_bus():
    print("\n[3] event_bus — isolated log, dispatch, invalid rejected")
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "events.jsonl"
        bus = EB.EventBus(log_path=log)
        seen = []
        bus.subscribe("PROJECT_RENDERED", lambda e: seen.append(e["project_id"]))
        bus.emit("PROJECT_RENDERED", "p1", {"render_ok": True})
        check("subscriber received the event", seen == ["p1"])
        check("event persisted to JSONL log", log.exists() and log.read_text().count("\n") == 1)
        check("replay() returns the 1 emitted event", len(bus.replay()) == 1)
        # NEGATIVE: invalid event type raises, does NOT persist a bad line
        before = log.read_text()
        try:
            bus.emit("TOTALLY_FAKE", "p1", {})
            raised = False
        except ValueError:
            raised = True
        check("emit invalid event_type raises ValueError", raised)
        check("log unchanged after rejected emit", log.read_text() == before)


def test_telemetry():
    print("\n[4] telemetry — append-only store, dedup, derive, read-only")
    with tempfile.TemporaryDirectory() as d:
        store = Path(d) / "telemetry.json"
        row = {"loop_run_id": "k::p1", "project_name": "p1", "platform": "tiktok",
               "collected_at": "2026-06-19T00:00:00Z", "avg_watch_pct": 46, "views": 1000}
        ok, info = TEL.append_telemetry(row, path=store)
        check("append valid row -> ok", ok)
        check("store now has 1 row", len(json.loads(store.read_text())) == 1)
        # NEGATIVE: duplicate key rejected, store unchanged
        before = store.read_bytes()
        ok2, _ = TEL.append_telemetry(row, path=store)
        check("duplicate (run+platform+ts) rejected", ok2 is False)
        check("store bytes unchanged after dup reject", store.read_bytes() == before)
        # NEGATIVE: invalid platform rejected
        bad = {**row, "platform": "myspace", "collected_at": "2026-06-20T00:00:00Z"}
        ok3, _ = TEL.append_telemetry(bad, path=store)
        check("invalid platform rejected", ok3 is False)
        # derive: avg_watch_pct computed from watch_time / duration
        der = TEL.derive({"avg_watch_time_s": 15, "avg_watch_pct": None}, output_duration_s=30)
        check("derive computes avg_watch_pct (15/30 -> 50.0)", der["avg_watch_pct"] == 50.0)


def test_recommendation():
    print("\n[5] recommendation_service — cold start, exact match, adoption")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        emptylib = d / "lib.json"; emptylib.write_text("{}", encoding="utf-8")
        bus = EB.EventBus(log_path=d / "ev.jsonl")
        # COLD START: no db -> quality none, cold-start note present, nothing persisted
        seed = RS.recommend("Gaming (MOBA)", "proj-a", db=str(d / "nope.json"),
                            lib_path=emptylib, bus=bus, persist=False)
        check("cold start -> match_quality none", seed["match_quality"] == "none")
        check("cold start note present", any("cold start" in n.lower() for n in seed["notes"]))
        check("nothing persisted (no _persisted_to)", "_persisted_to" not in seed)
        # EXACT MATCH: db has same niche -> quality exact, score 1.0
        db = d / "db.json"
        db.write_text(json.dumps([_good_record("prior")]), encoding="utf-8")
        seed2 = RS.recommend("Gaming (MOBA)", "proj-b", db=str(db),
                             lib_path=emptylib, bus=bus, persist=False)
        check("exact niche -> match_quality exact", seed2["match_quality"] == "exact")
        check("exact -> reference_project linked", seed2["reference_project"] == "prior")
        # loop_run_id stable + slugged
        k1 = RS.make_loop_run_id("2026-06-16T00:00:00.000Z", "My Project")
        k2 = RS.make_loop_run_id("2026-06-16T00:00:00.000Z", "My Project")
        check("make_loop_run_id deterministic", k1 == k2 and k1.endswith("::my-project"))
        # classify_hook_adoption truth table
        check("adoption adopted (used subset of suggested)",
              RS.classify_hook_adoption(["A", "B"], ["A"]) == "adopted")
        check("adoption rejected (disjoint)",
              RS.classify_hook_adoption(["A"], ["Z"]) == "rejected")
        check("adoption partial (overlap + extra)",
              RS.classify_hook_adoption(["A"], ["A", "Z"]) == "partial")
        check("adoption unrecorded (used is None)",
              RS.classify_hook_adoption(["A"], None) == "unrecorded")


def test_learning_manager_dryrun():
    print("\n[6] learning_manager — dry-run writes NOTHING to memory")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        edl = d / "edl.json"
        edl.write_text(json.dumps({"ranges": [], "total_duration_s": 0}), encoding="utf-8")
        db = d / "db.json"
        db.write_text("[]", encoding="utf-8")
        before = db.read_bytes()
        bus = EB.EventBus(log_path=d / "ev.jsonl")
        # dry_run prints the full record JSON to stdout — capture it to keep the
        # suite output clean (the record is still asserted on below).
        with contextlib.redirect_stdout(io.StringIO()):
            res = LM.process_project(str(edl), "dry-proj", "Gaming (MOBA)",
                                     db=str(db), dry_run=True, bus=bus,
                                     lib_path=d / "lib.json")
        check("dry_run -> status dry_run", res["status"] == "dry_run")
        check("dry_run -> memory_written False", res["memory_written"] is False)
        check("dry_run -> db file untouched", db.read_bytes() == before)
        check("dry_run -> record built with v1 fields",
              all(k in res["record"] for k in V.V1_REQUIRED))


def test_memory_writer_safe_append():
    print("\n[6b] memory_writer.safe_append — the critical persistence path")
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "database.json"
        db.write_text("[]", encoding="utf-8")
        r1 = _good_record("p1")
        ok, info = MW.safe_append(r1, db)
        check("valid record appended -> ok", ok)
        check("db now has 1 record", len(json.loads(db.read_text())) == 1)
        check("backup created in _db_backups/", (Path(d) / "_db_backups").exists())
        # NEGATIVE: duplicate (same project_name + created_at) rejected, file unchanged
        before = db.read_bytes()
        ok2, _ = MW.safe_append(r1, db)
        check("duplicate (name+created_at) rejected", ok2 is False)
        check("db bytes unchanged after dup reject", db.read_bytes() == before)
        # NEGATIVE: invalid record (retention out of range) rejected
        bad = _good_record("p2"); bad["retention_score"] = 150
        ok3, _ = MW.safe_append(bad, db)
        check("invalid record (score 150) rejected", ok3 is False)
        # APPEND-ONLY: a 2nd valid record keeps record #1 byte-identical
        r2 = _good_record("p2"); r2["created_at"] = "2026-06-16T01:00:00.000Z"
        ok4, _ = MW.safe_append(r2, db)
        arr = json.loads(db.read_text())
        check("2nd valid record appended", ok4 and len(arr) == 2)
        check("append-only: record #1 preserved", arr[0] == r1)
        # GUARD: refuses to write when the EXISTING db is already invalid
        bad_db = Path(d) / "corrupt.json"
        bad_db.write_text(json.dumps([{"project_name": "x"}]), encoding="utf-8")  # missing v1 fields
        ok5, info5 = MW.safe_append(_good_record("p3"), bad_db)
        check("refuses to write when existing DB is invalid", ok5 is False and "DB invalid" in info5)


def test_write_guard():
    print("\n[6c] write guard — direct writes blocked + tamper-evident integrity")
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "database.json"
        db.write_text("[]", encoding="utf-8")
        sidecar = Path(d) / ".database.json.integrity.json"
        # 1) DIRECT WRITE BLOCKED: low-level writer refuses without the private token
        raised = False
        try:
            MW._atomic_write_json(db, [{"x": 1}])           # no token -> must refuse
        except PermissionError:
            raised = True
        check("direct _atomic_write_json (no token) raises PermissionError", raised)
        check("db untouched by the blocked direct write", db.read_text() == "[]")
        # 2) SAFE PATH STILL WORKS + stamps the integrity marker
        ok, _ = MW.safe_append(_good_record("g1"), db)
        check("safe_append succeeds via the approved path", ok)
        check("integrity marker (.db_integrity.json) written", sidecar.exists())
        okv, _ = MW.verify_db_integrity(db)
        check("verify_db_integrity ok immediately after safe_append", okv)
        # 3) OUT-OF-BAND WRITE is detected (simulate raw open()/manual edit)
        arr = json.loads(db.read_text()); arr.append(_good_record("rogue"))
        db.write_text(json.dumps(arr), encoding="utf-8")     # rogue write; marker NOT updated
        okv2, info2 = MW.verify_db_integrity(db)
        check("verify detects out-of-band write", okv2 is False and "outside safe_append" in info2)
        # 4) safe_append REFUSES to build on a tampered DB
        ok2, info3 = MW.safe_append(_good_record("g2"), db)
        check("safe_append refuses tampered DB", ok2 is False and "outside safe_append" in info3)
        # 5) BOOTSTRAP: a fresh DB with no marker is trusted (prod-DB compatibility)
        fresh = Path(d) / "fresh.json"; fresh.write_text("[]", encoding="utf-8")
        okb, _ = MW.verify_db_integrity(fresh)
        check("no-marker DB is bootstrap-trusted", okb)


def test_dq_suite_subprocess():
    print("\n[7] delegate to existing DQ suite (test_dq_report.py) via subprocess")
    suite = _HERE / "test_dq_report.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(suite)], capture_output=True,
                          text=True, env=env)
    tail = "\n".join(proc.stdout.strip().splitlines()[-3:])
    print("        " + tail.replace("\n", "\n        "))
    check("DQ suite exits 0 (all its checks pass)", proc.returncode == 0)


def test_e2e_loop_subprocess():
    print("\n[8] delegate to end-to-end loop closure suite (test_e2e_loop.py)")
    suite = _HERE / "test_e2e_loop.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(suite)], capture_output=True,
                          text=True, env=env)
    tail = "\n".join(proc.stdout.strip().splitlines()[-3:])
    print("        " + tail.replace("\n", "\n        "))
    check("e2e loop suite exits 0 (recommend->render->telemetry->evaluator closes)",
          proc.returncode == 0)


def test_concurrency_subprocess():
    print("\n[9] delegate to memory concurrency regression (test_concurrency.py)")
    suite = _HERE / "test_concurrency.py"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(suite)], capture_output=True,
                          text=True, env=env)
    tail = "\n".join(proc.stdout.strip().splitlines()[-3:])
    print("        " + tail.replace("\n", "\n        "))
    check("concurrency suite exits 0 (no lost-update / temp-collision under N writers)",
          proc.returncode == 0)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" SUPER CREATOR OS — LEARNING LAYER SUITE (6/10 integration)")
    print("=" * 64)
    test_imports()
    test_validators()
    test_event_bus()
    test_telemetry()
    test_recommendation()
    test_learning_manager_dryrun()
    test_memory_writer_safe_append()
    test_write_guard()
    test_dq_suite_subprocess()
    test_e2e_loop_subprocess()
    test_concurrency_subprocess()
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
