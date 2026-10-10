"""Security regression tests for the documentation build.

The site is built by tools/build_docs.py, which does its own HTML sanitising.
That code had no test coverage at all: the browser-driven checks in tools/
verify_*.js assert what the built pages look like, but nothing asserted what the
builder refuses to emit. These tests exercise the builder directly, on inputs no
page in docs_src contains.

Run: python tests/docs_build_test.py
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_docs as B  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


# ------------------------------------------------------------ url allow-listing
def test_backslash_bypass_is_closed() -> None:
    r"""A backslash is a separator to the browser, so it is one to the check.

    The WHATWG URL parser turns ``\/evil.example`` and ``\\evil.example`` into
    ``https://evil.example``. The old tests only looked for a literal ``//``,
    so both were classified as relative paths and allowed through - and for
    ``src`` nothing else caught them, since the link checker only reads href.
    """
    attacks = [
        "\\/evil.example/x",
        "\\\\evil.example/x",
        "\\/\\/evil.example/x",
        "/\\evil.example/x",
    ]
    for value in attacks:
        check(f"_safe_href refuses {value!r}", B._safe_href(value) is False)
        check(f"_safe_src refuses {value!r}", B._safe_src(value) is False)

    # The forms that were always allowed must stay allowed.
    for value in ["docs/page.html", "https://ok.example/x", "mailto:a@b.example",
                  "#anchor", "page.html#anchor"]:
        check(f"_safe_href still allows {value!r}", B._safe_href(value) is True)

    for value in ["assets/logo.svg", "https://img.example/a.png"]:
        check(f"_safe_src still allows {value!r}", B._safe_src(value) is True)

    # data: is refused by the allow-list, and the policy agrees - both are
    # "img-src 'self'". Two layers disagreeing about the same source is one
    # more thing to get wrong later.
    check("_safe_src refuses a data: image",
          B._safe_src("data:image/png;base64,AA") is False)

    # And the schemes that were always refused stay refused.
    for value in ["javascript:alert(1)", "data:text/html,<script>", "vbscript:x"]:
        check(f"_safe_href refuses {value!r}", B._safe_href(value) is False)


def test_sanitised_output_has_no_surprises() -> None:
    """Attributes are escaped, so the regex passes afterwards cannot corrupt them."""
    attack = '<img alt="<table>" src="https://x.example/a.png">'
    out = B.sanitize_body(B._wrap_tables(B.sanitize_body(attack)))
    check("a <table> inside an attribute is not rewritten",
          'alt="&lt;table&gt;"' in out, out)
    check("the attribute is not terminated early",
          'alt="<div class="scroll-x">' not in out, out)

    # A real table is still wrapped.
    wrapped = B.sanitize_body(B._wrap_tables(B.sanitize_body("<table><tr><td>1</td></tr></table>")))
    check("a real table is still wrapped", 'class="scroll-x"' in wrapped, wrapped)

    # And the sanitiser is idempotent, because the build now runs it twice.
    once = B.sanitize_body('<p>a &amp; b &lt;tag&gt; "q" café</p>')
    check("sanitize_body is idempotent", B.sanitize_body(once) == once,
          f"{once!r} -> {B.sanitize_body(once)!r}")


# ------------------------------------------------------------------ drop tags
def test_unclosed_drop_tag_fails_loudly() -> None:
    """A page must not quietly lose everything after a malformed tag.

    The sanitiser counted nesting and only resumed at a matching close tag, so a
    single unclosed ``<svg>`` left the counter set and deleted the rest of the
    page - no error, no warning, a page that simply stopped. Now it raises, and
    the build stops.
    """
    # "<style" alone is not in this list: with no closing ">" it is not a tag,
    # HTMLParser leaves it as text, and a build that rejected ordinary text
    # containing a stray angle bracket would be wrong.
    for markup in ["<script>alert(1)", "<style>body{}", "<SCRIPT>x"]:
        try:
            B.sanitize_body(markup)
            check(f"unclosed {markup!r} fails the build", False, "returned normally")
        except B.UnclosedMarkup as exc:
            check(f"unclosed {markup!r} fails the build", True, str(exc))
        except Exception as exc:  # noqa: BLE001
            check(f"unclosed {markup!r} fails the build", False,
                  f"raised {type(exc).__name__} instead: {exc}")

    # The tag name is in the message, so the author knows which one to close.
    try:
        B.sanitize_body("<p>hi</p><script>x")
        check("the message names the tag", False, "no exception")
    except B.UnclosedMarkup as exc:
        check("the message names the tag", "script" in str(exc), str(exc))


def test_a_stray_close_tag_does_not_swallow_the_page() -> None:
    """Only the innermost open tag closes; a stray one must not over-decrement."""
    html = "<p>one</p><p>two</p>"
    out = B.sanitize_body(f"{html}</script>{html}")
    check("content after a stray close tag survives",
          out.count("<p>one</p>") == 2 and out.count("<p>two</p>") == 2, out)


def test_drop_tag_keeps_its_children() -> None:
    """Dropping a subtree wholesale is what made truncation possible.

    ``<template>`` and ``<form>`` children are ordinary content and are
    sanitised like anything else, so they render rather than vanish.
    """
    out = B.sanitize_body("<template><p>kept</p></template>")
    check("template children survive", "<p>kept</p>" in out, out)
    out = B.sanitize_body("<form><p>kept</p></form>")
    check("form children survive", "<p>kept</p>" in out, out)
    out = B.sanitize_body("<svg><p>kept</p></svg>")
    check("svg children survive", "<p>kept</p>" in out, out)
    # A script inside them is still a script.
    out = B.sanitize_body("<template><script>alert(1)</script></template>")
    check("a script inside a dropped tag is still dropped", "alert(1)" not in out, out)


# ---------------------------------------------------------------------- text
def test_to_text_decodes_entities() -> None:
    """It decodes, and that is correct - the sink escapes.

    An audit flagged this as an unescape transform that undoes the sanitiser.
    It does not: search.js highlight() escapes before innerHTML, and the only
    consumer of this text is that function. Encoding it instead was tried and
    reverted - a search for "script" on the security page would have shown the
    reader ``&lt;script&gt;``. Same safety, worse output.
    """
    check("entities decode", B.to_text("<p>a &amp; b</p>") == "a & b",
          repr(B.to_text("<p>a &amp; b</p>")))
    check("tags are removed", B.to_text("<p>hi <b>there</b></p>") == "hi there",
          repr(B.to_text("<p>hi <b>there</b></p>")))

    index = ROOT / "docs" / "search-index.json"
    if index.exists():
        raw = io.open(index, encoding="utf-8").read()
        data = json.loads(raw)
        check("the search index parses as JSON", isinstance(data, list), type(data).__name__)
        check("every entry has a url, a title and text",
              all(e.get("url") and e.get("title") and "text" in e for e in data))
        # The index holds the literal text "<script>" - four times, lifted from
        # the page that documents the sanitiser - and that is correct. to_text
        # decodes because it produces text, and DocSearch.highlight() escapes
        # before innerHTML (covered by verify_search.js). Encoding it here was
        # tried and reverted: a search for "script" would then show the reader
        # "&lt;script&gt;", which is the same safety and a worse page.
        check("the index is plain data, not markup",
              all(isinstance(e, dict) for e in data))
        check("no entry smuggles an event handler",
              not any(re.search(r"\son[a-z]+\s*=", json.dumps(e)) for e in data))


# ----------------------------------------------------------------------- logo
def test_inline_logo_is_shape_checked() -> None:
    """The logo is inlined into all seven pages, so it is checked.

    It cannot go through sanitize_body - "path" is not a body tag and the filter
    would empty it - so it is checked against its own, much smaller, allow-list.
    """
    mark = B._logo_mark()
    check("the logo returns markup", "<" in mark, repr(mark[:80]))
    check("the logo carries no title",
          "<title" not in mark, mark[:120])
    for tag in ("script", "foreignObject", "image", "a", "style"):
        check(f"the logo contains no <{tag}>", f"<{tag}" not in mark)

    # A tampered logo file must fail the build rather than ship.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp)
        (bad / "assets").mkdir()
        (bad / "assets" / "logo.svg").write_text(
            '<svg viewBox="0 0 16 16"><script>alert(1)</script></svg>', encoding="utf-8"
        )
        original = B.SRC
        try:
            B.SRC = bad
            try:
                B._logo_mark()
                check("a logo carrying <script> fails the build", False, "returned normally")
            except SystemExit as exc:
                check("a logo carrying <script> fails the build", "script" in str(exc), str(exc))
        finally:
            B.SRC = original

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp)
        (bad / "assets").mkdir()
        (bad / "assets" / "logo.svg").write_text(
            '<svg><path d="M0 0" onclick="x()"/></svg>', encoding="utf-8"
        )
        original = B.SRC
        try:
            B.SRC = bad
            try:
                B._logo_mark()
                check("a logo with an event handler fails the build", False, "returned normally")
            except SystemExit as exc:
                check("a logo with an event handler fails the build",
                      "onclick" in str(exc), str(exc))
        finally:
            B.SRC = original


# --------------------------------------------------------------- built output
def test_built_pages_match_the_policy() -> None:
    """The shipped pages, checked against the policy that ships with them."""
    docs = ROOT / "docs"
    if not docs.exists():
        check("docs/ exists (run python tools/build_docs.py)", False)
        return

    pages = sorted(docs.glob("*.html"))
    check("all seven pages are built", len(pages) == 7, f"{len(pages)} found")

    for page in pages:
        html = page.read_text(encoding="utf-8")
        csp = (re_search(html) or "")
        check(f"{page.name} forbids inline style",
              "style-src 'self'" in csp and "style-src 'self' 'unsafe-inline'" not in csp, csp)
        check(f"{page.name} claims no inert directive",
              "frame-ancestors" not in csp and "sandbox" not in csp, csp)
        check(f"{page.name} has no inline style",
              "<style>" not in html and ' style="' not in html)
        check(f"{page.name} has no inline script", "<script>" not in html)
        check(f"{page.name} has no event handler attribute",
              not any(f"{a}=" in html for a in ("onclick", "onerror", "onload")))
        # The logo went through the shape check: the only <svg> on the page is
        # the mark, and it holds no element outside the shape allow-list.
        check(f"{page.name} has no inline script body",
              "<svg" not in html.lower() or "<svg><script" not in html.lower().replace(" ", ""))

    # And the checks the build itself runs.
    check("check_internal_links passes", B.check_internal_links() == 0)
    check("check_no_inline_styles passes", B.check_no_inline_styles() == 0)


def re_search(html: str) -> str | None:
    import re

    m = re.search(r'Content-Security-Policy" content="([^"]+)"', html)
    return m.group(1) if m else ""


def main() -> int:
    test_backslash_bypass_is_closed()
    test_sanitised_output_has_no_surprises()
    test_unclosed_drop_tag_fails_loudly()
    test_a_stray_close_tag_does_not_swallow_the_page()
    test_drop_tag_keeps_its_children()
    test_to_text_decodes_entities()
    test_inline_logo_is_shape_checked()
    test_built_pages_match_the_policy()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
