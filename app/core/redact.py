"""Helpers for keeping credentials out of text that reaches the UI."""

from __future__ import annotations

import re

# GitHub personal access tokens (classic and fine grained) and the other
# common provider key shapes. Used to scrub anything before it is displayed.
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)\b(?:token|api[_-]?key|secret|password)\s*[=:]\s*\S{12,}"),
)

REDACTED = "[redacted]"

#: Values this process is actually holding, so they can be removed by exact
#: match rather than by shape.
#:
#: The patterns above only recognise credentials whose format is known. A token
#: this app issued is not hypothetical: whatever the user pasted is a live
#: credential, and a provider that mangles it, or a token older than the formats
#: listed, would sail past a shape check and be shown in a toast. Registering
#: the literal value closes that gap for the one secret that matters most.
_KNOWN: set[str] = set()

#: Shorter values would turn ordinary words into redaction targets.
_MIN_KNOWN_LENGTH = 8


def remember_secret(value: str) -> None:
    """Record a credential this process holds, for exact-match redaction."""
    text = str(value or "").strip()
    if len(text) >= _MIN_KNOWN_LENGTH:
        _KNOWN.add(text)


def forget_secrets() -> None:
    """Drop remembered credentials. Called when the token is cleared."""
    _KNOWN.clear()


def _redact_known(text: str) -> str:
    """Replace the remembered credentials, longest first.

    Longest first so a secret that contains another is replaced whole rather
    than leaving a fragment behind.
    """
    for value in sorted(_KNOWN, key=len, reverse=True):
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def redact_secrets(text: str) -> str:
    """Replace anything token-shaped in ``text`` with ``[redacted]``."""
    if not text:
        return ""
    result = _redact_known(text)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def looks_like_secret(text: str) -> bool:
    """True when ``text`` contains something token-shaped, or a known secret."""
    if any(value in (text or "") for value in _KNOWN):
        return True
    return any(pattern.search(text or "") for pattern in SECRET_PATTERNS)
