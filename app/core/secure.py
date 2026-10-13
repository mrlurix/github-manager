"""Replace the reversible obfuscation with a real secret store.

On Windows DPAPI ties each blob to the user account, so that path is
untouched. Everywhere else the old code wrote base64 of the reversed
bytes under an "obf:" prefix. That is not encryption: it is a fixed,
keyless transform, and anyone who can read the file can recover the token
with ``base64.b64decode(payload)[::-1]``. Calling it protected overstated it.

The replacement, in order of preference:

  1. DPAPI on Windows.
  2. The OS keystore - Keychain on macOS, Secret Service on Linux - through
     the ``keyring`` package. ``secrets.json`` then holds a reference, not a
     credential, and the credential is protected by the login keychain rather
     than by anything this app could get wrong.
  3. Nothing, and the secret is kept in memory for the session only.

Option 3 is the important one. The previous fallback wrote the value anyway
in a form any script can undo, which meant "no keystore available" silently
degraded to "plaintext with extra steps". Now it does not write at all: the
app works, the token simply has to be entered again next launch, and the user
is told why. ``GHM_ALLOW_WEAK_SECRET_STORE=1`` restores the old behaviour for
someone who has decided they would rather have the convenience.
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

#: Service name used in the OS keystore. Namespaced so a rebuild cannot read a
#: blob some other tool wrote under a generic name.
_KEYRING_SERVICE = "GitHubManager"

#: Set by the user to keep the old reversible storage when no real backend is
#: available. Off by default: silently downgrading is how the last version of
#: this file came to exist.
_ENV_ALLOW_WEAK = "GHM_ALLOW_WEAK_SECRET_STORE"


def _keyring_module():
    """The ``keyring`` module, or ``None`` when it is not installed."""
    try:
        import keyring  # noqa: PLC0415

        backend = keyring.get_keyring()
        # A null backend accepts writes and discards them, which looks like
        # success and loses the credential. Fail over to the next option.
        name = type(backend).__name__.lower()
        if "null" in name or "fail" in name:
            return None
        return keyring
    except Exception:
        return None


_KEYRING = _keyring_module()


def keyring_available() -> bool:
    """True when a real OS keystore is reachable."""
    return _KEYRING is not None


def weak_store_allowed() -> bool:
    return os.environ.get(_ENV_ALLOW_WEAK, "").strip().lower() in {"1", "true", "yes"}


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


def _protect(value: str, key: str) -> str | None:
    """Encode a secret for storage, or ``None`` when it must not be stored.

    ``key`` goes into the keystore reference so that decoding needs nothing
    but the stored string. An earlier attempt wrote a fixed marker here and
    passed the real key separately, which named the reference and the entry
    in the keystore differently - the value could be written but never read
    back, which looked like a successful save and cost the user their token
    on the next launch.
    """
    raw = value.encode("utf-8")
    if _WINDOWS:
        try:
            return "dpapi:" + base64.b64encode(
                _dpapi_protect(raw, _machine_entropy())
            ).decode("ascii")
        except OSError as exc:
            # DPAPI can fail in odd environments (locked profile, container).
            # Say so rather than silently downgrading the protection.
            print(f"[secrets] DPAPI unavailable ({exc})")
    if _KEYRING is not None:
        return f"keyring:{key}"
    if weak_store_allowed():
        print(
            "[secrets] no OS keystore; storing reversibly because "
            f"{_ENV_ALLOW_WEAK} is set"
        )
        return "obf:" + base64.b64encode(raw[::-1]).decode("ascii")
    return None


def _unprotect(value: str) -> str:
    prefix, _, payload = value.partition(":")
    try:
        if prefix == "keyring":
            if _KEYRING is None:
                return ""
            return str(_KEYRING.get_password(_KEYRING_SERVICE, payload) or "")
        raw = base64.b64decode(payload.encode("ascii"), validate=True)
        if prefix == "dpapi":
            return _dpapi_unprotect(raw, _machine_entropy()).decode("utf-8")
        if prefix == "obf":
            return raw[::-1].decode("utf-8")
    except (ValueError, UnicodeDecodeError, OSError):
        # Wrong user, corrupted file, or a value written by another build.
        return ""
    return ""


def backend_name() -> str:
    """A short name for the storage in use, for the settings screen."""
    if _WINDOWS:
        return "Windows DPAPI"
    if _KEYRING is not None:
        return f"OS keystore ({type(_KEYRING.get_keyring()).__name__})"
    if weak_store_allowed():
        return "reversible fallback (GHM_ALLOW_WEAK_SECRET_STORE)"
    return "memory only - nothing is written to disk"


class SecretStore:
    """Owner-only key/value storage for tokens and API keys."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or secrets_file()
        self._cache: dict[str, str] | None = None
        #: Values that have no backend and must never reach the disk. Kept
        #: beside the file cache rather than inside it, so _flush() cannot
        #: write them out by accident.
        self._memory: dict[str, str] = {}
        self._warned = False

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
        self._migrate(data)
        return data

    def _migrate(self, data: dict[str, str]) -> None:
        """Re-encode any value left in the old reversible form.

        Only when there is somewhere better to put it. A user on a system with
        no keystore keeps their existing file rather than losing the token the
        first time they launch an upgraded build.
        """
        if _WINDOWS or not data or not any(v.startswith("obf:") for v in data.values()):
            return
        if _KEYRING is None and not weak_store_allowed():
            print(
                "[secrets] this file still holds reversibly-encoded values from an "
                "earlier version; they stay readable until you re-enter them with "
                "a keystore available"
            )
            return
        changed = False
        for key, value in list(data.items()):
            if not value.startswith("obf:"):
                continue
            plain = _unprotect(value)
            encoded = _protect(plain, key) if plain else None
            if encoded and encoded != value:
                if encoded.startswith("keyring:"):
                    _KEYRING.set_password(_KEYRING_SERVICE, key, plain)
                data[key] = encoded
                changed = True
        if changed:
            self._flush()

    def _flush(self) -> None:
        """Write the store atomically and owner-only.

        Never writes a secret - ``_memory`` is not in ``_cache``, so a value with
        no backend cannot reach the disk even if this is called right after one
        was set. The file should still not be readable by other accounts on a
        shared machine.
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
        """Best-effort owner-only permissions (POSIX); a no-op on Windows.

        Windows relies on DPAPI, and the DPAPI entropy already binds a blob to
        this user account, so the ACL would be belt to that braces.
        """
        if _WINDOWS:
            return
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _warn_no_backend(self) -> None:
        if self._warned:
            return
        self._warned = True
        print(
            "[secrets] no OS keystore on this system, so the token is kept for "
            "this session only and nothing is written to disk. Install the "
            "'keyring' package (and, on Linux, python3-secretstorage or "
            "gnome-keyring) to keep it between launches."
        )

    def get(self, key: str) -> str:
        if key in self._memory:
            return self._memory[key]
        return _unprotect(self._load().get(key, ""))

    def set(self, key: str, value: str) -> None:
        data = self._load()
        if not value:
            data.pop(key, None)
            self._memory.pop(key, None)
            if _KEYRING is not None:
                try:
                    _KEYRING.delete_password(_KEYRING_SERVICE, key)
                except Exception:
                    pass
            self._cache = data
            self._flush()
            return

        encoded = _protect(value, key)
        if encoded is None:
            # No backend: keep it in the session and do not write it.
            self._warn_no_backend()
            self._memory[key] = value
            data.pop(key, None)
            self._cache = data
            return

        if encoded.startswith("keyring:"):
            try:
                _KEYRING.set_password(_KEYRING_SERVICE, key, value)
            except Exception as exc:
                print(f"[secrets] keystore write failed ({exc}); keeping it in memory")
                self._memory[key] = value
                data.pop(key, None)
                self._cache = data
                return
        self._memory.pop(key, None)
        data[key] = encoded
        self._cache = data
        self._flush()

    def has(self, key: str) -> bool:
        if key in self._memory:
            return True
        return bool(self._load().get(key))

    def delete(self, key: str) -> None:
        self.set(key, "")

    def clear(self) -> None:
        self._cache = {}
        self._memory.clear()
        if _KEYRING is not None:
            for key in (GH_TOKEN, AI_API_KEY):
                try:
                    _KEYRING.delete_password(_KEYRING_SERVICE, key)
                except Exception:
                    pass
        self._flush()


GH_TOKEN = "github_token"
AI_API_KEY = "ai_api_key"
