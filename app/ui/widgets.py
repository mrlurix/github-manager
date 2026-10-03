"""Reusable UI building blocks."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Iterable
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


# --------------------------------------------------------------------- icons
ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}


def icon_svg(name: str, color: str = "#e7ecf5", size: int = 20) -> QIcon:
    """Build (and cache) a QIcon from one of the bundled inline SVG paths."""
    key = (name, color, size)
    cached = ICON_CACHE.get(key)
    if cached is not None:
        return cached

    path = ICONS.get(name, ICONS["dot"])
    body = path.replace("{c}", color).replace("{s}", str(size))
    # Render at 2x for crisp icons on HiDPI screens, then tag the pixmap so Qt
    # scales it back down to the requested logical size.
    pixels = size * 2
    # NOTE: QSvgRenderer rejects a plain str in PySide6 - the data must be bytes.
    markup = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="{pixels}" height="{pixels}" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(markup.encode("utf-8"))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)

    icon = QIcon(pixmap)
    ICON_CACHE[key] = icon
    return icon


def clear_icon_cache() -> None:
    ICON_CACHE.clear()


ICONS: dict[str, str] = {
    "dot": '<circle cx="12" cy="12" r="3" fill="{c}" stroke="none"/>',
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5.5h4V20"/>',
    "book": '<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H19v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H19v3H5.5A1.5 1.5 0 0 1 4 19.5z"/>',
    "folder": '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h9A1.5 1.5 0 0 1 21 10v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"/>',
    "user": '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20c1.2-3.6 4-5.4 7.5-5.4S18.3 16.4 19.5 20"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M2.8 19.5c1-3.2 3.3-4.8 6.2-4.8s5.2 1.6 6.2 4.8"/><path d="M16 5.4a3.2 3.2 0 0 1 0 5.2"/><path d="M17.6 14.9c2 .6 3.3 2.2 3.7 4.6"/>',
    "sparkles": '<path d="m12 3 1.7 4.6L18.3 9l-4.6 1.7L12 15.3l-1.7-4.6L5.7 9l4.6-1.4z"/><path d="m18.5 15.5.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
    "chat": '<path d="M4 5.5h16v11H9l-5 4z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2 5.3"/><path d="M20 4.5V11h-6.2"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "save": '<path d="M5 4h11l3 3v13H5z"/><path d="M8.5 4v5h7V4M8.5 20v-6h7v6"/>',
    "upload": '<path d="M12 16V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M4 16v3.5h16V16"/>',
    "download": '<path d="M12 4v12"/><path d="m7.5 11.5 4.5 4.5 4.5-4.5"/><path d="M4 16v3.5h16V16"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M15 5.5V6A1.5 1.5 0 0 0 13.5 4.5H6A1.5 1.5 0 0 0 4.5 6v7.5A1.5 1.5 0 0 0 6 15h.5"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v5.5A1.5 1.5 0 0 1 16.5 21h-11A1.5 1.5 0 0 1 4 19.5v-11A1.5 1.5 0 0 1 5.5 7H11"/>',
    "edit": '<path d="M4 20h4l10-10-4-4L4 16z"/><path d="m14.5 5.5 4 4"/>',
    "trash": '<path d="M5 7h14"/><path d="M9 7V5h6v2"/><path d="M6.5 7 7.5 20h9l1-13"/>',
    "star": '<path d="m12 4 2.4 5 5.6.8-4 3.9 1 5.5-5-2.7-5 2.7 1-5.5-4-3.9 5.6-.8z"/>',
    "git-branch": '<circle cx="7" cy="6" r="2.4"/><circle cx="7" cy="18" r="2.4"/><circle cx="17" cy="8.5" r="2.4"/><path d="M7 8.4v7.2"/><path d="M17 11c0 3.2-2.6 4-5 4.2"/>',
    "git-commit": '<circle cx="12" cy="12" r="3"/><path d="M3.5 12H9M15 12h5.5"/>',
    "tag": '<path d="M4 11V5.5A1.5 1.5 0 0 1 5.5 4H11l8 8-6.5 6.5z"/><circle cx="8" cy="8" r="1.3"/>',
    "issue": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.4"/>',
    "pull": '<circle cx="7" cy="6" r="2.3"/><circle cx="7" cy="18" r="2.3"/><circle cx="17" cy="18" r="2.3"/><path d="M7 8.3v7.4"/><path d="M17 15.7V9a3 3 0 0 0-3-3h-2"/>',
    "release": '<path d="M12 3.5 19 8v8l-7 4.5L5 16V8z"/><path d="M12 9.5 15 11.3v3.4L12 16.5l-3-1.8v-3.4z"/>',
    "shield": '<path d="M12 3.5 19 6v6c0 4-3 7-7 8.5C8 19 5 16 5 12V6z"/>',
    "shield-key": '<path d="M12 3.5 19 6v6c0 4-3 7-7 8.5C8 19 5 16 5 12V6z"/><circle cx="12" cy="11" r="2"/><path d="M12 13v3"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>',
    "link": '<path d="M10 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1.2 1.2"/><path d="M14 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1.2-1.2"/>',
    "logout": '<path d="M14 5H7A1.5 1.5 0 0 0 5.5 6.5v11A1.5 1.5 0 0 0 7 19h7"/><path d="M17 12H9.5"/><path d="m14 8.5 3.5 3.5-3.5 3.5"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M4 4l16 16"/><path d="M9.6 5.9A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3.3 4"/><path d="M6.4 8A17 17 0 0 0 2.5 12S6 18.5 12 18.5c1.4 0 2.6-.3 3.7-.8"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5"/>',
    "monitor": '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8.5 20h7M12 17v3"/>',
    "cpu": '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3.5V7M14 3.5V7M10 17v3.5M14 17v3.5M3.5 10H7M3.5 14H7M17 10h3.5M17 14h3.5"/>',
    "send": '<path d="M4 12 20 4l-8 16-2-6.5z"/>',
    "trash-small": '<path d="M6 8h12"/><path d="m8 8 .8 12h6.4L16 8"/>',
    "code": '<path d="m8.5 8-4.5 4 4.5 4M15.5 8l4.5 4-4.5 4"/>',
    "book-open": '<path d="M12 6.5C10.5 5 8.5 4.5 4 4.8v13c4.5-.3 6.5.2 8 1.7 1.5-1.5 3.5-2 8-1.7v-13c-4.5-.3-6.5.2-8 1.7"/><path d="M12 6.5v13"/>',
    "list": '<path d="M8 6.5h12M8 12h12M8 17.5h12M4 6.5h.01M4 12h.01M4 17.5h.01"/>',
    "archive": '<rect x="3.5" y="4.5" width="17" height="5" rx="1.2"/><path d="M5 9.5V19a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5"/><path d="M10 13.5h4"/>',
    "fork": '<circle cx="7" cy="5.5" r="2.2"/><circle cx="7" cy="18.5" r="2.2"/><circle cx="17" cy="18.5" r="2.2"/><path d="M7 7.7v8.6"/><path d="M17 16.3V12a4 4 0 0 0-4-4H7"/>',
    "transfer": '<path d="M4 8h13"/><path d="m13.5 4.5 3.5 3.5-3.5 3.5"/><path d="M20 16H7"/><path d="m10.5 12.5-3.5 3.5 3.5 3.5"/>',
    "terminal": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m7.5 10 2.5 2.5-2.5 2.5M12.5 15.5h4"/>',
    "shield-check": '<path d="M12 3.5 19 6v6c0 4-3 7-7 8.5C8 19 5 16 5 12V6z"/><path d="m9 12 2 2 4-4"/>',
    "alert": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5M12 16h.01"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.5h.01"/>',
    "wand": '<path d="M5 19 16 8"/><path d="m14 4 1 2.5L17.5 7.5 15 8.5l-1 2.5-1-2.5L10.5 7.5 13 6.5z"/><path d="M19.5 13.5 20 15l1.5.5L20 16l-.5 1.5L19 16l-1.5-.5L19 15z"/>',
}


# ------------------------------------------------------------------ helpers
def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


def vline() -> QFrame:
    line = QFrame()
    line.setObjectName("VDivider")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    return line


def spacer(width: int = 0, height: int = 0) -> QWidget:
    widget = QWidget()
    if width:
        widget.setFixedWidth(width)
    else:
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    if height:
        widget.setFixedHeight(height)
    return widget


def label(
    text: str,
    role: str = "",
    *,
    align: Qt.AlignmentFlag | None = None,
    wrap: bool = False,
) -> QLabel:
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    if align is not None:
        lab.setAlignment(align)
    if wrap:
        lab.setWordWrap(True)
    return lab


def note(text: str, role: str = "dim") -> QLabel:
    """A dimmed, word-wrapped explanatory label."""
    lab = label(text, role, wrap=True)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def set_role(widget: QWidget, role: str) -> None:
    widget.setProperty("role", role)


def escape_mnemonic(text: str) -> str:
    """Escape ``&`` so Qt renders a literal ampersand instead of a mnemonic.

    Without this, a label such as ``Header & badges`` is measured as
    ``Header badges`` and the button ends up too narrow, clipping the text.
    """
    return text.replace("&", "&&")


def unescape_mnemonic(text: str) -> str:
    """Inverse of :func:`escape_mnemonic` for reading button labels back."""
    return text.replace("&&", "&")


def button(
    text: str = "",
    *,
    variant: str = "",
    icon: str = "",
    on_click: Callable[[], None] | None = None,
    tooltip: str = "",
    icon_size: int = 18,
) -> QPushButton:
    btn = QPushButton(escape_mnemonic(text))
    if variant:
        btn.setProperty("variant", variant)
    if tooltip:
        btn.setToolTip(tooltip)
    if icon:
        btn.setIcon(icon_svg(icon, "#ffffff" if variant == "primary" else "#9aa5bb", icon_size))
        btn.setIconSize(QSize(icon_size, icon_size))
    if on_click:
        btn.clicked.connect(on_click)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def icon_button(
    icon: str,
    *,
    tooltip: str = "",
    on_click: Callable[[], None] | None = None,
    size: int = 18,
    color: str = "#9aa5bb",
) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("IconButton")
    btn.setIcon(icon_svg(icon, color, size))
    btn.setIconSize(QSize(size, size))
    btn.setFixedSize(size + 14, size + 14)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def chip(text: str, *, checked: bool = False, on_toggle: Callable[[bool], None] | None = None) -> QPushButton:
    btn = QPushButton(escape_mnemonic(text))
    btn.setObjectName("Chip")
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    # Qt's QSS padding is applied when painting but is not fully reflected in
    # sizeHint(), which makes narrow labels clip. Pin the minimum width to the
    # measured text so the chip always fits its caption.
    from .theme import CHIP_PADDING_X

    metrics = btn.fontMetrics()
    btn.setMinimumWidth(
        metrics.horizontalAdvance(escape_mnemonic(text)) + 2 * CHIP_PADDING_X + 4
    )
    if on_toggle:
        btn.toggled.connect(on_toggle)
    return btn


def shortcut(parent: QWidget, keys: str | QKeySequence, handler: Callable[[], None]) -> QShortcut:
    seq = QKeySequence(keys) if isinstance(keys, str) else keys
    sc = QShortcut(seq, parent)
    sc.activated.connect(handler)
    return sc


# ---------------------------------------------------------------- containers
# Longest single-line label we allow before it must wrap onto several lines.
WRAP_MIN_CHARS = 90
# Labels wider than this are never wrapped - they are single-line captions and
# wrapping them looks worse than letting the card grow.
WRAP_MAX_CHARS = 400


def wrap_bodies(host: QWidget) -> None:
    """Enable word wrap on long plain QLabels inside ``host``.

    QLabel does not wrap by default, which makes long descriptions overflow
    their card. Short captions are left alone: wrapping them at the card width
    produces awkward one-word lines.
    """
    for lab in host.findChildren(QLabel):
        if lab.wordWrap():
            continue
        text = lab.text()
        if "\n" in text:
            continue
        if WRAP_MIN_CHARS <= len(text) <= WRAP_MAX_CHARS:
            lab.setWordWrap(True)


class Card(QFrame):
    """Rounded surface with optional title row."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        *,
        flat: bool = False,
        hover: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "CardHover" if hover else "Card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        self.header: QWidget | None = None
        if title:
            self.header = QWidget()
            head = QHBoxLayout(self.header)
            head.setContentsMargins(0, 0, 0, 0)
            head.setSpacing(10)
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            col.addWidget(label(title, "h3"))
            if subtitle:
                # The subtitle takes the remaining width so it wraps across the
                # card instead of being squeezed into a narrow column.
                col.addWidget(label(subtitle, "faint", wrap=True))
            head.addLayout(col, 1)
            outer.addWidget(self.header)
            self.header_layout = head

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        outer.addLayout(self.body)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        wrap_bodies(widget)
        return widget

    def add_layout(self, layout: QLayout) -> QLayout:
        self.body.addLayout(layout)
        wrap_bodies(self)
        return layout


class StatTile(QFrame):
    """Compact metric used on the dashboard."""

    clicked = Signal()

    def __init__(
        self,
        value: str,
        caption: str,
        *,
        icon: str = "",
        accent: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardHover")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(84)
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.caption_label = label(caption.upper(), "faint")
        top.addWidget(self.caption_label)
        top.addStretch(1)
        self.icon_label = QLabel()
        if icon:
            self.icon_label.setPixmap(icon_svg(icon, accent or "#6b7690", 18).pixmap(18, 18))
        top.addWidget(self.icon_label)
        layout.addLayout(top)

        self.value_label = label(value, "")
        self.value_label.setObjectName("StatValue")
        layout.addWidget(self.value_label)

    def set_value(self, value: Any) -> None:
        self.value_label.setText(str(value))

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        self.clicked.emit()
        super().mouseReleaseEvent(event)


class Badge(QLabel):
    def __init__(self, text: str = "", kind: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName(f"Badge{kind.capitalize()}" if kind else "Badge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_kind(self, kind: str) -> None:
        self.setObjectName(f"Badge{kind.capitalize()}" if kind else "Badge")


class Avatar(QLabel):
    """Circular avatar that falls back to initials."""

    def __init__(self, size: int = 40, url: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._url = ""
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._initials = "?"
        self._color = QColor("#7c6cff")
        if url:
            self.load(url)
        else:
            self._render_initials()

    def set_size(self, size: int) -> None:
        self._size = size
        self.setFixedSize(size, size)
        self.setFont(QFont(self.font().family(), max(8, int(size * 0.38))))
        self._render_initials()

    def set_initials(self, text: str) -> None:
        self._initials = (text or "?")[:2].upper()
        self._render_initials()

    def load(self, url: str) -> None:
        self._url = url
        if not url:
            self._render_initials()
            return
        QTimer.singleShot(0, self._fetch)

    def _fetch(self) -> None:
        import requests  # local import keeps startup fast

        try:
            resp = requests.get(self._url, timeout=12)
            resp.raise_for_status()
            pixmap = QPixmap()
            pixmap.loadFromData(resp.content)
            if not pixmap.isNull():
                self.setPixmap(self._circle(pixmap))
                return
        except Exception:
            pass
        self._render_initials()

    def _circle(self, pixmap: QPixmap) -> QPixmap:
        size = self._size * 2
        scaled = pixmap.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled)
        painter.end()
        canvas.setDevicePixelRatio(2.0)
        return canvas

    def _render_initials(self) -> None:
        size = self._size * 2
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setPixelSize(int(size * 0.42))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, self._initials)
        painter.end()
        canvas.setDevicePixelRatio(2.0)
        self.setPixmap(canvas)


class FlowLayout(QLayout):
    """Left-to-right layout that wraps to a new line when full.

    Unlike the classic Qt flow-layout example this implementation keeps the
    widget's *width* at whatever the parent gives it and only ever grows
    downwards, so the surrounding vertical layouts stay stable.
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[Any] = []
        self._spacing = spacing
        self._height = 0
        self.setContentsMargins(0, 0, 0, 0)

    # ------------------------------------------------------ QLayout plumbing
    def addItem(self, item: Any) -> None:  # noqa: N802
        self._items.append(item)
        self.invalidate()

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Any:  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Any:  # noqa: N802
        if 0 <= index < len(self._items):
            self.invalidate()
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._arrange(QRect(0, 0, max(1, width), 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._natural_width(), self._height or self._natural_height())

    def minimumSize(self) -> QSize:  # noqa: N802
        widest = 0
        tallest = 0
        for item in self._items:
            hint = item.minimumSize()
            widest = max(widest, hint.width())
            tallest = max(tallest, hint.height())
        return QSize(widest, tallest)

    # ----------------------------------------------------------- arranging
    def _natural_width(self) -> int:
        total = self._spacing * max(0, len(self._items) - 1)
        return total + sum(
            item.sizeHint().expandedTo(item.minimumSize()).width() for item in self._items
        )

    def _natural_height(self) -> int:
        width = max(1, self._natural_width())
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = area.x()
        y = area.y()
        line_height = 0

        for item in self._items:
            # Qt's QSS padding is missing from sizeHint(), so honour an explicit
            # minimum size when one was set.
            hint = item.sizeHint().expandedTo(item.minimumSize())
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())

        self._height = (y - area.y()) + line_height + margins.top() + margins.bottom()
        return self._height

    def refresh(self) -> None:
        """Re-run the arrangement after the child widgets changed size."""
        parent = self.parentWidget()
        if parent is None:
            return
        self._arrange(QRect(0, 0, parent.width(), parent.height()), apply=True)
        self.invalidate()


class FlowWidget(QWidget):
    """QWidget wrapper around :class:`FlowLayout`.

    A bare ``QWidget`` + flow layout does not reliably propagate its wrapped
    height to the parent layout, which makes the row collapse to a single line.
    This subclass reports the height-for-width result itself.
    """

    def __init__(self, spacing: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def add(self, widget: QWidget) -> QWidget:
        self.flow.addWidget(widget)
        return widget

    def clear(self) -> None:
        while self.flow.count():
            item = self.flow.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self.flow.heightForWidth(width)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.flow.sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.flow.minimumSize()

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.flow.refresh()


class Toast(QFrame):
    """Transient notification anchored to the bottom right of its parent."""

    #: Weak references, not the widgets themselves. A toast is normally removed
    #: by its timer, but if its parent window closes first the timer never fires
    #: and the entry would stay here - holding the toast, which holds its parent,
    #: which holds every page. A registry like that never empties, and the leak
    #: is invisible until the window count grows.
    _active: list["weakref.ReferenceType[Toast]"] = []

    @classmethod
    def _live(cls) -> list["Toast"]:
        """The toasts that still exist, pruning the ones that do not."""
        alive: list[Toast] = []
        kept: list[weakref.ReferenceType[Toast]] = []
        for ref in cls._active:
            toast = ref()
            if toast is not None:
                alive.append(toast)
                kept.append(ref)
        cls._active = kept
        return alive

    def __init__(self, parent: QWidget, message: str, kind: str = "info", msec: int = 3200) -> None:
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)

        colors = {
            "info": "#3aa0ff",
            "success": "#31c48d",
            "warning": "#f5a524",
            "error": "#f2555a",
        }
        icons = {"info": "info", "success": "shield-check", "warning": "alert", "error": "x"}
        icon = QLabel()
        icon.setPixmap(icon_svg(icons.get(kind, "info"), colors.get(kind, "#3aa0ff"), 18).pixmap(18, 18))
        layout.addWidget(icon)

        text = label(message, "")
        text.setWordWrap(True)
        text.setMaximumWidth(340)
        layout.addWidget(text)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self.adjustSize()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timer.start(msec)

        Toast._active.append(weakref.ref(self))
        self._reposition()
        self.show()
        self.raise_()
        self._fade_in()

    def _fade_in(self) -> None:
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        offset = 0
        for toast in Toast._live():
            if toast is self or toast.parentWidget() is not parent:
                continue
            offset += toast.height() + 10
        self.move(
            parent.width() - self.width() - 26,
            parent.height() - self.height() - 26 - offset,
        )

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._reposition()

    def mousePressEvent(self, _event: Any) -> None:  # noqa: N802
        # A click anywhere on the toast dismisses it.
        self.dismiss()

    def dismiss(self) -> None:
        # Held weakly, so dropping the reference is enough to unregister.
        Toast._active = [ref for ref in Toast._active if ref() is not None and ref() is not self]
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._destroy)
        anim.start()

    def _destroy(self) -> None:
        self.deleteLater()


def toast(parent: QWidget, message: str, kind: str = "info", msec: int = 3200) -> Toast:
    return Toast(parent, message, kind, msec)


class BusyOverlay(QWidget):
    """Dim + spinner shown on top of a page while a worker runs."""

    def __init__(self, parent: QWidget, text: str = "Working...") -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(8, 10, 16, 0.55);")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self.spinner = Spinner(34, parent=self)
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)

        self.label = label(text, "dim")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def show_busy(self, text: str = "") -> None:
        if text:
            self.label.setText(text)
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def stop(self) -> None:
        self.hide()


class Spinner(QWidget):
    """Lightweight indeterminate progress ring."""

    def __init__(self, size: int = 28, color: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self._angle = 0
        self._color = color or "#7c6cff"
        self.setFixedSize(size, size)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def set_color(self, color: str) -> None:
        self._color = color

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:  # noqa: D102
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        pen = QPen(QColor(self._color))
        pen.setWidthF(2.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, -self._angle * 16, 110 * 16)
        painter.end()


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.subtitle_label: QLabel | None = None
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        col.addWidget(label(title, "h1"))
        if subtitle:
            sub = label(subtitle, "dim", wrap=True)
            sub.setMinimumWidth(360)
            col.addWidget(sub)
            self.subtitle_label = sub
        layout.addLayout(col)
        layout.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget

    def set_subtitle(self, text: str) -> None:
        if self.subtitle_label is not None:
            self.subtitle_label.setText(text)


class ScrollPage(QScrollArea):
    """Vertical scroll container with a standard content column."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        # NOTE: do not call setStyleSheet() here. A widget level stylesheet takes
        # precedence over the application stylesheet for that whole subtree, so
        # buttons inside would lose their variant styling. The scroll-area rules
        # live in the global QSS instead.
        self._host = QWidget()
        self._host.setObjectName("ScrollHost")
        self.column = QVBoxLayout(self._host)
        self.column.setContentsMargins(26, 22, 26, 26)
        self.column.setSpacing(18)
        self.setWidget(self._host)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.column.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout: QLayout) -> QLayout:
        self.column.addLayout(layout)
        return layout

    def add_stretch(self) -> None:
        self.column.addStretch(1)


class DropArea(QFrame):
    """Simple drop target used for importing context files."""

    fileDropped = Signal(str)

    def __init__(self, text: str = "Drop a file here or click to browse", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Inset")
        self.setAcceptDrops(True)
        self.setMinimumHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(icon_svg("upload", "#6b7690", 20).pixmap(20, 20))
        layout.addWidget(icon)
        self.label = label(text, "dim")
        layout.addWidget(self.label)
        layout.addStretch(1)

    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()


class SegmentedControl(QWidget):
    """Compact radio-style selector."""

    changed = Signal(str)

    def __init__(self, options: Iterable[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._buttons: dict[str, QPushButton] = {}
        for key, text in options:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.set_current(k))
            layout.addWidget(btn)
            self._buttons[key] = btn
        if self._buttons:
            first = next(iter(self._buttons))
            self.set_current(first, emit=False)

    def set_current(self, key: str, *, emit: bool = True) -> None:
        for name, btn in self._buttons.items():
            btn.setChecked(name == key)
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        for name, btn in self._buttons.items():
            if btn.isChecked():
                return name
        return ""


def enable_dark_titlebar(window: Any, dark: bool = True) -> None:
    """Try to match the Windows title bar to the app theme."""
    try:
        import ctypes

        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def app_palette_colors(theme: str = "dark") -> dict[str, str]:
    from .theme import build_palette

    return build_palette(theme)


def action(text: str, handler: Callable[[], None], shortcut_str: str = "") -> QAction:
    act = QAction(text, None)
    act.triggered.connect(lambda: handler())
    if shortcut_str:
        act.setShortcut(QKeySequence(shortcut_str))
    return act


def apply_button_kind(btn: QPushButton, kind: str) -> None:
    btn.setProperty("variant", kind)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
