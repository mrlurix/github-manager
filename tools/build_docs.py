"""Build the GitHub Pages site from ``docs_src``.

The site is deliberately dependency-free: plain HTML, CSS and JavaScript, so
there is no toolchain to break and Pages serves exactly what this writes.

Why a hand-written search rather than a library: the content mixes scripts and
typography in the ways technical prose always does - Latin accents, curly
apostrophes and en dashes, ``Ctrl+N`` rather than ``ctrl+n``, plus Arabic text
wherever a Persian README is discussed. A generic index breaks on exactly that,
so :func:`normalise` folds case, accents, typographic punctuation and Arabic
letter variants into one canonical form. ``do not``, ``Do not`` and ``Do
n’t`` all reach the same entry.

Usage:
    python tools/build_docs.py
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs_src"
OUT = ROOT / "docs"

REPO_URL = "https://github.com/mrlurix/github-manager"
RELEASES_URL = f"{REPO_URL}/releases/latest"
# "/releases/latest/download/<name>" follows whatever the newest tag is, so the
# link keeps working after the next release. Hardcoding a tag here would 404.
EXE_URL = f"{RELEASES_URL}/download/GitHubManager.exe"

#: Kept in step with app/config.py. Only used for the visible download label, so
#: a mismatch is cosmetic, but it is still wrong to show a stale version.
APP_VERSION = "1.3.0"

#: Ordered navigation. Each entry maps to ``docs_src/pages/<slug>.md``.
#: Grouped so the sidebar reads as sections rather than one flat list, which is
#: what makes a ten-item set scannable.
NAV = [
    ("index", "Home", "Start here"),
    ("features", "Features", "What the app can do"),
    ("install", "Getting started", None),
    ("ai", "AI", "How the assistant works"),
    ("security", "Security", None),
    ("build", "Building from source", None),
    ("faq", "FAQ", "Answers and troubleshooting"),
]

#: Heading anchors per page, filled in during the build so the link checker
#: knows which ``page.html#anchor`` targets actually exist.
ANCHORS: dict[str, list[str]] = {}


# --------------------------------------------------------------- normalising
# The browser applies the same folding (see docs_src/assets/search.js). The two
# implementations have to agree step for step, or a query silently stops matching
# text that is visibly right in front of the reader.
_ZWNJ = "\u200c"
_TATWEEL = re.compile("\u0640+")
# A non-letter, non-digit, non-space becomes a space. Unicode-aware on purpose:
# an ASCII \w class would cut an accented letter out of the middle of a word,
# so "caf\u00e9" would index as "caf" followed by nothing useful.
_PUNCT = re.compile(r"[^\w\s\u0600-\u06ff]+", re.UNICODE)
_DIGIT_MAP = {
    ord(c): str(i) for i, c in enumerate("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")
}
_DIGIT_MAP.update(
    {ord(c): str(i) for i, c in enumerate("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")}
)
# Characters that read as ASCII but are stored as something else, so a query typed
# with a straight apostrophe still matches text written with a curly one.
_TYPOGRAPHIC = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"',
        "\u2013": "-", "\u2014": "-", "\u2012": "-", "\u2212": "-",
        "\u2011": "-", "\u2010": "-", "\u2043": "-",
    }
)
_LETTER_VARIANTS = {
    ord("\u064a"): "\u06cc",  # ARABIC YEH       -> FARSI YEH
    ord("\u0649"): "\u06cc",  # ALEF MAKSURA     -> FARSI YEH
    ord("\u0643"): "\u06a9",  # ARABIC KAF       -> KEHEH
    ord("\ufb50"): "\u06a9",  # ARABIC SWASH KAF -> KEHEH
    ord("\ufb90"): "\u06a9",  # ARABIC KAF WITH ATTACHED FATHA
    ord("\ufb91"): "\u06a9",  # ARABIC KAF WITH ATTACHED TOP RIGHT FATHA
    ord("\u0629"): "\u0647",  # TEH MARBUTA      -> HEH
    ord("\u0624"): "\u0648",  # WAW WITH HAMZA   -> WAW
    ord("\u0625"): "\u0627",  # ALEF WITH HAMZA BELOW -> ALEF
    ord("\u0623"): "\u0627",  # ALEF WITH HAMZA ABOVE -> ALEF
    ord("\u0622"): "\u0627",  # ALEF WITH MADDA  -> ALEF
    ord(_ZWNJ): " ",  # ZERO WIDTH NON-JOINER
    "\u200c": " ",  # ZWNJ, if it survived as a literal
}


def _strip_marks(value: str) -> str:
    r"""Drop every combining mark, whatever script it belongs to.

    The standard library's ``re`` has no ``\p{...}`` character classes, so the
    Unicode category is tested directly instead. Category ``M`` covers the Latin
    accents and the Arabic vowel marks alike.
    """
    return "".join(ch for ch in value if not unicodedata.category(ch).startswith("M"))


def normalise(text: str) -> str:
    """Fold text so a loosely typed query still matches.

    Case, Latin accents, typographic punctuation, Arabic letter variants and
    non-ASCII digits all collapse to one canonical form.
    """
    value = unicodedata.normalize("NFKC", text or "")
    # Split into combining marks, drop them, recompose.
    value = unicodedata.normalize("NFD", value)
    value = _strip_marks(value)
    value = unicodedata.normalize("NFC", value)
    value = value.translate(_LETTER_VARIANTS)
    value = value.translate(_DIGIT_MAP)
    value = value.translate(_TYPOGRAPHIC)
    value = _TATWEEL.sub("", value)
    value = _PUNCT.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip().lower()



def slugify(text: str) -> str:
    """URL fragment for a heading; keeps non-ASCII letters readable."""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = re.sub(r"[^\w\s؀-ۿ-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "-", value.strip())
    return value.strip("-") or "section"


# ------------------------------------------------------------------ markdown
# Raw HTML is allowed here on purpose: the landing page needs a hero block and a
# card grid, which markdown has no syntax for. The input is the repository's own
# markdown, reviewed in the same pull request as the code.
#
# That is a weaker guarantee than it looks, though. A typo, a bad merge, or a
# compromised account can put a <script> into one of these files, and the output
# is served from GitHub Pages with no review step in front of it. So the rendered
# body is put through an allow-list on the way out (:func:`sanitize_body`) and the
# pages carry a Content-Security-Policy that refuses inline script even if
# something got past it.
#
# This is a different trust boundary from the application, where markdown can
# come from a model or another user's repository and must go through
# app/ui/sanitize.py instead.
_md = MarkdownIt("commonmark", {"html": True, "linkify": True})
_md.enable(["table", "strikethrough"])

_slug_counts: dict[str, int] = {}

#: Tags the documentation is allowed to use. The hero and card grid need div,
#: span and their class attributes; everything else is ordinary prose markup.
_ALLOWED_TAGS = frozenset(
    """a abbr b blockquote br caption cite code dd del div dl dt em figcaption figure h1
    h2 h3 h4 h5 h6 hr i img ins kbd li mark ol p pre q s samp small span strong sub sup
    summary details table tbody td tfoot th thead tr u ul var""".split()
)
_ALLOWED_ATTRS = frozenset(
    """href src alt title id class colspan rowspan scope align width height target rel
    lang dir start type open""".split()
)
#: ``style`` is deliberately absent. CSS can fetch a URL and report where the
#: reader is, and nothing in these pages needs an inline declaration - present it
#: with an extra class in assets/style.css instead.
#: Tags whose content goes with them.
_DROP_CONTENT = frozenset(
    "script style iframe object embed applet form svg math frame frameset template noscript".split()
)
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
_LINK_SCHEMES = frozenset({"http", "https", "mailto"})
_CONTROL_CHARS = re.compile(r"[\x00-\x20\x7f]")


def _safe_href(value: str) -> bool:
    """True for a link this site is willing to emit."""
    text = _CONTROL_CHARS.sub("", str(value or ""))
    match = _SCHEME_RE.match(text)
    if not match:
        return not text.startswith("//")
    return match.group(1).lower() in _LINK_SCHEMES


def _safe_src(value: str) -> bool:
    """True for an image source. Local paths only: nothing is loaded remotely."""
    text = _CONTROL_CHARS.sub("", str(value or ""))
    match = _SCHEME_RE.match(text)
    if not match:
        return not text.startswith("//") and ".." not in text
    return match.group(1).lower() in {"http", "https"}


class _BodySanitiser(HTMLParser):
    """Allow-list filter for the rendered page body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open: list[str] = []
        self.skip = 0

    def _attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        parts: list[str] = []
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = raw_value or ""
            if name.startswith("on") or name not in _ALLOWED_ATTRS:
                continue
            if name == "href" and not _safe_href(value):
                continue
            if name == "src" and not _safe_src(value):
                continue
            if name == "target" and value.strip().lower() not in {"_blank", "_self"}:
                continue
            parts.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a" and any(p.startswith(" href=") for p in parts):
            parts = [p for p in parts if not p.startswith((" target=", " rel="))]
            parts.append(' target="_blank"')
            parts.append(' rel="noopener noreferrer"')
        return "".join(parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in _ALLOWED_TAGS:
            return
        self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")
        if tag not in {"br", "hr", "img"}:
            self.open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.skip and tag in {"br", "hr", "img"}:
            self.out.append(f"<{tag}{self._attrs(tag, attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROP_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in _ALLOWED_TAGS or tag not in self.open:
            return
        while self.open:
            current = self.open.pop()
            self.out.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        # Decoded entities are re-emitted as text, never as markup. Without the
        # escape, `&lt;script&gt;` in a markdown file would become a real tag.
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def result(self) -> str:
        while self.open:
            self.out.append(f"</{self.open.pop()}>")
        return "".join(self.out)


def sanitize_body(html: str) -> str:
    """Filter the rendered markdown down to the tags this site uses."""
    if not html:
        return ""
    parser = _BodySanitiser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # A parse failure must never fall back to emitting the raw document.
        return f"<pre>{escape(html)}</pre>"
    return parser.result()


def render(markdown_text: str) -> tuple[str, list[str]]:
    """Render markdown, adding ids to headings. Returns html and the TOC."""
    _slug_counts.clear()
    tokens = _md.parse(markdown_text)
    headings: list[tuple[int, str, str]] = []

    for token in tokens:
        if token.type != "heading_open":
            continue
        index = tokens.index(token)
        inline = tokens[index + 1]
        title = inline.content.strip()
        level = int(token.tag[1])
        base = slugify(title)
        _slug_counts[base] = _slug_counts.get(base, 0) + 1
        anchor = base if _slug_counts[base] == 1 else f"{base}-{_slug_counts[base]}"
        token.attrSet("id", anchor)
        if level in (2, 3):
            headings.append((level, title, anchor))

    html = _md.renderer.render(tokens, _md.options, {})
    # markdown-it escapes code blocks; external links get the usual treatment.
    html = re.sub(
        r'<a href="(https?://[^"]+)"',
        r'<a href="\1" target="_blank" rel="noopener noreferrer">',
        html,
    )
    return sanitize_body(html), headings


_TAG_RE = re.compile(r"<[^>]+>")


def to_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


# -------------------------------------------------------------------- layout
def layout(
    slug: str,
    title: str,
    description: str,
    body: str,
    toc: list[tuple[int, str, str]],
) -> str:
    nav_parts: list[str] = []
    caption = None
    for key, label, _blurb in NAV:
        if _blurb:
            if caption:
                nav_parts.append(f'<p class="nav-caption">{escape(caption)}</p>')
            caption = _blurb
        active = key == slug
        nav_parts.append(
            f'<a class="nav-link{" is-active" if active else ""}" href="{key}.html"'
            + (' aria-current="page"' if active else "")
            + f">{escape(label)}</a>"
        )
    nav_html = "".join(nav_parts)

    toc_html = ""
    if toc:
        items = "".join(
            f'<li class="toc-item toc-level-{level}">'
            f'<a href="#{anchor}">{escape(text)}</a></li>'
            for level, text, anchor in toc
        )
        toc_html = (
            f'<nav class="toc" aria-labelledby="toc-heading">'
            f'<p class="toc-title" id="toc-heading">On this page</p>'
            f"<ul>{items}</ul></nav>"
        )

    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Pages are served straight from this folder with no header of our own, so the
     policy travels with the document. It refuses inline script and event handler
     attributes even if something slipped past the body sanitiser, which is what
     turns a mistake in a markdown file into broken markup instead of a compromise.
     'unsafe-inline' is needed for style only, because markdown carries style
     attributes. -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://rsms.me; font-src 'self' https://rsms.me data:; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{escape(title)} · GitHub Manager</title>
<meta name="description" content="{escape(description)}">
<link rel="preconnect" href="https://rsms.me/inter" crossorigin>
<link rel="stylesheet" href="https://rsms.me/inter/inter.css">
<link rel="stylesheet" href="assets/style.css">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<meta property="og:title" content="{escape(title)} · GitHub Manager">
<meta property="og:description" content="{escape(description)}">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>

<header class="site-header">
  <div class="bar">
    <button class="icon-btn nav-toggle" id="navToggle" aria-label="Menu" aria-expanded="false">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>

    <a class="brand" href="index.html">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="6" cy="5" r="2.4"/><circle cx="6" cy="19" r="2.4"/><circle cx="18" cy="12" r="2.4"/>
        <path d="M6 7.4v9.2M8.4 6.1h4.6a4.6 4.6 0 0 1 4.6 4.6v-.3M15.6 17.9h-4.6A4.6 4.6 0 0 1 6.4 13.3v-.3"/>
      </svg>
      <span>GitHub&nbsp;Manager</span>
    </a>

    <div class="search" role="search">
      <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>
      </svg>
      <input id="searchInput" type="search" placeholder="Search the docs…"
             autocomplete="off" aria-label="Search the documentation" aria-controls="searchResults">
      <kbd class="hint" id="searchHint">Ctrl K</kbd>
      <div class="results" id="searchResults" hidden></div>
    </div>

    <div class="actions">
      <button class="icon-btn" id="themeToggle" aria-label="Switch theme">
        <svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5"/>
          <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"/>
        </svg>
        <svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>
        </svg>
      </button>
      <a class="icon-btn" href="{REPO_URL}" target="_blank" rel="noopener noreferrer" aria-label="Repository on GitHub">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.6 2.8 5.5 3.1 5.5 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21"/>
        </svg>
      </a>
    </div>
  </div>
</header>

<div class="shell">
  <aside class="sidebar" id="sidebar">
    <nav class="nav">{nav_html}</nav>
    <div class="sidebar-foot">
      <a class="btn btn-primary" href="{EXE_URL}" target="_blank" rel="noopener noreferrer">Download {APP_VERSION}</a>
      <p class="muted">One exe file · no Python needed</p>
    </div>
  </aside>

  <main id="main" class="content">
{body}
{toc_html}
    <footer class="page-foot">
      <nav class="foot-nav" aria-label="Footer">
        <a href="{RELEASES_URL}" target="_blank" rel="noopener noreferrer">Releases</a>
        <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">Repository</a>
        <a href="{REPO_URL}/issues" target="_blank" rel="noopener noreferrer">Report an issue</a>
        <a href="{REPO_URL}/blob/main/LICENSE" target="_blank" rel="noopener noreferrer">MIT licence</a>
      </nav>
      <p class="muted-foot">GitHub Manager {APP_VERSION} &middot; portable Windows client</p>
    </footer>
  </main>
</div>

<script src="assets/search.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
"""


def front_matter(text: str) -> tuple[str, str, str]:
    """Split optional ``---`` front matter into (title, description, body).

    A leading BOM is stripped first. Without that, a file saved by a Windows
    editor starts with ``\ufeff---`` rather than ``---``, the block is not
    recognised as front matter, and it renders into the page as visible
    content. That is a silent failure - the build still succeeds - so it is
    worth handling rather than relying on every contributor saving without one.
    """
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return "", "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", "", text
    head = text[3:end]
    body = text[end + 4 :].lstrip("\n")
    title = description = ""
    for line in head.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"')
        if key.strip() == "title":
            title = value
        elif key.strip() == "description":
            description = value
    return title, description, body


def check_internal_links() -> int:
    """Fail if a page links to a page that does not exist.

    Cheap, and it catches the failure that actually happens: adding a nav entry
    or renaming a slug and leaving the old hrefs behind.
    """
    broken: list[str] = []
    pages = {slug for slug, _label, _blurb in NAV}
    known_targets = {f"{slug}.html" for slug in pages} | {
        f"{slug}.html#{anchor}" for slug in pages for anchor in ANCHORS.get(slug, ())
    }

    for path in sorted(OUT.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', text):
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if href in known_targets or href in {"assets/style.css", "assets/favicon.svg"}:
                continue
            broken.append(f"{path.name} -> {href}")

    if broken:
        print("  BROKEN internal links:")
        for item in broken:
            print("    " + item)
        return 1
    print("  internal links OK")
    return 0


# --------------------------------------------------------------------- build
def build() -> int:
    pages_dir = SRC / "pages"
    OUT.mkdir(parents=True, exist_ok=True)
    assets_out = OUT / "assets"
    if assets_out.exists():
        shutil.rmtree(assets_out)
    shutil.copytree(SRC / "assets", assets_out)

    index: list[dict[str, object]] = []

    for slug, nav_title, _blurb in NAV:
        source = pages_dir / f"{slug}.md"
        if not source.exists():
            print(f"  MISSING {source}")
            continue
        raw_source = source.read_text(encoding="utf-8")
        title, description, body_md = front_matter(raw_source)
        if not title and raw_source.lstrip("\ufeff").startswith("---"):
            raise SystemExit(
                f"{source.name}: the front matter block was not parsed and would "
                "render as page content."
            )
        title = title or nav_title
        body_html, headings = render(body_md)
        ANCHORS[slug] = [anchor for _, _, anchor in headings]

        # Index every heading as its own searchable entry.
        page_text = to_text(body_html)
        index.append(
            {
                "url": f"{slug}.html",
                "page": nav_title,
                "title": title,
                "raw": page_text[:4000],
                "text": page_text[:4000],
            }
        )
        for level, text, anchor in headings:
            section_text = to_text(_section_html(body_html, anchor))
            index.append(
                {
                    "url": f"{slug}.html#{anchor}",
                    "page": nav_title,
                    "title": text,
                    "heading": text,
                    "level": level,
                    "raw": section_text[:900],
                    "text": section_text[:900],
                }
            )

        (OUT / f"{slug}.html").write_text(
            layout(slug, title, description, body_html, headings),
            encoding="utf-8",
        )
        print(f"  built {slug}.html  ({len(body_html):,} bytes, {len(headings)} headings)")

    index.sort(key=lambda item: (str(item["page"]), str(item["title"])))
    (OUT / "search-index.json").write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  built search-index.json  ({len(index)} entries)")
    return check_internal_links()


def _section_html(body_html: str, anchor: str) -> str:
    """Slice out the text of one heading section for the search index.

    The section includes everything nested under it, and only ends at a heading
    of the same level or shallower. Stopping at the next heading of any level
    would leave every parent section empty whenever it is immediately followed
    by a subheading - which is most of the FAQ page - and a search hit would
    then show a title with a blank excerpt.
    """
    opening = re.search(
        rf'<h([23]) id="{re.escape(anchor)}"[^>]*>.*?</h\1>',
        body_html,
        re.DOTALL,
    )
    if opening is None:
        return ""
    level = int(opening.group(1))
    rest = body_html[opening.end() :]
    end = len(rest)
    for tag in re.finditer(r'<h([23]) id="[^"]*"', rest):
        if int(tag.group(1)) <= level:
            end = tag.start()
            break
    return rest[:end]


if __name__ == "__main__":
    raise SystemExit(build())