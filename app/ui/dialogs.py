"""Reusable modal dialogs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..core.github_api import GitHubError, validate_repo_path
from .widgets import button, hline, icon_svg, label


def _human(size: int) -> str:
    """Byte count in the largest unit that keeps it readable."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class BaseDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, subtitle: str = "", width: int = 560) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(label(title, "h2"))
        if subtitle:
            sub = label(subtitle, "dim")
            sub.setWordWrap(True)
            head.addWidget(sub)
        layout.addLayout(head)
        layout.addWidget(hline())

        # The body scrolls. A dialog whose fields are taller than the screen would
        # otherwise push its own buttons off the bottom, leaving the user unable
        # to confirm or cancel at all - and the file sections make tall dialogs
        # easy to reach.
        holder = QWidget()
        self.form = QVBoxLayout(holder)
        self.form.setSpacing(12)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.body = QScrollArea()
        self.body.setWidgetResizable(True)
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # No setStyleSheet on a widget: a widget level sheet outranks the
        # application sheet for that whole subtree.
        self.body.setWidget(holder)
        layout.addWidget(self.body, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Keep the dialog inside the screen.

        A dialog taller than the display puts its own buttons off the bottom and
        the user cannot save or cancel, so the height is capped to what the
        screen can actually show and the body scrolls instead.
        """
        super().showEvent(event)
        screen = self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.setMaximumHeight(available.height() - 40)

    def add_row(self, caption: str, widget: QWidget) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(12)
        lab = label(caption, "")
        lab.setFixedWidth(140)
        # Top aligned: a row holding a list is far taller than its caption, and
        # a vertically centred label floats in the middle of it.
        lab.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        row.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(widget, 1)
        holder = QWidget()
        holder.setLayout(row)
        self.form.addWidget(holder)
        return widget


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    accept_text: str = "Confirm",
    danger: bool = False,
) -> bool:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)
    dlg.setMinimumWidth(460)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 22, 24, 18)
    layout.setSpacing(14)
    layout.addWidget(label(title, "h2"))
    body = label(message, "dim")
    body.setWordWrap(True)
    body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(body)

    row = QHBoxLayout()
    row.addStretch(1)
    cancel = button("Cancel", variant="ghost")
    ok = button(accept_text, variant="danger" if danger else "primary")
    cancel.clicked.connect(dlg.reject)
    ok.clicked.connect(dlg.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    layout.addLayout(row)
    ok.setDefault(True)
    return bool(dlg.exec())


class PromptDialog(BaseDialog):
    """Single field input."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        subtitle: str = "",
        *,
        value: str = "",
        placeholder: str = "",
        multiline: bool = False,
        accept_text: str = "Save",
    ) -> None:
        super().__init__(parent, title, subtitle)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(accept_text)
        if multiline:
            field = QPlainTextEdit(value)
            field.setPlaceholderText(placeholder)
            field.setMinimumHeight(140)
        else:
            field = QLineEdit(value)
            field.setPlaceholderText(placeholder)
        self.field = field
        self.add_row("Value", field)

    def value(self) -> str:
        if isinstance(self.field, QPlainTextEdit):
            return self.field.toPlainText()
        return self.field.text()


class RepoPickerDialog(BaseDialog):
    """Filterable repository picker."""

    def __init__(
        self,
        parent: QWidget | None,
        repos: Iterable[Any],
        *,
        title: str = "Select a repository",
        subtitle: str = "",
        multi: bool = False,
        allow_manual: bool = True,
    ) -> None:
        super().__init__(parent, title, subtitle, width=620)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Select")
        self.multi = multi
        self._repos = list(repos)

        search = QLineEdit()
        search.setPlaceholderText("Filter repositories...")
        search.setProperty("role", "search")
        search.setClearButtonEnabled(True)
        search.textChanged.connect(self._filter)
        self.search = search
        self.add_row("Search", search)

        self.list = QListWidget()
        self.list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection if multi else QListWidget.SelectionMode.SingleSelection
        )
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.form.addWidget(self.list, 1)

        self.manual = QLineEdit()
        self.manual.setPlaceholderText("owner/repository (manual entry)")
        if allow_manual:
            self.add_row("Or type", self.manual)
        self._populate("")
        self.list.setMinimumHeight(320)

    def _populate(self, needle: str) -> None:
        self.list.clear()
        needle = needle.lower().strip()
        for repo in self._repos:
            haystack = f"{repo.full_name} {repo.description}".lower()
            if needle and needle not in haystack:
                continue
            item = QListWidgetItem(f"{repo.full_name}\n{repo.description or 'no description'}")
            item.setData(Qt.ItemDataRole.UserRole, repo.full_name)
            item.setIcon(icon_svg("folder", "#7c6cff", 18))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _filter(self, text: str) -> None:
        self._populate(text)

    def selection(self) -> list[str]:
        manual = self.manual.text().strip() if hasattr(self, "manual") else ""
        picked = [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems()]
        if not picked and manual:
            picked = [manual]
        return picked


class FileQueue(QWidget):
    """A batch of files to add to a repository, chosen from disk.

    Shared by the three places a file can be added - creating a repository,
    editing one, and the standalone upload dialog - so the rules about how a
    destination path is worked out live in exactly one place.

    Rows are editable because the destination is what actually matters on
    GitHub: the same file may be wanted under a different name, or a different
    folder, and there is no reason to make that a separate dialog.

    ``changed`` fires once the batch has settled. Listeners that care about the
    batch as a whole should use it rather than the list widget's own
    ``itemChanged``, which fires per row while the list is still being rebuilt.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.items: list[tuple[str, str]] = []  # (source path, target path)
        #: Indices whose destination the user typed by hand, so a later refold
        #: does not silently undo the correction.
        self._edited: set[int] = set()
        self._suspend_edit = False

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.list = QListWidget()
        self.list.setMinimumHeight(130)
        column.addWidget(self.list)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Folder inside the repository, e.g. docs")
        row.addWidget(self.folder, 1)
        row.addWidget(
            button("Choose files…", variant="outline", icon="upload", on_click=self.choose_files)
        )
        row.addWidget(
            button("Remove", variant="ghost", icon="trash", on_click=self.remove_selected)
        )
        column.addLayout(row)

        self.summary = label("No files selected.", "faint", wrap=True)
        column.addWidget(self.summary)

        self.list.itemSelectionChanged.connect(self._update_summary)
        self.list.itemChanged.connect(self._on_item_edited)
        self.folder.textChanged.connect(self.refold)

    # ------------------------------------------------------------------ input
    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files to upload", "")
        if not paths:
            return
        self.add_paths(paths)

    def add_paths(self, paths: Iterable[str]) -> None:
        """Append files from disk, keeping any folder already typed."""
        for path in paths:
            self.items.append((path, self.target_for(path)))
        self._edited.clear()
        self.refresh()

    def remove_selected(self) -> None:
        rows = sorted((self.list.row(item) for item in self.list.selectedItems()), reverse=True)
        for row in rows:
            index = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            if isinstance(index, int) and 0 <= index < len(self.items):
                del self.items[index]
                self._edited = {i - 1 if i > index else i for i in self._edited}
        self.refresh()

    def clear(self) -> None:
        self.items.clear()
        self._edited.clear()
        self.refresh()

    def set_folder(self, value: str) -> None:
        self.folder.setText(value)

    # ------------------------------------------------------------------ paths
    def folder_value(self) -> str:
        return self.folder.text().strip().strip("/").replace("\\", "/")

    def target_for(self, source: str) -> str:
        """Destination for a file: the folder field plus the file's own name."""
        folder = self.folder_value()
        name = Path(source).name
        return f"{folder}/{name}" if folder else name

    def refold(self) -> None:
        """Re-apply the folder field to every row the user has not edited.

        Typing a folder should move the whole batch, but it must not silently
        undo a path someone corrected by hand, so edited rows are left alone.
        """
        folder = self.folder_value()
        folded = []
        for index, (source, current) in enumerate(self.items):
            if index in self._edited:
                folded.append((source, current))
            else:
                name = Path(source).name
                folded.append((source, f"{folder}/{name}" if folder else name))
        self.items = folded
        self.refresh()

    def displayed(self, row: int) -> str:
        """The path shown in a row, without the size suffix."""
        return self.list.item(row).text().split("  ·  ")[0].strip()

    # ------------------------------------------------------------------ result
    def selections(self) -> list[tuple[str, str]]:
        """``(source path, target path)`` for every chosen file."""
        out: list[tuple[str, str]] = []
        for row in range(self.list.count()):
            index = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            source, _default = self.items[index]
            out.append((source, self.displayed(row)))
        return out

    def size_on_disk(self, source: str) -> int | None:
        try:
            return Path(source).stat().st_size
        except OSError:
            return None

    def total_size(self) -> int:
        return sum(self.size_on_disk(source) or 0 for source, _t in self.items)

    def missing(self) -> list[str]:
        return [source for source, _t in self.items if self.size_on_disk(source) is None]

    def validate(self) -> str:
        """An error message, or an empty string when the batch is usable."""
        if not self.items:
            return "Choose at least one file."
        gone = self.missing()
        if gone:
            name = Path(gone[0]).name
            plural = "s are" if len(gone) > 1 else " is"
            return f"'{name}' and {len(gone) - 1} more file{plural} no longer on disk."
        for _source, target in self.selections():
            try:
                validate_repo_path(target)
            except GitHubError as exc:
                return str(exc)
        return ""

    # ----------------------------------------------------------------- display
    def refresh(self) -> None:
        """Rebuild the list from ``items``, showing each file's real size."""
        self._suspend_edit = True
        self.list.clear()
        for index, (source, target) in enumerate(self.items):
            size = self.size_on_disk(source)
            suffix = _human(size) if size is not None else "missing"
            item = QListWidgetItem(f"{target}  ·  {suffix}")
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.list.addItem(item)
        self._suspend_edit = False
        self._update_summary()
        self.changed.emit()

    def _on_item_edited(self, item: QListWidgetItem) -> None:
        """Fold a hand-typed path back into the model.

        Without this the next refold would rebuild the row from the stale
        default and quietly throw the correction away.
        """
        if self._suspend_edit:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int) and 0 <= index < len(self.items):
            source = self.items[index][0]
            self.items[index] = (source, self.displayed(self.list.row(item)))
            self._edited.add(index)
        self._update_summary()
        self.changed.emit()

    def _update_summary(self) -> None:
        if not self.items:
            self.summary.setText("No files selected.")
            return
        gone = len(self.missing())
        total = _human(self.total_size())
        if gone:
            plural = "file is" if gone == 1 else "files are"
            self.summary.setText(
                f"{len(self.items)} file(s), {total} · {gone} {plural} no longer on disk."
            )
            return
        self.summary.setText(f"{len(self.items)} file(s), {total} total.")


class CreateRepoDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, default_owner: str = "") -> None:
        super().__init__(
            parent,
            "Create repository",
            "Creates a repository through the GitHub API on the signed-in account.",
            width=600,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Create repository")

        self.name = QLineEdit()
        self.name.setPlaceholderText("my-project")
        self.name.textChanged.connect(self._sync_slug)
        self.add_row("Name", self.name)

        self.desc = QLineEdit()
        self.desc.setPlaceholderText("What does this project do?")
        self.add_row("Description", self.desc)

        self.homepage = QLineEdit()
        self.homepage.setPlaceholderText("https://example.com")
        self.add_row("Homepage", self.homepage)

        self.topics = QLineEdit()
        self.topics.setPlaceholderText("python, cli, automation")
        self.add_row("Topics", self.topics)

        self.owner_hint = label(default_owner, "faint")
        self.add_row("Owner", self.owner_hint)

        self.private = QCheckBox("Private repository")
        self.add_row("Visibility", self.private)

        self.auto_init = QCheckBox("Initialise with a README, .gitignore and a licence")
        self.auto_init.setChecked(True)
        self.add_row("Initialise", self.auto_init)

        self.license = QComboBox()
        self.license.addItems(
            ["No licence file", "mit", "apache-2.0", "gpl-3.0", "bsd-3-clause", "mpl-2.0", "unlicense"]
        )
        self.add_row("Licence", self.license)

        # Files chosen here are committed once the repository exists. The API
        # cannot take content in the create call, so this is a second step
        # rather than part of the payload - which is why the queue only matters
        # after a successful create.
        self.queue = FileQueue()
        self.add_row("Add files", self.queue)

        self.slug_preview = label("", "faint")
        self.add_row("Will create", self.slug_preview)
        self._sync_slug(self.name.text())

    def _sync_slug(self, name: str) -> None:
        owner = self.owner_hint.text() or "your-account"
        slug = name.strip().lower().replace(" ", "-")
        self.slug_preview.setText(f"{owner}/{slug}" if slug else "...")

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name.text().strip(),
            "description": self.desc.text().strip(),
            "homepage": self.homepage.text().strip(),
            "topics": [t.strip() for t in self.topics.text().split(",") if t.strip()],
            "private": self.private.isChecked(),
            "auto_init": self.auto_init.isChecked(),
            "license_template": "" if self.license.currentIndex() == 0 else self.license.currentText(),
        }

    def files(self) -> list[tuple[str, str]]:
        """``(source, target)`` for the files to commit after creation."""
        return self.queue.selections()

    def validate_files(self) -> str:
        if self.queue.items:
            return self.queue.validate()
        return ""


class UploadFileDialog(BaseDialog):
    """Add files to a repository that already exists."""

    def __init__(
        self,
        parent: QWidget | None,
        repo_name: str,
        *,
        branch: str = "",
        default_branch: str = "",
    ) -> None:
        super().__init__(
            parent,
            "Upload files",
            f"Files are committed to {repo_name} on "
            f"{branch or default_branch or 'the default branch'}.",
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Upload")

        self.repo_name = repo_name
        #: The message this dialog proposed last, so a proposal can be
        #: replaced or withdrawn but a typed one is never clobbered.
        self._proposed = ""

        self.queue = FileQueue()
        self.add_row("Files", self.queue)

        self.message = QLineEdit()
        self.message.setPlaceholderText("Commit message")
        self.add_row("Message", self.message)

        self.branch = QLineEdit(branch or default_branch)
        self.branch.setPlaceholderText("Target branch, empty for the default")
        self.add_row("Branch", self.branch)

        self.overwrite = QComboBox()
        self.overwrite.addItems(["Overwrite if the file exists", "Fail if the file exists"])
        self.add_row("Existing files", self.overwrite)

        self.error_label = label("", "danger", wrap=True)
        self.error_label.setVisible(False)
        self.add_row("", self.error_label)

        # Deliberately not connected to message.textChanged: re-proposing on
        # every keystroke would refill the field the moment it was cleared, so
        # the message could never be emptied. The proposal is refreshed only when
        # the batch actually changes.
        self.queue.changed.connect(self._sync_message)
        self._sync_message()

    def accept(self) -> None:
        """Refuse to close while the batch is unusable.

        Showing the problem after closing would mean the user had to choose every
        file again to fix one bad path.
        """
        problem = self.validate()
        if problem:
            self.error_label.setText(problem)
            self.error_label.setVisible(True)
            return
        super().accept()

    def _sync_message(self) -> None:
        """Propose a commit message, but never overwrite one the user typed.

        Emitted from the queue's ``changed`` signal rather than ``itemChanged``:
        that fires once per row while the list is still being rebuilt, so the
        batch would look half-built and the proposal would be wrong.
        """
        current = self.message.text().strip()
        if current and current != self._proposed:
            return  # the user is typing; leave it alone
        items = self.items()
        if not items:
            self._proposed = ""
            self.message.setText("")
            return
        subject = Path(items[0][1]).name
        proposal = (
            f"docs: add {subject}" if len(items) == 1 else f"docs: add {len(items)} files"
        )
        self._proposed = proposal
        self.message.setText(proposal)

    def items(self) -> list[tuple[str, str]]:
        return self.queue.selections()

    def add_paths(self, paths: Iterable[str]) -> None:
        self.queue.add_paths(paths)

    def commit_message(self) -> str:
        return self.message.text().strip()

    def target_branch(self) -> str:
        return self.branch.text().strip()

    def allow_overwrite(self) -> bool:
        return self.overwrite.currentIndex() == 0

    def validate(self) -> str:
        problem = self.queue.validate()
        if problem:
            return problem
        if not self.commit_message():
            return "A commit message is required."
        return ""


class FileChangesWidget(QWidget):
    """Add files to, and remove files from, a repository that already exists.

    Both lists live together because they land as one batch of commits: a file
    added and a file removed in the same save is a coherent change, and splitting
    them across two dialogs would mean two chances to half-apply something.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        files: Iterable[dict[str, Any]] = (),
        can_delete: bool = True,
    ) -> None:
        super().__init__(parent)
        self.files = list(files)
        self._deleting: set[str] = set()
        self._suspend = False

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        # ------------------------------------------------------------- remove
        remove_box = QVBoxLayout()
        remove_box.setSpacing(6)
        self.remove_label = label("Remove from the repository", "h4")
        remove_box.addWidget(self.remove_label)

        self.existing = QListWidget()
        self.existing.setMinimumHeight(110)
        self.existing.setToolTip(
            "Tick a file to delete it from the repository when you save."
        )
        remove_box.addWidget(self.existing)

        self.remove_hint = label("", "faint", wrap=True)
        remove_box.addWidget(self.remove_hint)
        column.addLayout(remove_box)

        # ---------------------------------------------------------------- add
        add_box = QVBoxLayout()
        add_box.setSpacing(6)
        add_box.addWidget(label("Add files", "h4"))
        self.queue = FileQueue()
        add_box.addWidget(self.queue)
        column.addLayout(add_box)

        if not can_delete:
            self.remove_label.setVisible(False)
            self.existing.setVisible(False)
            self.remove_hint.setVisible(False)

        self._reload_existing()

    # --------------------------------------------------------------- deleting
    def _reload_existing(self) -> None:
        self._suspend = True
        self.existing.clear()
        for entry in self.files:
            path = str(entry.get("path") or "")
            if not path:
                continue
            size = int(entry.get("size") or 0)
            item = QListWidgetItem(f"{path}  ·  {_human(size)}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if path in self._deleting:
                item.setCheckState(Qt.CheckState.Checked)
            self.existing.addItem(item)
        self._suspend = False
        self._update_remove_hint()

    def _on_toggled(self, item: QListWidgetItem) -> None:
        if self._suspend:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(path, str):
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._deleting.add(path)
        else:
            self._deleting.discard(path)
        self._update_remove_hint()

    def _update_remove_hint(self) -> None:
        if not self.files:
            self.remove_hint.setText("No files to show.")
            return
        if self._deleting:
            count = len(self._deleting)
            plural = "file" if count == 1 else "files"
            self.remove_hint.setText(f"{count} {plural} will be deleted.")
        else:
            self.remove_hint.setText(
                f"{len(self.files)} file(s) in the repository. Tick one to delete it."
            )

    # ----------------------------------------------------------------- result
    def deletions(self) -> list[dict[str, Any]]:
        """The files marked for deletion, each with the sha a delete needs."""
        out: list[dict[str, Any]] = []
        for entry in self.files:
            path = str(entry.get("path") or "")
            if path in self._deleting:
                out.append(entry)
        return out

    def additions(self) -> list[tuple[str, str]]:
        return self.queue.selections()

    def has_changes(self) -> bool:
        return bool(self.deletions()) or bool(self.queue.items)

    def validate(self) -> str:
        """Reject a request that would delete a file it is also uploading.

        The order of operations is not defined well enough to rely on, and the
        result would depend on which request landed last.
        """
        problem = self.queue.validate() if self.queue.items else ""
        if problem:
            return problem
        uploading = {target for _s, target in self.additions()}
        clash = sorted(uploading & {str(e.get("path")) for e in self.deletions()})
        if clash:
            name = clash[0]
            if len(clash) > 1:
                return (
                    f"{len(clash)} paths, including '{name}', are marked for deletion "
                    "and for upload at the same time."
                )
            return f"'{name}': it is marked for deletion and for upload at the same time."
        return ""


class EditRepoDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        repo: Any,
        *,
        files: Iterable[dict[str, Any]] = (),
        allow_file_changes: bool = True,
    ) -> None:
        super().__init__(
            parent,
            f"Edit {repo.full_name}",
            "Name changes require a rename on GitHub and are applied immediately.",
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save changes")

        self.name = QLineEdit(repo.name)
        self.add_row("Name", self.name)

        self.desc = QLineEdit(repo.description)
        self.add_row("Description", self.desc)

        self.homepage = QLineEdit(repo.homepage)
        self.add_row("Homepage", self.homepage)

        self.topics = QLineEdit(", ".join(repo.topics))
        self.topics.setPlaceholderText("comma separated topics")
        self.add_row("Topics", self.topics)

        self.branch = QLineEdit(repo.default_branch)
        self.add_row("Default branch", self.branch)

        self.private = QCheckBox("Private repository")
        self.private.setChecked(repo.private)
        self.add_row("Visibility", self.private)

        self.archived = QCheckBox("Archived (read only)")
        self.archived.setChecked(repo.archived)
        self.add_row("State", self.archived)

        # Archiving makes the repository read only, so a delete against it would
        # only come back as an error.
        self.file_changes: FileChangesWidget | None = None
        if allow_file_changes and not repo.archived:
            self.file_changes = FileChangesWidget(self, files=files)
            self.add_row("Files", self.file_changes)
            self.file_changes.existing.itemChanged.connect(self.file_changes._on_toggled)
        elif allow_file_changes:
            note = label(
                "This repository is archived, so files cannot be added or removed.",
                "dim",
                wrap=True,
            )
            self.add_row("Files", note)

        self.commit_message = QLineEdit()
        self.commit_message.setPlaceholderText(
            "Commit message for the file changes, e.g. docs: refresh notes"
        )
        self.add_row("Commit message", self.commit_message)

        # Shown in place rather than as a toast: refusing to close is the whole
        # point, and closing would throw away everything the user just typed.
        self.file_error = label("", "danger", wrap=True)
        self.file_error.setWordWrap(True)
        self.file_error.setVisible(False)
        self.add_row("", self.file_error)

    def accept(self) -> None:
        """Refuse to close while the file changes are unusable."""
        problem = self.validate_files()
        if problem:
            self.file_error.setText(problem)
            self.file_error.setVisible(True)
            return
        super().accept()

    def values(self) -> dict[str, Any]:
        return {
            "name": self.name.text().strip() or None,
            "description": self.desc.text().strip(),
            "homepage": self.homepage.text().strip(),
            "topics": [t.strip() for t in self.topics.text().split(",") if t.strip()],
            "default_branch": self.branch.text().strip() or None,
            "private": self.private.isChecked(),
            "archived": self.archived.isChecked(),
        }

    # ----------------------------------------------------------- file changes
    def additions(self) -> list[tuple[str, str]]:
        return self.file_changes.additions() if self.file_changes else []

    def deletions(self) -> list[dict[str, Any]]:
        return self.file_changes.deletions() if self.file_changes else []

    def has_file_changes(self) -> bool:
        return bool(self.file_changes and self.file_changes.has_changes())

    def file_message(self) -> str:
        return self.commit_message.text().strip()

    def validate_files(self) -> str:
        if not self.file_changes:
            return ""
        problem = self.file_changes.validate()
        if problem:
            return problem
        if self.has_file_changes() and not self.file_message():
            return "A commit message is required for the file changes."
        return ""


class TokenDialog(BaseDialog):
    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(
            parent,
            "Connect to GitHub",
            "Paste a personal access token. It is encrypted with Windows DPAPI and "
            "stored next to this executable only.",
            width=620,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Connect")

        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("ghp_... or github_pat_...")
        self.add_row("Token", self.token)

        tips = QLabel(
            "Recommended scopes: <b>repo</b>, <b>read:org</b>, <b>workflow</b>, "
            "<b>user</b>, <b>delete_repo</b> (only if you want repository deletion).<br>"
            "Create a token at github.com/settings/tokens (fine grained tokens work too)."
        )
        tips.setWordWrap(True)
        tips.setTextFormat(Qt.TextFormat.RichText)
        self.form.addWidget(tips)

        self.org = QLineEdit()
        self.org.setPlaceholderText("optional: create under this organization")
        self.add_row("Organisation", self.org)

    def values(self) -> dict[str, str]:
        return {"token": self.token.text().strip(), "org": self.org.text().strip()}


class TextInputDialog(BaseDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        subtitle: str = "",
        *,
        fields: list[tuple[str, str, str]] | None = None,
        accept_text: str = "Create",
    ) -> None:
        """``fields`` is a list of ``(caption, value, placeholder)``."""
        super().__init__(parent, title, subtitle)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(accept_text)
        self.fields: dict[str, QWidget] = {}
        for caption, value, placeholder in fields or []:
            if caption.lower() in {"body", "message", "notes", "description"}:
                widget: QWidget = QPlainTextEdit(value)
                widget.setPlaceholderText(placeholder)
                widget.setMinimumHeight(120)
            else:
                widget = QLineEdit(value)
                widget.setPlaceholderText(placeholder)
            self.fields[caption] = widget
            self.add_row(caption, widget)

    def values(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for caption, widget in self.fields.items():
            if isinstance(widget, QPlainTextEdit):
                out[caption] = widget.toPlainText()
            else:
                out[caption] = widget.text()
        return out


class DiffDialog(QDialog):
    """Read-only diff-ish preview with copy/save actions."""

    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        content: str,
        *,
        subtitle: str = "",
        on_copy: Callable[[], None] | None = None,
        accept_text: str = "Apply",
        extra: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(880, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(label(title, "h2"))
        if subtitle:
            sub = label(subtitle, "dim")
            sub.setWordWrap(True)
            layout.addWidget(sub)

        view = QTextBrowser()
        view.setObjectName("MarkdownView")
        view.setPlainText(content)
        layout.addWidget(view, 1)

        row = QHBoxLayout()
        if on_copy:
            row.addWidget(button("Copy", variant="outline", icon="copy", on_click=on_copy))
        for caption, handler in extra or []:
            row.addWidget(button(caption, variant="outline", on_click=handler))
        row.addStretch(1)
        cancel = button("Cancel", variant="ghost")
        cancel.clicked.connect(self.reject)
        apply = button(accept_text, variant="primary")
        apply.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(apply)
        layout.addLayout(row)
        self._text = content

    def text(self) -> str:
        return self._text


class LoadingDialog(QDialog):
    def __init__(self, parent: QWidget | None, text: str = "Loading...") -> None:
        super().__init__(parent)
        self.setWindowTitle("Please wait")
        self.setModal(True)
        self.setFixedSize(360, 130)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        self.label = label(text, "")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        from .widgets import Spinner

        self.spinner = Spinner(26)
        self.spinner.start()
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignLeft)
