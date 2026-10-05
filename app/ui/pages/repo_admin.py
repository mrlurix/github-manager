"""Repository management: files, branches, tags, collaborators and webhooks.

The Repositories page lists repositories and handles their settings. This page
is the other half - what is actually inside one. GitHub splits this across a
handful of screens on the website; here it is one page with a repository picker
and a tab per concern, because switching repository should not mean switching
screen.

Everything is read from the API rather than guessed: a file's sha comes back
with the listing, so a delete or an overwrite always quotes the version it read.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import workers
from ..dialogs import confirm
from ..widgets import (
    Card,
    PageHeader,
    button,
    label,
)
from .base import Page

TABS = ["Files", "Branches", "Tags", "Collaborators", "Webhooks"]

#: Collaborator permissions, mapped to the values the API expects.
PERMISSIONS = {
    "read": "read",
    "triage": "triage",
    "write": "write",
    "maintain": "maintain",
    "admin": "admin",
}


class _Toolbar(QFrame):
    """Repository picker plus the actions that apply to the whole repository."""

    def __init__(self, page: "RepoAdminPage") -> None:
        super().__init__(page)
        self.setObjectName("CardFlat")
        self.page = page
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)

        self.repo = QComboBox()
        self.repo.setMinimumWidth(240)
        self.repo.currentIndexChanged.connect(page.on_repo_changed)
        row.addWidget(self.repo, 1)

        self.branch = QComboBox()
        self.branch.setMinimumWidth(150)
        self.branch.setToolTip("Branch to read from")
        self.branch.currentIndexChanged.connect(page.on_branch_changed)
        row.addWidget(self.branch)

        row.addWidget(button("Refresh", variant="ghost", icon="refresh", on_click=page.reload))
        row.addWidget(button("Open on GitHub", variant="ghost", icon="external",
                            on_click=page.open_in_browser))

    def selected_repo(self) -> str:
        return self.repo.currentText().strip()

    def selected_branch(self) -> str:
        return self.branch.currentText().strip()


class RepoAdminPage(Page):
    title = "Repository"
    subtitle = "Files, branches, tags, collaborators and webhooks."
    icon = "folder"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.repo = ""
        self.branch = ""
        self.files: list[dict[str, Any]] = []
        self.branches: list[str] = []
        self.tags: list[dict[str, Any]] = []
        self.collaborators: list[dict[str, Any]] = []
        self.webhooks: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        self.header = PageHeader("Repository", "What is inside one of your repositories")
        self.header.add_action(
            button("Upload files", variant="primary", icon="upload", on_click=self.upload_files)
        )
        layout.addWidget(self.header)

        self.toolbar = _Toolbar(self)
        layout.addWidget(self.toolbar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        layout.addWidget(self.tabs, 1)

        self._build_files_tab()
        self._build_branches_tab()
        self._build_tags_tab()
        self._build_collaborators_tab()
        self._build_webhooks_tab()

        self.status = label("", "faint")
        layout.addWidget(self.status)

    # ------------------------------------------------------------- lifecycle
    def on_show(self) -> None:
        if self.ctx.signed_in and not self.repo:
            self._load_repo_list()

    def _load_repo_list(self) -> None:
        if self.ctx.repos:
            self._fill_repo_combo()
            return
        self.notify("Loading repositories…")
        workers.run(
            "admin-repos",
            lambda: self.ctx.github.list_repos(),
            on_result=lambda repos: self._fill_repo_combo(repos),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _fill_repo_combo(self, repos: list[Any] | None = None) -> None:
        names = (
            [r.full_name for r in repos]
            if repos is not None
            else [r.full_name for r in self.ctx.repos]
        )
        current = self.toolbar.selected_repo()
        self.toolbar.repo.blockSignals(True)
        self.toolbar.repo.clear()
        self.toolbar.repo.addItems(sorted(names))
        self.toolbar.repo.blockSignals(False)
        if current and current in names:
            self.toolbar.repo.setCurrentText(current)
        if names:
            self.toolbar.selected_repo()
            self.reload()

    def on_repo_changed(self) -> None:
        self.repo = self.toolbar.selected_repo()
        self.reload()

    def on_branch_changed(self) -> None:
        self.branch = self.toolbar.selected_branch()
        self.reload()

    def reload(self) -> None:
        if not self.require_auth():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        self.status.setText("Loading…")
        self._load_branches()

    def _load_branches(self) -> None:
        workers.run(
            "admin-branches",
            lambda: self.ctx.github.list_branches(self.repo),
            on_result=self._on_branches,
            on_error=lambda message: self.status.setText(""),
        )

    def _on_branches(self, branches: list[str]) -> None:
        self.branches = branches
        current = self.toolbar.selected_branch()
        box = self.toolbar.branch
        box.blockSignals(True)
        box.clear()
        box.addItems(branches)
        if current in branches:
            box.setCurrentText(current)
        box.blockSignals(False)
        self.branch = box.currentText().strip()
        self._load_all()

    def _load_all(self) -> None:
        index = self.tabs.currentIndex()
        loader = (
            self._load_files,
            self._load_branches_only,
            self._load_tags,
            self._load_collaborators,
            self._load_webhooks,
        )[index]
        loader()

    # ------------------------------------------------------------------ files
    def _build_files_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.file_filter = QLineEdit()
        self.file_filter.setPlaceholderText("Filter by path…")
        self.file_filter.textChanged.connect(self._render_files)
        bar.addWidget(self.file_filter, 1)
        bar.addWidget(button("Upload", variant="ghost", icon="upload", on_click=self.upload_files))
        bar.addWidget(button("Refresh", variant="ghost", icon="refresh",
                            on_click=lambda: self._load_files()))
        layout.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["Path", "Size"])
        self.file_tree.setColumnWidth(0, 420)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_tree.setAlternatingRowColors(True)
        split.addWidget(self.file_tree)

        detail = Card("Selected file", "Nothing selected.")
        detail_layout = QVBoxLayout(detail)
        self.detail_path = label("", "mono")
        self.detail_size = label("", "faint")
        self.detail_body = QPlainTextEdit()
        self.detail_body.setReadOnly(True)
        self.detail_body.setMinimumHeight(180)
        detail_layout.addWidget(self.detail_path)
        detail_layout.addWidget(self.detail_size)
        detail_layout.addWidget(self.detail_body, 1)
        split.addWidget(detail)

        self.file_tree.currentItemChanged.connect(self._on_file_selected)
        layout.addWidget(split, 1)
        self.tabs.addTab(page, "Files")

    def _load_files(self) -> None:
        workers.run(
            "admin-files",
            lambda: self.ctx.github.list_files(self.repo, self.branch),
            on_result=self._on_files,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_files(self, files: list[dict[str, Any]]) -> None:
        self.files = files
        self._render_files()
        self.status.setText(f"{len(files)} file(s) on {self.branch or 'the default branch'}")

    def _render_files(self) -> None:
        needle = self.file_filter.text().strip().lower()
        self.file_tree.clear()
        folders: dict[str, QTreeWidgetItem] = {}
        for entry in self.files:
            path = str(entry.get("path") or "")
            if needle and needle not in path.lower():
                continue
            parts = path.split("/")
            parent: QTreeWidgetItem | None = None
            prefix = ""
            for part in parts[:-1]:
                prefix = f"{prefix}/{part}" if prefix else part
                node = folders.get(prefix)
                if node is None:
                    node = QTreeWidgetItem([part, ""])
                    (parent.addChild(node) if parent else self.file_tree.addTopLevelItem(node))
                    folders[prefix] = node
                parent = node
            size = int(entry.get("size") or 0)
            item = QTreeWidgetItem([parts[-1], _human(size)])
            item.setData(0, Qt.ItemDataRole.UserRole, path)
            item.setToolTip(0, path)
            if parent:
                parent.addChild(item)
            else:
                self.file_tree.addTopLevelItem(item)
        self.file_tree.expandToDepth(1)

    def _on_file_selected(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None = None
    ) -> None:
        if current is None:
            return
        path = current.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        entry = next((f for f in self.files if f.get("path") == path), None)
        if entry is None:
            return
        self.detail_path.setText(path)
        self.detail_size.setText(f"{_human(int(entry.get('size') or 0))}")
        workers.run(
            "admin-file-read",
            lambda: self.ctx.github.get_file(self.repo, path, self.branch),
            on_result=lambda text: self.detail_body.setPlainText(text or ""),
            on_error=lambda message: self.notify(message, "error"),
        )

    # --------------------------------------------------------------- branches
    def _build_branches_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.new_branch = QLineEdit()
        self.new_branch.setPlaceholderText("New branch name")
        bar.addWidget(self.new_branch, 1)
        bar.addWidget(button("Create", variant="primary", icon="plus",
                            on_click=self.create_branch))
        layout.addLayout(bar)

        self.branch_list = QListWidget()
        self.branch_list.itemDoubleClicked.connect(lambda _item: self._use_branch())
        layout.addWidget(self.branch_list, 1)
        self.tabs.addTab(page, "Branches")

    def _load_branches_only(self) -> None:
        self.branch_list.clear()
        for name in self.branches:
            item = QListWidgetItem(name)
            if name == self.branch:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.branch_list.addItem(item)
        self.status.setText(f"{len(self.branches)} branch(es)")

    def _use_branch(self) -> None:
        item = self.branch_list.currentItem()
        if item:
            self.toolbar.branch.setCurrentText(item.text())
            self.notify(f"Switched to {item.text()}.")

    def create_branch(self) -> None:
        name = self.new_branch.text().strip()
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        if not name:
            self.notify("A branch name is required.", "warning")
            return
        workers.run(
            "admin-branch-create",
            lambda: self.ctx.github.create_branch(self.repo, name, self.branch),
            on_result=lambda _r: (
                self.new_branch.clear(),
                self.notify(f"Created {name}.", "success"),
                self._load_branches(),
            ),
            on_error=lambda message: self.notify(message, "error"),
        )

    # ------------------------------------------------------------------- tags
    def _build_tags_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        self.tag_table = QTableWidget(0, 2)
        self.tag_table.setHorizontalHeaderLabels(["Tag", "Commit"])
        self.tag_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tag_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tag_table)
        self.tabs.addTab(page, "Tags")

    def _load_tags(self) -> None:
        workers.run(
            "admin-tags",
            lambda: self.ctx.github.list_tags(self.repo),
            on_result=self._on_tags,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_tags(self, tags: list[dict[str, Any]]) -> None:
        self.tags = tags
        self.tag_table.setRowCount(len(tags))
        for row, tag in enumerate(tags):
            self.tag_table.setItem(row, 0, QTableWidgetItem(str(tag.get("name") or "")))
            self.tag_table.setItem(row, 1, QTableWidgetItem(str(tag.get("sha") or "")[:12]))
        self.status.setText(f"{len(tags)} tag(s)")

    # ---------------------------------------------------------- collaborators
    def _build_collaborators_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.who = QLineEdit()
        self.who.setPlaceholderText("username")
        bar.addWidget(self.who, 1)
        self.permission = QComboBox()
        self.permission.addItems(list(PERMISSIONS))
        bar.addWidget(self.permission)
        bar.addWidget(button("Add", variant="primary", icon="plus", on_click=self.add_collaborator))
        # remove_collaborator reads the selected row, so it sits beside the list
        # rather than beside the fields it does not use.
        bar.addWidget(button("Remove", variant="ghost", icon="trash",
                            on_click=self.remove_collaborator))
        layout.addLayout(bar)

        self.people = QListWidget()
        layout.addWidget(self.people, 1)
        self.tabs.addTab(page, "Collaborators")

    def _load_collaborators(self) -> None:
        workers.run(
            "admin-collabs",
            lambda: self.ctx.github.list_collaborators(self.repo),
            on_result=self._on_collaborators,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_collaborators(self, people: list[dict[str, Any]]) -> None:
        self.collaborators = people
        self.people.clear()
        for person in people:
            login = str(person.get("login") or "")
            permissions = person.get("permissions") or {}
            level = next(
                (name for name, key in PERMISSIONS.items() if permissions.get(key)), "read"
            )
            item = QListWidgetItem(f"{login}  —  {level}")
            item.setData(Qt.ItemDataRole.UserRole, login)
            self.people.addItem(item)
        self.status.setText(f"{len(people)} collaborator(s)")

    def add_collaborator(self) -> None:
        login = self.who.text().strip()
        if not login:
            self.notify("A username is required.", "warning")
            return
        level = self.permission.currentText()
        workers.run(
            "admin-collab-add",
            lambda: self.ctx.github.add_collaborator(self.repo, login, PERMISSIONS[level]),
            on_result=lambda _r: (
                self.who.clear(),
                self.notify(f"Added {login} as {level}.", "success"),
                self._load_collaborators(),
            ),
            on_error=lambda message: self.notify(message, "error"),
        )

    def remove_collaborator(self) -> None:
        item = self.people.currentItem()
        if item is None:
            self.notify("Select someone first.", "warning")
            return
        login = item.data(Qt.ItemDataRole.UserRole)
        if not confirm(
            self,
            f"Remove {login}?",
            "They lose access to this repository immediately.",
            accept_text="Remove",
            danger=True,
        ):
            return
        workers.run(
            "admin-collab-remove",
            lambda: self.ctx.github.remove_collaborator(self.repo, login),
            on_result=lambda _r: (
                self.notify(f"Removed {login}.", "success"),
                self._load_collaborators(),
            ),
            on_error=lambda message: self.notify(message, "error"),
        )

    # ---------------------------------------------------------------- webhooks
    def _build_webhooks_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label("Hooks are read-only here; create them on GitHub.", "dim"))
        bar.addStretch(1)
        bar.addWidget(button("Refresh", variant="ghost", icon="refresh",
                            on_click=lambda: self._load_webhooks()))
        layout.addLayout(bar)

        self.hooks = QListWidget()
        layout.addWidget(self.hooks, 1)
        self.tabs.addTab(page, "Webhooks")

    def _load_webhooks(self) -> None:
        workers.run(
            "admin-hooks",
            lambda: self.ctx.github.list_hooks(self.repo),
            on_result=self._on_webhooks,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_webhooks(self, hooks: list[dict[str, Any]]) -> None:
        self.webhooks = hooks
        self.hooks.clear()
        for hook in hooks:
            events = ", ".join(str(e) for e in (hook.get("events") or [])) or "—"
            item = QListWidgetItem(f"{hook.get('name') or '(no name)'}   ·   {events}")
            item.setToolTip(str(hook.get("config", {}).get("url", "")))
            self.hooks.addItem(item)
        self.status.setText(f"{len(hooks)} webhook(s)")

    # ---------------------------------------------------------------- actions
    def upload_files(self) -> None:
        window = self.window()
        if hasattr(window, "focus_repos"):
            window.focus_repos(self.repo)

    def open_in_browser(self) -> None:
        import webbrowser

        if self.repo:
            webbrowser.open(f"https://github.com/{self.repo}")


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"