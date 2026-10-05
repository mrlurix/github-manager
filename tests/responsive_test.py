"""Responsive layout tests: nothing may overlap or get clipped, at any size.

The existing layout suite checks that widgets do not collapse and do not get
pushed outside their parent. This one adds the check it was missing: two
controls sitting on top of each other. That is what a fixed-width row does when
the window gets narrow - both keep their size hint, the layout has nowhere to
put them, and they overlap instead of wrapping.

Every page is visited across a wide sweep of window sizes, including sizes wider
and shorter than a typical laptop, and every pair of sibling controls is tested
for visual overlap.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QScrollBar,
    QSlider,
    QWidget,
)

PASSED: list[str] = []
FAILED: list[str] = []

#: Deliberately wider than the app's own minimum: the point is to find what
#: breaks at sizes nobody tests.
SIZES = [
    (900, 560),
    (1024, 640),
    (1280, 720),
    (1366, 768),
    (1440, 900),
    (1600, 900),
    (1920, 1080),
    (2560, 1080),
    (2560, 1440),
]

#: Interactive controls. Overlapping two of these is what the user sees.
CONTROLS = (
    QPushButton,
    QLineEdit,
    QComboBox,
    QAbstractSpinBox,
    QCheckBox,
    QRadioButton,
    QSlider,
)

#: Labels matter too: overlapping text is unreadable even without a border.
COUNT_TEXT_LABELS = True


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def caption(widget: QWidget) -> str:
    for attribute in ("text", "title", "placeholderText"):
        value = getattr(widget, attribute, None)
        if isinstance(value, str) and value.strip():
            return value[:22]
    # Most controls are unnamed, so fall back to where they sit: the parent's
    # object name and the index within it. That is enough to find the row.
    parent = widget.parentWidget()
    owner = (parent.objectName() if parent is not None else "") or (
        type(parent).__name__ if parent is not None else "?"
    )
    siblings = [w for w in parent.findChildren(QWidget)] if parent is not None else []
    try:
        position = siblings.index(widget)
    except ValueError:
        position = -1
    return f"#{position} in {owner}"


def is_interesting(widget: QWidget) -> bool:
    if isinstance(widget, QScrollBar):
        return False
    if isinstance(widget, CONTROLS):
        return True
    if COUNT_TEXT_LABELS and isinstance(widget, QLabel):
        return bool(widget.text().strip())
    return False


def visible_siblings(root: QWidget) -> list[tuple[QWidget, tuple[int, int, int, int]]]:
    """Interactive descendants, each with its rect in window coordinates."""
    out: list[tuple[QWidget, tuple[int, int, int, int]]] = []
    for widget in root.findChildren(QWidget):
        if not widget.isVisible() or widget.isHidden():
            continue
        if widget.width() <= 2 or widget.height() <= 2:
            continue
        if not is_interesting(widget):
            continue
        # Skip anything floating above the page (toasts, popups).
        if widget.window() is not root.window():
            continue
        rect = widget.rect()
        top_left = widget.mapTo(root.window(), rect.topLeft())
        out.append((widget, (top_left.x(), top_left.y(), rect.width(), rect.height())))
    return out


def overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int]:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = min(ax + aw, bx + bw) - max(ax, bx)
    dy = min(ay + ah, by + bh) - max(ay, by)
    return (dx, dy) if dx > 0 and dy > 0 else (0, 0)


def audit_overlaps(page: QWidget) -> list[str]:
    """Pairs of controls that visually cover each other."""
    items = visible_siblings(page)
    problems: list[str] = []
    for i in range(len(items)):
        wa, ra = items[i]
        for j in range(i + 1, len(items)):
            wb, rb = items[j]
            # Only siblings are ever meant to sit side by side; a parent/child
            # relationship or a nested layout is legitimate.
            if wa.parentWidget() is not wb.parentWidget():
                continue
            dx, dy = overlap(ra, rb)
            if dx <= 1 or dy <= 1:
                continue
            # Ignore a sliver: rounded borders and shadows can report 1-2 px.
            if dx * dy < 24:
                continue
            problems.append(
                f"{type(wa).__name__}('{caption(wa)}') overlaps "
                f"{type(wb).__name__}('{caption(wb)}') by {dx}x{dy}px"
            )
    return problems


def audit_clipped(page: QWidget, limit: int = 26) -> list[str]:
    """Controls whose text is squeezed below a usable size."""
    problems: list[str] = []
    for widget in page.findChildren(QWidget):
        if not isinstance(widget, CONTROLS) or not widget.isVisible():
            continue
        if widget.window() is not page.window():
            continue
        hint = widget.sizeHint()
        if widget.width() < min(hint.width(), limit) - 4 and widget.width() > 0:
            problems.append(
                f"{type(widget).__name__}('{caption(widget)}') squeezed to "
                f"{widget.width()}px (wants {hint.width()}px)"
            )
    return problems


def in_scroll_area(widget: QWidget) -> bool:
    """True when the widget lives inside a scroll area.

    Content inside a scroll area is allowed to be taller than the viewport:
    that is the scroll area doing its job, not content being clipped.
    """
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QScrollArea):
            return True
        parent = parent.parentWidget()
    return False


def audit_clipped_vertically(page: QWidget) -> list[str]:
    """Widgets given less height than they insist on, i.e. clipped content.

    Qt will happily hand a widget less than its minimum height when the window
    is too short. The widget is not scrolled or shrunk - its children are simply
    drawn outside its bounds and disappear. That is worse than an overlap,
    because the control is gone with no visual hint that it was ever there.
    """
    problems: list[str] = []
    for widget in page.findChildren(QWidget):
        if not widget.isVisible() or widget.isHidden():
            continue
        if widget.window() is not page.window():
            continue
        if in_scroll_area(widget):
            continue
        # Skip Qt's own internal widgets: the clear button inside a QLineEdit,
        # the drop-down arrow inside a QComboBox and friends are placed by Qt,
        # not by a layout we control. Reporting them would be noise.
        parent = widget.parentWidget()
        if isinstance(parent, (QLineEdit, QComboBox, QAbstractSpinBox)):
            continue
        # Skip Qt's own scroll-area viewport containers.
        if widget.objectName().startswith("qt_scrollarea"):
            continue
        # A widget that reports a height-for-width is laid out from that value at
        # its real width; minimumSizeHint is measured at an assumed width and can
        # legitimately be larger. Comparing against it would flag correct layouts.
        if widget.hasHeightForWidth():
            needed = widget.heightForWidth(widget.width())
            if needed <= 0:
                continue
        else:
            needed = widget.minimumSizeHint().height()
        # QHeaderView reports its parent's minimum, not its own height, so a
        # perfectly normal 34px header looks like it "needs 68". The header is
        # laid out by the table, not by us.
        if isinstance(widget, QHeaderView):
            continue
        # 4px of slack: borders and rounding routinely cost a pixel.
        if needed > 0 and widget.height() < needed - 4:
            problems.append(
                f"{type(widget).__name__}('{caption(widget)}') "
                f"h={widget.height()} but needs {needed}"
            )
    return problems


def main() -> int:
    from tests.ai_flow_test import build_app, pump
    from tests.smoke_test import COMMITS, ISSUES, RELEASES
    from app.ui.pages.issues import IssuesPage

    app = QApplication.instance() or QApplication(sys.argv)
    ctx, window = build_app(app)
    window.show()
    pump(app, 20)

    seen_overlap: list[str] = []
    seen_clip: list[str] = []
    seen_clipped: list[str] = []

    for width, height in SIZES:
        window.resize(width, height)
        app.processEvents()
        for page in window.pages:
            window.goto(window.pages.index(page))
            page.load_once()
            pump(app, 10)
            app.processEvents()

            if isinstance(page, IssuesPage):
                page._on_loaded(ISSUES)
            if hasattr(page, "_on_commits"):
                page._on_commits(COMMITS)
            if hasattr(page, "_on_releases"):
                page._on_releases(RELEASES)
            if hasattr(page, "repos_flow"):
                page.repos_flow.flow.refresh()
            # Flow rows re-wrap on resize, so let the layout settle before any
            # measurement: a width that is still settling makes heightForWidth
            # report a height for a layout that is not on screen yet.
            for _ in range(3):
                app.processEvents()
                time.sleep(0.01)
            app.processEvents()

            label = f"{type(page).__name__} at {width}x{height}"
            overlaps = audit_overlaps(page)
            check(f"{label}: nothing overlaps", not overlaps, "; ".join(overlaps[:3]))
            seen_overlap += [f"{label}: {o}" for o in overlaps]

            clipped = audit_clipped(page)
            check(f"{label}: controls not squeezed", not clipped, "; ".join(clipped[:3]))
            seen_clip += [f"{label}: {c}" for c in clipped]

            cut = audit_clipped_vertically(page)
            check(f"{label}: nothing clipped", not cut, "; ".join(cut[:3]))
            seen_clipped += [f"{label}: {c}" for c in cut]

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if seen_overlap:
        print("\noverlapping controls:")
        for item in sorted(set(seen_overlap))[:40]:
            print("  " + item)
    if seen_clip:
        print("\nsqueezed controls:")
        for item in sorted(set(seen_clip))[:25]:
            print("  " + item)
    if seen_clipped:
        print("\nclipped content:")
        for item in sorted(set(seen_clipped))[:30]:
            print("  " + item)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())