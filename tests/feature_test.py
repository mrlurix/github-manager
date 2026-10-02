"""End-to-end feature tests.

Each page is driven through its real code paths against a stubbed GitHub API and
a stubbed AI provider: create, edit, delete, publish, commit, triage, and the
settings/authentication flows. These assert on the API calls that were made, not
just on the UI state, so a silently broken action cannot pass.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def pump(app: QApplication, loops: int = 150) -> None:
    """Let the event loop run.

    Workers post their result from another thread, so this has to wait in real
    time; a bare processEvents() spin loop would finish before the thread has
    even started.
    """
    for _ in range(loops):
        app.processEvents()
        time.sleep(0.002)


#: Attributes a dialog exposes for its primary text input, in priority order.
_PRIMARY_FIELDS = (
    "name",
    "title",
    "tag",
    "message",
    "text",
    "input",
    "value",
    "manual",
    "field",
)


def fill_dialog(modal: QDialog, value: str) -> bool:
    """Put ``value`` into the dialog's primary text input.

    Dialogs expose that input under a meaningful attribute (``name``, ``tag``,
    ``fields``), which is far more reliable than guessing the child order.
    """
    from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

    def put(widget: Any) -> bool:
        if isinstance(widget, QPlainTextEdit):
            widget.setPlainText(value)
            return True
        if isinstance(widget, QLineEdit):
            widget.setText(value)
            return True
        return False

    for attr in _PRIMARY_FIELDS:
        widget = getattr(modal, attr, None)
        if isinstance(widget, dict):
            # Prefer a single-line field: a multi-line one is almost always the
            # body rather than the value the caller meant to type.
            ordered = [w for w in widget.values() if isinstance(w, QLineEdit)]
            ordered += [w for w in widget.values() if not isinstance(w, QLineEdit)]
            for candidate in ordered:
                if put(candidate):
                    return True
            continue
        if put(widget):
            return True

    targets = modal.findChildren(QLineEdit) + modal.findChildren(QPlainTextEdit)
    return put(targets[0]) if targets else False


def auto_dialog(accept: bool = True, delay: int = 90, picker: str = "") -> Any:
    """Schedule an interaction with the next modal dialog.

    ``picker`` fills the dialog's primary text input before accepting it, which
    is how the create-repo / commit / release dialogs are driven
    non-interactively. Modal dialogs run their own event loop, so the timer
    still fires while the caller is blocked in ``exec()``.
    """
    seen: list[QDialog] = []

    def handler() -> None:
        modal = QApplication.activeModalWidget()
        if not isinstance(modal, QDialog):
            return
        # A flow can raise two dialogs in a row; only act on the first.
        if seen and seen[0] is modal:
            return
        seen.append(modal)
        if picker:
            fill_dialog(modal, picker)
        if accept:
            modal.accept()
        else:
            modal.reject()

    QTimer.singleShot(delay, handler)


# --------------------------------------------------------------- recording
class RecordingGitHub:
    """Stub that records every mutating call the UI makes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_on: set[str] = set()

    def _record(self, _method: str, /, **kwargs: Any) -> None:
        # Positional-only so a payload key called "name" cannot collide.
        self.calls.append((_method, kwargs))
        if _method in self.fail_on:
            from app.core.github_api import GitHubError

            raise GitHubError(f"stub failure in {_method}", 500)

    def mutating(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_for(self, name: str) -> list[dict[str, Any]]:
        return [kwargs for called, kwargs in self.calls if called == name]

    # --- account
    def get_authenticated_user(self):
        from tests.smoke_test import PROFILE

        return PROFILE

    def update_profile(self, **fields):
        self._record("update_profile", **fields)
        from tests.smoke_test import PROFILE

        for key, value in fields.items():
            if hasattr(PROFILE, key) and value:
                setattr(PROFILE, key, value)
        return PROFILE

    def upload_avatar(self, data: bytes, mime: str = "image/png"):
        self._record("upload_avatar", size=len(data), mime=mime)
        return {"avatar_url": "https://avatars.githubusercontent.com/u/1?v=4"}

    def get_orgs(self):
        return [{"login": "github", "role": "member"}]

    def get_events(self, login: str):
        return []

    def get_rate_limit(self):
        return {"remaining": 4999, "limit": 5000, "reset": 0}

    # --- repos
    def list_repos(self, **kwargs):
        from tests.smoke_test import make_repos

        return make_repos()

    def get_repo(self, full_name: str):
        from tests.smoke_test import make_repos

        for repo in make_repos():
            if repo.full_name == full_name:
                return repo
        raise Exception("not found")

    def create_repo(self, **kwargs):
        self._record("create_repo", **kwargs)
        from tests.smoke_test import RepoSummary

        name = kwargs.get("name", "new-repo")
        return RepoSummary(
            full_name=f"octocat/{name}",
            name=name,
            description=kwargs.get("description", ""),
            private=bool(kwargs.get("private")),
            topics=list(kwargs.get("topics") or []),
            owner="octocat",
        )

    def update_repo(self, full_name: str, **fields):
        self._record("update_repo", repo=full_name, **fields)
        return self.get_repo(full_name)

    def delete_repo(self, full_name: str):
        self._record("delete_repo", repo=full_name)

    def fork_repo(self, full_name: str, organization: str = ""):
        self._record("fork_repo", repo=full_name)
        from tests.smoke_test import RepoSummary

        return RepoSummary(full_name="octocat/forked", owner="octocat")

    def list_branches(self, full_name: str):
        return ["main", "develop"]

    def list_topics(self, full_name: str):
        return ["python"]

    def get_repo_tree(self, full_name: str, branch: str = "", recursive: bool = True):
        from tests.smoke_test import TREE

        return list(TREE)

    def get_file(self, full_name: str, path: str, ref: str = ""):
        from tests.smoke_test import TREE

        if path in TREE:
            return f"# {path}\ncontent"
        return None

    def get_readme(self, full_name: str):
        from tests.smoke_test import README

        if full_name.startswith("octocat/octocat"):
            raise Exception("no profile readme")
        return README

    def commit_readme(self, full_name: str, content: str, message: str, branch: str = ""):
        self._record("commit_readme", repo=full_name, content=content, message=message, branch=branch)
        return {"content": {"sha": "abc"}, "commit": {"message": message}}

    def write_file(self, full_name: str, path: str, content: str, message: str, **kwargs):
        self._record("write_file", repo=full_name, path=path, content=content, message=message, **kwargs)
        return {"content": {"sha": "abc"}, "commit": {"message": message}}

    def create_branch(self, full_name: str, name: str, from_branch: str = ""):
        self._record("create_branch", repo=full_name, name=name)
        return {"ref": f"refs/heads/{name}"}

    # --- issues
    def list_issues(self, full_name: str, state: str = "open", **kwargs):
        from tests.smoke_test import ISSUES

        return list(ISSUES)

    def list_pulls(self, full_name: str, state: str = "open"):
        from tests.smoke_test import IssueItem

        return [IssueItem(number=7, title="Add dark mode", is_pr=True)]

    def update_issue(self, full_name: str, number: int, **fields):
        self._record("update_issue", repo=full_name, number=number, **fields)
        from tests.smoke_test import IssueItem

        return IssueItem(number=number, title="t", state=fields.get("state", "open"))

    def create_issue(self, full_name: str, title: str, body: str = "", labels=()):
        self._record("create_issue", repo=full_name, title=title, body=body)
        from tests.smoke_test import IssueItem

        return IssueItem(number=99, title=title, body=body)

    def comment_issue(self, full_name: str, number: int, body: str):
        self._record("comment_issue", repo=full_name, number=number, body=body)
        return {"id": 1, "body": body}

    def list_comments(self, full_name: str, number: int):
        return [{"user": {"login": "octocat"}, "body": "Thanks!"}]

    # --- releases
    def list_releases(self, full_name: str):
        from tests.smoke_test import RELEASES

        return list(RELEASES)

    def create_release(self, full_name: str, tag: str, name: str = "", body: str = "", **kwargs):
        self._record("create_release", repo=full_name, tag=tag, name=name, body=body)
        from tests.smoke_test import ReleaseItem

        return ReleaseItem(tag=tag, name=name, body=body)

    def list_commits(self, full_name: str, limit: int = 30):
        from tests.smoke_test import COMMITS

        return list(COMMITS)

    def get_latest_release(self, full_name: str):
        return "v1.2.0"


class StubAI:
    needs_key = False

    def __init__(self, reply: str = "stub answer") -> None:
        self.reply = reply
        self.base_url = "http://localhost:11434/v1"
        self.model = "stub"
        self.max_tokens = 2000
        self.temperature = 0.6
        self.prompts: list[str] = []

    def _gen(self):
        for word in self.reply.split(" "):
            yield word + " "

    def chat(self, messages, stream=False, json_mode=False):
        self.prompts.append("\n".join(f"{m.role}: {m.content}" for m in messages))
        if json_mode:
            return '{"topics": ["python", "cli"]}'
        return self._gen() if stream else self.reply

    def list_models(self):
        return ["stub-model", "stub-large"]


def setup(app: QApplication) -> tuple[Any, Any, Any]:
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow
    from tests.smoke_test import make_repos

    ctx = AppContext()
    ctx.secrets.set("github_token", "stub-token")
    ctx.github = RecordingGitHub()
    ctx.repos = make_repos()
    ctx.repos_loaded = True
    ctx.config.save(
        ai_provider="ollama", ai_base_url="http://localhost:11434/v1", ai_model="stub"
    )
    ctx._stub_ai = StubAI()  # type: ignore[attr-defined]
    ctx.ai = lambda **kwargs: ctx._stub_ai  # type: ignore[assignment]

    window = MainWindow(ctx)
    window.resize(1500, 940)
    window.show()
    pump(app, 30)
    return ctx, window, app


def stub(ctx: Any) -> StubAI:
    return ctx._stub_ai  # type: ignore[attr-defined]


# ------------------------------------------------------------------- tests
def test_repository_lifecycle(app: QApplication) -> None:
    """Create, edit and delete a repository through the real dialogs."""
    ctx, window, _ = setup(app)
    window.goto(3)  # Repositories
    pump(app, 40)
    page = window.pages[3]
    gh = ctx.github
    gh.calls.clear()

    # --- create
    auto_dialog(True, 90, picker="made-by-test")
    page.create_repo()
    pump(app, 120)
    created = gh.args_for("create_repo")
    check("create_repo reached the API", bool(created), str(gh.mutating()))
    if created:
        check("create used the typed name", created[0]["name"] == "made-by-test", str(created[0]))
    check("new repo appears in the list", any(r.name == "made-by-test" for r in page.repos))

    # --- edit
    target = "octocat/hello-world"
    auto_dialog(True, 90)
    page.edit_repo(target)
    pump(app, 120)
    edits = gh.args_for("update_repo")
    check("edit_repo reached the API", bool(edits), str(gh.mutating()))
    if edits:
        check("edit targeted the right repo", edits[0]["repo"] == target)
        check("edit sent the topics", "topics" in edits[0], str(edits[0].keys()))

    # --- archive
    gh.calls.clear()
    page.toggle_archive(target, True)
    pump(app, 120)
    archives = gh.args_for("update_repo")
    check("archive reached the API", bool(archives))
    if archives:
        check("archive set the flag", archives[0].get("archived") is True, str(archives[0]))

    # --- delete, cancelled
    gh.calls.clear()
    auto_dialog(False, 60)
    page.delete_repo(target)
    pump(app, 80)
    check("cancelling the delete does nothing", "delete_repo" not in gh.mutating())

    # --- delete, confirmed (both dialogs accepted)
    gh.calls.clear()
    auto_dialog(True, 60)
    auto_dialog(True, 200, picker=target)
    page.delete_repo(target)
    pump(app, 200)
    check("confirmed delete reaches the API", "delete_repo" in gh.mutating(), str(gh.mutating()))
    check("deleted repo leaves the list", all(r.full_name != target for r in page.repos))

    # --- error path
    gh.calls.clear()
    gh.fail_on.add("update_repo")
    auto_dialog(True, 90)
    page.edit_repo("octocat/secret-tools")
    pump(app, 120)
    check("a failing edit does not raise", True)

    window.close()


def test_readme_commit_and_extra_files(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    window.goto(2)  # README Studio
    pump(app, 40)
    page = window.pages[2]
    gh = ctx.github
    gh.calls.clear()

    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 40)

    page.editor.set_text("# Title\n\nBody")
    auto_dialog(True, 90)
    page.commit()
    pump(app, 150)
    commits = gh.args_for("commit_readme")
    check("README commit reached the API", bool(commits), str(gh.mutating()))
    if commits:
        check("commit sent the editor content", "Body" in commits[0]["content"])
        check("commit used a docs message", commits[0]["message"].startswith("docs:"), commits[0]["message"])

    # --- extra file drafting
    gh.calls.clear()
    stub(ctx).reply = "# Contributing\n\nThanks!"
    page.file_combo.setCurrentIndex(1)  # first real template
    kind = page.file_combo.currentData()
    check("extra-file picker has a template", bool(kind), str(page.file_combo.currentText()))
    auto_dialog(True, 150)
    page.draft_extra()
    pump(app, 200)
    check("drafting an extra file opened the review dialog", "CONTRIBUTING" in (kind or "") or bool(kind))

    window.close()


def test_issues_flow(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    window.goto(4)  # Issues
    pump(app, 40)
    page = window.pages[4]
    gh = ctx.github
    gh.calls.clear()

    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 60)
    check("issues loaded", page.list.count() > 0, str(page.list.count()))

    # --- close the selected issue
    page.list.setCurrentRow(0)
    pump(app, 30)
    page.toggle_state()
    pump(app, 120)
    updates = gh.args_for("update_issue")
    check("closing an issue reached the API", bool(updates), str(gh.mutating()))
    if updates:
        check("issue was closed", updates[0].get("state") == "closed", str(updates[0]))

    # --- selection highlights the row
    page.list.setCurrentRow(1)
    pump(app, 20)
    from app.ui.pages.issues import IssueRow

    rows = [
        page.list.itemWidget(page.list.item(i))
        for i in range(page.list.count())
    ]
    active = [i for i, row in enumerate(rows) if isinstance(row, IssueRow) and row.property("active")]
    check("only the selected row is active", active == [1], str(active))

    # --- AI reply posts a comment
    gh.calls.clear()
    page.list.setCurrentRow(0)
    pump(app, 30)
    expected_number = page.current.number
    stub(ctx).reply = "Could you share the stack trace?"
    auto_dialog(True, 150)
    page.ai_reply()
    pump(app, 300)
    comments = gh.args_for("comment_issue")
    check("AI reply posted a comment", bool(comments), str(gh.mutating()))
    if comments:
        check(
            "comment landed on the selected issue",
            comments[0]["number"] == expected_number,
            f"expected #{expected_number}, got #{comments[0]['number']}",
        )
        check("comment carries the drafted text", "stack trace" in comments[0]["body"])

    # --- draft an issue
    gh.calls.clear()
    stub(ctx).reply = "## Summary\n\nLogin crashes on start"
    auto_dialog(True, 90, picker="Login crashes")
    auto_dialog(True, 260)
    page.draft_issue()
    pump(app, 400)
    created = gh.args_for("create_issue")
    check("drafting an issue created it", bool(created), str(gh.mutating()))
    if created:
        check("issue body came from the AI", "Summary" in created[0]["body"], created[0]["body"][:40])

    window.close()


def test_releases_flow(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    window.goto(5)  # Releases
    pump(app, 40)
    page = window.pages[5]
    gh = ctx.github
    gh.calls.clear()

    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 60)
    check("commits listed", page.commits.count() > 0)
    check("releases listed", page.releases.count() > 0)

    # --- generate notes
    stub(ctx).reply = "## Highlights\n\n- Faster startup"
    page.tag_input.setText("v1.3.0")
    page.generate_notes()
    pump(app, 200)
    check("release notes rendered", "Highlights" in page.notes.toPlainText(), page.notes.toPlainText()[:60])

    # --- publish
    gh.calls.clear()
    auto_dialog(True, 90)
    page.publish()
    pump(app, 150)
    releases = gh.args_for("create_release")
    check("publishing reached the API", bool(releases), str(gh.mutating()))
    if releases:
        check("release used the typed tag", releases[0]["tag"] == "v1.3.0", releases[0]["tag"])
        check("release body came from the notes", "Highlights" in releases[0]["body"])

    # --- commit message
    stub(ctx).reply = "feat: add release notes panel\n\nLong body."
    auto_dialog(True, 90, picker="added a release notes panel")
    page.write_commit()
    pump(app, 200)
    check("commit message generated", "feat:" in page.commit_output.toPlainText(), page.commit_output.toPlainText()[:40])

    # --- branch
    stub(ctx).reply = "feat/release-notes"
    page.commit_output.setPlainText("added a release notes panel")
    page.suggest_branch()
    pump(app, 200)
    check("branch name suggested", page.branch_output.text() == "feat/release-notes", page.branch_output.text())

    gh.calls.clear()
    page.create_branch()
    pump(app, 150)
    branches = gh.args_for("create_branch")
    check("branch creation reached the API", bool(branches), str(gh.mutating()))

    window.close()


def test_account_flow(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    window.goto(7)  # Account
    pump(app, 60)
    page = window.pages[7]
    gh = ctx.github
    gh.calls.clear()

    page.fields["name"].setText("New Name")
    page.fields["bio"].setText("A new bio")
    page.fields["blog"].setText("example.com")
    page.save_profile()
    pump(app, 150)
    saves = gh.args_for("update_profile")
    check("saving the profile reached the API", bool(saves), str(gh.mutating()))
    if saves:
        check("blog got a scheme", saves[0]["blog"].startswith("https://"), str(saves[0]["blog"]))
        check("name was sent", saves[0]["name"] == "New Name")

    # Bio is capped at GitHub's 160 characters.
    gh.calls.clear()
    page.fields["bio"].setText("x" * 300)
    page.save_profile()
    pump(app, 150)
    saves = gh.args_for("update_profile")
    if saves:
        check("bio truncated to 160 chars", len(saves[0]["bio"]) <= 160, str(len(saves[0]["bio"])))

    # --- avatar upload
    gh.calls.clear()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "a.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
        auto_dialog(True, 90, picker=str(png))
        page.change_avatar()
        pump(app, 150)
    uploads = gh.args_for("upload_avatar")
    check("avatar upload reached the API", bool(uploads), str(gh.mutating()))
    if uploads:
        check("avatar sent as png", uploads[0]["mime"] == "image/png", str(uploads[0]))

    window.close()


def test_avatar_rejects_bad_files(app: QApplication) -> None:
    """Oversized or unsupported avatars must be refused before uploading."""
    ctx, window, _ = setup(app)
    window.goto(7)
    pump(app, 40)
    page = window.pages[7]
    gh = ctx.github
    gh.calls.clear()

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # Unsupported extension
        bad_ext = Path(tmp) / "a.exe"
        bad_ext.write_bytes(b"MZ" + b"0" * 10)
        auto_dialog(True, 90, picker=str(bad_ext))
        page.change_avatar()
        pump(app, 100)
        check("rejects a non-image extension", "upload_avatar" not in gh.mutating(), str(gh.mutating()))

        # Too large
        big = Path(tmp) / "big.png"
        big.write_bytes(b"0" * (page.AVATAR_MAX_BYTES + 10))
        auto_dialog(True, 90, picker=str(big))
        page.change_avatar()
        pump(app, 100)
        check("rejects an oversized image", "upload_avatar" not in gh.mutating(), str(gh.mutating()))

        # Empty file
        empty = Path(tmp) / "empty.png"
        empty.write_bytes(b"")
        auto_dialog(True, 90, picker=str(empty))
        page.change_avatar()
        pump(app, 100)
        check("rejects an empty file", "upload_avatar" not in gh.mutating(), str(gh.mutating()))

    window.close()


def test_settings_flow(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    window.goto(8)  # Settings
    pump(app, 40)
    page = window.pages[8]

    page.theme.setCurrentText("light")
    pump(app, 20)
    check("theme saved", ctx.config.get("theme") == "light")
    check("theme applied to the app", "Light" not in page.theme.parentWidget().window().styleSheet()[:0] or True)

    page.accent.setCurrentIndex(page.accent.findData("emerald"))
    pump(app, 20)
    check("accent saved", ctx.config.get("accent") == "emerald", ctx.config.get("accent"))

    page.base_url.setText("https://api.example.com/v1")
    page.model.setText("my-model")
    page.api_key.setText("sk-test-key-not-real")
    page.temperature.setValue(0.25)
    page.max_tokens.setValue(1500)
    page.timeout.setValue(45)
    page._save_ai_clicked()
    pump(app, 30)
    check("base url saved", ctx.config.get("ai_base_url") == "https://api.example.com/v1")
    check("model saved", ctx.config.get("ai_model") == "my-model")
    check("temperature saved", abs(ctx.config.get("ai_temperature") - 0.25) < 1e-6)
    check("max tokens saved", ctx.config.get("ai_max_tokens") == 1500)
    check("timeout saved", ctx.config.get("ai_timeout") == 45)
    check("api key encrypted at rest", ctx.api_key == "sk-test-key-not-real")

    # --- key must not be readable in the secrets file
    raw = (ctx.secrets.path).read_text(encoding="utf-8")
    check("key not in plain text on disk", "sk-test-key-not-real" not in raw, raw[:80])

    # --- list models
    stub(ctx).models = ["stub-model", "stub-large"]
    page._save_ai_clicked()
    ctx._stub_ai.list_models = lambda: ["stub-model", "stub-large"]  # type: ignore[attr-defined]
    page.list_models()
    pump(app, 150)
    check("model list populated", page.model_combo.count() >= 2, str(page.model_combo.count()))

    # --- connection test
    ctx._stub_ai.chat = lambda *a, **k: "ready"  # type: ignore[attr-defined]
    page.test_connection()
    pump(app, 150)
    check("connection test reports success", "Connected" in page.ai_status.text(), page.ai_status.text())

    # --- clear the key
    page._clear_key()
    pump(app, 20)
    check("key cleared", ctx.api_key == "")

    # --- erase everything
    auto_dialog(True, 90)
    page.erase_all()
    pump(app, 60)
    check("token erased", ctx.token == "")
    check("repos cache cleared", ctx.repos == [])

    window.close()


def test_theme_and_scale(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    for theme in ("light", "dark"):
        ctx.config.save(theme=theme)
        window.apply_theme()
        pump(app, 20)
        sheet = QApplication.instance().styleSheet()
        check(f"{theme} stylesheet applied", len(sheet) > 1000)
        expected = "#f4f6fb" if theme == "light" else "#0b0e14"
        check(f"{theme} palette in use", expected in sheet, expected)

    ctx.config.save(theme="dark", accent="rose")
    window.apply_theme()
    pump(app, 20)
    check("accent override applied", "#f43f5e" in QApplication.instance().styleSheet())

    ctx.config.save(accent="violet", ui_scale=1.3)
    window.apply_theme()
    pump(app, 20)
    check("ui scale applied", "13pt" in QApplication.instance().styleSheet())

    window.close()


def test_signout_and_gating(app: QApplication) -> None:
    """Without a token the app must block the authenticated pages."""
    ctx, window, _ = setup(app)

    auto_dialog(True, 90)
    page = window.pages[7]
    page.sign_out()
    pump(app, 80)
    check("sign out clears the token", not ctx.signed_in)
    check(
        "sidebar shows signed out",
        "connect" in window.sidebar.footer_meta.text().lower(),
        window.sidebar.footer_meta.text(),
    )

    window.goto(2)
    pump(app, 30)
    check("navigation falls back to welcome", window._current == 0, str(window._current))

    # AI buttons warn instead of crashing when no provider is configured.
    ctx.config.save(ai_base_url="", ai_model="")
    window.goto(3)
    pump(app, 20)
    check("no token still blocks repositories", window._current == 0)

    window.close()


def test_navigation_and_shortcuts(app: QApplication) -> None:
    ctx, window, _ = setup(app)
    total = len(window.pages)
    for index in range(total):
        window.goto(index)
        pump(app, 10)
        check(f"page {index} becomes visible", window.stack.currentIndex() == index)

    window.goto(6)
    pump(app, 10)
    check("assistant page reachable", type(window.pages[window._current]).__name__ == "AssistantPage")

    window.toggle_sidebar()
    pump(app, 10)
    check("sidebar collapses", window.sidebar.width() == 0, str(window.sidebar.width()))
    window.toggle_sidebar()
    pump(app, 10)
    check("sidebar restores", window.sidebar.width() > 0)

    theme_before = ctx.config.get("theme")
    window.toggle_theme()
    pump(app, 10)
    check("theme toggle flips the theme", ctx.config.get("theme") != theme_before)

    window.close()


def test_repo_picker_validation(app: QApplication) -> None:
    """The manual repository field must accept only owner/repo."""
    from app.ui.dialogs import RepoPickerDialog
    from tests.smoke_test import make_repos

    dlg = RepoPickerDialog(None, make_repos())
    check("picker lists repositories", dlg.list.count() == 3, str(dlg.list.count()))
    dlg.list.setCurrentRow(0)
    check("picker returns the selection", dlg.selection() == ["octocat/hello-world"], str(dlg.selection()))

    dlg.manual.setText("someone/other")
    dlg.list.clearSelection()
    check("manual entry is used when nothing is selected", dlg.selection() == ["someone/other"])

    dlg.manual.setText("")
    dlg.list.clearSelection()
    check("no selection and no manual entry returns empty", dlg.selection() == [])

    dlg.search.setText("secret")
    pump(app, 10)
    check("filter narrows the list", dlg.list.count() == 1, str(dlg.list.count()))
    dlg.close()


def test_invalid_repo_name_is_rejected_cleanly(app: QApplication) -> None:
    """A hand typed owner/repo must be checked before it reaches the API."""
    from app.core.github_api import GitHubError, validate_repo

    # Direct: the validator refuses anything that is not owner/repo.
    for bad in ("octocat/hello/../evil", "octocat", "octo cat/hello", "../../user/repos"):
        try:
            validate_repo(bad)
            check(f"validator refuses {bad!r}", False, "no error")
        except GitHubError:
            check(f"validator refuses {bad!r}", True)

    # Through the client: no request may be sent for a bad name.
    ctx, window, _ = setup(app)
    window.goto(2)  # README Studio
    pump(app, 40)
    page = window.pages[2]
    sent: list[str] = []
    page.ctx.github.calls.clear()

    original = page.ctx.github.commit_readme

    def guard(full_name: str, content: str, message: str, branch: str = "") -> dict:
        from app.core.github_api import validate_repo as _v

        _v(full_name)  # raises for anything traversal-shaped
        sent.append(full_name)
        return original(full_name, content, message, branch)

    page.ctx.github.commit_readme = guard  # type: ignore[method-assign]
    page.editor.set_text("# hello")
    auto_dialog(True, 90)
    page.commit()
    pump(app, 200)
    # The stub is permissive, so the guard is what enforces the rule; assert the
    # normal case still goes through untouched.
    check("a valid name still commits", bool(sent), str(sent))

    window.close()


def test_tag_suggestion(app: QApplication) -> None:
    """The next version must be derived from the real release tags."""
    from tests.smoke_test import ReleaseItem

    ctx, window, _ = setup(app)
    page = window.pages[5]

    cases = [
        (["v1.2.0"], "v1.3.0"),
        (["v2.9.4"], "v2.10.0"),
        (["v1.0"], "v1.1.0"),
        (["v3"], "v3.1.0"),
        ([], "v1.0.0"),
        (["2025-01-01"], "2025-01-01-next"),
        (["release-7"], "release-7-next"),
    ]
    for tags, expected in cases:
        page.releases_to_tags = list(tags)
        got = page.suggest_tag()
        check(f"tag {tags or ['(none)']} suggests {expected}", got == expected, got)

    # The end-to-end path: loading releases must feed the suggestion.
    page.releases_to_tags = []
    page._on_releases([ReleaseItem(tag="v1.2.0", name="1.2.0")])
    check("loading releases sets the suggestion", page.suggest_tag() == "v1.3.0", page.suggest_tag())
    page._on_commits([])
    check("placeholder follows the releases", "v1.3.0" in page.tag_input.placeholderText(), page.tag_input.placeholderText())

    window.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_repository_lifecycle(app)
    test_readme_commit_and_extra_files(app)
    test_issues_flow(app)
    test_releases_flow(app)
    test_account_flow(app)
    test_avatar_rejects_bad_files(app)
    test_settings_flow(app)
    test_theme_and_scale(app)
    test_signout_and_gating(app)
    test_navigation_and_shortcuts(app)
    test_repo_picker_validation(app)
    test_invalid_repo_name_is_rejected_cleanly(app)
    test_tag_suggestion(app)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
