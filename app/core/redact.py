"""Close the gaps in redaction without starting to redact ordinary text.

Two real holes in the previous version:

  * A credential wrapped across lines by whatever produced the text - a log
    formatter, a terminal, a copy out of a narrow panel - was not matched at
    all. The patterns anchor on contiguous characters, so a single space in the
    middle of the token made it invisible to every one of them.

  * An elided credential, shown as "ghp_A1b2C3...Q7r8", was not matched either.
    A UI that shortens a token for display is still putting eight live
    characters in front of the reader.

An earlier attempt at the wrapped case rewrote the patterns to tolerate
whitespace inside them. That mostly did not work - four of five wrapped inputs
went straight through - so the approach here is different: the patterns are
left alone and run against a whitespace-stripped copy, and each match is mapped
back onto the original by position. What gets replaced is the span in the real
text, newlines included, so nothing is left visible.
"""
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
)

#: ``api_key=...``, ``token: ...`` and the rest.
#:
#: Kept out of SECRET_PATTERNS because the value has to be judged as a whole
#: rather than by a length prefix. Matching twelve non-space characters after
#: the "=" redacted ``api_key = os.environ.get('KEY')`` - the text after the "="
#: is fifteen non-space characters, none of which is a credential. A guard that
#: hides ordinary text is worse than no guard, because the reader learns to
#: disregard it.
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?:token|api[_-]?key|secret|password)\s*[=:]\s*(\S+)"
)

#: Characters that mean what follows the "=" is code or a quoted string rather
#: than a credential.
_NOT_A_CREDENTIAL = set("\"'(){}[]<>,;")


def _assignment(match: re.Match[str]) -> str:
    """Redact ``key=value``, but only when the value could be a secret."""
    value = match.group(1)
    if len(value) < 12:
        return match.group(0)
    if any(char in _NOT_A_CREDENTIAL for char in value):
        return match.group(0)
    return match.group(0).replace(value, REDACTED)

#: An elided credential: the head and the tail with a gap between them.
ELIDED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{4,14}"
        r"\s*(?:\.\.\.|…|\*{3,}|x{3,})\s*[A-Za-z0-9]{4,8}\b"
    ),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{4,14}"
               r"\s*(?:\.\.\.|…|\*{3,})\s*[A-Za-z0-9_]{4,10}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,12}"
               r"\s*(?:\.\.\.|…|\*{3,})\s*[A-Za-z0-9_-]{4,8}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{6,12}"
               r"\s*(?:\.\.\.|…|\*{3,})\s*[A-Za-z0-9_-]{4,8}\b"),
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


def _flatten(text: str) -> tuple[str, list[int]]:
    """The text without whitespace, plus where each kept character came from."""
    chars: list[str] = []
    where: list[int] = []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char)
            where.append(index)
    return "".join(chars), where


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort and join overlapping spans so two patterns cannot nest."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _redact_known(text: str) -> str:
    """Replace the remembered credentials, longest first.

    Longest first so a secret that contains another is replaced whole rather
    than leaving a fragment behind.
    """
    for value in sorted(_KNOWN, key=len, reverse=True):
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def _redact_wrapped(text: str) -> str:
    """Remove a credential broken across lines.

    Runs the ordinary patterns over a whitespace-free copy of the text, then
    replaces each match in the *original* by position - so the newline or space
    that hid the token goes with it, instead of leaving half a credential on
    screen with a hole where the other half was.
    """
    flat, where = _flatten(text)
    if len(flat) == len(text):
        return text

    spans: list[tuple[int, int]] = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(flat):
            spans.append((where[match.start()], where[match.end() - 1] + 1))

    spans = _merge(spans)
    if not spans:
        return text

    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(text[cursor:start])
        pieces.append(REDACTED)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def redact_secrets(text: str) -> str:
    """Replace anything token-shaped in ``text`` with ``[redacted]`."""
    if not text:
        return ""
    result = _redact_known(text)
    result = _redact_wrapped(result)
    for pattern in SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    result = ASSIGNMENT_PATTERN.sub(_assignment, result)
    for pattern in ELIDED_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def looks_like_secret(text: str) -> bool:
    """True when ``text`` contains something token-shaped, or a known secret."""
    if not text:
        return False
    if any(value in text for value in _KNOWN):
        return True
    if any(pattern.search(text) for pattern in ELIDED_PATTERNS):
        return True
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return True
    # A credential broken across lines: the token shapes run against the text
    # with its whitespace removed.
    flat, _where = _flatten(text)
    if len(flat) != len(text) and any(
        pattern.search(flat) for pattern in SECRET_PATTERNS
    ):
        return True
    # And the assignment shape, decided by the same rule that redacts it, so
    # the two never disagree about whether there is anything to hide.
    match = ASSIGNMENT_PATTERN.search(text)
    return bool(match) and _assignment(match) != match.group(0)
