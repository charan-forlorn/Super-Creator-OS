"""telemetry.py — observed-outcome sidecar (the last link in the causal chain).

database.json holds PREDICTED outcome (retention_score) and provenance (which
recommendation produced the edit). This sidecar holds the OBSERVED outcome from
the platform after publish (views, watch %, completion, engagement), joined back
by `loop_run_id`. With it the loop finally reads:

   recommendation -> decision -> execution -> predicted -> OBSERVED

Store: memory/telemetry.json  — a JSON array, ONE FILE, separate from database.json.
The v1 memory contract is never touched. Same write discipline as memory_writer:
validate -> backup -> append-only -> atomic. Multiple rows per project are allowed
(24h / 72h / 7d snapshots), so the key is (loop_run_id, platform, collected_at).

CLI:
  python integrations/learning/telemetry.py \
    --loop-run-id "<id>" --project-name "<name>" --platform tiktok \
    --collected-at 2026-06-18T20:30:00Z \
    --views 18400 --avg-watch-pct 46 --completion-rate 19 \
    --likes 1230 --comments 95 --shares 220 [--telemetry <path>]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _filelock import LockTimeout, atomic_replace, file_lock  # noqa: E402
from validators import validate_telemetry, validate_telemetry_store  # noqa: E402

DEFAULT_TELEMETRY = _HERE.parents[1] / "memory" / "telemetry.json"
ENV_TELEMETRY = "SCOS_TELEMETRY"


def resolve_path(explicit: str | os.PathLike | None = None) -> Path:
    """explicit arg > $SCOS_TELEMETRY > memory/telemetry.json (prod/test isolation)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get(ENV_TELEMETRY)
    return Path(env) if env else DEFAULT_TELEMETRY


def _atomic_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name (pid + uuid) — never share a fixed "telemetry.json.tmp"
    # between concurrent writers (audit scenario 3.3).
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def load_telemetry(path: str | os.PathLike | None = None) -> list[dict]:
    p = resolve_path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"telemetry store malformed: {exc.msg}") from exc
    if not isinstance(data, list):
        raise ValueError("telemetry store malformed: root is not a JSON array")
    return data


def append_telemetry(entry: dict, path: str | os.PathLike | None = None) -> tuple[bool, str]:
    """Safe append of one observed-outcome row. Returns (ok, info), never raises on
    a normal rejection. Append-only, atomic, backed up, deduped on
    (loop_run_id, platform, collected_at)."""
    p = resolve_path(path)

    errs = validate_telemetry(entry)
    if errs:
        return False, "telemetry invalid: " + "; ".join(errs)

    # CONCURRENCY GUARD (P0-4): lock read -> validate -> dedup -> append -> write
    # so concurrent telemetry writers can't lose a row (audit scenario 3.5).
    try:
        with file_lock(p):
            try:
                store = load_telemetry(p)
            except ValueError as exc:
                return False, str(exc)
            serrs = validate_telemetry_store(store)
            if serrs:
                return False, ("existing telemetry store invalid (refusing to write): "
                               + "; ".join(serrs))

            key = (entry["loop_run_id"], entry["platform"], entry["collected_at"])
            if any((r.get("loop_run_id"), r.get("platform"), r.get("collected_at")) == key
                   for r in store):
                return False, "duplicate (loop_run_id+platform+collected_at) — aborted"

            if p.exists():
                bdir = p.parent / "_telemetry_backups"
                bdir.mkdir(parents=True, exist_ok=True)
                stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                shutil.copy2(p, bdir / f"telemetry.{stamp}.json")

            new_store = store + [entry]
            if new_store[:len(store)] != store:   # post-condition: never alter old rows
                return False, "append would alter existing telemetry — aborted"

            _atomic_write(p, new_store)
            return True, f"appended telemetry row #{len(new_store)} for {entry['loop_run_id']}"
    except LockTimeout as e:
        return False, f"lock busy: {e}"


def derive(entry: dict, output_duration_s: float | None = None) -> dict:
    """Fill derived fields when computable. avg_watch_pct from watch_time/duration."""
    e = dict(entry)
    if e.get("avg_watch_pct") is None and e.get("avg_watch_time_s") and output_duration_s:
        e["avg_watch_pct"] = round(100 * e["avg_watch_time_s"] / output_duration_s, 1)
    return e


def join_causal_chain(db_path: str | os.PathLike | None = None,
                      telemetry_path: str | os.PathLike | None = None) -> list[dict]:
    """Join records (with provenance) to their observed telemetry on loop_run_id.

    Read-only. Returns one row per memory record that carries a loop_run_id,
    merging: provenance.recommended (what was suggested), provenance.decided
    (what was used), predicted retention_score, and the observed telemetry rows.
    This is the dataset Video Analyst / Pattern Discovery will consume.
    """
    dbp = Path(db_path) if db_path else (_HERE.parents[1] / "memory" / "database.json")
    records = json.loads(dbp.read_text(encoding="utf-8")) if dbp.exists() else []
    tele = load_telemetry(telemetry_path)

    by_run: dict[str, list[dict]] = {}
    for r in tele:
        by_run.setdefault(r.get("loop_run_id"), []).append(r)

    out = []
    for rec in records:
        prov = rec.get("provenance") or {}
        run_id = prov.get("loop_run_id")
        if not run_id:
            continue                              # pre-provenance record — not joinable
        out.append({
            "loop_run_id": run_id,
            "project_name": rec.get("project_name"),
            "product_niche": rec.get("product_niche"),
            "recommended": prov.get("recommended", {}),
            "decided": prov.get("decided", {}),
            "predicted_retention_score": rec.get("retention_score"),
            "retention_signals": rec.get("retention_signals"),
            "observed": by_run.get(run_id, []),
            "has_observed": run_id in by_run,
        })
    return out


def _num(v):
    return None if v is None else float(v)


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="Append an observed-outcome telemetry row")
    ap.add_argument("--loop-run-id", required=True)
    ap.add_argument("--project-name", required=True)
    ap.add_argument("--platform", required=True, help="tiktok | youtube_shorts | instagram_reels")
    ap.add_argument("--collected-at", required=True, help="ISO timestamp of measurement")
    ap.add_argument("--views", type=float, default=None)
    ap.add_argument("--avg-watch-pct", type=float, default=None)
    ap.add_argument("--avg-watch-time-s", type=float, default=None)
    ap.add_argument("--completion-rate", type=float, default=None)
    ap.add_argument("--rewatch-rate-pct", type=float, default=None)
    ap.add_argument("--ctr-pct", type=float, default=None)
    ap.add_argument("--likes", type=float, default=None)
    ap.add_argument("--comments", type=float, default=None)
    ap.add_argument("--shares", type=float, default=None)
    ap.add_argument("--saves", type=float, default=None)
    ap.add_argument("--output-duration-s", type=float, default=None)
    ap.add_argument("--source", default="manual", help="manual | api")
    ap.add_argument("--telemetry", default=None, help="store path (else $SCOS_TELEMETRY/default)")
    a = ap.parse_args()

    entry = {
        "loop_run_id": a.loop_run_id, "project_name": a.project_name,
        "platform": a.platform, "collected_at": a.collected_at, "source": a.source,
        "views": _num(a.views), "avg_watch_pct": _num(a.avg_watch_pct),
        "avg_watch_time_s": _num(a.avg_watch_time_s),
        "completion_rate": _num(a.completion_rate),
        "rewatch_rate_pct": _num(a.rewatch_rate_pct), "ctr_pct": _num(a.ctr_pct),
        "likes": _num(a.likes), "comments": _num(a.comments),
        "shares": _num(a.shares), "saves": _num(a.saves),
    }
    entry = {k: v for k, v in entry.items() if v is not None}
    entry = derive(entry, a.output_duration_s)

    ok, info = append_telemetry(entry, a.telemetry)
    print(("OK: " if ok else "REJECTED: ") + info)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
