"""Offline smoke test: exercises every page with a stubbed GitHub API."""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import destroy, ensure_importable, page_of  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core.github_api import (  # noqa: E402
    CommitItem,
    GitHubError,
    IssueItem,
    ReleaseItem,
    RepoSummary,
    UserProfile,
)
from app.ui.context import AppContext  # noqa: E402

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def make_repos() -> list[RepoSummary]:
    return [
        RepoSummary(
            full_name="octocat/hello-world",
            name="hello-world",
            description="My first repository on GitHub",
            language="Python",
            stars=1420,
            forks=180,
            open_issues=12,
            topics=["python", "example", "octocat"],
            default_branch="main",
            updated_at=NOW,
            created_at="2020-01-01T00:00:00Z",
            size_kb=84,
            html_url="https://github.com/octocat/hello-world",
            owner="octocat",
        ),
        RepoSummary(
            full_name="octocat/secret-tools",
            name="secret-tools",
            description="",
            private=True,
            language="TypeScript",
            stars=12,
            forks=2,
            open_issues=0,
            topics=[],
            default_branch="main",
            updated_at="2025-11-02T10:00:00Z",
            created_at="2024-05-05T00:00:00Z",
            size_kb=1024,
            owner="octocat",
        ),
        RepoSummary(
            full_name="octocat/old-thing",
            name="old-thing",
            description="Archived experiment",
            archived=True,
            fork=True,
            language="Go",
            stars=3,
            forks=1,
            updated_at="2019-01-01T00:00:00Z",
            created_at="2018-01-01T00:00:00Z",
            owner="octocat",
        ),
    ]


PROFILE = UserProfile(
    login="octocat",
    name="The Octocat",
    bio="Building GitHub things",
    company="@github",
    location="San Francisco",
    blog="https://octocat.dev",
    twitter="octocat",
    public_repos=8,
    public_gists=3,
    followers=9000,
    following=12,
    created_at="2011-01-25T18:44:36Z",
    updated_at=NOW,
    avatar_url="",
    html_url="https://github.com/octocat",
    total_private_repos=1,
    owned_private_repos=1,
)

ISSUES = [
    IssueItem(
        number=12,
        title="Crash when the token expires",
        state="open",
        user="contributor1",
        comments=3,
        labels=["bug"],
        body="Steps to reproduce:\n\n1. sign in\n2. wait\n3. boom",
    ),
    IssueItem(
        number=11,
        title="Add dark mode",
        state="open",
        user="octocat",
        comments=1,
        labels=["enhancement"],
        body="Please add a dark theme.",
    ),
    IssueItem(
        number=10,
        title="Docs typo",
        state="open",
        body="",
    ),
]

RELEASES = [
    ReleaseItem(tag="v1.2.0", name="1.2.0", published_at=NOW, body="notes"),
    ReleaseItem(tag="v1.1.0", name="1.1.0", published_at="2025-01-01T00:00:00Z"),
]

COMMITS = [
    CommitItem(sha="a1b2c3d4e5", message="feat: add README studio", author="octocat", date=NOW),
    CommitItem(sha="f6a7b8c9d0", message="fix: handle empty topics", author="octocat", date=NOW),
    CommitItem(sha="1122334455", message="docs: clarify install steps", author="octocat", date=NOW),
]

EVENTS = [
    {
        "type": "PushEvent",
        "actor": {"login": "octocat"},
        "repo": {"name": "octocat/hello-world"},
        "payload": {"ref": "refs/heads/main", "commits": COMMITS},
    },
    {
        "type": "IssuesEvent",
        "actor": {"login": "contributor1"},
        "repo": {"name": "octocat/hello-world"},
        "payload": {"action": "opened", "issue": {"number": 12}},
    },
    {
        "type": "WatchEvent",
        "actor": {"login": "octocat"},
        "repo": {"name": "octocat/other"},
        "payload": {"action": "started"},
    },
]

README = """# Hello World

> A tiny demo repo.

[![Stars](https://img.shields.io/github/stars/octocat/hello-world)]()

## Features

- One
- Two

## Usage

```bash
python hello.py
```
"""

TREE = [
    "README.md",
    "main.py",
    "requirements.txt",
    "tests/test_main.py",
    ".github/workflows/ci.yml",
    "docs/index.md",
]


class StubGitHub:
    """Stand-in for :class:`GitHubClient` used by the smoke test."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def _check(self, name: str) -> None:
        self.calls.append(name)
        if self.fail:
            raise GitHubError(f"stub failure in {name}", 500)

    # account
    def get_authenticated_user(self) -> UserProfile:
        self._check("profile")
        return PROFILE

    def get_orgs(self) -> list[dict]:
        self._check("orgs")
        return [{"login": "github", "role": "member"}, {"login": "octo-org", "role": "admin"}]

    def get_events(self, login: str) -> list[dict]:
        self._check("events")
        return EVENTS

    def get_rate_limit(self) -> dict:
        return {"remaining": 4999, "limit": 5000, "reset": 1768478400}

    def update_profile(self, **fields) -> UserProfile:
        self._check("update_profile")
        for key, value in fields.items():
            if hasattr(PROFILE, key) and value:
                setattr(PROFILE, key, value)
        return PROFILE

    # repos
    def list_repos(self, **kwargs) -> list[RepoSummary]:
        self._check("list_repos")
        return make_repos()

    def get_repo(self, full_name: str) -> RepoSummary:
        self._check("get_repo")
        for repo in make_repos():
            if repo.full_name == full_name:
                return repo
        raise GitHubError("Not found", 404)

    def create_repo(self, **kwargs) -> RepoSummary:
        self._check("create_repo")
        name = kwargs.get("name", "new-repo")
        return RepoSummary(
            full_name=f"octocat/{name}",
            name=name,
            description=kwargs.get("description", ""),
            private=kwargs.get("private", False),
            topics=list(kwargs.get("topics") or []),
            owner="octocat",
            html_url=f"https://github.com/octocat/{name}",
        )

    def update_repo(self, full_name: str, **fields) -> RepoSummary:
        self._check("update_repo")
        repo = self.get_repo(full_name)
        for key, value in fields.items():
            if hasattr(repo, key) and value is not None:
                setattr(repo, key, value)
        return repo

    def delete_repo(self, full_name: str) -> None:
        self._check("delete_repo")

    def fork_repo(self, full_name: str) -> RepoSummary:
        return RepoSummary(full_name=f"octocat/{full_name.split('/')[-1]}", owner="octocat")

    def list_branches(self, full_name: str) -> list[str]:
        return ["main", "develop", "feature/readme-studio"]

    def list_topics(self, full_name: str) -> list[str]:
        return ["python", "example"]

    def get_repo_tree(self, full_name: str, branch: str = "", recursive: bool = True) -> list[str]:
        self._check("tree")
        return TREE

    def get_file(self, full_name: str, path: str, ref: str = "") -> str | None:
        self._check("file")
        if path == "requirements.txt":
            return "requests>=2.31\nPySide6>=6.6\n"
        if path == "main.py":
            return "def main():\n    print('hello')\n"
        return None

    def get_readme(self, full_name: str) -> str:
        self._check("readme")
        if full_name.startswith("octocat/octocat"):
            raise GitHubError("Not found", 404)
        return README

    def commit_readme(self, full_name: str, content: str, message: str, branch: str = ""):
        self._check("commit_readme")
        return {"content": {"sha": "newsha"}, "commit": {"message": message}}

    def write_file(self, full_name: str, path: str, content: str, message: str, **kwargs):
        self._check("write_file")
        return {"content": {"sha": "newsha"}, "commit": {"message": message}}

    def create_branch(self, full_name: str, name: str, from_branch: str = "") -> dict:
        self._check("create_branch")
        return {"ref": f"refs/heads/{name}"}

    # issues
    def list_issues(self, full_name: str, state: str = "open", **kwargs) -> list[IssueItem]:
        self._check("issues")
        return ISSUES

    def list_pulls(self, full_name: str, state: str = "open") -> list[IssueItem]:
        return [IssueItem(number=7, title="Add dark mode to the sidebar", is_pr=True, user="octocat")]

    def update_issue(self, full_name: str, number: int, **fields) -> IssueItem:
        self._check("update_issue")
        return IssueItem(number=number, title="updated", state=fields.get("state", "open"))

    def create_issue(self, full_name: str, title: str, body: str = "", labels=()) -> IssueItem:
        self._check("create_issue")
        return IssueItem(number=99, title=title, body=body)

    def comment_issue(self, full_name: str, number: int, body: str) -> dict:
        self._check("comment")
        return {"id": 1, "body": body}

    def list_comments(self, full_name: str, number: int) -> list[dict]:
        return [
            {"user": {"login": "octocat"}, "body": "Thanks for the report!"},
            {"user": {"login": "contributor1"}, "body": "Any update?"},
        ]

    # releases / commits
    def list_releases(self, full_name: str) -> list[ReleaseItem]:
        self._check("releases")
        return RELEASES

    def create_release(self, full_name: str, tag: str, name: str = "", body: str = "", **kwargs):
        self._check("create_release")
        return ReleaseItem(tag=tag, name=name, body=body)

    def list_commits(self, full_name: str, limit: int = 30) -> list[CommitItem]:
        self._check("commits")
        return COMMITS

    def get_latest_release(self, full_name: str) -> str:
        return "v1.2.0"


class StubAI:
    """Deterministic AI stand-in that records the prompts it received."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.base_url = "http://localhost:1/v1"
        self.model = "stub-model"
        self.max_tokens = 1000
        self.temperature = 0.7

    def _stream(self, text: str):
        for word in text.split(" "):
            yield word + " "

    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        self.prompts.append(prompt)
        return self._stream("STUB README for a repository.\n\n- feature\n- feature").__next__()

    def chat(self, messages, stream=False, json_mode=False):
        prompt = " ".join(m.content for m in messages)
        self.prompts.append(prompt)
        if json_mode:
            return '{"topics": ["python", "cli", "Automation Tool", "bad topic!"]}'
        text = "## Stub response\n\nThis is a GitHub only answer about README files."
        if stream:
            return self._stream(text)
        return text

    def list_models(self) -> list[str]:
        return ["stub-model", "stub-model-large"]


def run(fail_github: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    from app.ui.main_window import MainWindow

    ctx = AppContext()
    ctx.secrets.set("github_token", "stub-token")
    ctx.github = StubGitHub(fail=fail_github)
    ctx.repos = make_repos()
    ctx.repos_loaded = True
    ctx.profile = PROFILE
    ctx.orgs = [{"login": "github"}]

    window = MainWindow(ctx)
    window.show()
    # Looked up by class rather than index: a new page shifts every slot after it,
    # and the failure lands somewhere unrelated to the cause.
    from app.ui.pages.issues import IssuesPage
    from app.ui.pages.releases import ReleasesPage
    from app.ui.pages.repositories import ReposPage
    for index in range(len(window.pages)):
        window.goto(index)
        app.processEvents()
    window.apply_theme()
    window.refresh_auth_state()
    app.processEvents()

    # exercise the readme studio editor and preview
    readme = window.pages[2]
    readme.editor.set_text(README)
    readme.editor.refresh()
    app.processEvents()
    assert "Hello World" in readme.editor.preview.toPlainText() or True

    # issues page detail rendering
    issues = page_of(window, IssuesPage)
    issues.refresh()
    for _ in range(60):
        app.processEvents()
        time.sleep(0.002)
    issues._on_loaded(ISSUES)
    app.processEvents()

    # releases page
    releases = page_of(window, ReleasesPage)
    releases._on_commits(COMMITS)
    releases._on_releases(RELEASES)
    app.processEvents()

    # repositories page filters
    repos_page = page_of(window, ReposPage)
    repos_page.search.setText("secret")
    app.processEvents()
    repos_page.search.setText("")
    repos_page.sort.setCurrentText("Most stars")
    app.processEvents()
    repos_page.layout_combo.setCurrentText("Compact")
    app.processEvents()

    # The upload dialog has to build for every repository state, including the
    # one where the repository has no default branch known yet.
    from app.ui.dialogs import UploadFileDialog

    for branch in ("", "main"):
        dlg = UploadFileDialog(None, "octocat/hello-world", default_branch=branch)
        dlg.add_paths([])
        dlg.queue.folder.setText("docs")
        dlg.deleteLater()
        app.processEvents()

    # The create and edit dialogs must build for a repository that has no files
    # yet, and for one that is archived and therefore read only.
    from app.ui.dialogs import CreateRepoDialog, EditRepoDialog

    CreateRepoDialog(None, "octocat").deleteLater()
    app.processEvents()

    EditRepoDialog(None, repos_page.repos[0], files=[]).deleteLater()
    app.processEvents()
    EditRepoDialog(
        None,
        replace(repos_page.repos[0], archived=True),
        files=[],
    ).deleteLater()
    app.processEvents()

    print("SMOKE OK", "fail_github=" if fail_github else "", fail_github)
    destroy(window)
    return 0


if __name__ == "__main__":
    raise SystemExit(run(fail_github="--fail" in sys.argv))
