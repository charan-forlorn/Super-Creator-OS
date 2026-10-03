"""Observed YouTube Analytics provider adapter.

Uses the official YouTube Analytics reports API with an OAuth bearer token.
No credentials are stored in telemetry evidence, and no values are inferred.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from observation_binding import ObservationBinding, ObservationBindingError, load_render_binding

YOUTUBE_ANALYTICS_ENDPOINT = "https://youtubeanalytics.googleapis.com/v2/reports"
DEFAULT_METRICS = (
    "views", "engagedViews", "averageViewDuration", "averageViewPercentage",
    "likes", "comments", "shares", "subscribersGained",
)


class YouTubeAnalyticsError(RuntimeError):
    """Raised when an observed YouTube report cannot be retrieved or normalized."""


@dataclass(frozen=True)
class YouTubeQuery:
    start_date: str
    end_date: str
    video_id: str
    metrics: tuple[str, ...] = DEFAULT_METRICS

    def params(self) -> dict[str, str]:
        return {
            "ids": "channel==MINE",
            "startDate": self.start_date,
            "endDate": self.end_date,
            "metrics": ",".join(self.metrics),
            "filters": f"video=={self.video_id}",
        }

    def canonical_query_sha256(self) -> str:
        encoded = urllib.parse.urlencode(sorted(self.params().items()))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


HttpGet = Callable[[str, dict[str, str], float], bytes]


def _http_get(url: str, headers: dict[str, str], timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise YouTubeAnalyticsError(f"YOUTUBE_HTTP_{exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise YouTubeAnalyticsError(f"YOUTUBE_NETWORK_ERROR: {exc.reason}") from exc


def _canonical_response_sha256(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _as_number(value: object) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise YouTubeAnalyticsError(f"NON_NUMERIC_METRIC_VALUE: {value!r}")
    number = float(value)
    return int(number) if number.is_integer() else number


def _validate_date(value: str, field: str) -> None:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise YouTubeAnalyticsError(f"{field}_INVALID: {value}") from exc


class YouTubeAnalyticsAdapter:
    provider = "youtube_analytics"
    platform = "youtube_shorts"

    def __init__(
        self,
        access_token: str,
        query: YouTubeQuery,
        *,
        timeout_s: float = 20.0,
        http_get: HttpGet = _http_get,
    ) -> None:
        if not access_token or not access_token.strip():
            raise YouTubeAnalyticsError("YOUTUBE_OAUTH_ACCESS_TOKEN_REQUIRED")
        _validate_date(query.start_date, "start_date")
        _validate_date(query.end_date, "end_date")
        if query.start_date > query.end_date:
            raise YouTubeAnalyticsError("DATE_RANGE_INVALID")
        if not query.video_id.strip():
            raise YouTubeAnalyticsError("VIDEO_ID_REQUIRED")
        self._access_token = access_token.strip()
        self._query = query
        self._timeout_s = timeout_s
        self._http_get = http_get

    def fetch(self, loop_run_id: str, platform: str) -> dict | None:
        if platform != self.platform:
            raise YouTubeAnalyticsError(f"UNSUPPORTED_PLATFORM: {platform}")
        if not loop_run_id:
            raise YouTubeAnalyticsError("LOOP_RUN_ID_REQUIRED")
        params = self._query.params()
        url = f"{YOUTUBE_ANALYTICS_ENDPOINT}?{urllib.parse.urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        body = self._http_get(url, headers, self._timeout_s)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise YouTubeAnalyticsError("YOUTUBE_RESPONSE_NOT_JSON") from exc
        if not isinstance(payload, dict):
            raise YouTubeAnalyticsError("YOUTUBE_RESPONSE_NOT_OBJECT")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise YouTubeAnalyticsError("NO_OBSERVED_ROWS_FOR_VIDEO")
        headers_raw = payload.get("columnHeaders")
        if not isinstance(headers_raw, list):
            raise YouTubeAnalyticsError("YOUTUBE_COLUMN_HEADERS_MISSING")
        names = [h.get("name") for h in headers_raw if isinstance(h, dict)]
        if len(names) != len(rows[0]):
            raise YouTubeAnalyticsError("YOUTUBE_COLUMN_ROW_WIDTH_MISMATCH")
        observed = dict(zip(names, rows[0], strict=True))
        collected_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        response_sha = _canonical_response_sha256(observed)
        return {
            "loop_run_id": loop_run_id,
            "project_name": "youtube-observation",
            "platform": self.platform,
            "collected_at": collected_at,
            "source": "api",
            "views": _as_number(observed["views"]) if "views" in observed else None,
            "avg_watch_time_s": _as_number(observed["averageViewDuration"]) if "averageViewDuration" in observed else None,
            "avg_watch_pct": _as_number(observed["averageViewPercentage"]) if "averageViewPercentage" in observed else None,
            "likes": _as_number(observed["likes"]) if "likes" in observed else None,
            "comments": _as_number(observed["comments"]) if "comments" in observed else None,
            "shares": _as_number(observed["shares"]) if "shares" in observed else None,
            "followers_gained": _as_number(observed["subscribersGained"]) if "subscribersGained" in observed else None,
            "observation_evidence": {
                "provider": self.provider,
                "platform_content_id": self._query.video_id,
                "query_sha256": self._query.canonical_query_sha256(),
                "response_sha256": response_sha,
                "start_date": self._query.start_date,
                "end_date": self._query.end_date,
                "metrics": list(self._query.metrics),
                "endpoint": YOUTUBE_ANALYTICS_ENDPOINT,
            },
        }


def capture_binding(
    adapter: YouTubeAnalyticsAdapter,
    binding: ObservationBinding,
    *,
    telemetry_path=None,
    db_path=None,
) -> dict:
    """Fetch one real report and bind it to a verified render artifact."""
    from telemetry_capture import capture

    raw = adapter.fetch(binding.loop_run_id, adapter.platform)
    if raw is None:
        return {"ok": False, "stage": "provider", "error": "NO_OBSERVED_ROW"}
    raw["project_name"] = binding.project_name
    raw["observation_evidence"].update({
        "graph_fingerprint": binding.graph_fingerprint,
        "artifact_sha256": binding.artifact_sha256,
    })
    return capture(raw, telemetry_path=telemetry_path, db_path=db_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture real YouTube Analytics telemetry")
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--telemetry", default=None)
    parser.add_argument("--db", default=None)
    parser.add_argument("--access-token-env", default="SCOS_YOUTUBE_ANALYTICS_ACCESS_TOKEN")
    args = parser.parse_args()

    token = os.environ.get(args.access_token_env)
    try:
        binding = load_render_binding(args.provenance, platform_content_id=args.video_id)
        adapter = YouTubeAnalyticsAdapter(
            token or "",
            YouTubeQuery(args.start_date, args.end_date, args.video_id),
        )
        result = capture_binding(adapter, binding, telemetry_path=args.telemetry, db_path=args.db)
    except (ObservationBindingError, YouTubeAnalyticsError) as exc:
        print(json.dumps({"ok": False, "stage": "binding_or_provider", "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
