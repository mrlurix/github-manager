"""Render every page to a PNG.

These are the pictures in the README, so they have to be right, and the thing
that makes them wrong is invisible unless you look for it.

Qt's ``offscreen`` platform has no fonts. It renders every glyph as an empty
box, which looks like a broken font at a glance and is easy to mistake for a
rendering fault in the app. Every screenshot this tool produced under offscreen
showed placeholder boxes for all text - a README of unreadable pictures.

So the platform is no longer forced. It defaults to ``windows``, which is the
real thing and has real fonts, and the tool refuses to render at all under
``offscreen`` rather than quietly producing tofu:

    python tools/screenshot.py [output_dir]

Run it from a normal desktop session. There is no headless mode that is honest
about text on this platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    sys.exit(
        "refusing to render under QT_QPA_PLATFORM=offscreen: that platform has no\n"
        "fonts, so every glyph comes out as an empty box. Unset the variable and\n"
        "run this from a desktop session."
    )

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# Keeps this tool out of the real data folder, same as the test suites.
from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402


#: Representative repository contents, so the Repository page is photographed
#: with a populated tree rather than an empty box. Without this the screenshot
#: showed a blank table and an empty branch picker, which reads as a broken page
#: rather than as one with nothing in it - the difference between a bug and a
#: decision, and a reader cannot tell which.
DEMO_TREE = [
    "README.md", "LICENSE", "requirements.txt", ".gitignore",
    "src/github_manager/__init__.py",
    "src/github_manager/app.py",
    "src/github_manager/core/api.py",
    "src/github_manager/core/auth.py",
    "src/github_manager/ui/main_window.py",
    "src/github_manager/ui/pages/readme.py",
    "tests/test_api.py",
    "docs/install.md",
    ".github/workflows/build.yml",
]

DEMO_BRANCHES = ["main", "develop", "feature/readme-studio"]

DEMO_TAGS = [
    {"name": "v1.5.0", "sha": "9f2c41ab77de0"},
    {"name": "v1.4.0", "sha": "3ab90e14c7f2"},
    {"name": "v1.3.1", "sha": "c41d8fe206ab"},
]

DEMO_PEOPLE = [
    {"login": "octocat", "permissions": {"admin": True, "push": True, "pull": True}},
    {"login": "contributor1", "permissions": {"push": True, "pull": True}},
    {"login": "docs-writer", "permissions": {"pull": True}},
]


def _fill_repo_admin(page: object, app: QApplication) -> None:
    """Drive the Repository page's own loaders with representative data.

    Calls the same ``_on_*`` handlers the API callbacks call, rather than
    monkeypatching the client, so what is photographed is the real render path.
    """
    page.toolbar.repo.setCurrentText("octocat/hello-world")
    page.repo = "octocat/hello-world"

    page._on_branches(list(DEMO_BRANCHES))
    app.processEvents()

    page._on_files([
        {
            "path": path,
            "size": len(path) * 37 + 120,
            "sha": f"{abs(hash(path)) % (16 ** 12):012x}",
        }
        for path in DEMO_TREE
    ])
    page._on_tags(DEMO_TAGS)
    page._on_collaborators(DEMO_PEOPLE)
    for _ in range(10):
        app.processEvents()


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)

    from tests.smoke_test import StubGitHub, make_repos
    from app.core.github_api import UserProfile
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow

    ctx = AppContext()
    ctx.secrets.set("github_token", "stub-token")
    ctx.github = StubGitHub()
    ctx.repos = make_repos()
    ctx.repos_loaded = True
    ctx.profile = UserProfile(
        login="octocat",
        name="The Octocat",
        bio="Building GitHub things with Python and Qt",
        company="@github",
        location="San Francisco, CA",
        blog="https://octocat.dev",
        twitter="octocat",
        public_repos=8,
        public_gists=3,
        followers=9234,
        following=31,
        avatar_url="",
        html_url="https://github.com/octocat",
    )
    ctx.orgs = [{"login": "github", "role": "member"}]

    for theme in ("dark", "light"):
        ctx.config.save(theme=theme)

        window = MainWindow(ctx)
        window.resize(1500, 940)
        window.apply_theme()
        app.processEvents()

        from tests.smoke_test import COMMITS, ISSUES, RELEASES, README
        from app.ui.pages.issues import IssuesPage
        from app.ui.pages.readme import ReadmePage
        from app.ui.pages.repo_admin import RepoAdminPage
        from app.ui.pages.releases import ReleasesPage

        for index, page in enumerate(window.pages):
            window.goto(index)
            app.processEvents()
            page.load_once()
            app.processEvents()
            for _ in range(40):
                app.processEvents()

            if isinstance(page, IssuesPage):
                page._on_loaded(ISSUES)
                app.processEvents()
            elif isinstance(page, ReleasesPage):
                page._on_commits(COMMITS)
                page._on_releases(RELEASES)
                app.processEvents()
            elif isinstance(page, ReadmePage):
                page.editor.set_text(README)
                page.editor.refresh()
                app.processEvents()
            elif isinstance(page, RepoAdminPage):
                _fill_repo_admin(page, app)

            name = type(page).__name__.replace("Page", "").lower()
            target = out_dir / f"{index:02d}_{name}_{theme}.png"
            window.grab().save(str(target))
            print("saved", target)

        window.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
