"""README Studio: generate, refine and publish repository READMEs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from ...core.ai_guard import validate_answer
from .. import workers
from ..dialogs import DiffDialog, RepoPickerDialog, TextInputDialog
from ..editor import MarkdownEditor, MarkdownStreamView
from ..markdown import README_SKELETON
from ..theme import markdown_css
from ..widgets import (
    Card,
    FlowWidget,
    ScrollPage,
    button,
    chip,
    icon_button,
    label,
    unescape_mnemonic,
)
from .base import Page

TONES = ["Professional", "Friendly", "Minimal", "Detailed", "Playful", "Enterprise"]
LANGUAGES = ["English", "Persian", "Spanish", "French", "German", "Turkish", "Arabic", "Hindi", "Portuguese"]
AUDIENCES = ["Developers", "Beginners", "Teams", "Open source contributors", "Product managers", "Students"]


class ReadmePage(Page):
    title = "README Studio"
    subtitle = "AI writes the README, you stay in control of what gets committed."
    icon = "book"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.repo: str = ""
        self.branch: str = ""
        self.busy_overlay = None
        self._task = None
        self._ask_commit_path = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # This page carries more controls than a 900px tall window can show, and
        # a plain vertical layout answers a shortfall by clipping: the generation
        # settings card is handed less than its own minimum and its controls are
        # drawn outside it, so they simply vanish. A scroll area keeps every
        # control reachable, and the editor still grows to fill a tall window.
        self.scroll = ScrollPage(self)
        outer.addWidget(self.scroll)
        layout = self.scroll.column
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        # ------------------------------------------------------------- header
        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("README Studio", "h1"))
        titles.addWidget(
            label(
                "Generate a complete README from the live repository, refine it, then commit it.",
                "dim",
            )
        )
        header.addLayout(titles)
        header.addStretch(1)
        self.status = label("", "faint")
        header.addWidget(self.status)
        layout.addLayout(header)

        # ------------------------------------------------------- repository bar
        repo_card = Card(flat=True)
        row = FlowWidget(spacing=10)
        row.add(label("Repository", ""))
        self.repo_combo = QComboBox()
        self.repo_combo.setMinimumWidth(240)
        self.repo_combo.setEditable(False)
        self.repo_combo.currentTextChanged.connect(self._on_repo_changed)
        row.add(self.repo_combo)

        pick = button("Choose…", variant="outline", icon="folder", on_click=self.pick_repo)
        row.add(pick)
        row.add(label("Branch", ""))
        self.branch_combo = QComboBox()
        self.branch_combo.setMinimumWidth(130)
        row.add(self.branch_combo)
        self.load_btn = button("Load existing", variant="ghost", icon="download", on_click=self.load_existing)
        row.add(self.load_btn)
        self.reload_btn = icon_button("refresh", tooltip="Reload repository list", on_click=self.reload_repos)
        row.add(self.reload_btn)
        repo_card.add(row)
        layout.addWidget(repo_card)

        # ------------------------------------------------------------- options
        options = Card("Generation settings", "Everything here is fed to the AI prompt")
        # Six labelled controls in one row overflow on a narrow window and, in a
        # plain QHBoxLayout, overlap instead of wrapping. A flow row keeps the
        # labels attached to their controls and lets the group reflow.
        opts_row = FlowWidget(spacing=12)

        self.tone = QComboBox()
        self.tone.addItems(TONES)
        opts_row.add(_field("Tone", self.tone))

        self.language = QComboBox()
        self.language.addItems(LANGUAGES)
        opts_row.add(_field("Language", self.language))

        self.audience = QComboBox()
        self.audience.addItems(AUDIENCES)
        opts_row.add(_field("Audience", self.audience))

        self.badges = QCheckBox("Badges")
        self.badges.setChecked(True)
        opts_row.add(_field("Extras", self.badges))

        self.improve_existing = QCheckBox("Improve current text")
        self.improve_existing.setChecked(True)
        opts_row.add(_field("Mode", self.improve_existing))

        self.temperature = QComboBox()
        self.temperature.addItems(["Focused (0.3)", "Balanced (0.6)", "Creative (0.9)"])
        self.temperature.setCurrentIndex(1)
        opts_row.add(_field("Creativity", self.temperature))
        options.add(opts_row)

        self.sections_flow = FlowWidget(spacing=7)
        for name in self.ctx.config.get("readme_sections", []):
            self.sections_flow.add(chip(name, checked=True))
        all_row = QHBoxLayout()
        all_row.setSpacing(10)
        sections_caption = label("Sections", "")
        all_row.addWidget(sections_caption, 0, Qt.AlignmentFlag.AlignTop)
        all_row.addWidget(self.sections_flow, 1)
        options.add_layout(all_row)

        self.notes = QLineEdit()
        # A text input must never be squeezed into an unusable strip. The flow
        # rows above grow when the window narrows; without a floor the vertical
        # layout takes the shortfall out of this field instead.
        self.notes.setMinimumHeight(36)
        self.notes.setPlaceholderText(
            "Extra instructions, e.g. 'include a Docker section and a CLI usage example'"
        )
        options.add(self.notes)
        layout.addWidget(options)

        # -------------------------------------------------------------- editor
        self.editor = MarkdownEditor()
        # A usable editor even when the window is short; it grows on taller ones.
        self.editor.setMinimumHeight(240)
        layout.addWidget(self.editor, 1)
        self.editor.statsChanged.connect(lambda s: self.status.setText(s))

        # ------------------------------------------------------------- actions
        # Ten fixed-width controls will not fit on one line at any realistic
        # window size, and a plain QHBoxLayout does not wrap: the children keep
        # their size hints and end up drawn on top of each other. Two flow rows
        # keep the primary actions on the left and the secondary ones on the
        # right, and each wraps onto the next line when the window is narrow.
        actions = QHBoxLayout()
        actions.setSpacing(8)
        primary_row = FlowWidget(spacing=8)
        self.generate_btn = button(
            "Generate README", variant="primary", icon="wand", on_click=self.generate
        )
        primary_row.add(self.generate_btn)
        self.refine_btn = button("Refine", variant="outline", icon="sparkles", on_click=self.refine)
        primary_row.add(self.refine_btn)
        self.review_btn = button("Review", variant="outline", icon="shield-check", on_click=self.review)
        primary_row.add(self.review_btn)

        self.file_combo = QComboBox()
        self.file_combo.addItem("README.md", "")
        for kind in ai_tasks.GITHUB_FILE_KINDS:
            self.file_combo.addItem(kind, kind)
        self.file_combo.setMinimumWidth(200)
        primary_row.add(self.file_combo)
        self.scaffold_btn = button(
            "Draft extra file", variant="outline", icon="code", on_click=self.draft_extra
        )
        primary_row.add(self.scaffold_btn)
        actions.addWidget(primary_row, 1)

        secondary_row = FlowWidget(spacing=8)
        template_btn = button("Template", variant="ghost", icon="list", on_click=self.insert_template)
        secondary_row.add(template_btn)
        copy_btn = button("Copy", variant="ghost", icon="copy", on_click=self.copy)
        secondary_row.add(copy_btn)
        save_local = button("Save .md", variant="ghost", icon="save", on_click=self.save_local)
        secondary_row.add(save_local)
        self.preview_btn = button("Preview", variant="ghost", icon="eye", on_click=self.toggle_preview)
        secondary_row.add(self.preview_btn)
        self.commit_btn = button(
            "Commit to GitHub", variant="primary", icon="upload", on_click=self.commit
        )
        secondary_row.add(self.commit_btn)
        actions.addWidget(secondary_row)
        layout.addLayout(actions)

        self.review_view = MarkdownStreamView(css=markdown_css())
        self.review_view.setVisible(False)
        self.review_view.setMaximumHeight(220)
        layout.addWidget(self.review_view)

    # ------------------------------------------------------------- lifecycle
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first.", "warning")
            return
        if not self.ctx.repos_loaded:
            self.reload_repos()
        else:
            self._fill_repos()
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.editor.set_theme(
            self.ctx.config.get("theme", "dark"),
            self.ctx.config.get("accent", "violet"),
        )

    def on_theme_changed(self) -> None:
        self._apply_theme()

    # ------------------------------------------------------------------ repo
    def _fill_repos(self) -> None:
        current = self.repo or self.ctx.config.get("last_repo", "")
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        for repo in self.ctx.repos:
            icon = "lock" if repo.private else "folder"
            self.repo_combo.addItem(icon_svg_item(icon), repo.full_name)
        self.repo_combo.blockSignals(False)
        if current:
            index = self.repo_combo.findText(current)
            if index >= 0:
                self.repo_combo.setCurrentIndex(index)
        if self.repo_combo.currentText():
            self._on_repo_changed(self.repo_combo.currentText())

    def _on_repo_changed(self, full_name: str) -> None:
        self.repo = full_name
        if full_name:
            self.ctx.config.save(last_repo=full_name)
            self._load_branches()
        else:
            self.branch_combo.clear()

    def _load_branches(self) -> None:
        if not self.repo:
            return
        workers.run(
            "readme-branches",
            lambda: self.ctx.github.list_branches(self.repo),
            on_result=self._on_branches,
            on_error=lambda _m: None,
        )

    def _on_branches(self, branches: list[str]) -> None:
        current = self.branch
        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        self.branch_combo.addItems(branches)
        self.branch_combo.blockSignals(False)
        if current in branches:
            self.branch_combo.setCurrentText(current)
        else:
            repo = self.ctx.find_repo(self.repo)
            default = repo.default_branch if repo else "main"
            if default in branches:
                self.branch_combo.setCurrentText(default)
        self.branch = self.branch_combo.currentText()

    def reload_repos(self) -> None:
        if not self.ctx.signed_in:
            return
        self.notify("Loading repositories…")
        workers.run(
            "readme-repos",
            lambda: self.ctx.github.list_repos(sort="updated"),
            on_result=self._on_repos,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_repos(self, repos: list[Any]) -> None:
        self.ctx.repos = repos
        self.ctx.repos_loaded = True
        self._fill_repos()

    def pick_repo(self) -> None:
        if not self.ctx.repos:
            self.reload_repos()
            return
        dlg = RepoPickerDialog(self, self.ctx.repos, subtitle="Pick the repository to document.")
        if dlg.exec():
            picked = dlg.selection()
            if picked:
                self.repo_combo.setCurrentText(picked[0])

    # --------------------------------------------------------------- helpers
        # --------------------------------------------------------------- helpers
    def _selected_sections(self) -> list[str]:
        sections: list[str] = []
        for index in range(self.sections_flow.flow.count()):
            item = self.sections_flow.flow.itemAt(index)
            widget = item.widget() if item else None
            if widget is not None and hasattr(widget, "isChecked") and widget.isChecked():
                sections.append(unescape_mnemonic(widget.text()))
        return sections

    def _current_temperature(self) -> float:
        return {"Focused (0.3)": 0.3, "Balanced (0.6)": 0.6, "Creative (0.9)": 0.9}[
            self.temperature.currentText()
        ]

    def _ai(self) -> Any:
        client = self.ctx.ai()
        client.temperature = self._current_temperature()
        return client

    def _stream_into_editor(self, iterator: Any) -> str:
        chunks: list[str] = []
        self.editor.set_text("")
        for piece in iterator:
            chunks.append(piece)
            self.editor.append_text(piece)
        return "".join(chunks)

    # ------------------------------------------------------------- AI actions
    def generate(self) -> None:
        if not self.require_ai():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return

        existing = self.editor.text().strip()
        use_existing = self.improve_existing.isChecked() and bool(existing)

        def build_context() -> Any:
            return ai_tasks.build_repo_context(self.ctx.github, self.repo)

        self._set_busy(True, "Reading repository…")

        def after_context(ctx: Any) -> None:
            self._set_busy(True, "Writing README…")
            kwargs = {
                "tone": self.tone.currentText(),
                "language": self.language.currentText(),
                "sections": self._selected_sections(),
                "audience": self.audience.currentText(),
                "extra_notes": self.notes.text(),
                "include_badges": self.badges.isChecked(),
                "keep_existing": existing if use_existing else "",
                "stream": True,
            }
            self._task = workers.run(
                "readme-generate",
                lambda: ai_tasks.generate_readme(self._ai(), ctx, **kwargs),
                on_progress=lambda chunk: self.editor.append_text(chunk),
                on_result=self._on_generated,
                on_error=lambda message: self._on_error(message),
                on_finish=lambda: self._set_busy(False),
            )

        workers.run(
            "readme-context",
            build_context,
            on_result=after_context,
            on_error=lambda message: self._on_error(message),
        )

    def _on_generated(self, text: str) -> None:
        ok, reason = validate_answer(text)
        if not ok:
            self.notify(reason, "error")
            self.editor.set_text("")
            return
        self.editor.set_text(text.strip())
        self.notify("README generated. Review it, then commit when happy.", "success")

    def refine(self) -> None:
        if not self.require_ai():
            return
        text = self.editor.text().strip()
        if not text:
            self.notify("There is nothing to refine yet.", "warning")
            return
        instruction = self.notes.text().strip() or "Improve clarity, structure and wording while keeping every fact accurate."
        selected = self.editor.selected_text()
        self._set_busy(True, "Refining…")
        self.editor.set_text("")

        def task() -> Any:
            client = self._ai()
            if selected:
                return ai_tasks.improve_text(
                    client, selected, instruction=instruction, stream=True
                )
            return ai_tasks.improve_text(
                client,
                text,
                instruction=f"{instruction} Return the full improved README.",
                stream=True,
            )

        self._task = workers.run(
            "readme-refine",
            task,
            on_progress=lambda chunk: self.editor.append_text(chunk),
            on_result=self._on_generated,
            on_error=lambda message: self._on_error(message),
            on_finish=lambda: self._set_busy(False),
        )

    def review(self) -> None:
        if not self.require_ai():
            return
        text = self.editor.text().strip()
        if not text:
            self.notify("Generate or write a README first.", "warning")
            return
        self.review_view.setVisible(True)
        self.review_view.setHtml(
            f"<style>{markdown_css()}</style><div>Reviewing…</div>"
        )
        self._set_busy(True, "Reviewing README…")
        self._task = workers.run(
            "readme-review",
            lambda: ai_tasks.summarize_readme(self._ai(), text),
            on_progress=lambda chunk: self.review_view.append_markdown(chunk),
            on_result=lambda text_out: self.review_view.setHtml(
                f"<style>{markdown_css()}</style>" + _render(text_out)
            ),
            on_error=lambda message: self._on_error(message),
            on_finish=lambda: self._set_busy(False),
        )

    def draft_extra(self) -> None:
        if not self.require_ai():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        kind = self.file_combo.currentData()
        if not kind:
            self.notify("README.md is generated with the main button.", "info")
            return

        self._set_busy(True, f"Drafting {kind}…")

        def task() -> Any:
            ctx = ai_tasks.build_repo_context(self.ctx.github, self.repo)
            return ai_tasks.github_file(self._ai(), kind, ctx, extra=self.notes.text(), stream=True)

        self._task = workers.run(
            "readme-extra",
            task,
            on_result=lambda text: self._show_draft(kind, text),
            on_error=lambda message: self._on_error(message),
            on_finish=lambda: self._set_busy(False),
        )

    def _show_draft(self, kind: str, text: str) -> None:
        text = _strip_fence(text)
        self.pending_file = (kind, text)
        dlg = DiffDialog(
            self,
            f"Draft {kind}",
            text,
            subtitle=f"Commit this file to {self.repo}?",
            on_copy=lambda: self._copy(text),
            accept_text="Open in editor",
        )
        if dlg.exec():
            self.editor.set_text(text)
            self.file_combo.setCurrentIndex(max(1, self.file_combo.currentIndex()))
            self.notify(f"{kind} loaded into the editor. Change the target file if needed.")
            self._ask_commit_path = kind
        else:
            self._ask_commit_path = ""

    # ------------------------------------------------------------ file output
    def load_existing(self) -> None:
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        self._set_busy(True, "Downloading README…")

        def task() -> Any:
            return self.ctx.github.get_readme(self.repo)

        self._task = workers.run(
            "readme-load",
            task,
            on_result=self._on_loaded,
            on_error=lambda message: self._on_error(message),
            on_finish=lambda: self._set_busy(False),
        )

    def _on_loaded(self, text: str) -> None:
        self.editor.set_text(text)
        self.notify("Loaded README.md from GitHub.", "success")

    def insert_template(self) -> None:
        self.editor.append_text(README_SKELETON)
        self.editor.refresh()

    def copy(self) -> None:
        text = self.editor.text()
        if not text.strip():
            return
        QApplication_clipboard().setText(text)
        self.notify("Copied to clipboard.", "success")

    def save_local(self) -> None:
        text = self.editor.text()
        if not text.strip():
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Save markdown", "README.md", "Markdown (*.md);;All files (*)"
        )
        if not target:
            return
        Path(target).write_text(text, encoding="utf-8")
        self.notify(f"Saved to {target}", "success")

    def toggle_preview(self) -> None:
        visible = self.editor.preview.isVisible()
        self.editor.set_preview_visible(not visible)
        self.preview_btn.setText("Hide preview" if not visible else "Preview")

    def commit(self) -> None:
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        text = self.editor.text()
        if not text.strip():
            self.notify("Nothing to commit.", "warning")
            return

        kind = getattr(self, "_ask_commit_path", "") or "README.md"
        dlg = TextInputDialog(
            self,
            f"Commit {kind}",
            f"This will write {kind} to {self.repo} on branch "
            f"{self.branch_combo.currentText() or 'the default branch'}.",
            fields=[
                ("Message", f"docs: update {kind}", "Commit message"),
                ("Branch", self.branch_combo.currentText(), "Target branch"),
            ],
            accept_text="Commit",
        )
        if not dlg.exec():
            return
        values = dlg.values()
        message = values.get("Message", "").strip()
        branch = values.get("Branch", "").strip()
        if not message:
            self.notify("A commit message is required.", "warning")
            return

        self._set_busy(True, "Committing…")

        def task() -> Any:
            if kind == "README.md":
                return self.ctx.github.commit_readme(self.repo, text, message, branch)
            return self.ctx.github.write_file(
                self.repo, kind, text, message, branch=branch
            )

        self._task = workers.run(
            "readme-commit",
            task,
            on_result=lambda _result: self.notify(f"Committed {kind} to {self.repo}.", "success"),
            on_error=lambda message: self._on_error(message),
            on_finish=lambda: self._set_busy(False),
        )

    # ------------------------------------------------------------- utilities
    def _set_busy(self, active: bool, text: str = "") -> None:
        for widget in (self.generate_btn, self.refine_btn, self.review_btn, self.commit_btn, self.scaffold_btn):
            widget.setEnabled(not active)
        if active:
            self.status.setText(text or "Working…")
        else:
            self.status.setText("")

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.notify(message, "error")

    def _copy(self, text: str) -> None:
        QApplication_clipboard().setText(text)


def QApplication_clipboard():  # noqa: N802
    from PySide6.QtWidgets import QApplication

    return QApplication.clipboard()


def _field(caption: str, widget: QWidget) -> QWidget:
    holder = QVBoxLayout()
    holder.setSpacing(4)
    holder.addWidget(label(caption.upper(), "faint"))
    holder.addWidget(widget)
    host = QWidget()
    host.setLayout(holder)
    return host


def _render(text: str) -> str:
    from ..markdown import render_markdown

    return render_markdown(text)


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lower().startswith("markdown") or text.lower().startswith("yml") or text.lower().startswith("yaml"):
                text = text.split("\n", 1)[-1] if "\n" in text else text
            text = text.strip()
    return text


def icon_svg_item(name: str):
    from ..widgets import icon_svg

    return icon_svg(name, "#9aa5bb", 16)
