"""Page base class shared by every screen."""

from __future__ import annotations


from PySide6.QtWidgets import QWidget

from ..context import AppContext


class Page(QWidget):
    """A screen in the stacked navigation."""

    title: str = ""
    subtitle: str = ""
    icon: str = "dot"

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._loaded = False

    def on_show(self) -> None:
        """Called every time the page becomes visible."""

    def load_once(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.on_show()

    def on_theme_changed(self) -> None:
        """Re-apply theme dependent styling."""

    def busy(self, active: bool, text: str = "") -> None:
        """Hook for subclasses to show progress."""

    def notify(self, message: str, kind: str = "info") -> None:
        """Show a transient notification, scrubbing any credential first."""
        from ...core.redact import redact_secrets
        from ..widgets import toast

        window = self.window()
        if window is not None:
            toast(window, redact_secrets(message), kind)

    def require_ai(self) -> bool:
        if self.ctx.ai_ready():
            return True
        self.notify(self.ctx.ai_missing_reason(), "warning")
        return False

    def require_auth(self) -> bool:
        if self.ctx.signed_in:
            return True
        self.notify("Sign in with a GitHub token first.", "warning")
        return False
