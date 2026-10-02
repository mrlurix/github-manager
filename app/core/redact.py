"""Helpers for keeping credentials out of text that reaches the UI."""

from __future__ import annotations

import re

# GitHub personal access tokens (classic and fine grained) and the other
# common provider key shapes. Used to scrub anything before it is displayed.
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{20,}"),
)

REDACTED = "[redacted]"


def redact_secrets(text: str) -> str:
    """Replace anything token-shaped in ``text`` with ``[redacted]``."""
    if not text:
        return ""
    result = text
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def looks_like_secret(text: str) -> bool:
    """True when ``text`` contains something token-shaped."""
    return any(pattern.search(text or "") for pattern in SECRET_PATTERNS)
