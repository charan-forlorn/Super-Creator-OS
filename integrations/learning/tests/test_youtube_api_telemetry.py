from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from integrations.learning.youtube_api_telemetry import (
    API_URL,
    YouTubeAnalyticsClient,
    YouTubeAnalyticsRequest,
    YouTubeObservationTarget,
    YouTubeObservedTelemetryAdapter,
)


def _transport(payload):
    seen = {}
    def send(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.headers.get("Authorization")
        seen["timeout"] = timeout
        return json.dumps(payload).encode("utf-8")
    return send, seen


def _payload():
    return {
        "columnHeaders": [
            {"name": "video"}, {"name": "views"}, {"name": "comments"},
            {"name": "likes"}, {"name": "shares"}, {"name": "subscribersGained"},
            {"name": "averageViewDuration"}, {"name": "averageViewPercentage"},
        ],
        "rows": [["vid-1", 1200, 14, 85, 7, 11, 18.5, 42.25]],
    }


def test_requires_auth():
    client = YouTubeAnalyticsClient(transport=lambda request, timeout: b"{}")
    try:
        client.query(YouTubeAnalyticsRequest("UC123", "2026-09-01", "2026-09-21"))
    except PermissionError as exc:
        assert str(exc) == "YOUTUBE_ANALYTICS_AUTH_REQUIRED"
    else:
        raise AssertionError("unauthorized client must fail closed")


def test_query_builds_authorized_video_request():
    transport, seen = _transport(_payload())
    client = YouTubeAnalyticsClient("token-123", transport=transport)
    request = YouTubeAnalyticsRequest(
        channel_id="UC123", start_date="2026-09-01", end_date="2026-09-21",
        video_ids=("vid-1", "vid-2"),
    )
    rows = client.query_rows(request, timeout=9.0)
    assert rows[0]["video"] == "vid-1"
    assert seen["auth"] == "Bearer token-123"
    assert seen["timeout"] == 9.0
    query = parse_qs(urlparse(seen["url"]).query)
    assert urlparse(seen["url"]).scheme + "://" + urlparse(seen["url"]).netloc + urlparse(seen["url"]).path == API_URL
    assert query["ids"] == ["channel==UC123"]
    assert query["dimensions"] == ["video"]
    assert query["filters"] == ["video==vid-1,vid-2"]
    assert "averageViewPercentage" in query["metrics"][0]


def test_builds_observed_only_rows_and_ignores_unknown_video():
    adapter = YouTubeObservedTelemetryAdapter(YouTubeAnalyticsClient("token", transport=lambda r, t: b"{}"))
    rows = _payload()["rows"] + [["unknown", 1, 1, 1, 1, 1, 1, 1]]
    observations = adapter.build_observations(
        [dict(zip([h["name"] for h in _payload()["columnHeaders"]], row)) for row in rows],
        (YouTubeObservationTarget("vid-1", "run-123", "Project A"),),
        collected_at="2026-09-21T01:00:00Z",
    )
    assert len(observations) == 1
    item = observations[0]
    assert item["source"] == "api"
    assert item["platform"] == "youtube_shorts"
    assert item["loop_run_id"] == "run-123"
    assert item["views"] == 1200.0
    assert item["avg_watch_pct"] == 42.25
    assert item["avg_watch_time_s"] == 18.5
    assert item["followers_gained"] == 11.0
    assert "retention_score" not in item


def test_collect_and_capture_uses_existing_observed_moat():
    transport, _ = _transport(_payload())
    adapter = YouTubeObservedTelemetryAdapter(YouTubeAnalyticsClient("token", transport=transport))
    target = YouTubeObservationTarget("vid-1", "run-xyz", "Project X")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "database.json"
        db.write_text("[]", encoding="utf-8")
        result = adapter.collect_and_capture(
            YouTubeAnalyticsRequest("UC123", "2026-09-01", "2026-09-21", ("vid-1",)),
            (target,),
            telemetry_path=root / "telemetry.json",
            db_path=db,
            collected_at="2026-09-21T01:00:00Z",
        )
        assert result["status"] == "BLOCKED"
        assert result["captures"][0]["ok"] is False
        assert result["captures"][0]["stage"] == "validate"
        assert "telemetry api rows require observation_evidence" in result["captures"][0]["errors"]
        assert not (root / "telemetry.json").exists()


def test_invalid_date_range_is_rejected_before_transport():
    called = []
    client = YouTubeAnalyticsClient("token", transport=lambda r, t: called.append(True) or b"{}")
    try:
        client.query(YouTubeAnalyticsRequest("UC123", "2026-09-22", "2026-09-21"))
    except ValueError as exc:
        assert "start_date must be <= end_date" in str(exc)
    else:
        raise AssertionError("invalid date range must fail")
    assert called == []


def test_more_than_500_video_ids_is_rejected():
    transport, _ = _transport(_payload())
    client = YouTubeAnalyticsClient("token", transport=transport)
    ids = tuple(f"v{i}" for i in range(501))
    try:
        client.query(YouTubeAnalyticsRequest("UC123", "2026-09-01", "2026-09-21", ids))
    except ValueError as exc:
        assert "500 video filter IDs" in str(exc)
    else:
        raise AssertionError(">500 filters must fail closed")



def test_api_export_snapshot_closes_through_causal_receipt():
    from integrations.learning.telemetry_receipt import build_telemetry_receipt
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = YouTubeObservedTelemetryAdapter(
            YouTubeAnalyticsClient("token", transport=lambda request, timeout: b"{}")
        )
        headers = [h["name"] for h in _payload()["columnHeaders"]]
        rows = [dict(zip(headers, _payload()["rows"][0]))]
        target = YouTubeObservationTarget("vid-1", "run-yt-1", "YouTube Demo")
        observations = adapter.build_observations(rows, (target,), collected_at="2026-09-21T01:00:00Z")
        export = root / "youtube_api.json"
        export.write_text(json.dumps(observations), encoding="utf-8")
        db = root / "database.json"
        db.write_text(json.dumps([{
            "project_name": "YouTube Demo", "product_niche": "test", "hook_successful": "x",
            "editing_specs": "x", "retention_score": 70, "lesson_learned": "x",
            "created_at": "2026-09-21T00:00:00Z", "provenance": {"loop_run_id": "run-yt-1"}
        }]), encoding="utf-8")
        telemetry = root / "telemetry.json"
        receipt = build_telemetry_receipt(export_path=export, db_path=db,
                                          telemetry_path=telemetry, receipt_path=root / "receipt.json",
                                          source="api")
        assert receipt["status"] == "BLOCKED"
        assert receipt["reason"] == "IMPORT_REJECTED"
        assert not telemetry.exists()
