"""Reusable modal dialogs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .widgets import button, hline, icon_svg, label


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

        self.form = QVBoxLayout()
        self.form.setSpacing(12)
        layout.addLayout(self.form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def add_row(self, caption: str, widget: QWidget) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(12)
        lab = label(caption, "")
        lab.setFixedWidth(140)
        row.addWidget(lab)
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


class EditRepoDialog(BaseDialog):
    def __init__(self, parent: QWidget | None, repo: Any) -> None:
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
