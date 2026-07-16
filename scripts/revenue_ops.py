"""SCOS Revenue Ops — local-first jobs / client tracker (Part A).

A small, dependency-free (stdlib only) tracker that records paid video
jobs you take on, tracks their pipeline state, and computes revenue
summaries. Designed to make daily life easier without any external SaaS:

  - append-only JSONL store (never overwrites history)
  - no network, no cloud, no push
  - deterministic, testable functions + a tiny CLI
  - a self-contained HTML dashboard generator (no backend)

Run:
  .venv\\Scripts\\python.exe scripts\\revenue_ops.py --help
  .venv\\Scripts\\python.exe scripts\\revenue_ops.py add --client "คุณ A" \
      --title "RoV Short x3" --amount 1500 --due 2026-07-20
  .venv\\Scripts\\python.exe scripts\\revenue_ops.py summary
  .venv\\Scripts\\python.exe scripts\\revenue_ops.py dashboard --out revenue_dashboard.html
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# --- store location -------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = _ROOT / "memory" / "jobs.jsonl"
_LEARNING_ROOT = _ROOT / "integrations" / "learning"
if str(_LEARNING_ROOT) not in sys.path:
    sys.path.insert(0, str(_LEARNING_ROOT))

from _filelock import LockTimeout, atomic_replace, file_lock  # noqa: E402

# Pipeline states, in order. Keeps a single source of truth for valid transitions.
STATES = ["lead", "accepted", "editing", "review", "done", "paid", "cancelled"]
ACTIVE_STATES = ["accepted", "editing", "review", "done"]  # not yet paid
OPEN_STATES = ["lead", "accepted", "editing", "review", "done", "paid"]

_VALID_STATUS = set(STATES)


# --- helpers --------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_due(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    # accept YYYY-MM-DD; keep as-is otherwise
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        raise SystemExit(f"ERROR: --due ต้องอยู่ในรูป YYYY-MM-DD (ได้: {value!r})")


def _coerce_amount(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        raise SystemExit(f"ERROR: จำนวนเงินไม่ถูกต้อง: {value!r}")


def _load_all(store: Path) -> list[dict]:
    if not store.is_file():
        return []
    rows: list[dict] = []
    with store.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"jobs store malformed at line {lineno}") from None
            if not isinstance(payload, dict):
                raise ValueError(f"jobs store malformed at line {lineno}: row is not an object")
            rows.append(payload)
    return rows


def _append_locked(store: Path, record: dict) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _atomic_write_rows(store: Path, rows: list[dict]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    tmp = store.with_name(f"{store.name}.{os.getpid()}.{datetime.now().strftime('%H%M%S%f')}.tmp")
    tmp.write_text(body, encoding="utf-8")
    atomic_replace(tmp, store)


def _next_id(rows: list[dict]) -> str:
    max_n = 0
    for r in rows:
        jid = r.get("job_id", "")
        if jid.startswith("JOB-"):
            try:
                max_n = max(max_n, int(jid.split("-", 1)[1]))
            except ValueError:
                pass
    return f"JOB-{max_n + 1:04d}"


# --- core API -------------------------------------------------------------
def add_job(
    store: Path,
    client: str,
    title: str,
    amount: float,
    due: Optional[str] = None,
    status: str = "accepted",
    note: str = "",
) -> dict:
    if status not in _VALID_STATUS:
        raise SystemExit(f"ERROR: status ไม่รู้จัก: {status!r} (ใช้หนึ่งใน {STATES})")
    try:
        with file_lock(store):
            rows = _load_all(store)
            now = _now_iso()
            record = {
                "job_id": _next_id(rows),
                "client": client,
                "title": title,
                "amount": _coerce_amount(amount),
                "status": status,
                "due": _parse_due(due),
                "note": note,
                "created_at": now,
                "updated_at": now,
                "paid_at": now if status == "paid" else None,
            }
            _append_locked(store, record)
            return record
    except LockTimeout as exc:
        raise RuntimeError(f"jobs store lock busy: {exc}") from exc


def _update_job_locked(store: Path, job_id: str, **changes) -> Optional[dict]:
    rows = _load_all(store)
    target = None
    for row in rows:
        if row.get("job_id") == job_id:
            target = row
            break
    if target is None:
        return None
    allowed = {"client", "title", "amount", "status", "due", "note"}
    for key, val in changes.items():
        if key not in allowed or val is None:
            continue
        if key == "amount":
            val = _coerce_amount(val)
        if key == "status" and val not in _VALID_STATUS:
            raise SystemExit(f"ERROR: status invalid: {val!r}")
        if key == "due":
            val = _parse_due(val)
        target[key] = val
    if changes.get("status") == "paid" and not target.get("paid_at"):
        target["paid_at"] = _now_iso()
    target["updated_at"] = _now_iso()
    _atomic_write_rows(store, rows)
    return target


def update_job(store: Path, job_id: str, **changes) -> Optional[dict]:
    try:
        with file_lock(store):
            return _update_job_locked(store, job_id, **changes)
    except LockTimeout as exc:
        raise RuntimeError(f"jobs store lock busy: {exc}") from exc


def set_status(store: Path, job_id: str, status: str) -> Optional[dict]:
    return update_job(store, job_id, status=status)


def summarize(store: Path, today: Optional[date] = None) -> dict:
    today = today or date.today()
    rows = _load_all(store)
    total_pipeline = 0.0
    total_paid = 0.0
    outstanding = 0.0
    by_status: dict[str, float] = {s: 0.0 for s in STATES}
    overdue: list[dict] = []
    due_soon: list[dict] = []
    for r in rows:
        amt = float(r.get("amount", 0) or 0)
        st = r.get("status", "lead")
        by_status[st] = by_status.get(st, 0.0) + amt
        if st == "paid":
            total_paid += amt
        elif st == "cancelled":
            pass
        else:
            total_pipeline += amt
            if st in ACTIVE_STATES:
                outstanding += amt
        due = r.get("due")
        if due and st in ACTIVE_STATES:
            try:
                d = datetime.strptime(due, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < today:
                overdue.append({**r, "_days": (today - d).days})
            elif d <= today + timedelta(days=3):
                due_soon.append({**r, "_days": (d - today).days})
    return {
        "jobs_total": len(rows),
        "pipeline_value": round(total_pipeline, 2),
        "outstanding_value": round(outstanding, 2),
        "paid_value": round(total_paid, 2),
        "by_status": {k: round(v, 2) for k, v in by_status.items()},
        "overdue": sorted(overdue, key=lambda x: x["_days"], reverse=True),
        "due_soon": sorted(due_soon, key=lambda x: x["_days"]),
    }


def render_dashboard(store: Path, out: Path, today: Optional[date] = None) -> Path:
    s = summarize(store, today=today)
    rows = _load_all(store)
    today = today or date.today()

    def fmt_money(v: float) -> str:
        return f"{v:,.2f}".replace(",", " ") if False else f"{v:,.0f}"

    cards = []
    cards.append(("มูลค่ารอเก็บ (Outstanding)", fmt_money(s["outstanding_value"]), "#dc2626"))
    cards.append(("มูลค่า Pipe (ยังไม่จบ)", fmt_money(s["pipeline_value"]), "#2563eb"))
    cards.append(("เงินที่เก็บแล้ว (Paid)", fmt_money(s["paid_value"]), "#15803d"))
    cards.append(("งานทั้งหมด", str(s["jobs_total"]), "#7c3aed"))

    tr = []
    for r in sorted(rows, key=lambda x: x.get("updated_at", ""), reverse=True):
        due = r.get("due") or "-"
        tr.append(
            f"<tr><td>{r.get('job_id','')}</td><td>{_esc(r.get('client',''))}</td>"
            f"<td>{_esc(r.get('title',''))}</td><td>{fmt_money(float(r.get('amount',0) or 0))}</td>"
            f"<td><span class='st st-{r.get('status','lead')}'>{r.get('status','')}</span></td>"
            f"<td>{due}</td></tr>"
        )

    alerts = []
    for o in s["overdue"]:
        alerts.append(f"<li class='bad'>⚠ Overdue {o['_days']} วัน: {_esc(o['client'])} — {_esc(o['title'])} ({o['job_id']})</li>")
    for d in s["due_soon"]:
        alerts.append(f"<li class='warn'>⏰ ใกล้ครบกำหนด ({d['_days']} วัน): {_esc(d['client'])} — {_esc(d['title'])} ({d['job_id']})</li>")

    html = _DASHBOARD_TMPL.format(
        generated=_now_iso(),
        today=today.isoformat(),
        cards="\n".join(
            f"<div class='card' style='border-color:{c}'><div class='v'>{v}</div><div class='k'>{k}</div></div>"
            for k, v, c in cards
        ),
        alerts="\n".join(alerts) or "<li class='ok'>✅ ไม่มีงานค้างกำหนด</li>",
        rows="\n".join(tr) or "<tr><td colspan='6' class='muted'>ยังไม่มีงาน</td></tr>",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_DASHBOARD_TMPL = """<!DOCTYPE html>
<html lang="th"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>SCOS Revenue Dashboard</title>
<style>
 body{{font-family:system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
 h1{{font-size:1.5rem}} .muted{{color:#666;font-size:.85rem}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin:1rem 0}}
 .card{{border:2px solid #ddd;border-radius:12px;padding:1rem;text-align:center}}
 .card .v{{font-size:1.6rem;font-weight:700}} .card .k{{color:#555;margin-top:.25rem}}
 ul.alerts{{list-style:none;padding:0}} ul.alerts li{{padding:.5rem .75rem;border-radius:8px;margin:.4rem 0}}
 .bad{{background:#fee2e2;color:#b91c1c}} .warn{{background:#fef3c7;color:#92400e}} .ok{{background:#dcfce7;color:#15803d}}
 table{{width:100%;border-collapse:collapse;margin-top:1rem}} th,td{{border-bottom:1px solid #eee;padding:.5rem;text-align:left;font-size:.9rem}}
 .st{{padding:.15rem .5rem;border-radius:999px;background:#eef2ff;color:#3730a3;font-size:.78rem}}
 .st-paid{{background:#dcfce7;color:#15803d}} .st-overdue,.st-cancelled{{background:#fee2e2;color:#b91c1c}}
</style></head>
<body>
<h1>📊 SCOS Revenue Dashboard</h1>
<p class="muted">สร้างเมื่อ {generated} · วันอ้างอิง {today} · Local-first ไม่มีคลาวด์</p>
<div class="cards">{cards}</div>
<h2>⏰ แจ้งเตือน</h2>
<ul class="alerts">{alerts}</ul>
<h2>📁 งานทั้งหมด</h2>
<table><thead><tr><th>ID</th><th>ลูกค้า</th><th>งาน</th><th>มูลค่า</th><th>สถานะ</th><th>กำหนด</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""


# --- CLI ------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SCOS Revenue Ops (local job tracker)")
    p.add_argument("--store", type=Path, default=DEFAULT_STORE, help="path to jobs.jsonl")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="เพิ่มงานใหม่")
    a.add_argument("--client", required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--amount", required=True, type=float)
    a.add_argument("--due", default=None)
    a.add_argument("--status", default="accepted")
    a.add_argument("--note", default="")

    u = sub.add_parser("update", help="แก้ไขงาน")
    u.add_argument("--id", required=True)
    u.add_argument("--client", default=None)
    u.add_argument("--title", default=None)
    u.add_argument("--amount", type=float, default=None)
    u.add_argument("--due", default=None)
    u.add_argument("--status", default=None)
    u.add_argument("--note", default=None)

    s = sub.add_parser("status", help="เปลี่ยนสถานะ")
    s.add_argument("--id", required=True)
    s.add_argument("--status", required=True, choices=STATES)

    sub.add_parser("summary", help="สรุปตัวเลข")
    d = sub.add_parser("dashboard", help="สร้าง HTML dashboard")
    d.add_argument("--out", type=Path, default=_ROOT / "revenue_dashboard.html")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    store = args.store
    if args.cmd == "add":
        rec = add_job(store, args.client, args.title, args.amount, args.due, args.status, args.note)
        print(f"เพิ่มแล้ว: {rec['job_id']} {rec['client']} — {rec['title']} ({rec['amount']:.0f} THB, {rec['status']})")
    elif args.cmd == "update":
        rec = update_job(store, args.id, client=args.client, title=args.title,
                         amount=args.amount, due=args.due, status=args.status, note=args.note)
        if rec is None:
            print(f"ไม่พบงาน: {args.id}")
            return 1
        print(f"อัปเดตแล้ว: {rec['job_id']} → {rec['status']}")
    elif args.cmd == "status":
        rec = set_status(store, args.id, args.status)
        if rec is None:
            print(f"ไม่พบงาน: {args.id}")
            return 1
        print(f"{rec['job_id']} → {rec['status']}")
    elif args.cmd == "summary":
        s = summarize(store)
        print(json.dumps(s, ensure_ascii=False, indent=2))
    elif args.cmd == "dashboard":
        out = render_dashboard(store, args.out)
        print(f"Dashboard: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
