"""Test bootstrap: keep the suites out of the real data folder.

Import this **before** anything from ``app`` is imported.

Without it the tests would resolve the same ``data/secrets.json`` the installed
application uses, so a stub token written by a test would overwrite the user's
real one - and the overwrite is invisible, because the file is encrypted. Every
suite therefore redirects the data folder into a throwaway directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

#: Sandbox shared by every suite in one process.
SANDBOX = Path(tempfile.gettempdir()) / "ghm-test-sandbox"

# Start from a clean slate so a stub token left by a previous run can never
# leak into the next one and make an assertion pass for the wrong reason.
if SANDBOX.exists() and SANDBOX.name.startswith("ghm-test-"):
    shutil.rmtree(SANDBOX, ignore_errors=True)

# Force the non-portable branch so nothing is written next to the source tree,
# then point that branch at a throwaway directory.
os.environ["GHM_PORTABLE"] = "0"
os.environ["APPDATA"] = str(SANDBOX)
# Windows also resolves LOCALAPPDATA for some APIs; keep them consistent.
os.environ["LOCALAPPDATA"] = str(SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SANDBOX.mkdir(parents=True, exist_ok=True)


def page_of(window: object, page_cls: type) -> object:
    """Find a page by its class instead of by its position in the stack.

    Indexing ``window.pages[n]`` breaks the moment a page is inserted, and it
    breaks silently: the test keeps running against whichever page took that
    slot and fails somewhere unrelated, or passes for the wrong reason.
    """
    for page in getattr(window, "pages", ()):
        if isinstance(page, page_cls):
            return page
    raise AssertionError(f"{page_cls.__name__} is not in the window's page stack")


def open_page(window: object, page_cls: type) -> object:
    """:func:`page_of`, but also selects it, the way a user would arrive."""
    page = page_of(window, page_cls)
    goto = getattr(window, "goto", None)
    if callable(goto):
        index = list(getattr(window, "pages", ())).index(page)
        goto(index)
    return page


def ensure_importable() -> None:
    """Put the project root and the tests folder on ``sys.path``."""
    root = Path(__file__).resolve().parents[1]
    for entry in (root, root / "tests"):
        text = str(entry)
        if text not in sys.path:
            sys.path.insert(0, text)


def destroy(widget: object) -> None:
    """Close a window and release the C++ object behind it.

    ``close()`` alone is not enough. The pages hold bound signal slots that point
    back at the window, so the window, its pages and those connections form a
    cycle that Python's collector will not break across the Qt wrappers. The
    whole tree then stays alive: the next ``setStyleSheet`` has to restyle every
    leftover widget, so each rebuild in a suite costs several times the first.
    Dropping the C++ object is what actually frees it.

    Harmless to call twice, and safe when the widget was never shown.
    """
    import gc

    import shiboken6
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication.instance()
    if app is not None:
        app.processEvents()

    if isinstance(widget, QWidget):
        try:
            widget.close()
        except RuntimeError:
            return  # already deleted
    try:
        shiboken6.delete(widget)
    except (RuntimeError, TypeError):
        pass

    del widget
    gc.collect()
    if app is not None:
        # Two passes: deleting the parent posts deletes for its children.
        app.processEvents()
        app.processEvents()
        gc.collect()


ensure_importable()