"""Allow-list HTML sanitiser for the markdown preview.

Markdown is rendered into a ``QTextBrowser``, which is a real HTML engine: it
fetches remote images and honours ``href`` on click. Source text is untrusted -
it comes from an AI provider, from a README belonging to any GitHub repository,
or from an issue body - so raw HTML must never reach the widget unchecked.

Without this, a crafted document could:

* point an ``<img>`` at ``file:///`` and have local content loaded;
* hide a ``javascript:`` or ``file:`` link that fires when the user clicks;
* run script or CSS that fetches a URL from the machine;
* reach a ``<iframe>`` or ``<object>``.

The policy is an allow-list: anything not explicitly permitted is dropped, so a
tag or attribute added by a future renderer stays inert by default. GitHub's own
README subset (badges, ``<details>``, ``<p align>``, tables) is preserved.

One thing is deliberately *not* blocked: remote ``http(s)`` images. A README
studio that refuses to show badges is not usable, and GitHub renders them too
(through its camo proxy). That is a deliberate trade of a low-severity
"someone can see which repository I opened" leak against a working product, so
it is recorded here rather than hidden. Everything an image could use to read
the machine - ``file:``, ``data:``, protocol-relative URLs - is refused.
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import unquote

#: Tags kept, mapped to the attributes each may carry.
#: ``*`` entries are allowed on every permitted tag.
ALLOWED_TAGS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title", "target", "rel"}),
    "abbr": frozenset({"title"}),
    "b": frozenset(),
    "blockquote": frozenset({"cite"}),
    "br": frozenset(),
    "code": frozenset({"class"}),
    "dd": frozenset(),
    "del": frozenset(),
    "details": frozenset({"open"}),
    "div": frozenset({"class", "align"}),
    "dl": frozenset(),
    "dt": frozenset(),
    "em": frozenset(),
    "figcaption": frozenset(),
    "figure": frozenset({"align"}),
    "h1": frozenset({"id"}),
    "h2": frozenset({"id"}),
    "h3": frozenset({"id"}),
    "h4": frozenset({"id"}),
    "h5": frozenset({"id"}),
    "h6": frozenset({"id"}),
    "hr": frozenset(),
    "i": frozenset(),
    "img": frozenset({"src", "alt", "title", "width", "height", "align"}),
    "ins": frozenset(),
    "kbd": frozenset(),
    "li": frozenset({"class"}),
    "mark": frozenset(),
    "ol": frozenset({"start", "type"}),
    "p": frozenset({"class", "align"}),
    "pre": frozenset({"class"}),
    "s": frozenset(),
    "samp": frozenset(),
    "small": frozenset(),
    "span": frozenset({"class"}),
    "strong": frozenset(),
    "sub": frozenset(),
    "summary": frozenset(),
    "sup": frozenset(),
    "table": frozenset({"class", "align"}),
    "tbody": frozenset(),
    "td": frozenset({"colspan", "rowspan", "align", "class"}),
    "tfoot": frozenset(),
    "th": frozenset({"colspan", "rowspan", "align", "scope", "class"}),
    "thead": frozenset(),
    "tr": frozenset({"class", "align"}),
    "u": frozenset(),
    "ul": frozenset({"class"}),
    "var": frozenset(),
}

#: Kept on every tag: presentational only, no behaviour.
#:
#: ``style`` is allowed because README authors rely on it for centred headers and
#: coloured text; :func:`_clean_style` strips the declarations that can fetch a
#: URL or execute code.
GLOBAL_ATTRS = frozenset({"class", "id", "title", "dir", "lang", "align", "style"})

#: Schemes a link may point at. Everything else is dropped.
LINK_SCHEMES = frozenset({"http", "https", "mailto"})

#: Schemes an image may load from. Narrower than links: only remote web images.
IMAGE_SCHEMES = frozenset({"http", "https"})

VOID_TAGS = frozenset({"br", "hr", "img"})

#: Tags whose *content* is discarded too, not just the tag itself.
_DROP_CONTENT = frozenset(
    {"script", "style", "iframe", "object", "embed", "applet", "form", "svg", "math"}
)

_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
#: CSS constructs that can fetch a URL or execute code.
_UNSAFE_CSS = re.compile(
    r"(url\s*\(|expression\s*\(|javascript\s*:|@import|behavior\s*:|-moz-binding)",
    re.IGNORECASE,
)
_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]")


def _canonical_url(url: str) -> str:
    """A URL reduced to the form a consumer will actually act on.

    Percent-encoding is peeled more than once on purpose. One pass leaves
    ``%256a%2561vascript:`` as ``%6a%61vascript:``, which carries no scheme and
    would be read as a harmless relative path - until the thing that opens it
    decodes a second time. Peeling to a fixed point means the check and the
    consumer see the same string.

    Control characters go too: ``java\\tscript:`` is a valid scheme to a parser
    that ignores whitespace, and stripping it first closes that route.
    """
    text = str(url or "").strip()
    for _ in range(3):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    return _CONTROL_CHARS.sub("", text)


def is_safe_link(url: str) -> bool:
    """True when a link may be handed to the system browser."""
    text = _canonical_url(url)
    if not text:
        return False
    # A fragment or a relative path never carries a scheme.
    match = _SCHEME_RE.match(text)
    if not match:
        return not text.lower().startswith(("//",))
    return match.group(1).lower() in LINK_SCHEMES


def is_safe_image(url: str) -> bool:
    """True when an image may be fetched by the preview."""
    text = _canonical_url(url)
    match = _SCHEME_RE.match(text)
    if not match:
        # No scheme at all: a relative path or a protocol-relative "//host" both
        # land here, and neither is a remote web image we intended to load.
        return False
    return match.group(1).lower() in IMAGE_SCHEMES


def safe_url(url: str) -> str | None:
    """The canonical form of a URL that may be handed to the OS, else ``None``.

    Separate from :func:`is_safe_link` on purpose. A relative path is fine to
    leave sitting inert in a rendered document, but it must never be *opened*:
    the shell would resolve it against the working directory, which turns a link
    in somebody else's README into a way to open a local file. Only an explicit
    allowed scheme is openable.

    Returning the canonical string also means the caller opens exactly the text
    that was checked, instead of re-parsing a different spelling of it.
    """
    text = _canonical_url(url)
    if not text:
        return None
    match = _SCHEME_RE.match(text)
    if not match or match.group(1).lower() not in LINK_SCHEMES:
        return None
    return text


def _clean_style(value: str) -> str:
    """Strip CSS that can load a remote resource or run code.

    Anything containing ``url()``, ``expression()``, ``@import``, ``behavior`` or
    ``-moz-binding`` is dropped whole - partial CSS filtering is where these
    bypasses live.
    """
    if not value or _UNSAFE_CSS.search(value):
        return ""
    # A comment can be used to split a keyword ("ur/**/l("), so drop those too.
    if "/*" in value or "*/" in value or "\\" in value:
        return ""
    return value.replace('"', "'")


class _Sanitiser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []
        self._skip_depth = 0

    # ------------------------------------------------------------------ tags
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_CONTENT:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag not in ALLOWED_TAGS:
            # Unknown-but-harmless wrappers (a <div> we already allow, or
            # something exotic) lose their markup but keep their text.
            return
        kept = self._attributes(tag, attrs)
        rendered = "".join(f' {name}="{escape(val, quote=True)}"' for name, val in kept)
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}{rendered}>")
            return
        self.out.append(f"<{tag}{rendered}>")
        self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID_TAGS and not self._skip_depth:
            kept = self._attributes(tag, attrs)
            rendered = "".join(f' {n}="{escape(v, quote=True)}"' for n, v in kept)
            self.out.append(f"<{tag}{rendered}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth or tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        if tag not in self._open:
            return
        # Close anything left open inside, so the output stays balanced.
        while self._open:
            current = self._open.pop()
            self.out.append(f"</{current}>")
            if current == tag:
                break

    # ------------------------------------------------------------ attributes
    def _attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
        allowed = ALLOWED_TAGS[tag] | GLOBAL_ATTRS
        kept: list[tuple[str, str]] = []
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = raw_value or ""
            # Event handlers and data-* can smuggle behaviour past a naive check.
            if name.startswith("on") or name.startswith("data-") or name.startswith("xlink"):
                continue
            if name not in allowed:
                continue
            if name == "href":
                if not is_safe_link(value):
                    continue
                value = value.strip()
            elif name == "src":
                if not is_safe_image(value):
                    continue
                value = value.strip()
            elif name == "style":
                cleaned = _clean_style(value)
                if not cleaned:
                    continue
                value = cleaned
            elif name == "target":
                # Only a new browsing context; never a named frame we can be
                # tricked into addressing.
                if value.strip().lower() not in {"_blank", "_self"}:
                    continue
                value = value.strip().lower()
            elif name == "rel":
                value = "noopener noreferrer nofollow"
            kept.append((name, value))
        # Every link gets the same protection regardless of the source document.
        if tag == "a" and any(name == "href" for name, _ in kept):
            kept = [(n, v) for n, v in kept if n not in {"target", "rel"}]
            kept.append(("target", "_blank"))
            kept.append(("rel", "noopener noreferrer nofollow"))
        return kept

    # ------------------------------------------------------------------ text
    def handle_data(self, data: str) -> None:
        """Emit character data as *text*, never as markup.

        ``convert_charrefs=True`` means entities have already been decoded by the
        time this runs, so ``&lt;img src=x onerror=...&gt;`` arrives here as the
        literal text ``<img src=x onerror=...>``. Emitting that verbatim rebuilt
        the tag as real markup, which bypassed the allow-list completely: no
        attribute was ever inspected, so a ``file:`` image or an ``onerror``
        handler survived where the same payload written plainly was stripped.

        Escaping restores the contract - what reaches the output is text, and
        only the allow-list can introduce a tag.
        """
        if self._skip_depth:
            return
        self.out.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:  # noqa: N802
        # Unreachable while convert_charrefs is True, but the raw form is safer
        # than a silently unescaped one if that ever changes.
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:  # noqa: N802
        self.handle_data(f"&#{name};")

    def result(self) -> str:
        while self._open:
            self.out.append(f"</{self._open.pop()}>")
        return "".join(self.out)


def sanitize_html(html: str) -> str:
    """Return ``html`` with everything outside the allow-list removed."""
    if not html:
        return ""
    parser = _Sanitiser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # A parser failure must never fall back to rendering the raw text.
        return escape(html, quote=False)
    return parser.result()
