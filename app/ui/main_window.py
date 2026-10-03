"""Main application window: sidebar navigation, top bar and page stack."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION
from .context import AppContext
from .pages.account import AccountPage
from .pages.assistant import AssistantPage
from .pages.base import Page
from .pages.dashboard import DashboardPage
from .pages.issues import IssuesPage
from .pages.readme import ReadmePage
from .pages.releases import ReleasesPage
from .pages.repositories import ReposPage
from .pages.settings_page import SettingsPage
from .pages.welcome import WelcomePage
from .theme import ACCENTS, stylesheet
from .widgets import (
    Avatar,
    button,
    icon_button,
    icon_svg,
    label,
    toast,
    wrap_bodies,
)

NAV_ITEMS = [
    ("Dashboard", "home"),
    ("README Studio", "book"),
    ("Repositories", "folder"),
    ("Issues & PRs", "issue"),
    ("Releases & commits", "release"),
    ("AI Assistant", "sparkles"),
    ("Account", "user"),
    ("Settings", "settings"),
]


class Sidebar(QFrame):
    navigate = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(6)

        # ------------------------------------------------------------- brand
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icon_svg("git-branch", "#7c6cff", 24).pixmap(24, 24))
        brand.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label(APP_NAME, "h3"))
        titles.addWidget(label(f"v{APP_VERSION}", "faint"))
        brand.addLayout(titles)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(14)

        # ----------------------------------------------------------- nav items
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        for index, (title, icon) in enumerate(NAV_ITEMS):
            btn = QPushButton(f"  {title}")
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(icon_svg(icon, "#9aa5bb", 17))
            btn.setIconSize(QSize(17, 17))
            btn.setToolTip(f"{title}  (Ctrl+{index + 1})")
            # Page 0 is the welcome screen and has no sidebar entry, so the nav
            # list is offset by one: button i drives page i + 1.
            btn.clicked.connect(lambda _=False, i=index: self.navigate.emit(i + 1))
            self.group.addButton(btn, index)
            layout.addWidget(btn)
            self.buttons.append(btn)

        layout.addStretch(1)

        # ------------------------------------------------------------- footer
        self.footer = QFrame()
        self.footer.setObjectName("Inset")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(10, 8, 10, 8)
        footer_layout.setSpacing(9)
        self.avatar = Avatar(30)
        footer_layout.addWidget(self.avatar)
        footer_col = QVBoxLayout()
        footer_col.setSpacing(0)
        self.footer_name = label("Signed out", "")
        self.footer_name.setStyleSheet("font-weight:600;")
        self.footer_meta = label("No token", "faint")
        footer_col.addWidget(self.footer_name)
        footer_col.addWidget(self.footer_meta)
        footer_layout.addLayout(footer_col, 1)
        layout.addWidget(self.footer)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def set_identity(self, login: str, connected: bool) -> None:
        if connected:
            self.avatar.set_initials(login[:2] or "?")
            self.footer_name.setText(login or "Connected")
            self.footer_meta.setText("GitHub connected")
        else:
            self.avatar.set_initials("?")
            self.footer_name.setText("Signed out")
            self.footer_meta.setText("Click to connect")


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext | None = None) -> None:
        super().__init__()
        self.ctx = ctx or AppContext()
        self.pages: list[Page] = []
        self._current = 0

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1440, 900)
        self.setMinimumSize(1080, 680)

        central = QWidget()
        central.setObjectName("Root")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.goto)
        root.addWidget(self.sidebar)

        right = QWidget()
        right.setObjectName("Content")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # ------------------------------------------------------------- topbar
        self.topbar = QFrame()
        self.topbar.setObjectName("TopBar")
        self.topbar.setFixedHeight(60)
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(24, 0, 20, 0)
        top.setSpacing(12)

        self.page_title = label("", "h2")
        top.addWidget(self.page_title)
        top.addStretch(1)

        self.ai_pill = QPushButton()
        self.ai_pill.setObjectName("BadgeAccent")
        self.ai_pill.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_pill.setIcon(icon_svg("sparkles", "#7c6cff", 13))
        self.ai_pill.setIconSize(QSize(13, 13))
        self.ai_pill.setToolTip("Open the AI assistant (Ctrl+K)")
        self.ai_pill.clicked.connect(lambda: self.goto(self._index_of(AssistantPage)))
        top.addWidget(self.ai_pill)

        self.theme_button = icon_button("moon", tooltip="Toggle light / dark", on_click=self.toggle_theme)
        top.addWidget(self.theme_button)
        self.add_button = button(
            "New repository", variant="primary", icon="plus", on_click=self.new_repo
        )
        top.addWidget(self.add_button)
        right_layout.addWidget(self.topbar)

        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        root.addWidget(right, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

        self._build_pages()
        self._install_shortcuts()
        self.apply_theme()
        self.refresh_auth_state()
        QTimer.singleShot(60, self._start)

    # -------------------------------------------------------------- building
    def _build_pages(self) -> None:
        self.welcome = WelcomePage(self.ctx)
        wrap_bodies(self.welcome)
        self.pages.append(self.welcome)
        self.stack.addWidget(self.welcome)

        for page_cls in (
            DashboardPage,
            ReadmePage,
            ReposPage,
            IssuesPage,
            ReleasesPage,
            AssistantPage,
            AccountPage,
            SettingsPage,
        ):
            page = page_cls(self.ctx)
            wrap_bodies(page)
            self.pages.append(page)
            self.stack.addWidget(page)

        dashboard = self.pages[1]
        if hasattr(dashboard, "set_navigator"):
            dashboard.set_navigator(self._nav_stub())

    def _nav_stub(self):
        window = self

        class _Nav:
            @staticmethod
            def setCurrentIndex(index: int) -> None:  # noqa: N802
                window.goto(index + 1)

        return _Nav()

    def _install_shortcuts(self) -> None:
        from .widgets import shortcut

        for index in range(1, 8):
            shortcut(self, f"Ctrl+{index}", lambda i=index: self.goto(i))
        shortcut(self, "Ctrl+K", lambda: self.goto(self._index_of(AssistantPage)))
        shortcut(self, "Ctrl+,", lambda: self.goto(self._index_of(SettingsPage)))
        shortcut(self, "Ctrl+R", self.refresh_current)
        shortcut(self, "Ctrl+N", self.new_repo)
        shortcut(self, "Ctrl+B", self.toggle_sidebar)
        shortcut(self, "Ctrl+Shift+R", self.toggle_theme)
        shortcut(self, "Ctrl+Q", self.close)

    def _index_of(self, page_cls: type) -> int:
        for index, page in enumerate(self.pages):
            if isinstance(page, page_cls):
                return index
        return 0

    def _start(self) -> None:
        target = self.ctx.config.get("last_page", 0)
        self.goto(max(0, min(target, len(self.pages) - 1)))
        if not self.ctx.signed_in:
            self.goto(0)

    # ------------------------------------------------------------ navigation
    def goto(self, index: int) -> None:
        index = max(0, min(index, len(self.pages) - 1))
        if index != 0 and not self.ctx.signed_in:
            toast(self, "Connect GitHub first — opening the welcome screen.", "warning")
            index = 0
        self._current = index
        page = self.pages[index]
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current(max(0, index - 1))
        self.page_title.setText(page.title)
        try:
            page.load_once()
        except Exception as exc:  # pragma: no cover
            toast(self, f"Could not open {page.title}: {exc}", "error")
        if index != 0:
            self.ctx.config.save(last_page=index)

    def refresh_current(self) -> None:
        page = self.pages[self._current]
        for name in ("refresh", "on_show"):
            handler = getattr(page, name, None)
            if callable(handler):
                try:
                    handler()
                except Exception as exc:  # pragma: no cover
                    toast(self, str(exc), "error")
                return

    def goto_settings(self) -> None:
        self.goto(self._index_of(SettingsPage))

    def focus_readme(self, repo_name: str = "", content: str = "") -> None:
        page = self.pages[self._index_of(ReadmePage)]
        self.goto(self._index_of(ReadmePage))
        if repo_name:
            page.repo_combo.setCurrentText(repo_name)
        if content:
            page.editor.set_text(content)

    def new_repo(self) -> None:
        if not self.ctx.signed_in:
            self.goto(0)
            return
        self.goto(self._index_of(ReposPage))
        page = self.pages[self._index_of(ReposPage)]
        QTimer.singleShot(120, page.create_repo)

    def toggle_sidebar(self) -> None:
        width = self.sidebar.width()
        self.sidebar.setFixedWidth(0 if width > 0 else 232)

    # --------------------------------------------------------------- theming
    def apply_theme(self) -> None:
        theme = self.ctx.config.get("theme", "dark")
        accent = self.ctx.config.get("accent", "violet")
        scale = float(self.ctx.config.get("ui_scale", 1.0) or 1.0)
        family = self.ctx.config.get("font_family", "")

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet(theme, accent, family, scale))

        if app is not None:
            from PySide6.QtGui import QPalette

            accent_color = ACCENTS.get(accent, "#7c6cff")
            dark = theme == "dark"
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#0b0e14" if dark else "#f4f6fb"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#e7ecf5" if dark else "#141824"))
            pal.setColor(QPalette.ColorRole.Base, QColor("#151a26" if dark else "#ffffff"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1b2130" if dark else "#f7f8fc"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#e7ecf5" if dark else "#141824"))
            pal.setColor(QPalette.ColorRole.Button, QColor("#1b2130" if dark else "#eef0f7"))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor("#e7ecf5" if dark else "#141824"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor(accent_color))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#222939" if dark else "#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#e7ecf5" if dark else "#141824"))
            app.setPalette(pal)

        self.theme_button.setIcon(icon_svg("sun" if theme == "dark" else "moon", "#9aa5bb", 18))

        for page in self.pages:
            if not hasattr(page, "on_theme_changed"):
                continue
            try:
                page.on_theme_changed()
            except Exception as exc:  # noqa: BLE001
                # One misbehaving page must not stop the rest from restyling,
                # but the failure should not vanish either.
                print(f"[theme] {type(page).__name__}: {exc}")

        from .widgets import enable_dark_titlebar

        enable_dark_titlebar(self, theme == "dark")

    def toggle_theme(self) -> None:
        new_theme = "light" if self.ctx.config.get("theme", "dark") == "dark" else "dark"
        self.ctx.config.save(theme=new_theme)
        self.apply_theme()
        toast(self, f"{new_theme.capitalize()} theme enabled.", "info")

    # ------------------------------------------------------------- auth state
    def refresh_auth_state(self) -> None:
        login = self.ctx.config.get("github_login", "")
        self.sidebar.set_identity(login, self.ctx.signed_in)
        connected = self.ctx.signed_in
        self.add_button.setVisible(connected)
        self.ai_pill.setVisible(True)
        if self.ctx.ai_ready():
            self.ai_pill.setText(f" AI ready · {self.ctx.config.get('ai_model', '')}")
        else:
            self.ai_pill.setText(" AI not configured")
        if not connected and self._current != 0:
            self.goto(0)

    # ------------------------------------------------------------------ close
    def closeEvent(self, event: Any) -> None:  # noqa: N802
        from . import workers

        workers.shutdown()
        super().closeEvent(event)
