"""Repository management: list, filter, create, edit, delete and AI assists."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from ...core.github_api import RepoSummary
from .. import workers
from ..dialogs import (
    CreateRepoDialog,
    DiffDialog,
    EditRepoDialog,
    PromptDialog,
    RepoPickerDialog,
    UploadFileDialog,
    confirm,
)
from ..widgets import (
    Badge,
    Card,
    FlowWidget,
    PageHeader,
    button,
    icon_button,
    icon_svg,
    label,
    spacer,
)
from .base import Page

SORTS = {
    "Recently updated": "updated",
    "Most stars": "stars",
    "Most forks": "forks",
    "Name": "name",
    "Newest": "created",
}


class RepoCard(QFrame):
    """Rich repository tile with inline actions."""

    openReadme = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal(str)
    archiveToggled = Signal(str, bool)
    openBrowser = Signal(str)
    forkRequested = Signal(str)
    uploadRequested = Signal(str)

    def __init__(self, repo: RepoSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setObjectName("CardHover")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 14, 12)
        layout.setSpacing(9)

        # ------------------------------------------------------------- title
        top = QHBoxLayout()
        top.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(icon_svg("lock" if repo.private else "folder", "#7c6cff", 18).pixmap(18, 18))
        top.addWidget(icon)

        name = label(repo.full_name, "")
        name.setStyleSheet("font-weight:600; font-size:11pt;")
        name.setToolTip(repo.full_name)
        top.addWidget(name)

        if repo.fork:
            top.addWidget(Badge("fork", ""))
        if repo.archived:
            top.addWidget(Badge("archived", "Warning"))
        if repo.private:
            top.addWidget(Badge("private", "Warning"))
        top.addWidget(spacer())

        top.addWidget(
            icon_button("external", tooltip="Open on github.com", on_click=self._open_browser)
        )
        more = icon_button("list", tooltip="More actions")
        menu = QMenu(more)
        menu.addAction("Edit settings…").triggered.connect(self._edit)
        menu.addAction("Upload files…").triggered.connect(self._upload)
        menu.addAction("Open in README Studio").triggered.connect(self._open_readme)
        menu.addAction("Copy clone URL").triggered.connect(self._copy_clone)
        menu.addSeparator()
        menu.addAction("Unarchive" if repo.archived else "Archive").triggered.connect(
            self._toggle_archive
        )
        menu.addAction("Fork on GitHub").triggered.connect(
            lambda: self.forkRequested.emit(self.repo.full_name)
        )
        menu.addSeparator()
        menu.addAction("Delete repository…").triggered.connect(
            lambda: self.deleteRequested.emit(self.repo.full_name)
        )
        more.setMenu(menu)
        top.addWidget(more)
        layout.addLayout(top)

        # description
        desc = label(
            repo.description or "No description yet — the AI can write one.",
            "dim",
            wrap=True,
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        # Elide to two lines rather than growing, so cards in a row stay the
        # same height regardless of description length.
        desc.setTextFormat(Qt.TextFormat.PlainText)
        desc.setMinimumHeight(40)
        desc.setMaximumHeight(40)
        layout.addWidget(desc)

        # metrics
        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        for value, icon_name in (
            (repo.stars, "star"),
            (repo.forks, "fork"),
            (repo.open_issues, "issue"),
            (f"{repo.size_kb} KB", "archive"),
        ):
            item = QHBoxLayout()
            item.setSpacing(4)
            pix = QLabel()
            pix.setPixmap(icon_svg(icon_name, "#6b7690", 13).pixmap(13, 13))
            item.addWidget(pix)
            item.addWidget(label(str(value), "faint"))
            metrics.addLayout(item)
        metrics.addStretch(1)
        metrics.addWidget(label(repo.language or "—", "faint"))
        layout.addLayout(metrics)

        # topics + actions
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        flow = FlowWidget(spacing=5)
        for topic in repo.topics[:5]:
            flow.add(Badge(topic, "Accent"))
        if len(repo.topics) > 5:
            flow.add(Badge(f"+{len(repo.topics) - 5}", ""))
        bottom.addWidget(flow, 1)
        bottom.addWidget(
            button("README", variant="ghost", icon="book", on_click=self._open_readme)
        )
        # Icon rather than a labelled button: three ghost buttons in a row do not
        # fit a narrow card, and this row already has to wrap.
        bottom.addWidget(
            icon_button("upload", tooltip="Upload files to this repository", on_click=self._upload)
        )
        bottom.addWidget(button("Edit", variant="ghost", icon="edit", on_click=self._edit))
        bottom_row = QWidget()
        bottom_row.setLayout(bottom)
        layout.addWidget(bottom_row)

    # ------------------------------------------------------------- handlers
    def _open_readme(self) -> None:
        self.openReadme.emit(self.repo.full_name)

    def _edit(self) -> None:
        self.editRequested.emit(self.repo.full_name)

    def _upload(self) -> None:
        self.uploadRequested.emit(self.repo.full_name)

    def _open_browser(self) -> None:
        self.openBrowser.emit(self.repo.full_name)

    def _toggle_archive(self) -> None:
        self.archiveToggled.emit(self.repo.full_name, not self.repo.archived)

    def _copy_clone(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(f"https://github.com/{self.repo.full_name}.git")
        self.setToolTip("Clone URL copied")


class ReposPage(Page):
    title = "Repositories"
    subtitle = "Create, tune and organise everything you own on GitHub."
    icon = "folder"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.repos: list[RepoSummary] = []
        self.cards: dict[str, RepoCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        self.header = PageHeader("Repositories", "Pulled straight from the GitHub API")
        self.header.add_action(
            button("AI description", variant="outline", icon="wand", on_click=self.ai_description)
        )
        self.header.add_action(
            button("New repository", variant="primary", icon="plus", on_click=self.create_repo)
        )
        self.header.add_action(icon_button("refresh", tooltip="Refresh", on_click=self.refresh))
        layout.addWidget(self.header)

        # ----------------------------------------------------------- filters
        filter_card = Card(flat=True)
        row = QHBoxLayout()
        row.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, description or topic…")
        self.search.setProperty("role", "search")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(
            icon_svg("search", "#6b7690", 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search.textChanged.connect(self._render)
        row.addWidget(self.search, 1)

        self.scope = QComboBox()
        self.scope.addItems(["All repositories", "Public only", "Private only"])
        self.scope.currentIndexChanged.connect(self._render)
        row.addWidget(self.scope)

        self.sort = QComboBox()
        self.sort.addItems(list(SORTS))
        self.sort.currentIndexChanged.connect(self._render)
        row.addWidget(self.sort)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Grid", "Compact"])
        self.layout_combo.currentIndexChanged.connect(self._render)
        row.addWidget(self.layout_combo)
        filter_card.add_layout(row)
        layout.addWidget(filter_card)

        self.count_label = label("", "faint")
        layout.addWidget(self.count_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self.scroll.setWidget(host)
        layout.addWidget(self.scroll, 1)

        self.empty = Card("No repositories", "Nothing matched the current filters.")
        self.empty.setVisible(False)
        layout.addWidget(self.empty, 1)

    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first.", "warning")
            return
        if self.ctx.repos_loaded:
            self.repos = self.ctx.repos
            self._render()
        else:
            self.refresh()

    def refresh(self) -> None:
        if not self.ctx.signed_in:
            return
        self.count_label.setText("Loading repositories…")
        workers.run(
            "repos-load",
            lambda: self.ctx.github.list_repos(sort="updated"),
            on_result=self._on_loaded,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_loaded(self, repos: list[RepoSummary]) -> None:
        self.ctx.repos = repos
        self.ctx.repos_loaded = True
        self.repos = repos
        self._render()

    # -------------------------------------------------------------- filters
    def _render(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.cards.clear()

        repos = self._filtered()
        stars = sum(r.stars for r in repos)
        self.count_label.setText(
            f"{len(repos)} of {len(self.repos)} repositories"
            + (f" · {stars} stars in view" if repos else "")
        )
        if not repos:
            self.scroll.setVisible(False)
            self.empty.setVisible(True)
            return
        self.scroll.setVisible(True)
        self.empty.setVisible(False)

        columns = 1 if self.layout_combo.currentText() == "Compact" else 2
        for index, repo in enumerate(repos):
            card = RepoCard(repo)
            card.openReadme.connect(self.open_readme_for)
            card.editRequested.connect(self.edit_repo)
            card.deleteRequested.connect(self.delete_repo)
            card.archiveToggled.connect(self.toggle_archive)
            card.openBrowser.connect(self.open_in_browser)
            card.forkRequested.connect(self.fork_repo)
            card.uploadRequested.connect(self.upload_files)
            self.cards[repo.full_name] = card
            self.grid.addWidget(card, index // columns, index % columns)
        self.grid.setRowStretch(self.grid.rowCount(), 1)

    def _filtered(self) -> list[RepoSummary]:
        needle = self.search.text().lower().strip()
        scope = self.scope.currentText()
        result: list[RepoSummary] = []
        for repo in self.repos:
            if scope == "Public only" and repo.private:
                continue
            if scope == "Private only" and not repo.private:
                continue
            if needle:
                haystack = " ".join(
                    [repo.full_name, repo.description, " ".join(repo.topics), repo.language]
                ).lower()
                if needle not in haystack:
                    continue
            result.append(repo)

        key = SORTS[self.sort.currentText()]
        if key == "stars":
            result.sort(key=lambda r: -r.stars)
        elif key == "forks":
            result.sort(key=lambda r: -r.forks)
        elif key == "name":
            result.sort(key=lambda r: r.full_name.lower())
        elif key == "created":
            result.sort(key=lambda r: r.created_at, reverse=True)
        else:
            result.sort(key=lambda r: r.updated_at, reverse=True)
        return result

    # ----------------------------------------------------------- operations
    def open_in_browser(self, full_name: str) -> None:
        webbrowser.open(f"https://github.com/{full_name}")

    def open_readme_for(self, full_name: str) -> None:
        window = self.window()
        if hasattr(window, "focus_readme"):
            window.focus_readme(full_name)

    def edit_repo(self, full_name: str) -> None:
        repo = self.ctx.find_repo(full_name)
        if not repo:
            return
        # The dialog needs the current file list to offer deletions, and that
        # list costs a network call. An archived repository is read only, so
        # there is nothing to list and the fetch would only fail.
        if repo.archived:
            self._open_edit_dialog(full_name, repo, [])
            return
        self.notify("Loading files…")
        workers.run(
            "repo-edit-files",
            lambda: self.ctx.github.list_files(full_name),
            on_result=lambda files: self._open_edit_dialog(full_name, repo, files),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _open_edit_dialog(
        self, full_name: str, repo: Any, files: list[dict[str, Any]]
    ) -> None:
        dlg = EditRepoDialog(self, repo, files=files)
        if not dlg.exec():
            return

        problem = dlg.validate_files()
        if problem:
            self.notify(problem, "warning")
            return

        values = dlg.values()
        self.notify("Updating repository settings…")
        workers.run(
            "repo-edit",
            lambda: self.ctx.github.update_repo(full_name, **values),
            on_result=lambda updated: self._after_file_changes(dlg, full_name, updated),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _after_file_changes(self, dlg: Any, full_name: str, repo: RepoSummary) -> None:
        """Apply the file changes once the settings update has landed."""
        deletions = dlg.deletions()
        additions = dlg.additions()
        if not deletions and not additions:
            self._after_update(repo)
            return

        message = dlg.file_message()
        branch = repo.default_branch
        # Deletions first, deliberately. A delete has to quote the sha the file
        # currently has, so removing before uploading keeps a path that is
        # deleted and re-added at a new destination from being clobbered by the
        # order the requests happen to land in.
        todo: list[tuple[str, str, str | None]] = [
            (str(entry.get("path") or ""), "", str(entry.get("sha") or "")) for entry in deletions
        ]
        todo += [(target, source, None) for source, target in additions]
        self._apply_file_changes(full_name, todo, message, branch, 0)

    def _apply_file_changes(
        self,
        full_name: str,
        pending: list[tuple[str, str, str | None]],
        message: str,
        branch: str,
        done: int,
    ) -> None:
        """Run one file change, then queue the next.

        GitHub takes one file per request, so a batch is a sequence. Reporting
        each step as it lands is what makes a long change legible, and stopping
        on the first failure leaves the repository in a state the user can see
        rather than one they have to guess at.
        """
        if not pending:
            noun = "change" if done == 1 else "changes"
            self.notify(f"Applied {done} file {noun} to {full_name}.", "success")
            self._refresh_repo(full_name)
            return

        path, source, sha = pending[0]
        rest = pending[1:]

        if sha is not None:
            if not path or not sha:
                # A delete with nothing to quote cannot succeed, so say which
                # file was skipped and carry on with the rest.
                self.notify(f"Skipped {path or 'a file'}: the server gave no sha.", "error")
                self._apply_file_changes(full_name, rest, message, branch, done)
                return
            self.notify(f"Deleting {path}…")

            def delete_task() -> Any:
                return self.ctx.github.delete_file(full_name, path, message, sha, branch)

            workers.run(
                "repo-file-delete",
                delete_task,
                on_result=lambda _r: self._apply_file_changes(
                    full_name, rest, message, branch, done + 1
                ),
                on_error=lambda problem: self.notify(f"{path}: {problem}", "error"),
            )
            return

        try:
            data = Path(source).read_bytes()
        except OSError as exc:
            self.notify(f"Could not read {Path(path).name}: {exc}", "error")
            self._apply_file_changes(full_name, rest, message, branch, done)
            return

        self.notify(f"Uploading {path}…")

        def upload_task() -> Any:
            return self.ctx.github.put_file(full_name, path, data, message, branch)

        workers.run(
            "repo-file-put",
            upload_task,
            on_result=lambda _r: self._apply_file_changes(full_name, rest, message, branch, done + 1),
            on_error=lambda problem: self.notify(f"{path}: {problem}", "error"),
        )

    def upload_files(self, full_name: str) -> None:
        """Commit one or more files from disk into a repository."""
        repo = self.ctx.find_repo(full_name)
        dlg = UploadFileDialog(
            self,
            full_name,
            default_branch=(repo.default_branch if repo else ""),
        )
        if not dlg.exec():
            return
        problem = dlg.validate()
        if problem:
            self.notify(problem, "warning")
            return

        selections = dlg.items()
        message = dlg.commit_message()
        branch = dlg.target_branch()
        overwrite = dlg.allow_overwrite()
        self.notify(f"Uploading {len(selections)} file(s) to {full_name}…")
        self._run_upload(full_name, selections, message, branch, overwrite, [])

    def _run_upload(
        self,
        full_name: str,
        pending: list[tuple[str, str]],
        message: str,
        branch: str,
        overwrite: bool,
        done: list[str],
    ) -> None:
        """Upload one file, then queue the next.

        GitHub's contents API commits a single file per request, so a batch has
        to be a sequence. Chaining through the worker thread keeps the UI
        responsive and reports each file as it lands, instead of leaving the user
        watching one spinner for a long upload with no feedback.
        """
        if not pending:
            count = len(done)
            plural = "file" if count == 1 else "files"
            self.notify(f"Uploaded {count} {plural} to {full_name}.", "success")
            self._refresh_repo(full_name)
            return

        source, target = pending[0]
        try:
            data = Path(source).read_bytes()
        except OSError as exc:
            self.notify(f"Could not read {Path(source).name}: {exc}", "error")
            return

        def task() -> Any:
            return self.ctx.github.put_file(
                full_name, target, data, message, branch, overwrite=overwrite
            )

        workers.run(
            "repo-upload",
            task,
            on_result=lambda _r: (
                done.append(target),
                self.notify(f"{target} uploaded.", "success"),
                self._run_upload(
                    full_name, pending[1:], message, branch, overwrite, done
                ),
            ),
            on_error=lambda problem: self.notify(f"{target}: {problem}", "error"),
        )

    def _refresh_repo(self, full_name: str) -> None:
        """Pull one repository's current state so the card stops lying."""
        workers.run(
            "repo-refresh-one",
            lambda: self.ctx.github.get_repo(full_name),
            on_result=self._after_update,
            on_error=lambda message: self.notify(message, "error"),
        )

    def delete_repo(self, full_name: str) -> None:
        if not confirm(
            self,
            f"Delete {full_name}?",
            "This permanently removes the repository, its issues, releases and history "
            "from GitHub. This action cannot be undone.",
            accept_text="Delete repository",
            danger=True,
        ):
            return
        typed = PromptDialog(
            self,
            "Confirm deletion",
            "Type the repository name exactly to confirm.",
            placeholder=full_name,
            accept_text="Delete",
        )
        if not typed.exec():
            return
        if typed.value().strip() != full_name:
            self.notify("Name did not match, nothing was deleted.", "warning")
            return

        self.notify("Deleting repository…")
        workers.run(
            "repo-delete",
            lambda: self.ctx.github.delete_repo(full_name),
            on_result=lambda _r: self._after_delete(full_name),
            on_error=lambda message: self.notify(message, "error"),
        )

    def toggle_archive(self, full_name: str, archived: bool) -> None:
        workers.run(
            "repo-archive",
            lambda: self.ctx.github.update_repo(full_name, archived=archived),
            on_result=self._after_update,
            on_error=lambda message: self.notify(message, "error"),
        )

    def fork_repo(self, full_name: str) -> None:
        if not confirm(
            self,
            f"Fork {full_name}?",
            "A copy will be created in your account. Nothing in the original repository "
            "is modified.",
            accept_text="Fork",
        ):
            return
        workers.run(
            "repo-fork",
            lambda: self.ctx.github.fork_repo(full_name),
            on_result=lambda repo: self._after_update(repo, announce="Forked"),
            on_error=lambda message: self.notify(message, "error"),
        )

    def create_repo(self) -> None:
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first.", "warning")
            return
        dlg = CreateRepoDialog(self, self.ctx.config.get("github_login", ""))
        if not dlg.exec():
            return
        values = dlg.values()
        if not values["name"]:
            self.notify("Repository name is required.", "warning")
            return
        problem = dlg.validate_files()
        if problem:
            self.notify(problem, "warning")
            return
        # The API takes no file content in the create call, so the chosen files
        # are a second step. Keep them: the repository is still worth creating if
        # a later upload fails, and the user is told which files did not land.
        files = dlg.files()
        self.notify(f"Creating {values['name']}…")

        workers.run(
            "repo-create",
            lambda: self.ctx.github.create_repo(**values),
            on_result=lambda repo: self._after_create_with_files(repo, files),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _after_create_with_files(self, repo: RepoSummary, files: list[tuple[str, str]]) -> None:
        self._after_create(repo)
        if not files:
            return
        message = f"docs: add {len(files)} initial file(s)".replace(
            "1 initial file(s)", "the initial file"
        )
        self.notify(f"Committing {len(files)} file(s) to {repo.full_name}…")
        self._apply_file_changes(
            repo.full_name,
            [(target, source, None) for source, target in files],
            message,
            repo.default_branch or "main",
            0,
        )

    # ------------------------------------------------------------ AI assists
    def ai_description(self) -> None:
        if not self.require_ai():
            return
        if not self.ctx.signed_in:
            return
        if not self.ctx.repos:
            self.refresh()
            return
        dlg = RepoPickerDialog(
            self, self.ctx.repos, subtitle="Which repository should the AI improve?"
        )
        if not dlg.exec():
            return
        picked = dlg.selection()
        if not picked:
            return
        full_name = picked[0]
        self.notify("Reading repository…")

        def task() -> dict[str, Any]:
            ctx = ai_tasks.build_repo_context(self.ctx.github, full_name)
            return {
                "description": ai_tasks.suggest_description(self.ctx.ai(), ctx),
                "topics": ai_tasks.suggest_topics(self.ctx.ai(), ctx),
            }

        workers.run(
            "repo-ai-desc",
            task,
            on_result=lambda result: self._show_ai_suggestion(full_name, result),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _show_ai_suggestion(self, full_name: str, result: dict[str, Any]) -> None:
        topics = ", ".join(result["topics"])
        body = (
            f"**Description**\n\n{result['description']}\n\n"
            f"**Topics**\n\n{topics}\n\n"
            "Nothing is sent to GitHub until you press Apply."
        )
        dlg = DiffDialog(
            self,
            f"AI suggestion for {full_name}",
            body,
            accept_text="Apply to repository",
        )
        if not dlg.exec():
            return
        workers.run(
            "repo-ai-apply",
            lambda: self.ctx.github.update_repo(
                full_name, description=result["description"], topics=result["topics"]
            ),
            on_result=lambda repo: self._after_update(repo, announce="Applied suggestion to"),
            on_error=lambda message: self.notify(message, "error"),
        )

    # --------------------------------------------------------------- results
    def _after_update(self, repo: RepoSummary, announce: str = "Updated") -> None:
        for index, existing in enumerate(self.repos):
            if existing.full_name == repo.full_name:
                self.repos[index] = repo
                break
        else:
            self.repos.append(repo)
        self.ctx.repos = self.repos
        self.ctx.repos_loaded = True
        self.notify(f"{announce} {repo.full_name}.", "success")
        self._render()

    def _after_create(self, repo: RepoSummary) -> None:
        self.repos.insert(0, repo)
        self.ctx.repos = self.repos
        self.ctx.repos_loaded = True
        self.notify(f"Created {repo.full_name}.", "success")
        self._render()

    def _after_delete(self, full_name: str) -> None:
        self.repos = [r for r in self.repos if r.full_name != full_name]
        self.ctx.repos = self.repos
        self.notify(f"{full_name} deleted.", "success")
        self._render()
