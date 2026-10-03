"""Layout regression tests.

Every page is opened at several window sizes and checked for collapsed widgets:
zero-height rows, zero-width children, controls pushed outside their parent and
text clipped by a too-small container.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import destroy, ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QScrollBar,
    QWidget,
)

PASSED: list[str] = []
FAILED: list[str] = []

SIZES = [(1080, 680), (1366, 768), (1600, 900), (1920, 1080)]


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


COLLAPSIBLE = (
    QLineEdit,
    QComboBox,
    QAbstractSpinBox,
    QPlainTextEdit,
    QPushButton,
)


def in_scroll_area(widget: QWidget) -> bool:
    parent = widget.parent()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return True
        parent = parent.parent()
    return False


def audit(page: QWidget, size: tuple[int, int]) -> list[str]:
    """Return a list of layout problems found on ``page``."""
    problems: list[str] = []
    for widget in page.findChildren(QWidget):
        if not widget.isVisible():
            continue
        name = widget.objectName()
        # A scroll area's content host is legitimately taller than the viewport.
        if name == "ScrollHost" or name.startswith("qt_scrollarea"):
            continue
        if isinstance(widget, QScrollBar):
            continue
        # Content hosted by a QScrollArea lives in its viewport, so its parent is
        # not the QScrollArea itself.
        parent_name = (widget.parentWidget().objectName() or "") if widget.parentWidget() else ""
        if parent_name.startswith("qt_scrollarea"):
            continue
        if widget.width() <= 0 or widget.height() <= 0:
            if widget.sizeHint().height() > 8:
                problems.append(
                    f"collapsed {type(widget).__name__}({name}) {widget.sizeHint()}"
                )
            continue

        if (
            isinstance(widget, COLLAPSIBLE)
            and widget.height() < 12
            and not in_scroll_area(widget)
        ):
            problems.append(
                f"short {type(widget).__name__}({_caption(widget)}) h={widget.height()}"
            )

        # Children must stay inside a plain (layout-less) parent.
        parent = widget.parentWidget()
        if parent is None or parent is page:
            continue
        if not parent.isVisible():
            continue
        if isinstance(parent, QScrollArea):
            continue
        rect = widget.geometry()
        if rect.height() > 0 and parent.height() > 0:
            if rect.bottom() > parent.height() + 4 and parent.layout() is None:
                problems.append(
                    f"overflow {type(widget).__name__}({_caption(widget)}) "
                    f"{rect} in {type(parent).__name__} h={parent.height()}"
                )
    return problems


def _caption(widget: QWidget) -> str:
    for attribute in ("text", "title", "placeholderText"):
        getter = getattr(widget, attribute, None)
        if callable(getter):
            try:
                return str(getter())[:28]
            except TypeError:
                continue
    return widget.objectName() or type(widget).__name__


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from tests.ai_flow_test import build_app, pump
    from tests.smoke_test import COMMITS, ISSUES, RELEASES
    from app.ui.pages.issues import IssuesPage

    app = QApplication.instance() or QApplication(sys.argv)
    ctx, window = build_app(app)

    for width, height in SIZES:
        window.resize(width, height)
        app.processEvents()
        for index, page in enumerate(window.pages):
            window.goto(index)
            page.load_once()
            pump(app, 12)
            app.processEvents()

            if isinstance(page, IssuesPage):
                page._on_loaded(ISSUES)
            if hasattr(page, "_on_commits"):
                page._on_commits(COMMITS)
            if hasattr(page, "_on_releases"):
                page._on_releases(RELEASES)
            if hasattr(page, "repos_flow"):
                page.repos_flow.flow.refresh()
            pump(app, 12)

            problems = audit(page, (width, height))
            label_name = type(page).__name__.replace("Page", "")
            check(
                f"{label_name} at {width}x{height}",
                not problems,
                "; ".join(problems[:4]),
            )

    destroy(window)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
