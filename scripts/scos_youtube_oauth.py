"""Human-consent Google OAuth 2.0 flow for SCOS YouTube Analytics.

Desktop/installed-app flow: PKCE + loopback callback. The browser consent action is
Human-controlled. Tokens are exchanged locally and the refresh token is encrypted
with Windows DPAPI before persistence; plaintext tokens are never written to logs.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.learning.youtube_oauth_store import DEFAULT_STORE, save_credential

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REPORTS_ENDPOINT = "https://youtubeanalytics.googleapis.com/v2/reports"
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YT_ANALYTICS_READONLY_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
REQUIRED_SCOPES = (YOUTUBE_READONLY_SCOPE, YT_ANALYTICS_READONLY_SCOPE)


def load_client_config(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8-sig").strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        for kind in ("installed", "web"):
            block = data.get(kind)
            if isinstance(block, dict) and block.get("client_id"):
                return {
                    "type": kind,
                    "client_id": str(block["client_id"]),
                    "client_secret": str(block.get("client_secret") or ""),
                    "redirect_uris": tuple(str(x) for x in block.get("redirect_uris", ()) if x),
                    "token_uri": str(block.get("token_uri") or TOKEN_ENDPOINT),
                }
        raise ValueError("OAuth client JSON must contain an installed or web client")
    matches = re.findall(r"[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com", raw)
    if not matches:
        raise ValueError("Google OAuth client ID not found")
    return {
        "type": "unknown",
        "client_id": matches[0],
        "client_secret": "",
        "redirect_uris": (),
        "token_uri": TOKEN_ENDPOINT,
    }


def extract_client_id(path: Path) -> str:
    return load_client_config(path)["client_id"]


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _form_post(url: str, payload: dict[str, str], timeout: float = 30.0) -> dict:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("OAuth token response is not an object")
    return data


def _authorized_report(access_token: str) -> dict:
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=7)
    params = {
        "ids": "channel==MINE",
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "metrics": "views",
        "dimensions": "day",
    }
    req = urllib.request.Request(
        REPORTS_ENDPOINT + "?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30.0) as response:
        return json.loads(response.read().decode("utf-8"))


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict[str, str] = {}
    expected_state = ""

    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        state = (query.get("state") or [""])[0]
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]
        if state != self.expected_state:
            self.result = {"error": "STATE_MISMATCH"}
        elif error:
            self.result = {"error": error}
        elif not code:
            self.result = {"error": "AUTH_CODE_MISSING"}
        else:
            self.result = {"code": code}
        body = b"SCOS OAuth authorization received. You may close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:
        return


def authorize(config: dict, *, timeout_s: int = 300, open_browser: bool = True) -> dict:
    client_id = config["client_id"]
    client_secret = config.get("client_secret", "")
    client_type = config.get("type", "unknown")
    state = secrets.token_urlsafe(32)
    verifier, challenge = _pkce()

    configured_redirects = tuple(config.get("redirect_uris", ()))
    if client_type == "unknown":
        raise RuntimeError(
            "OAUTH_CLIENT_TYPE_UNKNOWN: use a downloaded Google OAuth Desktop client JSON; "
            "a bare client ID cannot safely determine its registered redirect method"
        )
    if client_type == "web":
        local_redirects = tuple(
            uri for uri in configured_redirects
            if uri.startswith("http://localhost:") or uri.startswith("http://127.0.0.1:")
        )
        if not local_redirects:
            raise RuntimeError(
                "WEB_CLIENT_REDIRECT_URI_REQUIRED: create a Desktop OAuth client or add an exact "
                "localhost redirect URI such as http://127.0.0.1:8787/oauth2callback"
            )
        redirect_uri = local_redirects[0]
        parsed = urllib.parse.urlparse(redirect_uri)
        if parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.port:
            raise RuntimeError("configured redirect URI must be localhost with an explicit port")
        server = HTTPServer((parsed.hostname, parsed.port), _CallbackHandler)
    else:
        server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        redirect_uri = f"http://127.0.0.1:{server.server_port}/oauth2callback"

    _CallbackHandler.expected_state = state
    _CallbackHandler.result = {}
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(REQUIRED_SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)
    print("AUTHORIZATION_REQUIRED")
    print("Opening Google consent in the default browser...")
    if open_browser:
        webbrowser.open(auth_url, new=1, autoraise=True)
    else:
        print("Authorization URL:")
        print(auth_url)
    deadline = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=timeout_s)
    while not _CallbackHandler.result:
        remaining = (deadline - dt.datetime.now(dt.timezone.utc)).total_seconds()
        if remaining <= 0:
            server.server_close()
            raise TimeoutError("OAuth consent callback timed out")
        server.timeout = min(1.0, remaining)
        server.handle_request()
    server.server_close()
    result = _CallbackHandler.result
    if "error" in result:
        raise RuntimeError(f"Google OAuth authorization failed: {result['error']}")
    token_payload = {
        "client_id": client_id,
        "code": result["code"],
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    if client_secret:
        token_payload["client_secret"] = client_secret
    token = _form_post(str(config.get("token_uri") or TOKEN_ENDPOINT), token_payload)
    granted = tuple(str(token.get("scope", "")).split())
    missing = sorted(set(REQUIRED_SCOPES) - set(granted))
    if missing:
        raise PermissionError("OAuth consent did not grant required scopes: " + ", ".join(missing))
    access_token = str(token.get("access_token") or "")
    refresh_token = str(token.get("refresh_token") or "")
    if not access_token or not refresh_token:
        raise RuntimeError("OAuth response did not contain both access_token and refresh_token")
    _authorized_report(access_token)
    return {"client_id": client_id, "refresh_token": refresh_token, "scopes": list(granted), "authorized_at": dt.datetime.now(dt.timezone.utc).isoformat()}
def main() -> int:
    ap = argparse.ArgumentParser(description="SCOS YouTube Analytics OAuth authorization")
    ap.add_argument(
        "--client-file",
        default=r"C:\Users\chara\Downloads\gooale API.txt",
        help="Text file containing a client ID, or downloaded Google OAuth client JSON",
    )
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    config = load_client_config(Path(args.client_file))
    payload = authorize(config, timeout_s=args.timeout, open_browser=not args.no_browser)
    store = save_credential(payload, args.store)
    print(json.dumps({
        "status": "OAUTH_AUTHORIZED",
        "credential_store": str(store),
        "scopes": payload["scopes"],
        "refresh_token_persisted": True,
        "refresh_token_value_exposed": False,
        "api_publish_or_dispatch": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
