"""learning_evaluator.py — the OBSERVED -> KNOWLEDGE step (the missing link).

This is the component that makes "learning" real. learning_manager writes PREDICTED
records; telemetry_capture writes OBSERVED rows; join_causal_chain joins them. But
nothing yet turns the predicted-vs-observed gap into KNOWLEDGE that changes a future
decision. This does.

It reads the joined causal chain and produces:
  - learning_events : records whose real outcome is now known (predicted vs observed)
  - calibration     : per-niche prediction error (mae/bias) + an OBSERVED benchmark
  - calibrated_benchmark(niche): the observed retention a future recommendation should
    use INSTEAD of the predicted guess -> the behavior change that CLOSES the loop.

PURE + DERIVED: recomputes from database.json + telemetry.json (read-only join). Any
cache it writes is rebuildable -> not a system of record, not a moat asset. No stable
module changed (Rule 1).

INTEGRITY: consumes OBSERVED only. Predicted retention_score is used ONLY as the thing
being calibrated AGAINST observed — never as a substitute for it (the WF-3 mandate).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import telemetry as TEL                       # noqa: E402  (read-only join, reused)


def _latest_observed_pct(rows: list[dict]) -> float | None:
    """avg_watch_pct from the latest snapshot that has it (observed ground truth)."""
    have = [r for r in rows if r.get("avg_watch_pct") is not None]
    if not have:
        return None
    have.sort(key=lambda r: str(r.get("collected_at", "")))
    return float(have[-1]["avg_watch_pct"])


def evaluate(db_path=None, telemetry_path=None) -> dict:
    """Turn the joined chain into knowledge. Returns learning_events + per-niche
    calibration. Empty/honest when no observed data exists yet."""
    chain = TEL.join_causal_chain(db_path, telemetry_path)
    events: list[dict] = []
    per_niche: dict[str, list[tuple[float, float]]] = {}

    for c in chain:
        if not c.get("has_observed"):
            continue
        observed = _latest_observed_pct(c.get("observed", []))
        predicted = c.get("predicted_retention_score")
        if observed is None or predicted is None:
            continue
        niche = c.get("product_niche") or "unknown"
        error = round(float(predicted) - observed, 2)        # +ve => over-predicted
        events.append({
            "loop_run_id": c["loop_run_id"],
            "project_name": c.get("project_name"),
            "product_niche": niche,
            "predicted_retention": float(predicted),
            "observed_avg_watch_pct": observed,
            "prediction_error": error,
            "hooks_actually_used": c.get("decided", {}).get("hooks_actually_used"),
        })
        per_niche.setdefault(niche, []).append((float(predicted), observed))

    calibration: dict[str, dict] = {}
    for niche, pairs in per_niche.items():
        preds = [p for p, _ in pairs]
        obss = [o for _, o in pairs]
        n = len(pairs)
        mae = round(sum(abs(p - o) for p, o in pairs) / n, 2)
        bias = round(sum(p - o for p, o in pairs) / n, 2)
        calibration[niche] = {
            "n": n,
            "mean_predicted": round(sum(preds) / n, 2),
            "mean_observed": round(sum(obss) / n, 2),
            "mae": mae,
            "bias": bias,                                    # +ve => system over-predicts
            "observed_benchmark": round(sum(obss) / n, 2),   # <- use THIS next time
        }

    return {"has_learning": bool(events), "learning_events": events,
            "calibration": calibration}


def calibrated_benchmark(niche: str, default=None, *, db_path=None, telemetry_path=None):
    """The OBSERVED retention benchmark for a niche — the value a future recommendation
    should seed with instead of the predicted guess. Returns `default` until observed
    data exists. THIS is the knowledge that changes future behavior (loop closed)."""
    cal = evaluate(db_path, telemetry_path)["calibration"].get(niche)
    return cal["observed_benchmark"] if cal else default


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="Observed->Knowledge learning evaluator")
    ap.add_argument("--db", default=None)
    ap.add_argument("--telemetry", default=None)
    ap.add_argument("--out", default=None, help="optional: write calibration cache JSON")
    a = ap.parse_args()
    rep = evaluate(a.db, a.telemetry)
    if not rep["has_learning"]:
        print("NO LEARNING YET — 0 records with observed telemetry. "
              "Publish + capture real metrics first (no observed data cannot be faked).")
    else:
        print(f"LEARNING EVENTS: {len(rep['learning_events'])}")
        for e in rep["learning_events"]:
            print(f"  {e['product_niche']}: predicted {e['predicted_retention']} vs "
                  f"observed {e['observed_avg_watch_pct']} -> error {e['prediction_error']}")
        print("\nCALIBRATION (use observed_benchmark next time):")
        print(json.dumps(rep["calibration"], ensure_ascii=False, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[cache] {a.out} (derived, rebuildable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
