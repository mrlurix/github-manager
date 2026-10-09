"""Releases & commits: version notes, commit messages, branch names."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from .. import workers
from ..dialogs import RepoPickerDialog, TextInputDialog, confirm
from ..editor import MarkdownStreamView
from ..markdown import render_markdown
from ..theme import markdown_css
from ..widgets import (
    Card,
    FlowWidget,
    PageHeader,
    ScrollPage,
    button,
    icon_button,
    label,
)
from .base import Page


class ReleasesPage(Page):
    title = "Releases & commits"
    subtitle = "Turn raw commits into release notes, or draft the commit itself."
    icon = "release"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.repo = ""
        self.commits_to_text: list[Any] = []
        self.releases_to_tags: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # Two stacked cards on the left and two on the right need more height
        # than a short window has. Without a scroll area the splitter is given
        # less than its minimum and the lists are drawn outside their cards.
        self.scroll = ScrollPage(self)
        outer.addWidget(self.scroll)
        layout = self.scroll.column
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        self.header = PageHeader(
            "Releases & commits", "AI writes the notes; you approve the release"
        )
        self.header.add_action(
            button("New release", variant="primary", icon="release", on_click=self.create_release)
        )
        self.header.add_action(icon_button("refresh", tooltip="Refresh", on_click=self.refresh))
        layout.addWidget(self.header)

        bar = Card(flat=True)
        row = FlowWidget(spacing=10)
        self.repo_combo = QComboBox()
        self.repo_combo.setMinimumWidth(200)
        self.repo_combo.currentTextChanged.connect(self._on_repo_changed)
        row.add(self.repo_combo)
        row.add(button("Choose…", variant="outline", icon="folder", on_click=self.pick_repo))
        row.add(label("Commit convention", "dim"))
        self.convention = QComboBox()
        self.convention.addItems(["Conventional Commits", "Plain imperative", "Angular style"])
        row.add(self.convention)
        bar.add(row)
        layout.addWidget(bar)

        self.split = QSplitter(Qt.Orientation.Horizontal)

        # ---------------------------------------------------------- left panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        commits_card = Card("Recent commits", "Used as the source for release notes")
        self.commits = QListWidget()
        self.commits.setMinimumHeight(80)
        commits_card.add(self.commits)
        commits_card.add(
            button("Load commits", variant="ghost", icon="download", on_click=self.load_commits)
        )
        left_layout.addWidget(commits_card, 1)

        releases_card = Card("Releases", "Published versions on GitHub")
        self.releases = QListWidget()
        self.releases.setMinimumHeight(80)
        releases_card.add(self.releases)
        releases_card.add(
            button(
                "Load releases",
                variant="ghost",
                icon="download",
                on_click=self.load_releases,
            )
        )
        left_layout.addWidget(releases_card, 1)
        self.split.addWidget(left)

        # --------------------------------------------------------- right panel
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        notes_card = Card("AI release notes", "Generated from the commit list")
        notes_actions = QHBoxLayout()
        notes_actions.setSpacing(8)
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("v1.2.0")
        notes_actions.addWidget(self.tag_input)
        notes_actions.addWidget(
            button("Generate notes", variant="primary", icon="wand", on_click=self.generate_notes)
        )
        notes_actions.addWidget(button("Publish", variant="outline", icon="upload", on_click=self.publish))
        notes_card.add_layout(notes_actions)
        self.notes = MarkdownStreamView(css=markdown_css())
        self.notes.setMinimumHeight(150)
        self.notes.setHtml(
            f"<style>{markdown_css()}</style>"
            '<div style="color:#737373">Press <b>Generate notes</b> to turn the '
            "commit list into release notes.</div>"
        )
        notes_card.add(self.notes)
        right_layout.addWidget(notes_card, 1)

        commit_card = Card("Commit message", "Describe your change, get a Conventional Commit")
        commit_actions = QHBoxLayout()
        commit_actions.addWidget(
            button(
                "Write commit message",
                variant="outline",
                icon="git-commit",
                on_click=self.write_commit,
            )
        )
        commit_actions.addWidget(
            button("Copy message", variant="ghost", icon="copy", on_click=self.copy_commit)
        )
        commit_actions.addStretch(1)
        commit_card.add_layout(commit_actions)
        self.commit_output = QPlainTextEdit()
        self.commit_output.setPlaceholderText("subject line\n\nbody\n\nCloses #12")
        self.commit_output.setMinimumHeight(90)
        commit_card.add(self.commit_output)
        commit_card.setMinimumHeight(190)
        right_layout.addWidget(commit_card, 2)

        branch_card = Card("Branch name", "Conventional, lowercase, hyphenated")
        self.branch_output = QLineEdit()
        self.branch_output.setReadOnly(True)
        self.branch_output.setPlaceholderText("feat/add-readme-studio")
        branch_card.add(self.branch_output)
        branch_row = QHBoxLayout()
        branch_row.addWidget(
            button("Suggest name", variant="outline", icon="wand", on_click=self.suggest_branch)
        )
        branch_row.addWidget(
            button(
                "Create branch",
                variant="primary",
                icon="git-branch",
                on_click=self.create_branch,
            )
        )
        branch_row.addWidget(button("Copy", variant="ghost", icon="copy", on_click=self.copy_branch))
        branch_card.add_layout(branch_row)
        branch_card.setMinimumHeight(140)
        right_layout.addWidget(branch_card)

        # The right column can be taller than the window on small screens, so it
        # gets its own scroll area instead of being squeezed to nothing.
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(right)

        self.split.addWidget(right_scroll)
        self.split.setSizes([420, 700])
        layout.addWidget(self.split, 1)

    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first.", "warning")
            return
        current = self.repo or self.ctx.config.get("last_repo", "")
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        for repo in self.ctx.repos:
            self.repo_combo.addItem(repo.full_name)
        self.repo_combo.blockSignals(False)
        if not self.ctx.repos_loaded:
            workers.run(
                "rel-repos",
                lambda: self.ctx.github.list_repos(sort="updated"),
                on_result=lambda repos: self._fill(repos, current),
                on_error=lambda message: self.notify(message, "error"),
            )
            return
        # Signals stay blocked while the selection moves. setCurrentText is a
        # no-op when the value already matches, so the load is triggered by an
        # explicit call rather than by the change signal.
        if current and self.repo_combo.findText(current) >= 0:
            self.repo_combo.setCurrentText(current)
        if self.repo_combo.count():
            self._on_repo_changed(self.repo_combo.currentText())

    def _fill(self, repos: list[Any], current: str) -> None:
        self.ctx.repos = repos
        self.ctx.repos_loaded = True
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        for repo in repos:
            self.repo_combo.addItem(repo.full_name)
        self.repo_combo.blockSignals(False)
        if current and self.repo_combo.findText(current) >= 0:
            self.repo_combo.setCurrentText(current)
        if self.repo_combo.count():
            self._on_repo_changed(self.repo_combo.currentText())

    def _on_repo_changed(self, full_name: str) -> None:
        self.repo = full_name
        if full_name:
            self.ctx.config.save(last_repo=full_name)
            self.refresh()

    def pick_repo(self) -> None:
        if not self.ctx.repos:
            self.notify("Repositories are still loading.", "info")
            return
        dlg = RepoPickerDialog(self, self.ctx.repos)
        if dlg.exec():
            picked = dlg.selection()
            if picked:
                self.repo_combo.setCurrentText(picked[0])

    # --------------------------------------------------------------- loading
    def refresh(self) -> None:
        self.load_commits()
        self.load_releases()

    def load_commits(self) -> None:
        if not self.repo:
            return
        self.commits.clear()
        self.commits.addItem(QListWidgetItem("Loading commits…"))
        workers.run(
            "rel-commits",
            lambda: self.ctx.github.list_commits(self.repo, limit=40),
            on_result=self._on_commits,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_commits(self, commits: list[Any]) -> None:
        self.commits.clear()
        self.commits_to_text = commits
        if not commits:
            self.commits.addItem(QListWidgetItem("No commits found."))
            return
        for commit in commits:
            item = QListWidgetItem(f"{commit.sha}  {commit.message}")
            item.setToolTip(f"{commit.author} · {commit.date}")
            self.commits.addItem(item)
        if not self.tag_input.text().strip():
            self.tag_input.setPlaceholderText(self.suggest_tag())

    def suggest_tag(self) -> str:
        """Next version to publish, derived from the already loaded releases.

        Deliberately local: this is reached from the commit refresh callback on
        the GUI thread, so it must not touch the network.
        """
        if not self.releases_to_tags:
            return "v1.0.0"
        tag = self.releases_to_tags[0]
        if tag.startswith("v") and tag[1:2].isdigit():
            # split(), not partition(): partition keeps the whole remainder
            # after the first dot, so "v1.2.0" would yield minor="2.0" and the
            # version would never actually be bumped.
            parts = tag[1:].split(".")
            major = parts[0]
            minor = parts[1] if len(parts) > 1 else "0"
            if minor.isdigit():
                return f"v{major}.{int(minor) + 1}.0"
        return f"{tag}-next"

    def load_releases(self) -> None:
        if not self.repo:
            return
        self.releases.clear()
        self.releases.addItem(QListWidgetItem("Loading releases…"))
        workers.run(
            "rel-releases",
            lambda: self.ctx.github.list_releases(self.repo),
            on_result=self._on_releases,
            on_error=lambda _m: self.releases.clear(),
        )

    def _on_releases(self, releases: list[Any]) -> None:
        self.releases.clear()
        self.releases_to_tags = [release.tag for release in releases]
        # Keep the suggested version in step even when the commit list is
        # already on screen and no new commit callback will arrive.
        if not self.tag_input.text().strip():
            self.tag_input.setPlaceholderText(self.suggest_tag())
        if not releases:
            self.releases.addItem(QListWidgetItem("No releases yet."))
            return
        for release in releases:
            flags = []
            if release.draft:
                flags.append("draft")
            if release.prerelease:
                flags.append("pre-release")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            item = QListWidgetItem(f"{release.tag} · {release.name}{suffix}")
            item.setToolTip(release.published_at)
            self.releases.addItem(item)

    # ----------------------------------------------------------- AI features
    def generate_notes(self) -> None:
        if not self.require_ai():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        tag = self.tag_input.text().strip() or self.suggest_tag()
        self.notes.setHtml(f"<style>{markdown_css()}</style><div>Writing release notes…</div>")

        def task() -> Any:
            commits = self.commits_to_text or self.ctx.github.list_commits(self.repo, limit=60)
            return ai_tasks.release_notes(
                self.ctx.ai(), repo=self.repo, tag=tag, commits=commits, stream=True
            )

        workers.run(
            "rel-notes",
            task,
            on_progress=lambda chunk: self.notes.append_markdown(chunk),
            on_result=lambda text: self.notes.setHtml(
                f"<style>{markdown_css()}</style>" + render_markdown(text)
            ),
            on_error=lambda message: self.notify(message, "error"),
        )

    def write_commit(self) -> None:
        if not self.require_ai():
            return
        dlg = TextInputDialog(
            self,
            "Describe the change",
            "Summarise the diff in plain language and the AI writes the commit message.",
            fields=[("Description", "", "e.g. added caching layer to the HTTP client")],
            accept_text="Write message",
        )
        if not dlg.exec():
            return
        description = dlg.values().get("Description", "").strip()
        if not description:
            return
        self.notify("Writing commit message…")

        workers.run(
            "rel-commit-msg",
            lambda: ai_tasks.commit_message(
                self.ctx.ai(),
                diff_summary=description,
                convention=self.convention.currentText(),
            ),
            on_result=lambda text: self.commit_output.setPlainText(text.strip()),
            on_error=lambda message: self.notify(message, "error"),
        )

    def suggest_branch(self) -> None:
        if not self.require_ai():
            return
        description = self.commit_output.toPlainText().strip()
        if not description:
            self.notify("Write or describe a change first.", "warning")
            return
        workers.run(
            "rel-branch",
            lambda: ai_tasks.branch_name(self.ctx.ai(), description),
            on_result=self.branch_output.setText,
            on_error=lambda message: self.notify(message, "error"),
        )

    # ------------------------------------------------------------ publishing
    def publish(self) -> None:
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        body = self.notes.toPlainText().strip()
        if not body:
            self.notify("Generate the notes first.", "warning")
            return
        tag = self.tag_input.text().strip() or self.suggest_tag()
        if not confirm(
            self,
            f"Publish {tag}?",
            f"A GitHub release will be created in {self.repo} with the generated notes.",
            accept_text="Publish release",
        ):
            return

        workers.run(
            "rel-publish",
            lambda: self.ctx.github.create_release(self.repo, tag, tag, body),
            on_result=lambda release: self.notify(f"Published {release.tag}.", "success"),
            on_error=lambda message: self.notify(message, "error"),
            on_finish=self.load_releases,
        )

    def create_release(self) -> None:
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        dlg = TextInputDialog(
            self,
            "New release",
            "Create a release. Leave the body empty to use the AI generated notes.",
            fields=[
                ("Tag", self.suggest_tag(), "v1.2.0"),
                ("Name", "", "Release title"),
                ("Body", "", "Release notes in markdown"),
            ],
            accept_text="Create",
        )
        if not dlg.exec():
            return
        values = dlg.values()
        tag = values.get("Tag", "").strip()
        if not tag:
            self.notify("A tag is required.", "warning")
            return
        body = values.get("Body", "").strip() or self.notes.toPlainText().strip()

        workers.run(
            "rel-create",
            lambda: self.ctx.github.create_release(
                self.repo, tag, values.get("Name", "").strip() or tag, body
            ),
            on_result=lambda release: self.notify(f"Created release {release.tag}.", "success"),
            on_error=lambda message: self.notify(message, "error"),
            on_finish=self.load_releases,
        )

    def create_branch(self) -> None:
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        name = self.branch_output.text().strip()
        if not name:
            self.notify("Suggest a branch name first.", "warning")
            return
        workers.run(
            "rel-branch-create",
            lambda: self.ctx.github.create_branch(self.repo, name),
            on_result=lambda _r: self.notify(f"Branch {name} created.", "success"),
            on_error=lambda message: self.notify(message, "error"),
        )

    # ----------------------------------------------------------------- utils
    def copy_commit(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.commit_output.toPlainText())
        self.notify("Commit message copied.", "success")

    def copy_branch(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.branch_output.text())
        self.notify("Branch name copied.", "success")
