"""test_youtube_adapter.py — SCOS Stage 3.1 adapter framework tests.

Deterministic, stdlib only. Writes temp CSV fixtures and validates loading,
validation errors, normalization, unknown-column tolerance, and reproducibility.

Run: python scos/analytics/adapters/tests/test_youtube_adapter.py
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))     # adapters dir (sibling modules)

from analytics_models import NormalizedAnalytics          # noqa: E402
from base_adapter import AnalyticsValidationError, BaseAnalyticsAdapter  # noqa: E402
from youtube_adapter import YouTubeAnalyticsAdapter, parse_duration       # noqa: E402

_PASS, _FAIL = 0, 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print(f"  PASS  {name}")
    else:
        _FAIL += 1; print(f"  FAIL  {name}")


_HEADER = ["Video ID", "Video title", "Video publish time", "Views", "Watch time (hours)",
           "Average view duration", "Average percentage viewed (%)",
           "Impressions click-through rate (%)", "Likes", "Comments added", "Shares",
           "Subscribers", "Duration", "Impressions"]


def _row(vid="vid1", publish="2026-06-01", views="1000", watch="5.5", avd="0:32",
         retpct="45.0", ctr="4.5", likes="120", comments="15", shares="8",
         subs="10", duration="1:10", title="My Video", impressions="20000"):
    return [vid, title, publish, views, watch, avd, retpct, ctr, likes, comments,
            shares, subs, duration, impressions]


def _write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def _adapter(path):
    a = YouTubeAnalyticsAdapter()
    a.load(path)
    return a


def test_valid(tmp):
    print("\n[1] valid CSV normalizes correctly")
    p = Path(tmp) / "valid.csv"
    _write_csv(p, _HEADER, [_row(vid="A"), _row(vid="B", views="2,000", duration="1:05:00")])
    a = _adapter(p)
    check("validate() returns no errors", a.validate() == [])
    out = a.normalize()
    check("returns List[NormalizedAnalytics]", isinstance(out, list)
          and all(isinstance(x, NormalizedAnalytics) for x in out))
    check("two records", len(out) == 2)
    r0 = out[0]
    check("platform tag", r0.platform == "youtube")
    check("watch hours->seconds", r0.watch_time_seconds == 5.5 * 3600)
    check("avd '0:32'->32s", r0.average_view_duration == 32.0)
    check("retention pct->fraction", abs(r0.retention_rate - 0.45) < 1e-9)
    check("ctr pct->fraction", abs(r0.ctr - 0.045) < 1e-9)
    check("comma int parsed", out[1].views == 2000)
    check("duration '1:05:00'->3900s", out[1].duration_seconds == 3900.0)
    check("publish iso", r0.publish_time == "2026-06-01")


def test_missing_columns(tmp):
    print("\n[2] missing required column -> error + normalize raises")
    p = Path(tmp) / "missing.csv"
    hdr = [c for c in _HEADER if c != "Views"]
    _write_csv(p, hdr, [[v for c, v in zip(_HEADER, _row()) if c != "Views"]])
    a = _adapter(p)
    errs = a.validate()
    check("reports missing Views", any("missing required column: Views" in e for e in errs))
    raised = False
    try:
        a.normalize()
    except AnalyticsValidationError as e:
        raised = "Views" in "; ".join(e.errors)
    check("normalize raises AnalyticsValidationError", raised)


def test_duplicate_ids(tmp):
    print("\n[3] duplicate video ids detected")
    p = Path(tmp) / "dup.csv"
    _write_csv(p, _HEADER, [_row(vid="DUP"), _row(vid="DUP")])
    errs = _adapter(p).validate()
    check("duplicate id error", any("duplicate video id: 'DUP'" in e for e in errs))


def test_invalid_metrics(tmp):
    print("\n[4] negative + non-numeric metrics rejected (never auto-fixed)")
    p = Path(tmp) / "bad.csv"
    _write_csv(p, _HEADER, [_row(vid="N", views="-5"), _row(vid="X", likes="abc")])
    errs = _adapter(p).validate()
    check("negative metric flagged", any("negative metric in Views" in e for e in errs))
    check("invalid numeric flagged", any("invalid numeric in Likes" in e for e in errs))


def test_invalid_timestamp(tmp):
    print("\n[5] invalid timestamp rejected")
    p = Path(tmp) / "ts.csv"
    _write_csv(p, _HEADER, [_row(vid="T", publish="not-a-date")])
    errs = _adapter(p).validate()
    check("timestamp error", any("invalid timestamp" in e for e in errs))


def test_empty(tmp):
    print("\n[6] empty CSV rejected")
    p = Path(tmp) / "empty.csv"
    _write_csv(p, _HEADER, [])
    errs = _adapter(p).validate()
    check("empty CSV error", errs == ["empty CSV: no data rows"])


def test_unknown_columns_ignored(tmp):
    print("\n[7] unknown columns ignored")
    p = Path(tmp) / "extra.csv"
    hdr = _HEADER + ["Some Future Metric", "Weird Column"]
    _write_csv(p, hdr, [_row() + ["999", "xyz"]])
    a = _adapter(p)
    check("validates despite extras", a.validate() == [])
    out = a.normalize()
    check("normalized ignoring extras", len(out) == 1 and out[0].metadata == {})


def test_determinism(tmp):
    print("\n[8] deterministic normalization across runs")
    p = Path(tmp) / "det.csv"
    _write_csv(p, _HEADER, [_row(vid="A"), _row(vid="B"), _row(vid="C")])
    out1 = [r.to_dict() for r in _adapter(p).normalize()]
    out2 = [r.to_dict() for r in _adapter(p).normalize()]
    check("identical normalized output", out1 == out2)


def test_framework_extensibility():
    print("\n[9] framework — base is abstract, youtube inherits it")
    check("YouTube inherits BaseAnalyticsAdapter",
          issubclass(YouTubeAnalyticsAdapter, BaseAnalyticsAdapter))
    check("adapter_name", YouTubeAnalyticsAdapter().adapter_name() == "youtube")
    check("base cannot be instantiated", _abstract(BaseAnalyticsAdapter))
    check("duration parser pure", parse_duration("2:00") == 120.0)


def _abstract(cls):
    try:
        cls()
        return False
    except TypeError:
        return True


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    print("=" * 60); print(" STAGE 3.1 — ANALYTICS ADAPTER FRAMEWORK — TEST SUITE"); print("=" * 60)
    with tempfile.TemporaryDirectory() as tmp:
        test_valid(tmp); test_missing_columns(tmp); test_duplicate_ids(tmp)
        test_invalid_metrics(tmp); test_invalid_timestamp(tmp); test_empty(tmp)
        test_unknown_columns_ignored(tmp); test_determinism(tmp)
    test_framework_extensibility()
    print("\n" + "=" * 60); print(f" RESULT: {_PASS} passed, {_FAIL} failed"); print("=" * 60)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
