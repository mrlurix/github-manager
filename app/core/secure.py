"""Secret storage.

Tokens and API keys are never written in plain text. On Windows they are
protected with DPAPI (CryptProtectData) which ties them to the current user
account; everywhere else we fall back to a light obfuscation so the file is
not accidentally committed or shared in a readable form.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from pathlib import Path

from ..config import secrets_file

_MAGIC = b"GHM1"
_WINDOWS = sys.platform.startswith("win")


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _dpapi_protect(data: bytes, entropy: bytes) -> bytes:
    in_blob, in_buf = _blob(data)
    ent_blob, ent_buf = _blob(entropy)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
        ctypes.byref(in_blob),
        "GitHub Manager",
        ctypes.byref(ent_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = (in_buf, ent_buf)
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)  # type: ignore[attr-defined]


def _dpapi_unprotect(data: bytes, entropy: bytes) -> bytes:
    in_blob, in_buf = _blob(data)
    ent_blob, ent_buf = _blob(entropy)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
        ctypes.byref(in_blob),
        None,
        ctypes.byref(ent_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = (in_buf, ent_buf)
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)  # type: ignore[attr-defined]


def _machine_entropy() -> bytes:
    """Extra DPAPI entropy so a blob is bound to this app and this user."""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return b"GitHubManager::v1::" + base64.b64encode(user.encode())


def _protect(value: str) -> str:
    raw = value.encode("utf-8")
    if _WINDOWS:
        try:
            return "dpapi:" + base64.b64encode(
                _dpapi_protect(raw, _machine_entropy())
            ).decode("ascii")
        except OSError as exc:
            # DPAPI can fail in odd environments (locked profile, container).
            # Say so rather than silently downgrading the protection.
            print(f"[secrets] DPAPI unavailable ({exc}); using obfuscated storage")
    return "obf:" + base64.b64encode(raw[::-1]).decode("ascii")


def _unprotect(value: str) -> str:
    prefix, _, payload = value.partition(":")
    try:
        raw = base64.b64decode(payload.encode("ascii"), validate=True)
        if prefix == "dpapi":
            return _dpapi_unprotect(raw, _machine_entropy()).decode("utf-8")
        if prefix == "obf":
            return raw[::-1].decode("utf-8")
    except (ValueError, UnicodeDecodeError, OSError):
        # Wrong user, corrupted file, or a value written by another build.
        return ""
    return ""


class SecretStore:
    """Tiny encrypted key/value file for tokens and API keys."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or secrets_file()
        self._cache: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        data: dict[str, str] = {}
        try:
            if self.path.exists():
                data = {
                    str(k): str(v)
                    for k, v in (json.loads(self.path.read_text(encoding="utf-8")) or {}).items()
                }
        except Exception:
            data = {}
        self._cache = data
        return data

    def _flush(self) -> None:
        """Write the store atomically and owner-only.

        The contents are encrypted, but the file should still not be readable
        by other accounts on a shared machine.
        """
        if self._cache is None:
            return
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._restrict(tmp)
            tmp.replace(self.path)
            self._restrict(self.path)
        except OSError as exc:  # pragma: no cover
            print(f"[secrets] could not persist: {exc}")

    @staticmethod
    def _restrict(path: Path) -> None:
        """Best-effort owner-only permissions (POSIX); a no-op on Windows."""
        if _WINDOWS:
            return
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def get(self, key: str) -> str:
        return _unprotect(self._load().get(key, ""))

    def set(self, key: str, value: str) -> None:
        data = self._load()
        if value:
            data[key] = _protect(value)
        else:
            data.pop(key, None)
        self._cache = data
        self._flush()

    def has(self, key: str) -> bool:
        return bool(self._load().get(key))

    def delete(self, key: str) -> None:
        self.set(key, "")

    def clear(self) -> None:
        self._cache = {}
        self._flush()


GH_TOKEN = "github_token"
AI_API_KEY = "ai_api_key"
