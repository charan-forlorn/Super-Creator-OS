"""Daily revenue report for cron (item #3).

Runs the Revenue Ops summary and prints a human-readable briefing.
Designed to be called by a Hermes cron job (no_agent mode) so the captured
stdout is delivered to the user's Slack/chat every morning.

Run:
  .venv\\Scripts\\python.exe scripts\\daily_revenue_report.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from scripts.revenue_ops import DEFAULT_STORE, summarize  # noqa: E402


def build_report(today: date | None = None) -> str:
    today = today or date.today()
    s = summarize(DEFAULT_STORE, today=today)
    lines = [
        f"📊 รายงานรายได้ประจำวัน — {today.isoformat()}",
        "────────────────────────────",
        f"💰 รอเก็บ (outstanding): {s['outstanding_value']:,.0f} THB",
        f"📦 ท่อไหล (pipeline):    {s['pipeline_value']:,.0f} THB",
        f"✅ เก็บแล้ว (paid):       {s['paid_value']:,.0f} THB",
        f"📁 งานทั้งหมด:           {s['jobs_total']} งาน",
    ]
    if s["overdue"]:
        lines.append("")
        lines.append("⚠️ เลยกำหนด:")
        for o in s["overdue"][:5]:
            lines.append(f"  • {o['client']} — {o['title']} ({o['job_id']}) เกิน {o['_days']} วัน")
    if s["due_soon"]:
        lines.append("")
        lines.append("⏰ ใกล้ครบกำหนด (≤3 วัน):")
        for d in s["due_soon"][:5]:
            lines.append(f"  • {d['client']} — {d['title']} ({d['job_id']}) อีก {d['_days']} วัน")
    if not s["overdue"] and not s["due_soon"]:
        lines.append("")
        lines.append("✅ ไม่มีงานค้างกำหนด")
    return "\n".join(lines)


def main() -> int:
    print(build_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
