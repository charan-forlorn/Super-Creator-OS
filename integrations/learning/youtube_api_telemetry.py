"""Read-only YouTube Analytics -> SCOS observed telemetry bridge.

No publish/dispatch, no secret storage, and no predicted metrics. OAuth material is
supplied by the caller/token provider and never written to disk by this module.
The adapter queries the YouTube Analytics v2 reports endpoint with video dimension
and maps measured metrics into the existing observed-only telemetry contract.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from integrations.learning.telemetry_capture import capture
from integrations.learning.youtube_oauth_runtime import refresh_access_token

API_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
REQUIRED_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YT_ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
DEFAULT_METRICS = (
    "views,comments,likes,shares,subscribersGained,"
    "averageViewDuration,averageViewPercentage"
)


@dataclass(frozen=True)
class YouTubeObservationTarget:
    video_id: str
    loop_run_id: str
    project_name: str


@dataclass(frozen=True)
class YouTubeAnalyticsRequest:
    channel_id: str
    start_date: str
    end_date: str
    video_ids: tuple[str, ...] = ()
    metrics: str = DEFAULT_METRICS


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_iso_date(value: str) -> str:
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value!r}") from exc
    return value


def _rows_from_report(payload: dict[str, Any]) -> list[dict[str, Any]]:
    headers = payload.get("columnHeaders")
    rows = payload.get("rows", [])
    if not isinstance(headers, list) or not all(isinstance(h, dict) and h.get("name") for h in headers):
        raise ValueError("YouTube response missing valid columnHeaders")
    if not isinstance(rows, list):
        raise ValueError("YouTube response rows must be a list")
    names = [str(h["name"]) for h in headers]
    out = []
    for raw in rows:
        if not isinstance(raw, list) or len(raw) != len(names):
            raise ValueError("YouTube response row shape does not match columnHeaders")
        out.append(dict(zip(names, raw)))
    return out
class YouTubeAnalyticsClient:
    """Read-only client; transport can be injected for deterministic tests."""

    def __init__(self, access_token: str | None = None, *, transport: Callable[..., bytes] | None = None) -> None:
        self._access_token = str(access_token or "").strip()
        self._transport = transport or self._default_transport

    @classmethod
    def from_secure_store(cls, store_path=None, *, transport: Callable[..., bytes] | None = None) -> "YouTubeAnalyticsClient":
        return cls(refresh_access_token(store_path), transport=transport)

    @staticmethod
    def _default_transport(request: Request, timeout: float) -> bytes:
        with urlopen(request, timeout=timeout) as response:
            return response.read()

    @property
    def authorized(self) -> bool:
        return bool(self._access_token)

    def query(self, request: YouTubeAnalyticsRequest, *, timeout: float = 30.0) -> dict[str, Any]:
        if not self.authorized:
            raise PermissionError("YOUTUBE_ANALYTICS_AUTH_REQUIRED")
        if not request.channel_id.strip():
            raise ValueError("channel_id is required")
        start = _validate_iso_date(request.start_date)
        end = _validate_iso_date(request.end_date)
        if start > end:
            raise ValueError("start_date must be <= end_date")
        params = {
            "ids": f"channel=={request.channel_id.strip()}",
            "startDate": start,
            "endDate": end,
            "dimensions": "video",
            "metrics": request.metrics,
            "sort": "-views",
        }
        if request.video_ids:
            ids = tuple(dict.fromkeys(v.strip() for v in request.video_ids if v.strip()))
            if not ids:
                raise ValueError("video_ids cannot contain only empty values")
            if len(ids) > 500:
                raise ValueError("YouTube Analytics API supports up to 500 video filter IDs per request")
            params["filters"] = "video==" + ",".join(ids)
        req = Request(
            API_URL + "?" + urlencode(params),
            headers={"Authorization": f"Bearer {self._access_token}", "Accept": "application/json"},
            method="GET",
        )
        payload = json.loads(self._transport(req, timeout).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("YouTube response root must be an object")
        if "error" in payload:
            raise RuntimeError(f"YouTube Analytics API error: {payload['error']}")
        return payload

    def query_rows(self, request: YouTubeAnalyticsRequest, *, timeout: float = 30.0) -> list[dict[str, Any]]:
        return _rows_from_report(self.query(request, timeout=timeout))


class YouTubeObservedTelemetryAdapter:
    """Converts measured YouTube rows into SCOS source='api' observations."""

    def __init__(self, client: YouTubeAnalyticsClient) -> None:
        self.client = client

    @staticmethod
    def _metric_float(row: dict[str, Any], name: str) -> float | None:
        value = row.get(name)
        return None if value in (None, "") else float(value)

    def build_observations(
        self,
        rows: list[dict[str, Any]],
        targets: tuple[YouTubeObservationTarget, ...],
        *,
        collected_at: str | None = None,
    ) -> list[dict[str, Any]]:
        by_video = {target.video_id: target for target in targets}
        observed_at = collected_at or _utc_now()
        observations: list[dict[str, Any]] = []
        for row in rows:
            video_id = str(row.get("video") or "").strip()
            target = by_video.get(video_id)
            if target is None:
                continue
            observations.append({
                "loop_run_id": target.loop_run_id,
                "project_name": target.project_name,
                "platform": "youtube_shorts",
                "collected_at": observed_at,
                "source": "api",
                "video_id": video_id,
                "views": self._metric_float(row, "views"),
                "avg_watch_pct": self._metric_float(row, "averageViewPercentage"),
                "avg_watch_time_s": self._metric_float(row, "averageViewDuration"),
                "likes": self._metric_float(row, "likes"),
                "comments": self._metric_float(row, "comments"),
                "shares": self._metric_float(row, "shares"),
                "followers_gained": self._metric_float(row, "subscribersGained"),
            })
        return observations

    def collect_and_capture(
        self,
        request: YouTubeAnalyticsRequest,
        targets: tuple[YouTubeObservationTarget, ...],
        *,
        telemetry_path=None,
        db_path=None,
        collected_at: str | None = None,
    ) -> dict[str, Any]:
        rows = self.client.query_rows(request)
        observations = self.build_observations(rows, targets, collected_at=collected_at)
        captures = [capture(item, telemetry_path=telemetry_path, db_path=db_path) for item in observations]
        return {
            "status": "OBSERVATIONS_CAPTURED" if observations and all(x.get("ok") for x in captures) else "BLOCKED",
            "source": "api",
            "platform": "youtube_shorts",
            "rows_received": len(rows),
            "observations_built": len(observations),
            "captures": captures,
            "authorization_scope": REQUIRED_SCOPE,
        }


__all__ = [
    "API_URL",
    "DEFAULT_METRICS",
    "REQUIRED_SCOPE",
    "YT_ANALYTICS_SCOPE",
    "YouTubeAnalyticsClient",
    "YouTubeAnalyticsRequest",
    "YouTubeObservationTarget",
    "YouTubeObservedTelemetryAdapter",
]
