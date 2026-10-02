"""GitHub-only AI assistant with scope enforcement and live repo context."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from ...core.ai_guard import (
    classify,
    refusal_message,
    validate_answer,
)
from .. import workers
from ..editor import AutoHeightTextBrowser
from ..markdown import render_markdown
from ..theme import markdown_css
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


class Bubble(QFrame):
    """One chat message."""

    def __init__(self, role: str, text: str, *, streaming: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.role = role
        self._placeholder = not text.strip()
        self.setObjectName("CardFlat" if role == "user" else "GlassCard")
        # No maximum width: the bubble fills the chat column so long code blocks
        # and tables have room to breathe.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(7)
        icon = QLabel()
        if role == "user":
            icon.setPixmap(icon_svg("user", "#9aa5bb", 15).pixmap(15, 15))
            head.addWidget(icon)
            head.addWidget(label("You", ""))
        else:
            icon.setPixmap(icon_svg("sparkles", "#7c6cff", 15).pixmap(15, 15))
            head.addWidget(icon)
            head.addWidget(label("GitHub Assistant", ""))
            head.addWidget(Badge("github only", "Accent"))
        head.addStretch(1)
        if streaming:
            self.cursor_label = label("…", "faint")
            head.addWidget(self.cursor_label)
        layout.addLayout(head)

        self.view = AutoHeightTextBrowser()
        self.view.setObjectName("BubbleView")
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self.view)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        layout.addLayout(self.actions)
        self.set_markdown(text)

    def set_markdown(self, text: str) -> None:
        self._placeholder = False
        self.view.setHtml(f"<style>{markdown_css()}</style>" + render_markdown(text))
        self.updateGeometry()

    def append_markdown(self, chunk: str) -> None:
        """Stream a chunk in, clearing the empty placeholder on the first one."""
        if self._placeholder:
            self._placeholder = False
            self.set_markdown("")
        self.view.append_markdown(chunk)
        self.updateGeometry()

    def add_actions(self, entries: list[tuple[str, Any]]) -> None:
        for caption, handler in entries:
            self.actions.addWidget(button(caption, variant="ghost", on_click=handler))


class AssistantPage(Page):
    title = "AI Assistant"
    subtitle = "Ask anything about GitHub. Nothing else."
    icon = "sparkles"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.history: list[tuple[str, str]] = []
        self.bubble: Bubble | None = None
        self._buffer = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        header = PageHeader("AI Assistant", "Scoped to GitHub by design — it refuses anything else")
        header.add_action(icon_button("trash", tooltip="Clear conversation", on_click=self.clear))
        layout.addWidget(header)

        # --------------------------------------------------------- scope banner
        banner = Card(flat=True)
        row = QHBoxLayout()
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(icon_svg("shield-check", "#31c48d", 18).pixmap(18, 18))
        row.addWidget(icon)
        text = label(
            "Scope lock: requests and answers outside GitHub are blocked before they reach "
            "the model.",
            "dim",
        )
        text.setWordWrap(True)
        row.addWidget(text, 1)
        self.context_toggle = QComboBox()
        self.context_toggle.addItem("Attach repo context: On", True)
        self.context_toggle.addItem("Attach repo context: Off", False)
        self.context_toggle.setFixedWidth(200)
        row.addWidget(self.context_toggle)
        banner.add_layout(row)
        layout.addWidget(banner)

        # ------------------------------------------------------------- chat log
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.host = QWidget()
        self.column = QVBoxLayout(self.host)
        self.column.setContentsMargins(0, 0, 8, 0)
        self.column.setSpacing(12)
        self.scroll.setWidget(self.host)
        layout.addWidget(self.scroll, 1)

        self._render_welcome()

        # ------------------------------------------------------------- composer
        composer = Card(flat=True)
        comp = QVBoxLayout()
        comp.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "Ask about a README, a pull request, workflows, tokens, releases…  (Enter to send)"
        )
        self.input.returnPressed.connect(self.send)
        comp.addWidget(self.input)

        suggestions = QHBoxLayout()
        suggestions.setSpacing(8)
        suggestions.addWidget(label("Try:", "faint"), 0, Qt.AlignmentFlag.AlignTop)
        # A fixed maximum height keeps the chip area from growing downwards and
        # pushing the composer off-screen on short windows.
        self.suggestions = FlowWidget(spacing=6)
        self.suggestions.setMaximumHeight(74)
        for prompt in ai_tasks.SUGGESTION_PROMPTS[:6]:
            self.suggestions.add(
                _suggestion(prompt, lambda text=prompt: self._send_text(text))
            )
        suggestions.addWidget(self.suggestions, 1)
        comp.addLayout(suggestions)

        bottom = QHBoxLayout()
        self.repo_combo = QComboBox()
        self.repo_combo.setMinimumWidth(200)
        self.repo_combo.addItem("No repository context")
        bottom.addWidget(self.repo_combo)
        bottom.addWidget(spacer())
        self.send_btn = button("Send", variant="primary", icon="send", on_click=self.send)
        bottom.addWidget(self.send_btn)
        self.stop_btn = button("Stop", variant="ghost", icon="x", on_click=self.stop)
        self.stop_btn.setVisible(False)
        bottom.addWidget(self.stop_btn)
        comp.addLayout(bottom)
        composer.add_layout(comp)
        layout.addWidget(composer)

        self._task = None

    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        self.repo_combo.addItem("No repository context", "")
        for repo in self.ctx.repos:
            self.repo_combo.addItem(repo.full_name, repo.full_name)
        self.repo_combo.blockSignals(False)
        current = self.ctx.config.get("last_repo", "")
        index = self.repo_combo.findData(current)
        if index >= 0:
            self.repo_combo.setCurrentIndex(index)

    # ---------------------------------------------------------------- render
    def _render_welcome(self) -> None:
        self._clear_bubbles()
        self._add(
            "assistant",
            "Hi — I am the GitHub assistant built into **GitHub Manager**.\n\n"
            "I can help with:\n"
            "- writing and improving **READMEs**, profile READMEs and docs\n"
            "- **repository** settings, topics, visibility, releases and tags\n"
            "- **issues** and **pull requests**: drafting, triage, review replies\n"
            "- **commits**, branch names, rebase/merge questions\n"
            "- **GitHub Actions** workflows, `.gitignore`, `LICENSE`, `CONTRIBUTING.md`\n"
            "- **tokens**, permissions, SSH keys and repository security\n\n"
            "Anything outside GitHub is out of scope — I will say so instead of guessing.",
        )
        self.column.addStretch(1)
        self._scroll_bottom()

    def _clear_bubbles(self) -> None:
        while self.column.count():
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _add(self, role: str, text: str, *, streaming: bool = False) -> Bubble:
        """Append a bubble, letting it stretch to the chat width but stay left aligned."""
        bubble = Bubble(role, text, streaming=streaming)
        row = QWidget()
        row.setObjectName("BubbleRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        # Stretch 1 with no alignment flag: the bubble fills the chat width and
        # stays flush left.
        row_layout.addWidget(bubble, 1)
        self.column.insertWidget(self.column.count() - 1, row)
        self._scroll_bottom()
        return bubble

    def _scroll_bottom(self) -> None:
        """Pin the view to the newest message once the layout has settled."""
        bar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def _bubbles(self) -> list["Bubble"]:
        return self.host.findChildren(Bubble)

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        # Re-measure the bubbles so streamed content wraps to the new width.
        for bubble in self._bubbles():
            bubble.view.updateGeometry()

    def last_assistant_text(self) -> str:
        """Plain text of the most recent assistant bubble (used by tests/UI)."""
        for bubble in reversed(self._bubbles()):
            if bubble.role == "assistant":
                return bubble.view.toPlainText()
        return ""

    # ----------------------------------------------------------------- send
    def send(self) -> None:
        self._send_text(self.input.text())

    def _send_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.input.clear()
        self._send(text)

    def _send(self, message: str) -> None:
        if not self.ctx.ai_ready():
            self.notify(self.ctx.ai_missing_reason(), "warning")
            return

        verdict = classify(message)
        self._add("user", message)
        if not verdict.allowed:
            bubble = self._add("assistant", refusal_message())
            bubble.add_actions(
                [
                    ("Write a README instead", lambda: self._send_text("Write a README for my repository")),
                    ("Review my profile", lambda: self._send_text("Review my GitHub profile and suggest improvements")),
                ]
            )
            return

        use_context = self._context_enabled()
        repo_name = self.repo_combo.currentData() or ""
        self._buffer = ""
        # The first streamed chunk clears the empty placeholder in place.
        self.bubble = self._add("assistant", "", streaming=True)
        self._set_busy(True)

        if use_context and repo_name:

            def build() -> tuple[str, Any]:
                ctx = ai_tasks.build_repo_context(self.ctx.github, repo_name)
                return repo_name, ctx.as_prompt()

            workers.run(
                "assistant-context",
                build,
                on_result=lambda pair: self._run_chat(message, pair[1]),
                on_error=lambda _m: self._run_chat(message, ""),
            )
        else:
            self._run_chat(message, "")

    def _context_enabled(self) -> bool:
        """Whether live repository context should be attached to the prompt."""
        data = self.context_toggle.currentData()
        return True if data is None else bool(data)

    def _run_chat(self, message: str, context: str) -> None:
        stream = bool(self.ctx.config.get("ai_stream", True))

        def task() -> Any:
            return ai_tasks.assistant_reply(
                self.ctx.ai(),
                self.history,
                message,
                context=context,
                stream=stream,
            )

        self._task = workers.run(
            "assistant-chat",
            task,
            on_progress=self._on_chunk,
            on_result=self._on_done,
            on_error=self._on_error,
            on_finish=lambda: self._set_busy(False),
        )

    def _on_chunk(self, chunk: str) -> None:
        if self.bubble is None:
            return
        self._buffer += chunk
        self.bubble.append_markdown(chunk)
        self._scroll_bottom()

    def _on_done(self, text: str) -> None:
        self.history.append(("user", self._last_user_message()))
        self.history.append(("assistant", text))
        ok, reason = validate_answer(text)
        final = text if ok else refusal_message()
        if self.bubble:
            self.bubble.set_markdown(final)
            if not ok:
                self.notify(reason, "warning")
            else:
                self.bubble.add_actions(
                    [
                        ("Copy", lambda: self._copy(final)),
                        (
                            "Use in README Studio",
                            lambda: self._open_readme(final),
                        ),
                    ]
                )
        self._scroll_bottom()

    def _last_user_message(self) -> str:
        for role, content in reversed(self.history):
            if role == "user":
                return content
        return ""

    def _on_error(self, message: str) -> None:
        if self.bubble:
            self.bubble.set_markdown(f"**Something went wrong:** {message}")
        self.notify(message, "error")

    def _set_busy(self, active: bool) -> None:
        self.send_btn.setEnabled(not active)
        self.input.setEnabled(not active)
        self.stop_btn.setVisible(active)

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._set_busy(False)
        self.notify("Stopped.", "info")

    def clear(self) -> None:
        self.history.clear()
        self._render_welcome()

    def _copy(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        self.notify("Copied to clipboard.", "success")

    def _open_readme(self, text: str) -> None:
        window = self.window()
        if hasattr(window, "focus_readme"):
            window.focus_readme(self.repo_combo.currentData() or "", content=text)
        self.notify("Loaded into README Studio.", "success")


def _suggestion(text: str, handler: Any) -> QPushButton:
    from ..widgets import chip

    btn = chip(text)
    btn.clicked.connect(lambda _=False: handler())
    return btn
