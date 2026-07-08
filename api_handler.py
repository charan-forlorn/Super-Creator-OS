"""Local HTTP server for the SCOS customer portal (no external deps).

Serves customer.html (the standalone customer UI) and a small JSON API:
  GET  /                      -> customer.html
  GET  /static/<file>         -> static assets
  GET  /api/health            -> {"status":"ok"}
  GET  /error-report          -> operator page listing reported errors
  POST /api/report-error      -> record a customer-reported error (lenient)

No backend, no secrets, no network egress. Stage 6.7 scope-add: customer
error-report wiring (frontend button -> POST /api/report-error -> operator page).
"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG = os.path.join(HERE, "api_errors.log")

REPORT_FIELDS = ("customer_id", "message", "url", "severity")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_error(payload):
    entry = {
        "ts": _now_iso(),
        "customer_id": str(payload.get("customer_id", "")).strip(),
        "message": str(payload.get("message", "")).strip(),
        "url": str(payload.get("url", "")).strip(),
        "severity": str(payload.get("severity", "medium")).strip().lower()
        or "medium",
        "handled": False,
    }
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_errors():
    if not os.path.exists(ERROR_LOG):
        return []
    out = []
    with open(ERROR_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def render_html(title, body_html, head_extra=""):
    return (
        "<!DOCTYPE html>\n<html lang='th'>\n<head>\n<meta charset='utf-8'>\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        f"<title>{title}</title>\n{head_extra}\n</head>\n<body>\n"
        f"{body_html}\n</body>\n</html>\n"
    )


def render_error_report_page():
    errors = load_errors()
    rows = []
    for e in errors:
        badge = "已处理" if e.get("handled") else "尚未处理"
        rows.append(
            "<tr><td>{ts}</td><td>{cid}</td><td>{msg}</td>"
            "<td>{sev}</td><td>{badge}</td></tr>".format(
                ts=e.get("ts", ""),
                cid=e.get("customer_id", "") or "-",
                msg=e.get("message", ""),
                sev=e.get("severity", ""),
                badge=badge,
            )
        )
    if not rows:
        rows.append("<tr><td colspan='5'>ไม่มีรายการ</td></tr>")
    body = (
        "<h1>รายงานข้อผิดพลาด (Error Reports)</h1>\n"
        "<p><a href='/'>หน้าแรก</a></p>\n"
        "<table border='1' cellpadding='6' cellspacing='0'>\n"
        "<thead><tr><th>เวลา</th><th>รหัสลูกค้า</th><th>ข้อความ</th>"
        "<th>ระดับ</th><th>สถานะ</th></tr></thead>\n<tbody>\n"
        + "\n".join(rows)
        + "\n</tbody>\n</table>\n"
    )
    return render_html("Error Reports", body)


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "SCOS-Customer/1.0"

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False),
                       "application/json; charset=utf-8")

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path in ("/", "/index.html"):
                self._serve_customer_html()
            elif path == "/api/health":
                self._send_json(200, {"status": "ok"})
            elif path == "/error-report":
                self._send(200, render_error_report_page())
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            else:
                self._send(404, render_html("404", "<h1>ไม่พบหน้า (404)</h1>"))

        def _serve_customer_html(self):
            target = os.path.join(HERE, "customer.html")
            if os.path.exists(target):
                with open(target, "r", encoding="utf-8") as f:
                    self._send(200, f.read())
            else:
                self._send(404, render_html("404",
                                            "<h1>customer.html ไม่พบ</h1>"))

        def _serve_static(self, name):
            safe = os.path.basename(name)
            full = os.path.join(HERE, "static", safe)
            if os.path.exists(full) and os.path.isfile(full):
                with open(full, "rb") as f:
                    self._send(200, f.read())
            else:
                self._send(404, render_html("404", "<h1>ไม่พบไฟล์</h1>"))

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            if path == "/api/report-error":
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                except json.JSONDecodeError:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                entry = record_error(payload)
                self._send_json(201, {"status": "received", "entry": entry})
            elif path.startswith("/api/"):
                self._send_json(404, {"error": "unknown endpoint"})
            else:
                self._send(404, render_html("404", "<h1>ไม่พบ (404)</h1>"))

        def log_message(self, fmt, *args):
            # Quiet; errors are persisted to api_errors.log instead.
            return

    return Handler


def main():
    port = int(os.environ.get("PORT", 8765))
    srv = HTTPServer(("127.0.0.1", port), make_handler())
    print(f"SCOS customer server on http://127.0.0.1:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
