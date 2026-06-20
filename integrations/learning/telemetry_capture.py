"""telemetry_capture.py — WF-3 Observed Telemetry Capture (the learning ground truth).

The OBSERVED-ONLY intake layer on top of the existing, tested telemetry sidecar.
It does NOT reimplement storage — it normalizes + validates + DQ-checks an observed
row, enforces observed-only provenance, then routes the write through
telemetry.append_telemetry (the safe moat path: validate -> backup -> append-only ->
atomic -> dedup on (loop_run_id, platform, collected_at)).

ADDITIVE: new module. Does NOT modify validators.py or telemetry.py (stable, moat-
guarding). It adds the two WF-3 fields (reach, followers_gained) + a manual-intake and
pluggable API-adapter interface + capture-time data-quality checks + causal linking.

LEARNING-INTEGRITY MANDATE (WF-3): there is NO code path here that derives an OBSERVED
metric from a PREDICTED one. retention_score (predicted) can NEVER enter telemetry —
predicted-looking keys are REJECTED. Every row must carry source in {manual, api}.

CLI:
  python integrations/learning/telemetry_capture.py \
    --loop-run-id "<id>" --project-name "<name>" --platform tiktok \
    --collected-at 2026-06-20T08:00:00Z --source manual \
    --views 18400 --reach 25100 --avg-watch-pct 46 --completion-rate 19 \
    --likes 1230 --comments 95 --shares 220 --saves 410 --followers-gained 37
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Protocol

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import telemetry as TEL                      # noqa: E402  (the safe storage layer — reused, not rebuilt)
from validators import validate_telemetry    # noqa: E402  (the core contract — reused, not changed)

SOURCES = {"manual", "api"}
# WF-3 names -> existing storage field names (keep one canonical schema)
NAME_MAP = {"avg_watch_time": "avg_watch_time_s", "rewatch_rate": "rewatch_rate_pct"}
# new WF-3 fields validated at THIS layer (additive; core validator untouched)
EXTRA_NONNEG = ("reach", "followers_gained")
# INTEGRITY: any of these keys in an observed row is a predicted-metric leak -> reject
PREDICTED_FORBIDDEN = {"retention_score", "predicted_retention_score",
                       "predicted", "predicted_score", "score"}

WF3_METRICS = ("views", "reach", "avg_watch_pct", "avg_watch_time_s", "completion_rate",
               "rewatch_rate_pct", "likes", "comments", "shares", "saves", "followers_gained")


# ---------------------------------------------------------------------------
# pluggable observed-data source (manual default; API adapter is future-pluggable)
# ---------------------------------------------------------------------------
class ApiAdapter(Protocol):
    """A platform API backend implements this to FETCH real observed metrics. It must
    return observed numbers only (source='api'); it never invents values."""
    def fetch(self, loop_run_id: str, platform: str) -> dict | None: ...


class NullApiAdapter:
    """Default: no API wired. Honest no-op — capture proceeds from manual input."""
    def fetch(self, loop_run_id: str, platform: str) -> dict | None:
        return None


# ---------------------------------------------------------------------------
# normalize / validate / DQ
# ---------------------------------------------------------------------------
def normalize_entry(raw: dict) -> dict:
    """Map WF-3 metric names to canonical storage names; drop None values."""
    out = {}
    for k, v in raw.items():
        if v is None:
            continue
        out[NAME_MAP.get(k, k)] = v
    return out


def validate_capture(entry: dict) -> list[str]:
    """Observed-only contract. Empty list == valid."""
    errs: list[str] = []
    # (1) INTEGRITY GUARD — predicted metrics forbidden
    leaked = PREDICTED_FORBIDDEN & set(entry)
    if leaked:
        errs.append("predicted metric(s) not allowed in observed telemetry: "
                    + ", ".join(sorted(leaked)))
    # (2) observed provenance required
    src = entry.get("source")
    if src not in SOURCES:
        errs.append(f"source must be one of {sorted(SOURCES)} (observed-only); got {src!r}")
    # (3) new WF-3 fields: non-negative when present
    for f in EXTRA_NONNEG:
        v = entry.get(f)
        if v is not None and not (isinstance(v, (int, float)) and v >= 0):
            errs.append(f"{f} must be a non-negative number")
    # (4) defer the CORE contract (loop_run_id/platform/collected_at + known ranges)
    errs += validate_telemetry(entry)
    return errs


def dq_checks(entry: dict, record: dict | None = None) -> list[str]:
    """Non-blocking warnings that protect learning quality."""
    warns: list[str] = []
    if (entry.get("avg_watch_pct") is None and entry.get("avg_watch_time_s")
            and entry.get("output_duration_s")):
        warns.append("avg_watch_pct missing but derivable (watch_time/duration) — derive applied")
    if record is not None:
        pred, obs = record.get("retention_score"), entry.get("avg_watch_pct")
        if pred is not None and obs is not None and float(pred) == float(obs):
            warns.append("observed avg_watch_pct EXACTLY equals predicted retention_score — "
                         "verify this is measured, not copied")
    return warns


def _joined_to_record(loop_run_id: str, db_path, telemetry_path) -> bool:
    """True if this loop_run_id joins a record that carries provenance (causal chain
    complete). Records predating provenance (no loop_run_id) -> orphan (False)."""
    for c in TEL.join_causal_chain(db_path, telemetry_path):
        if c.get("loop_run_id") == loop_run_id and c.get("has_observed"):
            return True
    return False


# ---------------------------------------------------------------------------
# capture (orchestration — reuses the safe write path)
# ---------------------------------------------------------------------------
def capture(raw: dict, *, output_duration_s: float | None = None,
            telemetry_path=None, db_path=None, record: dict | None = None) -> dict:
    """Validate + DQ + persist one OBSERVED row via the safe sidecar path.
    Returns {ok, info|errors, warnings, joined_to_record, orphan}. Writes nothing on
    validation failure. Never fabricates or derives-from-predicted."""
    entry = normalize_entry(raw)
    entry = TEL.derive(entry, output_duration_s)        # only fills observed-from-observed
    errs = validate_capture(entry)
    if errs:
        return {"ok": False, "stage": "validate", "errors": errs}
    warns = dq_checks(entry, record)
    ok, info = TEL.append_telemetry(entry, telemetry_path)
    if not ok:
        return {"ok": False, "stage": "append", "info": info, "warnings": warns}
    joined = _joined_to_record(entry["loop_run_id"], db_path, telemetry_path)
    return {"ok": True, "info": info, "warnings": warns,
            "joined_to_record": joined, "orphan": not joined}


def _num(v):
    return None if v is None else float(v)


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-3 Observed Telemetry Capture (observed-only)")
    ap.add_argument("--loop-run-id", required=True)
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--platform", required=True, help="tiktok | youtube_shorts | instagram_reels")
    ap.add_argument("--collected-at", required=True)
    ap.add_argument("--source", required=True, help="manual | api (observed provenance)")
    for m in ("views", "reach", "avg-watch-pct", "avg-watch-time", "completion-rate",
              "rewatch-rate", "likes", "comments", "shares", "saves",
              "followers-gained", "output-duration-s"):
        ap.add_argument(f"--{m}", type=float, default=None)
    ap.add_argument("--telemetry", default=None)
    ap.add_argument("--db", default=None)
    a = ap.parse_args()

    raw = {
        "loop_run_id": a.loop_run_id, "project_name": a.project_name,
        "platform": a.platform, "collected_at": a.collected_at, "source": a.source,
        "views": _num(a.views), "reach": _num(a.reach),
        "avg_watch_pct": _num(a.avg_watch_pct), "avg_watch_time": _num(a.avg_watch_time),
        "completion_rate": _num(a.completion_rate), "rewatch_rate": _num(a.rewatch_rate),
        "likes": _num(a.likes), "comments": _num(a.comments), "shares": _num(a.shares),
        "saves": _num(a.saves), "followers_gained": _num(a.followers_gained),
    }
    res = capture(raw, output_duration_s=a.output_duration_s,
                  telemetry_path=a.telemetry, db_path=a.db)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
