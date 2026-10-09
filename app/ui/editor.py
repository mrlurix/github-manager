"""Markdown editor with live preview and GitHub-aware helpers."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .markdown import render_markdown, set_palette, word_count
from .sanitize import safe_url


class _Highlighter(QSyntaxHighlighter):
    """Lightweight markdown highlighter (headings, emphasis, code, links).

    The four roles are taken from the palette rather than written out, so the
    editor cannot end up one theme behind the rest of the app - which is what
    happened: the highlighter kept its own copy of eight hex values and only
    three of them were ever updated when a colour moved.

    Emphasis and strong are weight rather than colour. A syntax highlighter that
    tints its categories needs six hues to stay apart; a monochrome one can only
    lean on weight and opacity, so it does that instead of reaching for a palette
    the app does not have.
    """

    ROLES = ("heading", "emphasis", "strong", "link", "faint")

    def __init__(self, document: QTextDocument, theme: str = "dark") -> None:
        # Formats must exist before super().__init__(), which triggers the first
        # highlightBlock() pass.
        self.formats: dict[str, QTextCharFormat] = {}
        self._rebuild(theme)
        super().__init__(document)
        self.setTheme(theme)

    def _rebuild(self, theme: str = "dark") -> None:
        from .theme import build_palette

        pal = build_palette(theme)
        text = pal["text"]
        dim = pal["text_dim"]
        faint = pal["text_faint"]

        def make(colour: str, *, bold: bool = False, italic: bool = False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            if italic:
                fmt.setFontItalic(True)
            return fmt

        self.formats = {
            "heading": make(text, bold=True),
            "emphasis": make(dim, italic=True),
            "strong": make(text, bold=True),
            "link": make(text),
            "faint": make(faint),
        }

    def setTheme(self, theme: str) -> None:  # noqa: N802
        self._rebuild(theme)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        formats = self.formats
        if not formats:
            return

        stripped = text.lstrip()
        if stripped.startswith("#"):
            self.setFormat(0, len(text), formats["heading"])
            return
        if stripped.startswith(">"):
            self.setFormat(0, len(text), formats["faint"])
            return
        if stripped.startswith("```") or stripped.startswith("~~~"):
            self.setFormat(0, len(text), formats["faint"])
            return

        for pattern, key in (
            (r"`[^`]+`", "link"),
            (r"\*\*[^*]+\*\*", "strong"),
            (r"\*[^*]+\*", "emphasis"),
            (r"\[([^\]]*)\]\([^)]*\)", "link"),
            (r"^#{1,6}\s", "heading"),
            (r"^\s*[-*+]\s", "faint"),
            (r"^\s*\d+\.\s", "faint"),
        ):
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), formats[key])


def append_markdown(view: QTextBrowser, text: str) -> None:
    """Append a streamed markdown chunk to ``view``, pinned to the bottom.

    Shared by every streaming surface so they all scroll the same way.
    """
    bar = view.verticalScrollBar()
    at_bottom = bar.value() >= bar.maximum() - 40
    cursor = view.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertHtml(render_markdown(text))
    if at_bottom:
        bar.setValue(bar.maximum())


class SafeLinksMixin:
    """Routes link clicks through an allow-list before opening them.

    ``setOpenExternalLinks(True)`` will hand Qt any scheme it finds in the
    document, including ``javascript:`` and ``file:``. Managing link handling
    manually means every click is checked before it reaches the browser.

    The URL that gets opened is the one that was checked, not the one Qt
    supplied: re-parsing a differently spelled equivalent is how a check gets
    bypassed.
    """

    def _init_safe_links(self) -> None:
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_anchor)

    def _open_anchor(self, url: QUrl) -> None:
        target = safe_url(url.toString())
        if target is None:
            return
        # Check the re-parsed form too: QUrl has its own normalisation, and it
        # is the QUrl that would actually be handed to the OS.
        resolved = QUrl(target)
        if not resolved.isValid() or safe_url(resolved.toString()) is None:
            return
        QDesktopServices.openUrl(resolved)


class MarkdownStreamView(SafeLinksMixin, QTextBrowser):
    """A scrolling markdown view that AI output is streamed into.

    ``QTextBrowser`` has no markdown helpers of its own; every page that streams
    an AI response needs these two methods, so they live here rather than being
    reimplemented per page.
    """

    def __init__(self, parent: QWidget | None = None, css: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("MarkdownView")
        self._css = css
        self._init_safe_links()
        if css:
            self.document().setDefaultStyleSheet(css)

    def set_css(self, css: str) -> None:
        self._css = css
        self.document().setDefaultStyleSheet(css)

    def set_markdown(self, text: str) -> None:
        self.setHtml(f"<style>{self._css}</style>{render_markdown(text)}")
        self.verticalScrollBar().setValue(0)

    def append_markdown(self, text: str) -> None:
        append_markdown(self, text)


class AutoHeightTextBrowser(SafeLinksMixin, QTextBrowser):
    """A ``QTextBrowser`` that reports a height-for-width.

    Qt's text browser has ``hasHeightForWidth() == False`` and a fixed size hint,
    so it cannot live inside a vertical layout without an inner scrollbar. This
    subclass measures the laid-out document for the current width and grows to
    fit, which is what chat bubbles and inline previews need.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._extra = 8
        self._init_safe_links()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._measure(width) + self._extra

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # A floor, not the full measured height: without it a parent may crush
        # the bubble to a couple of lines and the text stops being readable. A
        # real floor makes the containing scroll area scroll instead.
        return QSize(120, max(24, min(self._measure(480), 48)))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(480, self._measure(480) + self._extra)

    def _measure(self, width: int) -> int:
        """Lay the document out at ``width`` and return its height in pixels."""
        doc = self.document()
        available = max(40, width - 4)
        doc.setTextWidth(available)
        height = doc.size().height()
        if height <= 1:
            # size() is unreliable until the layout has run once.
            height = doc.documentLayout().documentSize().height()
        doc.setTextWidth(-1)
        return int(height) + 4

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.updateGeometry()

    def set_markdown(self, text: str, css: str = "") -> None:
        """Replace the content with rendered markdown."""
        self.setHtml(f"<style>{css}</style>{render_markdown(text)}")
        self.verticalScrollBar().setValue(0)
        self.updateGeometry()

    def append_markdown(self, text: str) -> None:
        """Append a streamed chunk, keeping the view pinned to the bottom."""
        append_markdown(self, text)
        self.updateGeometry()


class MarkdownPreview(AutoHeightTextBrowser):
    """Auto-growing markdown preview used in the README editor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MarkdownView")
        self._css = ""

    def set_css(self, css: str) -> None:
        self._css = css
        self.document().setDefaultStyleSheet(css)

    def set_markdown(self, text: str) -> None:  # type: ignore[override]
        super().set_markdown(text, self._css)


class MarkdownEditor(QWidget):
    """Editor + live preview with a status bar."""

    changed = Signal()
    statsChanged = Signal(str)

    def __init__(
        self,
        *,
        splitter: bool = True,
        preview_visible: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("CodeEditor")
        self.editor.setPlaceholderText(
            "Write or generate your README here.\n\nThe AI can create it from the "
            "repository contents, or you can paste an existing file."
        )
        self.editor.setTabStopDistance(32)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.highlighter = _Highlighter(self.editor.document(), "dark")
        from .theme import markdown_palette

        set_palette(markdown_palette("dark"))

        self.preview = MarkdownPreview()
        self.preview.setVisible(preview_visible)

        self.status = QLabel("0 words")
        self.status.setProperty("role", "faint")

        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(180)
        self._sync_timer.timeout.connect(self.refresh)

        if splitter:
            self.split = QSplitter(Qt.Orientation.Horizontal)
            self.split.addWidget(self.editor)
            self.split.addWidget(self.preview)
            self.split.setSizes([520, 480])
            self.split.setChildrenCollapsible(False)
            self.split.setHandleWidth(2)
            layout.addWidget(self.split)
        else:
            layout.addWidget(self.editor, 1)
            layout.addWidget(self.preview, 1)

        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._update_status)

    # ------------------------------------------------------------------ api
    def text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)
        self.refresh()

    def set_preview_visible(self, visible: bool) -> None:
        self.preview.setVisible(visible)
        if hasattr(self, "split"):
            self.split.setSizes([520, 480] if visible else [1000, 0])

    def append_text(self, chunk: str) -> None:
        """Stream content into the editor, keeping the cursor at the end."""
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        self.editor.setTextCursor(cursor)
        self.refresh()

    def selected_text(self) -> str:
        cursor = self.editor.textCursor()
        return cursor.selectedText() if cursor.hasSelection() else ""

    def replace_selection(self, text: str) -> None:
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(text)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(text)
        self.refresh()

    def set_theme(self, theme: str, accent: str = "violet") -> None:
        from .theme import markdown_css, markdown_palette

        self.highlighter.setTheme(theme)
        css = markdown_css(theme, accent)
        set_palette(markdown_palette(theme, accent))
        self.preview.set_css(css)
        self.refresh()

    def refresh(self) -> None:
        text = self.editor.toPlainText()
        self.preview.set_markdown(text)
        words, chars, lines = word_count(text)
        self.statsChanged.emit(f"{words} words · {chars} chars · {lines} lines")
        self.changed.emit()

    # ------------------------------------------------------------- internals
    def _on_text_changed(self) -> None:
        self._sync_timer.start()

    def _update_status(self) -> None:
        words, chars, lines = word_count(self.editor.toPlainText())
        self.statsChanged.emit(f"{words} words · {chars} chars · {lines} lines")

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        super().keyPressEvent(event)


def indent_selection(editor: QPlainTextEdit, prefix: str = "  ") -> None:
    cursor = editor.textCursor()
    cursor.beginEditBlock()
    if cursor.hasSelection():
        start = cursor.selectionStart()
        cursor.insertText(prefix)
        cursor.setPosition(start)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor
        )
    else:
        cursor.insertText(prefix)
    cursor.endEditBlock()


def insert_snippet(editor: QPlainTextEdit, snippet: str) -> None:
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    if editor.toPlainText() and not editor.toPlainText().endswith("\n"):
        cursor.insertText("\n\n")
    cursor.insertText(snippet)
    editor.setTextCursor(cursor)
