"""Welcome / onboarding screen shown when no GitHub token is configured."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.ai_api import PROVIDER_PRESETS
from ..dialogs import TokenDialog
from ..widgets import (
    Card,
    FlowWidget,
    button,
    icon_svg,
    label,
    spacer,
    toast,
)
from .base import Page


class WelcomePage(Page):
    title = "Welcome"
    subtitle = "Connect GitHub and an AI provider to get started."
    icon = "home"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        column = QVBoxLayout()
        column.setContentsMargins(40, 32, 40, 32)
        column.setSpacing(16)
        column_host = QWidget()
        column_host.setLayout(column)
        column_host.setMaximumWidth(780)

        # ------------------------------------------------------------- hero
        hero = QWidget()
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(0, 0, 0, 0)
        hero_row.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icon_svg("git-branch", "#7c6cff", 34).pixmap(34, 34))
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        hero_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(2)
        title = label("GitHub Manager", "h1")
        hero_text.addWidget(title)
        tagline = label(
            "Write READMEs, manage repositories and run your GitHub admin work — "
            "with an AI assistant that only ever talks about GitHub.",
            "dim",
            wrap=True,
        )
        hero_text.addWidget(tagline)
        hero_row.addLayout(hero_text, 1)
        # Keep the title on the same baseline as the logo.
        hero_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        column.addWidget(hero)

        # ------------------------------------------------------- connect card
        self.connect_card = Card("1 · Connect GitHub", "A personal access token is all we need")
        self.connect_card.setMinimumHeight(170)
        self.connect_card.add(
            label(
                "Create a token at github.com/settings/tokens. Recommended scopes: repo, "
                "read:org, workflow, user. Fine grained tokens work too. The token is "
                "encrypted with Windows DPAPI and never leaves this machine.",
                "dim",
            )
        )
        connect_row = QHBoxLayout()
        self.connect_button = button(
            "Connect GitHub", variant="primary", icon="shield-key", on_click=self.connect_github
        )
        connect_row.addWidget(self.connect_button)
        connect_row.addWidget(
            button("How to create a token", variant="ghost", icon="info", on_click=self.explain_token)
        )
        connect_row.addWidget(spacer())
        self.connect_status = label("", "faint")
        connect_row.addWidget(self.connect_status)
        self.connect_card.add_layout(connect_row)
        column.addWidget(self.connect_card)

        # ----------------------------------------------------------- AI card
        ai_card = Card("2 · Choose an AI provider", "Optional — every AI feature needs it")
        ai_card.add(
            label(
                "The assistant is scoped to GitHub: off-topic requests are blocked before "
                "they reach the model. Pick any OpenAI compatible endpoint, or run a local "
                "model with Ollama for a fully offline setup.",
                "dim",
            )
        )
        providers = FlowWidget(spacing=8)
        for name in PROVIDER_PRESETS:
            providers.add(
                button(
                    name.capitalize(),
                    variant="outline",
                    icon="cpu",
                    on_click=lambda n=name: self.quick_ai(n),
                )
            )
        ai_card.add(providers)
        ai_row = QHBoxLayout()
        ai_row.addWidget(
            button("Open settings", variant="primary", icon="settings", on_click=self.open_settings)
        )
        ai_row.addWidget(button("Skip for now", variant="ghost", on_click=self.skip))
        ai_row.addWidget(spacer())
        self.ai_status = label("", "faint")
        ai_row.addWidget(self.ai_status)
        ai_card.add_layout(ai_row)
        ai_card.setMinimumHeight(190)
        column.addWidget(ai_card)

        # ------------------------------------------------------------ features
        features = Card("What you can do", "Everything here is AI assisted, nothing is automatic")
        features.setMinimumHeight(180)
        grid = QHBoxLayout()
        grid.setSpacing(12)
        for title, text, icon in (
            ("README Studio", "Generate a full README from the live repo, refine it, commit it.", "book"),
            ("Repository admin", "Create, rename, archive, topics, releases, branches.", "folder"),
            ("Issues & PRs", "Draft issues, triage the backlog, reply as a maintainer.", "issue"),
            ("Profile", "Bio, profile README, avatar, organisation overview.", "user"),
        ):
            card = Card(flat=True)
            head = QHBoxLayout()
            head.setSpacing(8)
            icon_label = QLabel()
            icon_label.setPixmap(icon_svg(icon, "#7c6cff", 16).pixmap(16, 16))
            head.addWidget(icon_label)
            head.addWidget(label(title, "h3"))
            head.addStretch(1)
            card.add_layout(head)
            card.add(label(text, "faint", wrap=True))
            grid.addWidget(card, 1)
        features.add_layout(grid)
        column.addWidget(features)

        # A scroll area keeps the cards at full height on short windows.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # QScrollArea centres a widget narrower than its viewport; force the
        # column to the top so the page starts below the top bar.
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(column_host)
        outer.addWidget(self.scroll)

    # ------------------------------------------------------------------ flow
    def on_show(self) -> None:
        if self.ctx.signed_in:
            self.connect_status.setText(f"Connected as {self.ctx.config.get('github_login', '')}")
            self.connect_button.setText("Replace token")

    def connect_github(self) -> None:
        dlg = TokenDialog(self)
        if not dlg.exec():
            return
        token = dlg.values()["token"]
        if not token:
            return
        self.ctx.set_token(token)
        self.connect_status.setText("Verifying…")
        self.connect_button.setEnabled(False)

        from .. import workers

        workers.run(
            "welcome-token",
            self.ctx.github.get_authenticated_user,
            on_result=self._on_ok,
            on_error=self._on_error,
        )

    def _on_ok(self, profile: Any) -> None:
        self.ctx.config.save(github_login=profile.login)
        self.connect_button.setEnabled(True)
        self.connect_status.setText(f"Connected as {profile.login}")
        toast(self.window(), f"Signed in as {profile.login}. Welcome!", "success")
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()

    def _on_error(self, message: str) -> None:
        self.ctx.sign_out()
        self.connect_button.setEnabled(True)
        self.connect_status.setText("Token rejected")
        toast(self.window(), f"Token rejected: {message}", "error")

    def quick_ai(self, provider: str) -> None:
        preset = PROVIDER_PRESETS.get(provider, {})
        self.ctx.config.save(
            ai_provider=provider,
            ai_base_url=preset.get("base_url", ""),
            ai_model=preset.get("model", ""),
        )
        self.ctx.reset_ai()
        self.ai_status.setText(f"{provider} selected")
        self.open_settings()

    def open_settings(self) -> None:
        window = self.window()
        if hasattr(window, "goto_settings"):
            window.goto_settings()

    def skip(self) -> None:
        window = self.window()
        if hasattr(window, "goto_settings"):
            window.goto_settings()

    def explain_token(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl("https://github.com/settings/tokens"))
