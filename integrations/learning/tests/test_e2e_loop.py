"""test_e2e_loop.py — end-to-end closure test for the full learning loop.

The unit suite (run_suite.py) exercises each module in ISOLATION. This test proves
the modules compose into ONE closed loop on a SINGLE `loop_run_id`:

    recommend  ->  render_to_memory(+provenance)  ->  telemetry_capture  ->  evaluator
    (forward)      (predicted record, real CLI)       (observed outcome)     (knowledge)

and that the knowledge then FEEDS FORWARD into the next recommendation — i.e. the
observed benchmark (ground truth) overrides the predicted guess. That feed-forward
is the behaviour the P0 wiring added (recommendation_service seeds
retention_benchmark from learning_evaluator.calibrated_benchmark), so this test is
the regression that proves the loop is actually closed, not just wired.

100% isolated: a tempdir DB + $SCOS_TELEMETRY redirection. Never touches production
memory. The render->memory step runs the REAL adapter CLI as a subprocess (no ffmpeg
needed — `--render` is omitted), so it also serves as the first executable test of
render_to_memory's provenance stamping + safe-write path.

No pytest. Run standalone:
    python integrations/learning/tests/test_e2e_loop.py
Exit 0 if all pass, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent                                   # integrations/learning
_ADAPTER = _PKG.parent / "adapter" / "render_to_memory.py"
sys.path.insert(0, str(_PKG))

import recommendation_service as RS                    # noqa: E402
import telemetry as TEL                                # noqa: E402
import learning_evaluator as LE                        # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _run_render_to_memory(*, edl, project, niche, score, created, db):
    """Invoke the REAL render_to_memory CLI (no --render => no ffprobe needed)."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_ADAPTER),
         "--edl", str(edl), "--project-name", project, "--product-niche", niche,
         "--retention-score", str(score), "--created-at", created, "--db", str(db)],
        capture_output=True, text=True, env=env)
    return proc


def test_closed_loop():
    print("\n[e2e] recommend -> render_to_memory(+provenance) -> telemetry -> evaluator")
    NICHE = "Gaming (MOBA)"
    PROJ = "E2E Loop Demo"
    CREATED = "2026-06-20T00:00:00.000Z"
    PREDICTED = 90          # what the editor predicted
    OBSERVED = 60.0         # what the platform actually measured (ground truth)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db = d / "database.json"; db.write_text("[]", encoding="utf-8")
        tele = d / "telemetry.json"
        edl = d / "edl.json"
        edl.write_text(json.dumps({"ranges": [], "total_duration_s": 0}), encoding="utf-8")
        emptylib = d / "lib.json"; emptylib.write_text("{}", encoding="utf-8")
        # recommend's internal calibrated_benchmark resolves telemetry via env.
        os.environ["SCOS_TELEMETRY"] = str(tele)
        loop_run_id = RS.make_loop_run_id(CREATED, PROJ)
        try:
            # 1) RECOMMEND — cold start (empty db): no observed data yet.
            seed = RS.recommend(NICHE, PROJ, db=str(db), lib_path=emptylib, persist=False)
            check("cold-start recommend -> match_quality none", seed["match_quality"] == "none")
            check("cold-start -> retention_benchmark None (nothing observed yet)",
                  seed["retention_benchmark"] is None)

            # 2) RENDER -> MEMORY via the real adapter CLI, stamping provenance.
            proc = _run_render_to_memory(edl=edl, project=PROJ, niche=NICHE,
                                         score=PREDICTED, created=CREATED, db=db)
            check("render_to_memory CLI exits 0", proc.returncode == 0)
            arr = json.loads(db.read_text(encoding="utf-8"))
            check("one record persisted to memory", len(arr) == 1)
            rec = arr[0] if arr else {}
            check("record carries provenance.loop_run_id (joinable)",
                  (rec.get("provenance") or {}).get("loop_run_id") == loop_run_id)
            check("record predicted retention_score preserved (=90)",
                  rec.get("retention_score") == PREDICTED)

            # 3) BEFORE telemetry — evaluator honestly reports NO learning.
            rep0 = LE.evaluate(str(db), str(tele))
            check("pre-telemetry -> has_learning False", rep0["has_learning"] is False)
            check("pre-telemetry -> calibrated_benchmark falls back to default",
                  LE.calibrated_benchmark(NICHE, default=-1.0,
                                          db_path=str(db), telemetry_path=str(tele)) == -1.0)

            # 4) TELEMETRY CAPTURE — observed outcome for the SAME loop_run_id.
            row = {"loop_run_id": loop_run_id, "project_name": PROJ, "platform": "tiktok",
                   "collected_at": "2026-06-22T00:00:00Z", "avg_watch_pct": OBSERVED,
                   "views": 12000}
            ok, info = TEL.append_telemetry(row, path=tele)
            check("telemetry row appended -> ok", ok)

            # 5) EVALUATOR — knowledge is now real (predicted vs observed joined).
            rep1 = LE.evaluate(str(db), str(tele))
            check("post-telemetry -> has_learning True", rep1["has_learning"] is True)
            check("exactly one learning_event", len(rep1["learning_events"]) == 1)
            ev = (rep1["learning_events"] or [{}])[0]
            check("learning_event joined on loop_run_id", ev.get("loop_run_id") == loop_run_id)
            check("observed avg_watch_pct surfaced (=60)", ev.get("observed_avg_watch_pct") == OBSERVED)
            check("prediction_error = predicted - observed (90-60=30)",
                  ev.get("prediction_error") == 30.0)
            cal = rep1["calibration"].get(NICHE, {})
            check("per-niche observed_benchmark = 60", cal.get("observed_benchmark") == OBSERVED)

            # 6) FEED FORWARD — the NEXT recommendation seeds the OBSERVED benchmark
            #    (60), not the predicted guess (the exact-match ref would give 90).
            seed2 = RS.recommend(NICHE, "E2E Loop Next", db=str(db),
                                 lib_path=emptylib, persist=False)
            check("next recommend exact-matches the prior project",
                  seed2["match_quality"] == "exact")
            check("LOOP CLOSED: next retention_benchmark = observed 60 (overrides predicted 90)",
                  seed2["retention_benchmark"] == OBSERVED)
        finally:
            os.environ.pop("SCOS_TELEMETRY", None)


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" SUPER CREATOR OS — END-TO-END LEARNING LOOP CLOSURE")
    print("=" * 64)
    test_closed_loop()
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
