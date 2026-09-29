"""Runtime token refresh from the DPAPI-backed SCOS YouTube OAuth store."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Callable

from integrations.learning.youtube_oauth_store import DEFAULT_STORE, load_credential

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def refresh_access_token(
    store_path=None,
    *,
    opener: Callable[..., object] | None = None,
    timeout: float = 30.0,
) -> str:
    cred = load_credential(store_path or DEFAULT_STORE)
    payload = urllib.parse.urlencode({
        "client_id": cred["client_id"],
        "refresh_token": cred["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    transport = opener or urllib.request.urlopen
    with transport(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    token = str(result.get("access_token") or "") if isinstance(result, dict) else ""
    if not token:
        raise RuntimeError("Google OAuth refresh response did not contain access_token")
    return token


__all__ = ["TOKEN_ENDPOINT", "refresh_access_token"]
