"""Markdown rendering and code highlighting for the preview pane."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from .sanitize import sanitize_html

_md: MarkdownIt | None = None


def _has_linkify() -> bool:
    try:
        import linkify_it  # noqa: F401

        return True
    except ImportError:
        return False


def markdown_renderer() -> MarkdownIt:
    """CommonMark + GitHub tables / strikethrough, with autolinks if available."""
    global _md  # noqa: PLW0603
    if _md is None:
        rules = ["table", "strikethrough"]
        if _has_linkify():
            rules.append("linkify")
        md = MarkdownIt(
            "commonmark",
            {"html": True, "linkify": _has_linkify(), "typographer": False},
        )
        md.enable(rules)
        _md = md
    return _md


_palette: dict[str, str] | None = None


def set_palette(palette: dict[str, str] | None) -> None:
    """Provide the active theme palette so code blocks get inline colours.

    Qt's rich-text engine ignores padding on ``<pre>``, so the code block has to
    be built from a table with inline styles. Those styles need the palette,
    which is why it is passed in rather than hard-coded.
    """
    global _palette  # noqa: PLW0603
    _palette = palette


def render_markdown(text: str) -> str:
    if not text:
        return '<p style="color:#737373">Nothing to preview yet.</p>'
    try:
        html = markdown_renderer().render(text)
    except Exception:
        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return _code_block(escaped)

    # Source text is untrusted (AI output, another user's README, an issue
    # body), so raw HTML is filtered down to an allow-list before it reaches a
    # widget that would otherwise fetch images and follow links.
    html = sanitize_html(html)
    return _highlight_blocks(html)


# Qt's rich-text engine ignores vertical padding on <pre>, so code blocks are
# rendered inside a single-cell table, which does honour it. The width has to be
# a presentational HTML attribute: Qt drops the whole style attribute if it
# cannot parse every declaration in it.
def _code_cell(inner: str, palette: dict[str, str] | None = None) -> str:
    """Wrap ``inner`` in a padded code block that spans the container width."""
    palette = palette or _fallback_palette()
    table_style = (
        f"background-color:{palette['code_bg']}; border:1px solid {palette['border']}"
    )
    cell_style = (
        f"padding:10px 12px; color:{palette['text']}; "
        f"font-family:{palette['mono']}; line-height:150%; white-space:pre-wrap"
    )
    return (
        f'<table width="100%" cellspacing="0" cellpadding="0" style="{table_style}">'
        f'<tr><td style="{cell_style}">{inner}</td></tr></table>'
    )


def _fallback_palette() -> dict[str, str]:
    """Palette for rendering outside a themed widget (e.g. unit tests).

    Deliberately avoids QFontDatabase: that needs a QGuiApplication and would
    crash in headless scripts.
    """
    if _palette is not None:
        return _palette
    from .theme import DARK

    return {
        "code_bg": DARK["code_bg"],
        "border": DARK["border"],
        "text": DARK["text"],
        "mono": "Cascadia Mono, Consolas, monospace",
    }


_FENCE = re.compile(
    r'<pre><code(?: class="language-([\w+#.-]+)")?>(.*?)</code></pre>', re.DOTALL
)


def _highlight_blocks(html: str) -> str:
    formatter = HtmlFormatter(nowrap=True, cssclass="highlight")

    def replace(match: re.Match[str]) -> str:
        lang = match.group(1) or ""
        code = _unescape(match.group(2))
        try:
            lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
        except (ClassNotFound, ValueError):
            try:
                lexer = guess_lexer(code)
            except (ClassNotFound, ValueError):
                return _code_block(match.group(2))
        try:
            body = highlight(code, lexer, formatter)
        except Exception:
            return _code_block(match.group(2))
        return _code_cell(body)

    return _FENCE.sub(replace, html)


def _code_block(escaped_html: str) -> str:
    return _code_cell(f'<span style="white-space:pre-wrap;">{escaped_html}</span>')


def _unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&amp;", "&")
    )


PYGMENTS_CSS = HtmlFormatter(style="material").get_style_defs(".highlight")


def outline(text: str) -> list[tuple[int, str, str]]:
    """Return ``(level, text, anchor)`` for a markdown document."""
    items: list[tuple[int, str, str]] = []
    in_fence = False
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if not match:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip().rstrip("#").strip()
        anchor = re.sub(r"[^\w\s-]", "", heading.lower()).strip().replace(" ", "-")
        items.append((level, heading, anchor))
    return items


def word_count(text: str) -> tuple[int, int, int]:
    """Return ``(words, characters, lines)`` for the editor status bar."""
    if not text:
        return 0, 0, 0
    return len(text.split()), len(text), text.count("\n") + 1


README_SKELETON = """# Project Name

> One sentence tagline that explains what this project does.

[![Build](https://img.shields.io/badge/build-passing-31c48d)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Python](https://img.shields.io/badge/python-3.11-3776ab)]()
[![Stars](https://img.shields.io/github/stars/OWNER/REPO?style=social)]()

Short paragraph (2-4 lines) describing the problem this project solves and who
it is for.

## Features

- Feature one
- Feature two
- Feature three

## Tech stack

| Layer | Choice |
| --- | --- |
| Language | ... |
| Framework | ... |

## Installation

```bash
pip install project-name
```

## Usage

```python
from project import main

main()
```

## Contributing

Contributions are welcome.

## License

[MIT](LICENSE)
"""
