"""UI layer for GitHub Manager."""

from __future__ import annotations

__all__ = ["MainWindow", "AppContext"]


def __getattr__(name: str):  # pragma: no cover - lazy import helper
    if name == "MainWindow":
        from .main_window import MainWindow

        return MainWindow
    if name == "AppContext":
        from .context import AppContext

        return AppContext
    raise AttributeError(name)
