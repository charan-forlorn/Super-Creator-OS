"""dq_report.py — READ-ONLY Data Quality Report for Super Creator OS.

Measures whether the accumulated data is ready to build Video Analyst. Reads
database.json, telemetry.json, events.jsonl and the anchor library; computes 9
quality dimensions + a readiness verdict; prints a scannable report (and an
optional JSON dump).

HARD GUARANTEES (by construction):
  - opens every data file READ-ONLY; no write/append/replace path to any data file
  - never imports memory_writer / safe_append / append_telemetry / record_project_anchors
  - the ONLY thing it may write is a derived report artifact via --json-out
    (a file the operator names; never database.json / telemetry.json / the library)
  - honors the same environment isolation as the rest of the system
    ($SCOS_TELEMETRY, $SCOS_ANCHOR_LIB, $SCOS_EVENTS) + explicit CLI flags

CLI:
  python integrations/learning/dq_report.py
  python integrations/learning/dq_report.py --db memory/database.json \
      --telemetry memory/telemetry.json --events integrations/learning/events.jsonl \
      [--lib-path ...] [--json-out report.json] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import telemetry as _tele                              # noqa: E402  (resolve_path, join_causal_chain)
import anchor_library as _anchor                       # noqa: E402  (resolve_lib_path)
import event_bus as _eb                                # noqa: E402  (DEFAULT_LOG, ENV_EVENTS)
from validators import (validate_provenance,           # noqa: E402
                        validate_telemetry, validate_record)

DB_DEFAULT = _HERE.parents[1] / "memory" / "database.json"

# ---- Recommended thresholds (see §10 of DATA_INFRASTRUCTURE_PHASE) ----------
THRESHOLDS = {
    "coverage_pct": 100,            # every rendered project reaches a terminal event
    "provenance_pct": 95,           # records carrying a valid provenance block
    "hooks_recorded_pct": 80,       # decided.hooks_actually_used not 'unrecorded'
    "ground_truth_fill_pct": 80,    # records (w/ loop_run_id) that have observed telemetry
    "dq_pass_pct": 95,              # rows/records passing their validators
    "min_records_per_niche": 30,    # M2 volume
    "min_hits_per_niche": 5,
    "min_flops_per_niche": 5,
    "max_prediction_mae": 20.0,     # advisory: |predicted - observed avg_watch_pct|
    "min_observed_for_percentiles": 8,
}

# ---- F6: tri-state coverage gate -------------------------------------------
COVERAGE_PASS = "PASS"
COVERAGE_FAIL = "FAIL"
COVERAGE_UNKNOWN = "UNKNOWN"
COVERAGE_STATES = (COVERAGE_PASS, COVERAGE_FAIL, COVERAGE_UNKNOWN)

_STOP = {"the", "a", "an", "of", "and", "for", "to", "in", "on"}


# ----------------------------------------------------------------------------
# Read-only loaders
# ----------------------------------------------------------------------------
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_db(path=None) -> list[dict]:
    p = Path(path) if path else DB_DEFAULT
    data = _load_json(p, [])
    return data if isinstance(data, list) else []


def load_events(path=None) -> list[dict]:
    if path:
        p = Path(path)
    elif os.environ.get(_eb.ENV_EVENTS):
        p = Path(os.environ[_eb.ENV_EVENTS])
    else:
        p = _eb.DEFAULT_LOG
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _tokens(s: str) -> frozenset:
    words = re.split(r"[^a-z0-9]+", str(s).lower())
    return frozenset(w for w in words if w and w not in _STOP)


def _ratio(num, den) -> float | None:
    """RAW percentage (unrounded) — for gate comparisons. None if den == 0."""
    return (100 * num / den) if den else None


def _pct(num, den) -> float | None:
    """ROUNDED percentage — for human-readable display only (never for gate logic)."""
    r = _ratio(num, den)
    return round(r, 1) if r is not None else None


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


# ----------------------------------------------------------------------------
# Dimension computations (all pure / read-only)
# ----------------------------------------------------------------------------
def coverage_metrics(records, events) -> dict:
    # F5: use .get() so a malformed event line (missing keys) is skipped, not fatal.
    def ids(evtype):
        return {e.get("project_id") for e in events
                if isinstance(e, dict) and e.get("event_type") == evtype
                and e.get("project_id") is not None}
    rendered = ids("PROJECT_RENDERED")
    complete = ids("PROJECT_COMPLETE")
    qafailed = ids("PROJECT_QA_FAILED")
    terminal = complete | qafailed
    orphans = sorted(rendered - terminal)
    cov_raw = _ratio(len(rendered & terminal), len(rendered))

    # F6: tri-state coverage. absence of evidence is UNKNOWN, never PASS, never FAIL.
    if not rendered:                              # nothing to evaluate against
        if not events:
            state, reason = COVERAGE_UNKNOWN, "coverage_evidence_missing"   # no events.jsonl / empty
        else:
            state, reason = COVERAGE_UNKNOWN, "coverage_unavailable"        # events exist, none usable
    elif cov_raw is not None and cov_raw >= THRESHOLDS["coverage_pct"] and not orphans:
        state, reason = COVERAGE_PASS, "coverage_complete"
    else:
        state, reason = COVERAGE_FAIL, "coverage_insufficient"

    return {
        "total_records": len(records),
        "events_rendered": len(rendered),
        "events_complete": len(complete),
        "events_qa_failed": len(qafailed),
        "orphan_rendered": orphans,           # rendered but never reached a terminal event
        "coverage_pct": _pct(len(rendered & terminal), len(rendered)),   # display (rounded)
        "coverage_pct_raw": cov_raw,                                     # gate (raw) — back-compat name
        "coverage_raw": cov_raw,                                         # gate (raw) — F6 brief name
        "coverage_state": state,                                         # PASS | FAIL | UNKNOWN
        "coverage_reason": reason,
        "records_with_loop_run_id": sum(1 for r in records
                                        if (r.get("provenance") or {}).get("loop_run_id")),
        "note": "no events.jsonl found" if not events else None,
    }


def provenance_quality(records) -> dict:
    n = len(records)
    has_prov = [r for r in records if isinstance(r.get("provenance"), dict)]
    valid = [r for r in has_prov if not validate_provenance(r["provenance"])]
    with_rec_id = [r for r in has_prov
                   if (r["provenance"].get("recommended") or {}).get("recommendation_id")]
    mq = Counter((r["provenance"].get("recommended") or {}).get("match_quality")
                 for r in has_prov)
    return {
        "records": n,
        "with_provenance": len(has_prov),
        "with_provenance_pct": _pct(len(has_prov), n),
        "with_provenance_pct_raw": _ratio(len(has_prov), n),
        "provenance_valid_pct": _pct(len(valid), len(has_prov)) if has_prov else None,
        "with_recommendation_id_pct": _pct(len(with_rec_id), len(has_prov)) if has_prov else None,
        "match_quality_distribution": dict(mq),
    }


def hook_adoption_metrics(records) -> dict:
    decided = [(r.get("provenance") or {}).get("decided") or {} for r in records]
    adoption = Counter(d.get("hook_adoption") for d in decided if d)
    decided_known = adoption.get("adopted", 0) + adoption.get("partial", 0) + adoption.get("rejected", 0)
    return {
        "adoption_distribution": dict(adoption),
        "adoption_rate_pct": _pct(adoption.get("adopted", 0), decided_known),
        "rejected_rate_pct": _pct(adoption.get("rejected", 0), decided_known),
        "unrecorded": adoption.get("unrecorded", 0),
        "recorded_pct": _pct(
            sum(v for k, v in adoption.items() if k != "unrecorded"),
            sum(adoption.values())),
        "recorded_pct_raw": _ratio(
            sum(v for k, v in adoption.items() if k != "unrecorded"),
            sum(adoption.values())),
    }


def _observed_watch(rows):
    """avg_watch_pct from the chronologically latest telemetry snapshot.

    F4: sort by `collected_at` (ISO-8601 strings sort lexicographically = chronologically)
    instead of trusting file/append order, so an out-of-order row can't be mistaken for
    'latest'. Rows missing avg_watch_pct are ignored; among the rest the newest wins.
    """
    cand = [r for r in rows if isinstance(r.get("avg_watch_pct"), (int, float))]
    if not cand:
        return None
    cand.sort(key=lambda r: str(r.get("collected_at", "")))
    return cand[-1].get("avg_watch_pct")


def ground_truth_fill(chain) -> dict:
    joinable = [c for c in chain if c["loop_run_id"]]
    with_obs = [c for c in joinable if c["has_observed"]]
    per_niche = defaultdict(lambda: [0, 0])  # niche -> [joinable, with_observed]
    for c in joinable:
        per_niche[c["product_niche"]][0] += 1
        if c["has_observed"]:
            per_niche[c["product_niche"]][1] += 1
    return {
        "joinable_records": len(joinable),
        "with_observed": len(with_obs),
        "fill_rate_pct": _pct(len(with_obs), len(joinable)),
        "fill_rate_pct_raw": _ratio(len(with_obs), len(joinable)),
        "per_niche": {k: {"records": v[0], "with_observed": v[1],
                          "fill_pct": _pct(v[1], v[0])} for k, v in per_niche.items()},
    }


def prediction_calibration(chain) -> dict:
    pairs = []
    for c in chain:
        pred = c.get("predicted_retention_score")
        obs = _observed_watch(c.get("observed") or [])
        if isinstance(pred, (int, float)) and isinstance(obs, (int, float)):
            pairs.append((pred, obs))
    if not pairs:
        return {"calibration_pairs": 0, "mae": None, "mean_pred": None, "mean_obs": None}
    errs = [abs(p - o) for p, o in pairs]
    return {
        "calibration_pairs": len(pairs),
        "mae": round(sum(errs) / len(errs), 1),
        "mean_pred": round(sum(p for p, _ in pairs) / len(pairs), 1),
        "mean_obs": round(sum(o for _, o in pairs) / len(pairs), 1),
        "note": "predicted retention_score vs observed avg_watch_pct (both 0..100)",
    }


def niche_distribution(records, chain) -> dict:
    counts = Counter(r.get("product_niche") for r in records)
    # canonical hygiene: distinct spellings that share a token set (DQ-10)
    by_tokens = defaultdict(set)
    for niche in counts:
        if niche:
            by_tokens[_tokens(niche)].add(niche)
    dup_groups = [sorted(v) for v in by_tokens.values() if len(v) > 1]

    # hit/flop per niche among observed (needs enough samples for percentiles)
    obs_by_niche = defaultdict(list)
    for c in chain:
        w = _observed_watch(c.get("observed") or [])
        if isinstance(w, (int, float)):
            obs_by_niche[c["product_niche"]].append(w)
    hitflop = {}
    minp = THRESHOLDS["min_observed_for_percentiles"]
    for niche, vals in obs_by_niche.items():
        sv = sorted(vals)
        if len(sv) < minp:
            hitflop[niche] = {"n": len(sv), "eligible": False,
                              "reason": f"need >= {minp} observed for percentiles"}
            continue
        p25, p75 = _percentile(sv, 0.25), _percentile(sv, 0.75)
        if p25 == p75:
            # F2: zero spread -> a single value can't be both hit and flop; not learnable yet
            hitflop[niche] = {"n": len(sv), "p25": round(p25, 1), "p75": round(p75, 1),
                              "hits": 0, "flops": 0, "eligible": False,
                              "reason": "insufficient_variance"}
            continue
        hits = sum(1 for v in sv if v >= p75)
        flops = sum(1 for v in sv if v <= p25)
        hitflop[niche] = {"n": len(sv), "p25": round(p25, 1), "p75": round(p75, 1),
                          "hits": hits, "flops": flops, "eligible": True}
    return {
        "records_per_niche": dict(counts),
        "canonical_violations": dup_groups,    # should be [] — same niche spelled differently
        "hit_flop_per_niche": hitflop,
    }


def telemetry_health(records, telemetry_rows) -> dict:
    valid = [r for r in telemetry_rows if not validate_telemetry(r)]
    platforms = Counter(r.get("platform") for r in telemetry_rows)
    run_ids_in_records = {(r.get("provenance") or {}).get("loop_run_id")
                          for r in records if (r.get("provenance") or {}).get("loop_run_id")}
    orphan = sorted({r.get("loop_run_id") for r in telemetry_rows
                     if r.get("loop_run_id") not in run_ids_in_records})
    keys = [(r.get("loop_run_id"), r.get("platform"), r.get("collected_at")) for r in telemetry_rows]
    dup = [k for k, n in Counter(keys).items() if n > 1]
    snaps = Counter(r.get("loop_run_id") for r in telemetry_rows)
    return {
        "total_rows": len(telemetry_rows),
        "valid_pct": _pct(len(valid), len(telemetry_rows)) if telemetry_rows else None,
        "by_platform": dict(platforms),
        "orphan_loop_run_ids": orphan,         # telemetry that joins to no record
        "duplicate_keys": dup,                 # should be [] (writer dedupes)
        "max_snapshots_per_run": max(snaps.values()) if snaps else 0,
    }


def dataset_growth(records, telemetry_rows) -> dict:
    def by_day(items, field):
        c = Counter()
        for it in items:
            ts = str(it.get(field, ""))[:10]
            if ts:
                c[ts] += 1
        return dict(sorted(c.items()))
    return {
        "records_by_day": by_day(records, "created_at"),
        "telemetry_by_day": by_day(telemetry_rows, "collected_at"),
        "total_records": len(records),
        "total_telemetry_rows": len(telemetry_rows),
    }


def _derive_coverage_state(cov) -> str:
    """The coverage tri-state. Prefer the field set by coverage_metrics; fall back to
    deriving it from raw counts so legacy callers (that pass only coverage_pct_raw)
    still get correct behavior. Absence of evidence -> UNKNOWN (never PASS)."""
    st = cov.get("coverage_state")
    if st in COVERAGE_STATES:
        return st
    raw = cov.get("coverage_pct_raw")
    if raw is None:                                  # no rendered events to evaluate
        return COVERAGE_UNKNOWN
    return COVERAGE_PASS if (raw >= THRESHOLDS["coverage_pct"]
                            and not cov.get("orphan_rendered")) else COVERAGE_FAIL


def readiness(cov, prov, hooks, fill, niche, dq_pass_pct_raw) -> dict:
    # F3: gate logic compares against RAW (unrounded) percentages so a value like
    # 99.95% can never round up to 100% and slip through a strict gate.
    T = THRESHOLDS
    gates = {}

    # F6: tri-state coverage. coverage_100 stays a bool for backward compatibility and
    # is True ONLY on a real PASS (UNKNOWN and FAIL both -> False).
    coverage_state = _derive_coverage_state(cov)
    gates["coverage_100"] = coverage_state == COVERAGE_PASS

    gates["provenance_ok"] = (prov.get("with_provenance_pct_raw") or 0) >= T["provenance_pct"]
    gates["hooks_recorded"] = (hooks.get("recorded_pct_raw") or 0) >= T["hooks_recorded_pct"]
    gates["ground_truth_fill"] = (fill.get("fill_rate_pct_raw") or 0) >= T["ground_truth_fill_pct"]
    gates["dq_pass"] = (dq_pass_pct_raw or 0) >= T["dq_pass_pct"]
    gates["niche_hygiene"] = not niche["canonical_violations"]

    # a niche reaching M2: >= min records, with hits & flops
    m2_niche = None
    for nm, hf in niche["hit_flop_per_niche"].items():
        recs = niche["records_per_niche"].get(nm, 0)
        if (hf.get("eligible")                       # F2: must have real variance
                and recs >= T["min_records_per_niche"]
                and hf.get("hits", 0) >= T["min_hits_per_niche"]
                and hf.get("flops", 0) >= T["min_flops_per_niche"]):
            m2_niche = nm
            break
    gates["niche_at_M2"] = m2_niche is not None

    # F6: three-way verdict.
    #   - any CONCRETE failure (coverage FAIL, or any other gate False) -> "fail"
    #   - else if coverage is merely UNKNOWN (missing evidence) -> "blocked"
    #   - else everything passed -> "ready"
    other_gates_pass = all(v for k, v in gates.items() if k != "coverage_100")
    if coverage_state == COVERAGE_PASS and other_gates_pass:
        status = "ready"
    elif coverage_state == COVERAGE_UNKNOWN and other_gates_pass:
        status = "blocked"                           # absence of evidence != pass and != fail
    else:
        status = "fail"

    ready = status == "ready"
    blockers = [g for g, ok in gates.items() if not ok]
    return {"ready": ready, "status": status, "coverage_state": coverage_state,
            "gates": gates, "m2_niche": m2_niche, "blockers": blockers}


# ----------------------------------------------------------------------------
# Report assembly
# ----------------------------------------------------------------------------
def build_report(db=None, telemetry=None, events=None, lib_path=None) -> dict:
    records = load_db(db)
    telemetry_rows = _tele.load_telemetry(telemetry)
    ev = load_events(events)
    db_path = Path(db) if db else DB_DEFAULT
    tel_path = _tele.resolve_path(telemetry)
    chain = _tele.join_causal_chain(db_path=db_path, telemetry_path=tel_path)

    cov = coverage_metrics(records, ev)
    prov = provenance_quality(records)
    hooks = hook_adoption_metrics(records)
    fill = ground_truth_fill(chain)
    calib = prediction_calibration(chain)
    niche = niche_distribution(records, chain)
    tel = telemetry_health(records, telemetry_rows)
    growth = dataset_growth(records, telemetry_rows)

    # overall DQ pass-rate: records valid + provenance valid + telemetry valid
    rec_bad = sum(1 for r in records if validate_record(r))
    prov_bad = sum(1 for r in records
                   if isinstance(r.get("provenance"), dict) and validate_provenance(r["provenance"]))
    tel_bad = sum(1 for r in telemetry_rows if validate_telemetry(r))
    checked = len(records) + sum(1 for r in records if isinstance(r.get("provenance"), dict)) \
        + len(telemetry_rows)
    dq_pass_pct = _pct(checked - (rec_bad + prov_bad + tel_bad), checked)
    dq_pass_pct_raw = _ratio(checked - (rec_bad + prov_bad + tel_bad), checked)

    rdy = readiness(cov, prov, hooks, fill, niche, dq_pass_pct_raw)

    return {
        "sources": {"db": str(db_path), "telemetry": str(tel_path),
                    "anchor_lib": str(_anchor.resolve_lib_path(lib_path)),
                    "events_found": bool(ev)},
        "coverage": cov, "provenance_quality": prov, "hook_adoption": hooks,
        "ground_truth_fill": fill, "prediction_calibration": calib,
        "niche_distribution": niche, "telemetry_health": tel, "dataset_growth": growth,
        "dq_pass_pct": dq_pass_pct, "readiness": rdy, "thresholds": THRESHOLDS,
    }


def _events_path(events=None) -> Path:
    """The events log path actually in effect: explicit > $SCOS_EVENTS > default."""
    if events:
        return Path(events)
    if os.environ.get(_eb.ENV_EVENTS):
        return Path(os.environ[_eb.ENV_EVENTS])
    return _eb.DEFAULT_LOG


def _protected_paths(db=None, telemetry=None, events=None, lib_path=None) -> set:
    """Every input/data file the report reads, resolved to absolute paths. --json-out
    must never collide with any of these (F1: read-only contract)."""
    paths = [
        Path(db) if db else DB_DEFAULT,         # database (custom OR default)
        _tele.resolve_path(telemetry),          # telemetry (honors --telemetry/$SCOS_TELEMETRY)
        _events_path(events),                   # event log (honors --events/$SCOS_EVENTS)
        _anchor.resolve_lib_path(lib_path),     # anchor library (honors --lib-path/$SCOS_ANCHOR_LIB)
    ]
    out = set()
    for p in paths:
        try:
            out.add(p.resolve())
        except Exception:
            out.add(Path(os.path.abspath(str(p))))
    return out


def _is_protected_path(out_path: Path, db=None, telemetry=None,
                       events=None, lib_path=None) -> bool:
    try:
        target = out_path.resolve()
    except Exception:
        target = Path(os.path.abspath(str(out_path)))
    return target in _protected_paths(db=db, telemetry=telemetry,
                                      events=events, lib_path=lib_path)


def _flag(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_text(rep: dict) -> str:
    L = []
    cov, prov, hk = rep["coverage"], rep["provenance_quality"], rep["hook_adoption"]
    fill, calib, niche = rep["ground_truth_fill"], rep["prediction_calibration"], rep["niche_distribution"]
    tel, rdy = rep["telemetry_health"], rep["readiness"]
    T = rep["thresholds"]

    L.append("=" * 64)
    L.append(" SUPER CREATOR OS — DATA QUALITY REPORT (read-only)")
    L.append("=" * 64)
    L.append(f"sources: db={rep['sources']['db']}")
    L.append(f"         telemetry={rep['sources']['telemetry']}")
    L.append(f"         events_found={rep['sources']['events_found']}")
    L.append("")
    verdict = {"ready": "READY ✅", "fail": "NOT READY ⛔",
               "blocked": "BLOCKED ⚠ (missing evidence)"}.get(rdy.get("status"),
               "READY ✅" if rdy["ready"] else "NOT READY ⛔")
    L.append(f"VIDEO ANALYST READINESS: {verdict}")
    L.append(f"  coverage_state: {rdy.get('coverage_state')}")
    if rdy["blockers"]:
        L.append(f"  blockers: {', '.join(rdy['blockers'])}")
    if rdy["m2_niche"]:
        L.append(f"  niche at M2: {rdy['m2_niche']}")
    L.append("")

    L.append("-- 1. Coverage ----------------------------------------------")
    L.append(f"  records={cov['total_records']}  rendered={cov['events_rendered']}  "
             f"complete={cov['events_complete']}  qa_failed={cov['events_qa_failed']}")
    L.append(f"  coverage_state={cov.get('coverage_state')}  reason={cov.get('coverage_reason')}")
    L.append(f"  coverage_pct={cov['coverage_pct']} (display)  coverage_raw={cov.get('coverage_raw')}  "
             f"orphan_rendered={cov['orphan_rendered']}")
    if cov.get("note"):
        L.append(f"  ({cov['note']})")

    L.append("-- 2. Provenance Quality ------------------------------------")
    L.append(f"  with_provenance={prov['with_provenance']}/{prov['records']} "
             f"({prov['with_provenance_pct']}%)  valid={prov['provenance_valid_pct']}%  "
             f"rec_id={prov['with_recommendation_id_pct']}%")
    L.append(f"  match_quality={prov['match_quality_distribution']}")

    L.append("-- 3. Hook Adoption -----------------------------------------")
    L.append(f"  {hk['adoption_distribution']}")
    L.append(f"  adoption_rate={hk['adoption_rate_pct']}%  rejected={hk['rejected_rate_pct']}%  "
             f"recorded={hk['recorded_pct']}%  unrecorded={hk['unrecorded']}")

    L.append("-- 4. Ground Truth Fill -------------------------------------")
    L.append(f"  joinable={fill['joinable_records']}  with_observed={fill['with_observed']}  "
             f"fill_rate={fill['fill_rate_pct']}% (target >= {T['ground_truth_fill_pct']}%)")
    for nm, v in fill["per_niche"].items():
        L.append(f"    {nm}: {v['with_observed']}/{v['records']} ({v['fill_pct']}%)")

    L.append("-- 5. Prediction Calibration --------------------------------")
    L.append(f"  pairs={calib['calibration_pairs']}  MAE={calib['mae']} "
             f"(target <= {T['max_prediction_mae']})  mean_pred={calib['mean_pred']}  "
             f"mean_obs={calib['mean_obs']}")

    L.append("-- 6. Niche Distribution ------------------------------------")
    L.append(f"  records_per_niche={niche['records_per_niche']}")
    if niche["canonical_violations"]:
        L.append(f"  ⚠ canonical_violations={niche['canonical_violations']}")
    for nm, hf in niche["hit_flop_per_niche"].items():
        L.append(f"    {nm}: {hf}")

    L.append("-- 7. Telemetry Health --------------------------------------")
    L.append(f"  rows={tel['total_rows']}  valid={tel['valid_pct']}%  by_platform={tel['by_platform']}")
    L.append(f"  orphan_loop_run_ids={tel['orphan_loop_run_ids']}  duplicate_keys={tel['duplicate_keys']}")

    L.append("-- 8. Dataset Growth ----------------------------------------")
    L.append(f"  records_by_day={rep['dataset_growth']['records_by_day']}")
    L.append(f"  telemetry_by_day={rep['dataset_growth']['telemetry_by_day']}")

    L.append("-- 9. Readiness Gates ---------------------------------------")
    for g, ok in rdy["gates"].items():
        L.append(f"  [{_flag(ok)}] {g}")
    L.append(f"  overall DQ pass-rate = {rep['dq_pass_pct']}% (target >= {T['dq_pass_pct']}%)")
    L.append("=" * 64)
    return "\n".join(L)


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Read-only Data Quality Report")
    ap.add_argument("--db", default=None)
    ap.add_argument("--telemetry", default=None, help="else $SCOS_TELEMETRY / default")
    ap.add_argument("--events", default=None, help="else $SCOS_EVENTS / default")
    ap.add_argument("--lib-path", default=None, help="else $SCOS_ANCHOR_LIB / default")
    ap.add_argument("--json-out", default=None,
                    help="optional: write the computed report to THIS path (a derived "
                         "artifact, never a data file)")
    ap.add_argument("--quiet", action="store_true", help="suppress text report (JSON only)")
    a = ap.parse_args()

    rep = build_report(db=a.db, telemetry=a.telemetry, events=a.events, lib_path=a.lib_path)
    if not a.quiet:
        print(render_text(rep))
    if a.json_out:
        out = Path(a.json_out)
        if _is_protected_path(out, db=a.db, telemetry=a.telemetry,
                              events=a.events, lib_path=a.lib_path):
            print("REFUSED: --json-out must not target a data/input file.", file=sys.stderr)
            return 2
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[report written] {out}")
    # F6 exit-code policy for CI gating:
    #   0 = READY · 1 = FAIL (concrete problem) · 3 = UNKNOWN/BLOCKED (missing evidence)
    return {"ready": 0, "fail": 1, "blocked": 3}.get(rep["readiness"].get("status"),
                                                     0 if rep["readiness"]["ready"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
