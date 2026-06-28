"""SCOS Stage 3.1 — YouTube analytics adapter (reference implementation).

Converts a YouTube Studio CSV export into canonical `NormalizedAnalytics`. Adapter
only: no learning, no scoring, no persistence. Unknown columns are ignored; malformed
data is reported by validate() and refused by normalize() (never auto-fixed).

This is the template every future platform adapter follows — subclass
`BaseAnalyticsAdapter`, declare the schema, implement field validation + build.
"""

from __future__ import annotations

from datetime import datetime

from analytics_models import NormalizedAnalytics
from base_adapter import BaseAnalyticsAdapter

# Canonical YouTube Studio column headers this adapter understands.
COL_ID = "Video ID"
COL_PUBLISH = "Video publish time"
COL_VIEWS = "Views"
COL_WATCH_HOURS = "Watch time (hours)"
COL_AVD = "Average view duration"
COL_RETENTION_PCT = "Average percentage viewed (%)"
COL_CTR_PCT = "Impressions click-through rate (%)"
COL_LIKES = "Likes"
COL_COMMENTS = "Comments added"
COL_SHARES = "Shares"
COL_SUBS = "Subscribers"
COL_DURATION = "Duration"

_REQUIRED = (COL_ID, COL_PUBLISH, COL_VIEWS, COL_WATCH_HOURS, COL_AVD, COL_RETENTION_PCT,
             COL_CTR_PCT, COL_LIKES, COL_COMMENTS, COL_SHARES, COL_SUBS, COL_DURATION)

_INT_FIELDS = [COL_VIEWS, COL_LIKES, COL_COMMENTS, COL_SHARES, COL_SUBS]
_FLOAT_FIELDS = [COL_WATCH_HOURS]
_DURATION_FIELDS = [COL_AVD, COL_DURATION]
_PCT_FIELDS = [COL_RETENTION_PCT, COL_CTR_PCT]

_TS_FORMATS = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%b %d, %Y"]
_TS_DATE_ONLY = {"%Y-%m-%d", "%b %d, %Y"}


# ---- pure parsers (raise ValueError on bad input) ------------------------- #
def parse_duration(value: str) -> float:
    """'h:mm:ss' | 'm:ss' | plain seconds -> float seconds."""
    v = (value or "").strip()
    if v == "":
        raise ValueError("empty duration")
    if ":" not in v:
        return float(v)
    parts = v.split(":")
    if not all(p.strip() != "" for p in parts):
        raise ValueError(f"bad duration {value!r}")
    seconds = 0.0
    for p in parts:
        seconds = seconds * 60.0 + float(p)
    return seconds


def parse_pct(value: str) -> float:
    """Percentage string -> fraction in 0..1 space (e.g. '4.5' -> 0.045)."""
    return float((value or "").strip()) / 100.0


def parse_timestamp(value: str) -> str:
    """Parse a publish time into a canonical ISO string. Raises on failure."""
    v = (value or "").strip()
    for fmt in _TS_FORMATS:
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        return dt.date().isoformat() if fmt in _TS_DATE_ONLY else dt.isoformat()
    raise ValueError(f"unparseable timestamp {value!r}")


class YouTubeAnalyticsAdapter(BaseAnalyticsAdapter):
    """Normalizes YouTube Studio CSV exports."""

    def adapter_name(self) -> str:
        return "youtube"

    def required_columns(self) -> tuple[str, ...]:
        return _REQUIRED

    def id_column(self) -> str:
        return COL_ID

    # ---- field-level validation (deterministic, row order) ---------------- #
    def _validate_rows(self, rows: list[dict]) -> list[str]:
        errors: list[str] = []
        for i, row in enumerate(rows, start=1):
            vid = (row.get(COL_ID) or "").strip()
            if vid == "":
                errors.append(f"row {i}: empty {COL_ID}")

            for col in _INT_FIELDS:
                errors += self._num_error(row, col, i, integer=True)
            for col in _FLOAT_FIELDS:
                errors += self._num_error(row, col, i, integer=False)
            for col in _DURATION_FIELDS:
                errors += self._dur_error(row, col, i)
            for col in _PCT_FIELDS:
                errors += self._pct_error(row, col, i)

            try:
                parse_timestamp(row.get(COL_PUBLISH, ""))
            except ValueError:
                errors.append(f"row {i}: invalid timestamp in {COL_PUBLISH}: "
                              f"{row.get(COL_PUBLISH, '')!r}")
        return errors

    @staticmethod
    def _num_error(row, col, i, integer):
        raw = row.get(col, "")
        try:
            val = (BaseAnalyticsAdapter.to_int if integer else BaseAnalyticsAdapter.to_float)(raw)
        except (ValueError, TypeError):
            return [f"row {i}: invalid numeric in {col}: {raw!r}"]
        return [f"row {i}: negative metric in {col}: {val}"] if val < 0 else []

    @staticmethod
    def _dur_error(row, col, i):
        raw = row.get(col, "")
        try:
            val = parse_duration(raw)
        except (ValueError, TypeError):
            return [f"row {i}: invalid numeric in {col}: {raw!r}"]
        return [f"row {i}: negative metric in {col}: {val}"] if val < 0 else []

    @staticmethod
    def _pct_error(row, col, i):
        raw = row.get(col, "")
        try:
            val = parse_pct(raw)
        except (ValueError, TypeError):
            return [f"row {i}: invalid numeric in {col}: {raw!r}"]
        return [f"row {i}: negative metric in {col}: {val}"] if val < 0 else []

    # ---- build (rows already validated) ----------------------------------- #
    def _build(self, rows: list[dict]) -> list[NormalizedAnalytics]:
        out: list[NormalizedAnalytics] = []
        for row in rows:
            out.append(NormalizedAnalytics(
                video_id=(row[COL_ID]).strip(),
                platform=self.adapter_name(),
                publish_time=parse_timestamp(row[COL_PUBLISH]),
                views=self.to_int(row[COL_VIEWS]),
                watch_time_seconds=self.to_float(row[COL_WATCH_HOURS]) * 3600.0,
                average_view_duration=parse_duration(row[COL_AVD]),
                retention_rate=parse_pct(row[COL_RETENTION_PCT]),
                ctr=parse_pct(row[COL_CTR_PCT]),
                likes=self.to_int(row[COL_LIKES]),
                comments=self.to_int(row[COL_COMMENTS]),
                shares=self.to_int(row[COL_SHARES]),
                subscribers_gained=self.to_int(row[COL_SUBS]),
                duration_seconds=parse_duration(row[COL_DURATION]),
                metadata={},
            ))
        return out
