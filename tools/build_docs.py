"""Build the GitHub Pages site from ``docs_src``.

The site is deliberately dependency-free: plain HTML, CSS and JavaScript, so
there is no toolchain to break and Pages serves exactly what this writes.

Why a hand-written search rather than a library: the content is Persian, and a
generic index breaks on the things Persian text actually contains - Arabic yeh
and kaf that look identical to Persian ones, the ZWNJ in words like
``می‌رود``, and Arabic diacritics. :func:`normalise` handles those, so typing
``مي رود`` still finds ``می‌رود``.

Usage:
    python tools/build_docs.py
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from html import escape
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

#: Ordered navigation. Each entry maps to ``docs_src/pages/<slug>.md``.
NAV = [
    ("index", "خانه"),
    ("features", "قابلیت‌ها"),
    ("install", "نصب و راه‌اندازی"),
    ("ai", "هوش مصنوعی"),
    ("security", "امنیت"),
    ("build", "ساخت از سورس"),
    ("faq", "سوالات متداول"),
]

#: Heading anchors per page, filled in during the build so the link checker
#: knows which ``page.html#anchor`` targets actually exist.
ANCHORS: dict[str, list[str]] = {}


# --------------------------------------------------------------- normalising
_ZWNJ = "‌"
_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭ]")
_TATWEEL = re.compile(r"ـ+")
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})


def normalise(text: str) -> str:
    """Fold Persian text so a loosely typed query still matches."""
    value = unicodedata.normalize("NFKC", text or "")
    value = value.translate(
        {
            ord("ي"): "ی",  # ARABIC YEH -> FARSI YEH
            ord("ى"): "ی",  # ALEF MAKSURA -> FARSI YEH
            ord("ك"): "ک",  # ARABIC KAF -> KEHEH
            ord("ﭐ"): "ک",  # ARABIC SWASH KAF -> KEHEH
            ord("ة"): "ه",  # TEH MARBUTA -> HEH
            ord("ؤ"): "و",  # WAW WITH HAMZA -> WAW
            ord("إ"): "ا",  # ALEF WITH HAMZA BELOW -> ALEF
            ord("أ"): "ا",  # ALEF WITH HAMZA ABOVE -> ALEF
            ord("آ"): "ا",  # ALEF WITH MADDA -> ALEF
            ord(_ZWNJ): " ",  # ZERO WIDTH NON-JOINER
            "‌": " ",  # ZWNJ, if it survived as a literal
        }
    )
    value = value.translate(_DIGIT_MAP)
    value = _DIACRITICS.sub("", value)
    value = _TATWEEL.sub("", value)
    value = re.sub(r"[^\w\s؀-ۿ]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().lower()


def slugify(text: str) -> str:
    """URL fragment for a heading; keeps Persian letters readable."""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = re.sub(r"[^\w\s؀-ۿ-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_]+", "-", value.strip())
    return value.strip("-") or "بخش"


# ------------------------------------------------------------------ markdown
# Raw HTML is allowed here on purpose. The input is the repository's own
# markdown, which is trusted and reviewed in the same pull request as the code.
# This is a different trust boundary from the application, where markdown can
# come from a model or another user's repository and must go through
# app/ui/sanitize.py instead.
_md = MarkdownIt("commonmark", {"html": True, "linkify": True})
_md.enable(["table", "strikethrough"])

_slug_counts: dict[str, int] = {}


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
    return html, headings


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
    nav_html = "".join(
        f'<a class="nav-link{" is-active" if key == slug else ""}" href="{key}.html">'
        f"{escape(label)}</a>"
        for key, label in NAV
    )
    toc_html = ""
    if toc:
        items = "".join(
            f'<li class="toc-item toc-level-{level}">'
            f'<a href="#{anchor}">{escape(text)}</a></li>'
            for level, text, anchor in toc
        )
        toc_html = f'<nav class="toc" aria-label="فهرست این صفحه"><p class="toc-title">در این صفحه</p><ul>{items}</ul></nav>'

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · GitHub Manager</title>
<meta name="description" content="{escape(description)}">
<link rel="stylesheet" href="assets/style.css">
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<meta property="og:title" content="{escape(title)} · GitHub Manager">
<meta property="og:description" content="{escape(description)}">
</head>
<body>
<a class="skip" href="#main">پرش به محتوا</a>

<header class="site-header">
  <div class="bar">
    <button class="icon-btn nav-toggle" id="navToggle" aria-label="منو" aria-expanded="false">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
    </button>

    <a class="brand" href="index.html">
      <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="9" r="2.6"/>
        <path d="M6 8.6v6.8M8.4 7.2h4.2a4 4 0 0 1 4 1.4"/>
      </svg>
      <span>GitHub Manager</span>
    </a>

    <div class="search" role="search">
      <svg class="search-icon" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>
      </svg>
      <input id="searchInput" type="search" placeholder="جستجو در مستندات…"
             autocomplete="off" aria-label="جستجو در مستندات" aria-controls="searchResults">
      <kbd class="hint" id="searchHint">Ctrl K</kbd>
      <div class="results" id="searchResults" hidden></div>
    </div>

    <div class="actions">
      <button class="icon-btn" id="themeToggle" aria-label="تغییر پوسته">
        <svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4.5"/>
          <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4"/>
        </svg>
        <svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>
        </svg>
      </button>
      <a class="icon-btn" href="{REPO_URL}" target="_blank" rel="noopener noreferrer" aria-label="مخزن روی گیت‌هاب">
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
      <a class="btn btn-primary" href="{EXE_URL}">دانلود نسخه ۱.۰.۰</a>
      <p class="muted">یک فایل exe · بدون نیاز به نصب پایتون</p>
    </div>
  </aside>

  <main id="main" class="content">
{body}
{toc_html}
    <footer class="page-foot">
      <p>متن و کد این پروژه تحت مجوز MIT منتشر شده است.</p>
      <p><a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">مخزن گیت‌هاب</a> · <a href="{RELEASES_URL}" target="_blank" rel="noopener noreferrer">انتشارها</a></p>
    </footer>
  </main>
</div>

<script src="assets/search.js"></script>
<script src="assets/app.js"></script>
</body>
</html>
"""


def front_matter(text: str) -> tuple[str, str, str]:
    """Split optional ``---`` front matter into (title, description, body)."""
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
    pages = {slug for slug, _ in NAV}
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

    for slug, nav_title in NAV:
        source = pages_dir / f"{slug}.md"
        if not source.exists():
            print(f"  MISSING {source}")
            continue
        title, description, body_md = front_matter(
            source.read_text(encoding="utf-8")
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
    """Slice out the text of one heading section for the search index."""
    match = re.search(
        rf'<h[23] id="{re.escape(anchor)}".*?</h[23]>(.*?)(?=<h[23] id=|$)',
        body_html,
        re.DOTALL,
    )
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(build())