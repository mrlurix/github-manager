"""Renders every page to a PNG so the UI can be reviewed visually.

Usage:
    python tools/screenshot.py [output_dir]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

# Keeps this tool out of the real data folder, same as the test suites.
from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402


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

            name = type(page).__name__.replace("Page", "").lower()
            target = out_dir / f"{index:02d}_{name}_{theme}.png"
            window.grab().save(str(target))
            print("saved", target)

        window.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
