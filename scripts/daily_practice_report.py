"""Daily practice-render loop report for cron (item #2 cron half).

Runs the practice loop in LEARN-ONLY (safe) mode by default and prints a
briefing of what patterns were exercised/learned today. Real rendering is
OFF unless --allow-real is passed AND the HVS approval gate is satisfied.

Run (safe, daily):
  .venv\\Scripts\\python.exe scripts\\daily_practice_report.py
Run (real, only after operator enables HVS approval):
  .venv\\Scripts\\python.exe scripts\\daily_practice_report.py --allow-real
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from scripts.practice_render_loop import PLATFORM_FORMATS, run_daily  # noqa: E402


def build_report(allow_real: bool = False) -> str:
    result = run_daily(allow_real=allow_real)
    lines = [
        f"🎬 Practice Render Loop — {result['date']}",
        "────────────────────────────",
        f"แพลตฟอร์มที่ซ้อม: {result['platforms']} รูปแบบ",
        f"เรียนรู้ pattern ใหม่: {result['learned_patterns']} รายการ",
        f"โหมด: {'REAL' if result['real_renders'] else 'LEARN-ONLY (ไม่ render จริง)'}",
        "",
        "รายละเอียด:",
    ]
    for r in result["reports"]:
        tag = "SIM" if r["simulated"] else "REAL"
        status = "✅" if r["render_ok"] else "❌"
        lines.append(f"  [{tag}] {status} {r['platform_key']} → {r['format_id']} : {r['learned_record']}")
    lines.append("")
    lines.append("💡 ระบบสะสม 'รูปแบบ render' ลง memory/database.json ทุกวัน")
    lines.append("   วิดีโอที่ render จริงจะถูกลบอัตโนมัติหลัง verify (เก็บแค่ pattern)")
    if not result["real_renders"]:
        lines.append("⚠️ ยังไม่เปิด real render — ต้องเปิด HVS approval ก่อน (แจ้ง Hermes)")
    return "\n".join(lines)


def main() -> int:
    allow_real = "--allow-real" in sys.argv
    print(build_report(allow_real=allow_real))
    return 0


if __name__ == "__main__":
    sys.exit(main())
