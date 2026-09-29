"""Windows DPAPI-backed local storage for SCOS YouTube OAuth refresh credentials."""

from __future__ import annotations

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

DEFAULT_STORE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SCOS" / "credentials" / "youtube_analytics.dpapi"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data)
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    return blob, buf


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI credential store requires Windows")
    source, source_buf = _blob(data)
    target = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI credential store requires Windows")
    source, source_buf = _blob(data)
    target = _DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def save_credential(payload: dict, path: str | os.PathLike | None = None) -> Path:
    required = {"client_id", "refresh_token", "scopes"}
    if not required.issubset(payload):
        raise ValueError("credential payload missing required fields")
    if not payload["refresh_token"]:
        raise ValueError("refresh_token must not be empty")
    p = Path(path) if path else DEFAULT_STORE
    p.parent.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    encrypted = _protect(plaintext)
    tmp = p.with_suffix(p.suffix + f".{os.getpid()}.tmp")
    tmp.write_bytes(encrypted)
    os.replace(tmp, p)
    return p


def load_credential(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else DEFAULT_STORE
    if not p.is_file():
        raise FileNotFoundError(f"OAuth credential store not found: {p}")
    payload = json.loads(_unprotect(p.read_bytes()).decode("utf-8"))
    if not isinstance(payload, dict) or not payload.get("refresh_token"):
        raise ValueError("credential store is invalid")
    return payload


def credential_exists(path: str | os.PathLike | None = None) -> bool:
    p = Path(path) if path else DEFAULT_STORE
    return p.is_file()


__all__ = ["DEFAULT_STORE", "credential_exists", "load_credential", "save_credential"]
