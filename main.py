"""GitHub Manager - application entry point."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Allow "python main.py" from anywhere by putting the package folder on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import APP_NAME, APP_VERSION, ORG_NAME, app_root  # noqa: E402


def _excepthook(exc_type, exc_value, exc_tb) -> None:  # pragma: no cover
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    sys.stderr.write(text)
    try:
        QMessageBox.critical(
            None,
            "Something went wrong",
            f"{exc_value}\n\nThe full traceback was written to the console.",
        )
    except Exception:
        pass


def _make_icon() -> QIcon | None:
    """Render the app icon at runtime so no binary asset is required."""
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap

        from app.ui.widgets import icon_svg

        sizes = [16, 24, 32, 48, 64, 128, 256]
        pixmaps = []
        for size in sizes:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            gradient = QLinearGradient(0, 0, size, size)
            gradient.setColorAt(0.0, QColor("#8b7cff"))
            gradient.setColorAt(1.0, QColor("#5b4bdb"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
            glyph = icon_svg("git-branch", "#ffffff", int(size * 0.6)).pixmap(
                int(size * 0.6), int(size * 0.6)
            )
            painter.drawPixmap(
                int(size * 0.2), int(size * 0.2), glyph
            )
            painter.end()
            pixmaps.append(pixmap)
        icon = QIcon()
        for pixmap in pixmaps:
            icon.addPixmap(pixmap)
        return icon
    except Exception:
        return None


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    icon = _make_icon()
    if icon is not None:
        app.setWindowIcon(icon)

    sys.excepthook = _excepthook

    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow

    ctx = AppContext()
    window = MainWindow(ctx)
    window.show()

    # Portable mode: keep a data folder next to the executable.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
