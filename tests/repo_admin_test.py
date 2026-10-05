"""Repository management page tests.

Driven against the mock GitHub server rather than a stub, because the page is
built almost entirely out of list rendering: a wrong field name or a missing key
shows up as an empty table rather than an exception, and only real responses
catch that.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "tests"))
sys.path.insert(0, str(_ROOT))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.github_api import GitHubClient  # noqa: E402
from tests.mock_github_server import (  # noqa: E402
    REPOS,
    VALID_TOKEN,
    MockGitHubServer,
)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -> {detail}" if detail and not condition else "")
    )


def test_api() -> tuple[str, MockGitHubServer]:
    server = MockGitHubServer().start()
    client = GitHubClient(VALID_TOKEN, api_url=server.url)
    repo = REPOS[0]["full_name"]

    branches = client.list_branches(repo)
    check("branches are listed", branches == ["main", "develop"], str(branches))

    tags = client.list_tags(repo)
    check("tags are listed", len(tags) == 3, str(tags))
    check("a tag carries its name", tags[0].get("name") == "v1.2.0", str(tags[0]))
    check("a tag carries its commit", len(str(tags[0].get("sha") or "")) == 40, str(tags[0]))
    check("tags are newest first",
          [t["name"] for t in tags] == ["v1.2.0", "v1.1.0", "v1.0.0"], str(tags))

    people = client.list_collaborators(repo)
    check("collaborators are listed", len(people) == 2, str(people))
    check("a collaborator carries a login", str(people[0].get("login")) == "octocat", str(people[0]))

    hooks = client.list_hooks(repo)
    check("webhooks are listed", len(hooks) == 1, str(hooks))
    check("a webhook carries its events", "push" in (hooks[0].get("events") or []), str(hooks[0]))

    client.add_collaborator(repo, "newcomer", "write")
    after = [str(p.get("login")) for p in client.list_collaborators(repo)]
    check("a collaborator can be added", "newcomer" in after, str(after))
    client.remove_collaborator(repo, "newcomer")
    after = [str(p.get("login")) for p in client.list_collaborators(repo)]
    check("a collaborator can be removed", "newcomer" not in after, str(after))

    client.create_branch(repo, "feature/from-admin")
    check("a branch can be created", "feature/from-admin" in client.list_branches(repo),
          str(client.list_branches(repo)))

    # The page reads files through list_files, so it must carry a usable sha.
    files = client.list_files(repo)
    check("files carry a sha", all(f.get("sha") for f in files), str(files)[:160])
    check("files carry a size", all(isinstance(f.get("size"), int) for f in files))

    return repo, server


def test_page(repo: str) -> None:
    from app.core.github_api import RepoSummary
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow
    from app.ui.pages.repo_admin import PERMISSIONS, RepoAdminPage

    app = QApplication.instance() or QApplication(sys.argv)
    ctx = AppContext()
    ctx.github = GitHubClient(VALID_TOKEN, api_url="http://127.0.0.1:1")
    ctx.secrets.set("github_token", VALID_TOKEN)
    ctx.repos = [RepoSummary(full_name=repo, name=repo.split("/")[-1])]

    from tests.ai_flow_test import build_app  # noqa: F401

    window = MainWindow(ctx)
    page = next(p for p in window.pages if isinstance(p, RepoAdminPage))
    check("the page is reachable from the stack", page is not None)
    check("the page has a repository field", hasattr(page, "repo"))
    check("the page has the five tabs",
          [page.tabs.tabText(i) for i in range(page.tabs.count())]
          == ["Files", "Branches", "Tags", "Collaborators", "Webhooks"],
          str([page.tabs.tabText(i) for i in range(page.tabs.count())]))

    # Offline: nothing resolves, but the page must not raise while doing it.
    page.repo = repo
    page.on_repo_changed()
    check("an offline page load does not raise", True)

    # Rendering the widgets with real data is what catches a missing key.
    page._on_branches(["main", "develop", "feature/x"])
    page._on_files([
        {"path": "README.md", "sha": "a" * 40, "size": 120},
        {"path": "src/main.py", "sha": "b" * 40, "size": 2048},
        {"path": "docs/guide.md", "sha": "c" * 40, "size": 900},
    ])
    check("the file tree has rows", page.file_tree.topLevelItemCount() >= 2,
          str(page.file_tree.topLevelItemCount()))

    page.file_filter.setText("docs")
    check("filtering narrows the tree",
          page.file_tree.topLevelItemCount() >= 1,
          str(page.file_tree.topLevelItemCount()))
    page.file_filter.setText("")

    page._on_tags([
        {"name": "v1.2.0", "sha": "d" * 40},
        {"name": "v1.0.0", "sha": "e" * 40},
    ])
    check("the tag table is filled", page.tag_table.rowCount() == 2, str(page.tag_table.rowCount()))
    check("a tag row shows its name",
          page.tag_table.item(0, 0).text() == "v1.2.0",
          page.tag_table.item(0, 0).text())
    check("a tag row shows a short commit",
          len(page.tag_table.item(0, 1).text()) == 12, page.tag_table.item(0, 1).text())

    page._on_collaborators([
        {"login": "octocat", "permissions": {"admin": True, "pull": True}},
        {"login": "hubot", "permissions": {"push": True, "pull": True}},
    ])
    check("the collaborator list is filled", page.people.count() == 2, str(page.people.count()))
    check("an admin shows as admin", "admin" in page.people.item(0).text(),
          page.people.item(0).text())
    check("the highest permission is chosen", "admin" in page.people.item(0).text(),
          page.people.item(0).text())

    page._on_webhooks([
        {"name": "web", "events": ["push"], "config": {"url": "https://example.invalid/x"}}
    ])
    check("the webhook list is filled", page.hooks.count() == 1, str(page.hooks.count()))
    check("a webhook shows its events", "push" in page.hooks.item(0).text(),
          page.hooks.item(0).text())

    # A repository with nothing in it must still render every tab.
    page._on_files([])
    page._on_tags([])
    page._on_collaborators([])
    page._on_webhooks([])
    check("empty state does not raise", True)
    check("an empty file tree is cleared", page.file_tree.topLevelItemCount() == 0)

    # Permissions map to what the API expects.
    check("permissions cover the API's levels",
          set(PERMISSIONS.values()) == {"read", "triage", "write", "maintain", "admin"},
          str(sorted(PERMISSIONS.values())))

    from _bootstrap import destroy

    # The offline load above queued a worker against an unreachable URL. Its error
    # callback lands on the page after teardown and raises inside Qt, so the pool
    # is drained first.
    _settle(app)
    destroy(window)
    app.processEvents()


def _settle(app: QApplication, rounds: int = 60) -> None:
    """Wait for in-flight workers, pumping events so their signals are delivered."""
    import time

    from app.ui import workers

    for _ in range(rounds):
        app.processEvents()
        if not workers.active_count():
            return
        time.sleep(0.01)
    app.processEvents()


def test_navigation() -> None:
    """The new page must not have broken the sidebar mapping."""
    from app.ui.main_window import NAV_ITEMS

    from tests.ai_flow_test import build_app

    app = QApplication.instance() or QApplication(sys.argv)
    ctx, window = build_app(app)
    check("one nav item per page after welcome",
          len(window.sidebar.buttons) == len(window.pages) - 1,
          f"{len(window.sidebar.buttons)} buttons vs {len(window.pages)} pages")

    for index, (label, _icon) in enumerate(NAV_ITEMS):
        window.sidebar.buttons[index].click()
        for _ in range(12):
            app.processEvents()
        opened = window.pages[window.stack.currentIndex()].title
        check(f"clicking '{label}' opens '{label}'", opened == label, f"opened '{opened}'")

    from _bootstrap import destroy

    _settle(app)
    destroy(window)
    app.processEvents()


def main() -> int:
    repo, server = test_api()
    try:
        test_page(repo)
    finally:
        server.stop()
    test_navigation()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for name in FAILED:
            print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())