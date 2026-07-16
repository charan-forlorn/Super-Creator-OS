"""Tests for SCOS Revenue Ops tracker (Part A). Stdlib-only, local, deterministic."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from scripts.revenue_ops import (
    STATES,
    add_job,
    render_dashboard,
    set_status,
    summarize,
    update_job,
)


def _store(tmp_path: Path) -> Path:
    return tmp_path / "jobs.jsonl"


def test_add_creates_append_only_records(tmp_path: Path):
    store = _store(tmp_path)
    r1 = add_job(store, "คุณ A", "RoV Short x3", 1500, due="2026-07-20")
    r2 = add_job(store, "คุณ B", "PetGlow Ad", 2500, status="paid")
    assert r1["job_id"] == "JOB-0001"
    assert r2["job_id"] == "JOB-0002"
    # append-only: both lines present
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert r2["paid_at"] is not None


def test_summary_computes_outstanding_and_paid(tmp_path: Path):
    store = _store(tmp_path)
    add_job(store, "A", "j1", 1000, status="editing")
    add_job(store, "B", "j2", 2000, status="paid")
    add_job(store, "C", "j3", 500, status="cancelled")
    s = summarize(store)
    assert s["paid_value"] == 2000.0
    assert s["outstanding_value"] == 1000.0
    # pipeline = ยังไม่จบ = หัก paid + cancelled (editing เหลือ 1000)
    assert s["pipeline_value"] == 1000.0
    assert s["jobs_total"] == 3


def test_overdue_and_due_soon(tmp_path: Path):
    today = date(2026, 7, 15)
    store = _store(tmp_path)
    add_job(store, "Late", "old", 1000, due="2026-07-10", status="review")
    add_job(store, "Soon", "near", 800, due="2026-07-17", status="editing")
    add_job(store, "Ok", "far", 500, due="2026-08-01", status="accepted")
    s = summarize(store, today=today)
    assert len(s["overdue"]) == 1
    assert s["overdue"][0]["client"] == "Late"
    assert s["overdue"][0]["_days"] == 5
    assert len(s["due_soon"]) == 1
    assert s["due_soon"][0]["client"] == "Soon"


def test_update_status_and_amount(tmp_path: Path):
    store = _store(tmp_path)
    r = add_job(store, "A", "j", 1000, status="accepted")
    updated = update_job(store, r["job_id"], status="done", amount=1200)
    assert updated["status"] == "done"
    assert updated["amount"] == 1200.0
    s = summarize(store)
    assert s["by_status"]["done"] == 1200.0


def test_set_status_to_paid_stamps_paid_at(tmp_path: Path):
    store = _store(tmp_path)
    r = add_job(store, "A", "j", 900, status="review")
    rec = set_status(store, r["job_id"], "paid")
    assert rec["status"] == "paid"
    assert rec["paid_at"] is not None
    s = summarize(store)
    assert s["paid_value"] == 900.0


def test_invalid_status_rejected(tmp_path: Path):
    store = _store(tmp_path)
    try:
        add_job(store, "A", "j", 100, status="bogus")
    except SystemExit:
        pass
    else:
        raise AssertionError("expected SystemExit for invalid status")
    assert not store.exists() or store.read_text(encoding="utf-8").strip() == ""


def test_dashboard_renders_html(tmp_path: Path):
    store = _store(tmp_path)
    add_job(store, "Late", "old", 1000, due="2026-07-10", status="review")
    out = tmp_path / "dash.html"
    render_dashboard(store, out, today=date(2026, 7, 15))
    html = out.read_text(encoding="utf-8")
    assert "<html" in html
    assert "overdue" in html.lower() or "Overdue" in html
    assert "Late" in html


def test_all_statuses_valid():
    assert "paid" in STATES
    assert "cancelled" in STATES


def test_malformed_store_fails_closed_and_preserves_bytes(tmp_path: Path):
    store = _store(tmp_path)
    store.write_text(
        json.dumps({"job_id": "JOB-0001", "amount": 100, "status": "accepted"}) + "\n"
        "{broken\n",
        encoding="utf-8",
    )
    before = store.read_bytes()

    try:
        summarize(store)
    except ValueError as exc:
        assert "line 2" in str(exc)
    else:
        raise AssertionError("malformed jobs store must fail closed")

    try:
        add_job(store, "A", "j", 100)
    except ValueError as exc:
        assert "line 2" in str(exc)
    else:
        raise AssertionError("append onto malformed jobs store must be rejected")
    assert store.read_bytes() == before


def test_update_rewrites_atomically_without_temp_debris(tmp_path: Path):
    store = _store(tmp_path)
    rec = add_job(store, "A", "j", 1000, status="accepted")

    updated = update_job(store, rec["job_id"], status="done", amount=1250)

    assert updated is not None
    assert updated["status"] == "done"
    assert updated["amount"] == 1250.0
    assert list(tmp_path.glob("*.tmp")) == []


def test_concurrent_adds_are_serialized_with_unique_ids(tmp_path: Path):
    store = _store(tmp_path)

    def add_one(index: int) -> str:
        return add_job(store, f"C{index}", f"j{index}", 100 + index)["job_id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(add_one, range(16)))

    assert sorted(ids) == [f"JOB-{i:04d}" for i in range(1, 17)]
    rows = [json.loads(line) for line in store.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 16
    assert sorted(row["job_id"] for row in rows) == sorted(ids)
