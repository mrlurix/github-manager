"""GitHub Manager - application entry point."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Allow "python main.py" from anywhere by putting the package folder on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import APP_NAME, APP_VERSION, ORG_NAME  # noqa: E402


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


def _system_is_dark() -> bool:
    """Whether the OS is in dark mode, or whether we could not tell.

    Defaults to dark. A white mark is the one that survives being wrong more
    often: Windows light taskbars are the minority and app icons are usually
    shown over a wallpaper thumbnail anyway, while a white mark on a dark
    surface is the combination the app itself is designed around.
    """
    try:
        from PySide6.QtCore import Qt

        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme != Qt.ColorScheme.Light
    except (AttributeError, ImportError, TypeError):
        return True


def _make_icon() -> QIcon | None:
    """Render the app icon at runtime so no binary asset is required.

    Rendered on an opaque plate rather than as a bare mark: the title bar and
    the taskbar are the OS's to colour, and a mark that has to guess is a mark
    that is invisible half the time. The plate is black on a light system and
    white on a dark one, so the mark inside it always has contrast.
    """
    try:
        from app.ui.widgets import logo_plate_pixmap

        dark = _system_is_dark()
        icon = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            # 2x so a HiDPI taskbar is not upscaling a bitmap it was just
            # handed; Qt halves it back on the way out.
            pixmap = logo_plate_pixmap(dark_plate=dark, pixels=size * 2)
            pixmap.setDevicePixelRatio(2.0)
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
