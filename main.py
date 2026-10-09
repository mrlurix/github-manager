"""GitHub Manager - application entry point."""

from __future__ import annotations

import ctypes
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


#: Must be a dotted, reverse-DNS-looking string and must never change between
#: releases. Windows keys its taskbar and icon caches on it, so a stable value is
#: what lets an upgraded executable replace its own cached icon, and an unstable
#: one leaves every past version's icon behind in the cache.
APP_USER_MODEL_ID = "mrlurix.GitHubManager.Desktop"


def _claim_taskbar_identity(app: QApplication) -> None:
    """Give the taskbar a stable identity for this app.

    Without an AppUserModelID, Windows derives one from the executable's path.
    A portable app is copied to wherever the user likes, so the same build
    presents a different identity in each place, and the taskbar and the icon
    cache accumulate one entry per location instead of one per application.

    Called before any window exists, which is what the API requires. A failure
    here is not worth interrupting startup for: the app runs, it just inherits
    whatever identity Windows guesses.
    """
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        # Present on every Windows this app targets, but an app that will not
        # start over a missing taskbar nicety would be a worse trade.
        pass


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

    _claim_taskbar_identity(app)

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
