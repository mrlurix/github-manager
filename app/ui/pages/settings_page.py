"""Settings: appearance, AI provider, GitHub token and data."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...config import APP_NAME, APP_VERSION, data_dir, open_path
from ...core.ai_api import PROVIDER_PRESETS
from .. import workers
from ..dialogs import TokenDialog
from ..widgets import (
    Badge,
    Card,
    PageHeader,
    ScrollPage,
    button,
    label,
    spacer,
)
from .base import Page


class SettingsPage(Page):
    title = "Settings"
    subtitle = "Appearance, AI provider and credentials."
    icon = "settings"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self._syncing_model = False

        # Several cards plus two forms: without a scroll area the form rows are
        # squeezed to zero height on shorter windows.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollPage(self)
        outer.addWidget(self.scroll)

        self.header = PageHeader("Settings", "Everything is stored locally in the portable data folder")
        self.scroll.add(self.header)

        # ---------------------------------------------------------- appearance
        # No accent control. There were six, and every one of them now resolves
        # to the same value - a row of identical choices is worse than no row,
        # because it invites the reader to look for a difference that is not
        # there. The app is monochrome; that is the setting, and it is not a
        # preference.
        look = Card("Appearance", "Theme and scaling")
        look_form = QFormLayout()
        look_form.setSpacing(10)

        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.currentTextChanged.connect(self._save_appearance)
        look_form.addRow(label("Theme", "dim"), self.theme)

        self.font = QComboBox()
        from PySide6.QtGui import QFontDatabase

        families = [f for f in QFontDatabase.families() if not f.startswith("@")]
        self.font.addItems(["(system default)"] + sorted(families))
        self.font.currentTextChanged.connect(self._save_appearance)
        look_form.addRow(label("Font", "dim"), self.font)

        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.8, 1.6)
        self.scale.setSingleStep(0.05)
        self.scale.setSuffix(" ×")
        self.scale.valueChanged.connect(self._save_appearance)
        look_form.addRow(label("UI scale", "dim"), self.scale)

        look.add_layout(look_form)
        self.scroll.add(look)

        # ------------------------------------------------------------------ AI
        ai = Card(
            "AI provider",
            "Any OpenAI compatible endpoint works: OpenAI, OpenRouter, Groq, Together, "
            "Ollama, LM Studio or your own gateway.",
        )
        provider_row = QHBoxLayout()
        provider_row.setSpacing(8)
        self.provider = QComboBox()
        self.provider.addItems(list(PROVIDER_PRESETS))
        self.provider.currentTextChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self.provider)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumWidth(280)
        self.model_combo.setToolTip("Pick a model from the provider list, or type one")
        self.model_combo.editTextChanged.connect(self._on_model_pick)
        self.model_combo.currentTextChanged.connect(self._on_model_pick)
        provider_row.addWidget(self.model_combo, 1)
        list_models = button("List models", variant="outline", icon="download", on_click=self.list_models)
        provider_row.addWidget(list_models)
        ai.add_layout(provider_row)

        ai_form = QFormLayout()
        ai_form.setSpacing(10)

        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.openai.com/v1")
        ai_form.addRow(label("Base URL", "dim"), self.base_url)

        self.model = QLineEdit()
        self.model.setPlaceholderText("gpt-4o-mini")
        ai_form.addRow(label("Model", "dim"), self.model)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Paste the API key (stored encrypted)")
        self.api_key.editingFinished.connect(self._save_key)
        ai_form.addRow(label("API key", "dim"), self.api_key)

        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.5)
        self.temperature.setSingleStep(0.05)
        self.temperature.valueChanged.connect(self._save_ai)
        ai_form.addRow(label("Temperature", "dim"), self.temperature)

        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(256, 32000)
        self.max_tokens.setSingleStep(256)
        self.max_tokens.valueChanged.connect(self._save_ai)
        ai_form.addRow(label("Max tokens", "dim"), self.max_tokens)

        self.timeout = QSpinBox()
        self.timeout.setRange(10, 600)
        self.timeout.setSuffix(" s")
        self.timeout.valueChanged.connect(self._save_ai)
        ai_form.addRow(label("Timeout", "dim"), self.timeout)

        self.stream = QComboBox()
        self.stream.addItems(["Streaming responses", "Single response"])
        self.stream.currentIndexChanged.connect(self._save_ai)
        ai_form.addRow(label("Transport", "dim"), self.stream)

        ai.add_layout(ai_form)

        ai_actions = QHBoxLayout()
        ai_actions.setSpacing(8)
        save_ai = button("Save", variant="primary", icon="save", on_click=self._save_ai_clicked)
        ai_actions.addWidget(save_ai)
        test = button("Test connection", variant="outline", icon="shield-check", on_click=self.test_connection)
        ai_actions.addWidget(test)
        ai_actions.addWidget(button("Clear key", variant="ghost", on_click=self._clear_key))
        ai_actions.addWidget(spacer())
        self.ai_status = label("", "faint")
        ai_actions.addWidget(self.ai_status)
        ai.add_layout(ai_actions)
        self.scroll.add(ai)

        # --------------------------------------------------------------- GitHub
        gh = Card("GitHub account", "The token used for every GitHub API call")
        self.gh_status = QWidget()
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        self.gh_badge = Badge("Not connected", "Danger")
        status_row.addWidget(self.gh_badge)
        self.gh_login = label("", "dim")
        status_row.addWidget(self.gh_login)
        status_row.addWidget(spacer())
        status_row.addWidget(button("Connect / replace", variant="primary", icon="shield-key", on_click=self.connect_github))
        status_row.addWidget(button("Sign out", variant="ghost", icon="logout", on_click=self.sign_out))
        self.gh_status.setLayout(status_row)
        gh.add(self.gh_status)

        note = label(
            "Fine grained tokens work too. Recommended permissions: Contents (read & write), "
            "Issues, Pull requests, Metadata (always on), and Delete repository only if you "
            "want the destructive action.",
            "faint",
        )
        note.setWordWrap(True)
        gh.add(note)
        self.scroll.add(gh)

        # ------------------------------------------------------------ assistant
        guard = Card("Assistant scope", "The AI is restricted to GitHub topics")
        guard.add(
            label(
                "GitHub Manager blocks requests that fall outside GitHub before they reach "
                "the model, and discards answers that drift off-topic. The assistant never "
                "runs commands, never writes files on its own and only talks to the GitHub "
                "API.",
                "dim",
            )
        )
        scope_chips = QHBoxLayout()
        for name in ("README", "Repositories", "Issues & PRs", "Commits & branches", "Actions & CI", "Releases", "Profiles", "Tokens & security"):
            scope_chips.addWidget(Badge(name, "Accent"))
        scope_chips.addWidget(spacer())
        guard.add_layout(scope_chips)
        self.scroll.add(guard)

        # ----------------------------------------------------------------- data
        data = Card("Data & about", "Portable storage, updates and diagnostics")
        self.about = QTextBrowser()
        self.about.setObjectName("MarkdownView")
        self.about.setMinimumHeight(120)
        data.add(self.about)

        data_actions = QHBoxLayout()
        data_actions.setSpacing(8)
        data_actions.addWidget(button("Open data folder", variant="outline", icon="folder", on_click=lambda: open_path(data_dir())))
        data_actions.addWidget(button("Reset appearance", variant="ghost", on_click=self.reset_appearance))
        data_actions.addWidget(button("Erase all local data", variant="danger", icon="trash", on_click=self.erase_all))
        data_actions.addWidget(spacer())
        data.add_layout(data_actions)
        self.scroll.add(data)


    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        s = self.ctx.config.settings
        self.theme.setCurrentText(s.theme)
        self.font.setCurrentText(s.font_family or "(system default)")
        self.scale.setValue(s.ui_scale)

        self.provider.setCurrentText(s.ai_provider)
        self.base_url.setText(s.ai_base_url)
        self.model.setText(s.ai_model)
        self.api_key.setText(self.ctx.api_key)
        self.api_key.setPlaceholderText(
            "Key stored securely" if self.ctx.secrets.has("ai_api_key") else "Paste the API key (stored encrypted)"
        )
        self.temperature.setValue(s.ai_temperature)
        self.max_tokens.setValue(s.ai_max_tokens)
        self.timeout.setValue(s.ai_timeout)
        self.stream.setCurrentIndex(0 if s.ai_stream else 1)

        login = self.ctx.config.get("github_login", "")
        if self.ctx.signed_in:
            self.gh_badge.setText(f"Connected as {login}" if login else "Connected")
            self.gh_badge.set_kind("Success")
            self.gh_login.setText("Token encrypted locally with Windows DPAPI")
        else:
            self.gh_badge.setText("Not connected")
            self.gh_badge.set_kind("Danger")
            self.gh_login.setText("Add a personal access token to enable GitHub features")

        self._render_about()

    def _render_about(self) -> None:
        from ...config import app_root

        self.about.setHtml(
            f"""
            <p><b>{APP_NAME}</b> v{APP_VERSION} — portable GitHub client with an AI assistant.</p>
            <p><b>Executable folder:</b> {app_root()}<br>
               <b>Data folder:</b> {data_dir()}</p>
            <p><b>Keyboard:</b> Ctrl+1..6 switch pages · Ctrl+R refresh · Ctrl+K AI assistant ·
               Ctrl+N new repository · Ctrl+, settings · Ctrl+Q quit</p>
            """
        )

    # ------------------------------------------------------------ appearance
    def _save_appearance(self) -> None:
        family = self.font.currentText()
        self.ctx.config.save(
            theme=self.theme.currentText(),
            # The accent stays in settings.json for an older file to keep
            # round-tripping, but nothing reads it any more: the palette has no
            # accent. Left as-is rather than cleared, because writing a default
            # over it would mean this function quietly edits a key it no longer
            # owns.
            font_family="" if family == "(system default)" else family,
            ui_scale=self.scale.value(),
        )
        window = self.window()
        if hasattr(window, "apply_theme"):
            window.apply_theme()

    def reset_appearance(self) -> None:
        self.ctx.config.save(theme="dark", font_family="", ui_scale=1.0)
        self.on_show()
        window = self.window()
        if hasattr(window, "apply_theme"):
            window.apply_theme()
        self.notify("Appearance reset.", "success")

    # -------------------------------------------------------------------- AI
    def _on_provider_changed(self, name: str) -> None:
        preset = PROVIDER_PRESETS.get(name, {})
        base = preset.get("base_url", "")
        model = preset.get("model", "")
        if base:
            self.base_url.setText(base)
        if model:
            self.model.setText(model)
        self.ai_status.setText(preset.get("hint", ""))
        self._sync_model_combo()

    def _sync_model_combo(self) -> None:
        """Keep the model picker and the model field in sync, without loops."""
        current = self.model.text().strip()
        self._syncing_model = True
        try:
            if self.model_combo.currentText().strip() != current:
                self.model_combo.setCurrentText(current or "(set a model)")
        finally:
            self._syncing_model = False

    def _on_model_pick(self, text: str) -> None:
        if self._syncing_model:
            return
        text = (text or "").strip()
        if not text or text == "(set a model)":
            return
        if text != self.model.text().strip():
            self.model.setText(text)
        self.ctx.config.save(ai_model=text)
        self.ctx.reset_ai()

    def _save_key(self) -> None:
        text = self.api_key.text().strip()
        if text == self.ctx.api_key:
            return
        self.ctx.set_api_key(text)
        self.api_key.setText(text)
        self.api_key.setPlaceholderText(
            "Key stored securely" if self.ctx.secrets.has("ai_api_key") else "Paste the API key (stored encrypted)"
        )
        self.notify("API key saved." if text else "API key cleared.", "success")
        self._render_about()

    def _clear_key(self) -> None:
        self.ctx.set_api_key("")
        self.api_key.clear()
        self.api_key.setPlaceholderText("Paste the API key (stored encrypted)")
        self.notify("API key removed.", "info")

    def _save_ai(self) -> None:
        self._sync_model_combo()
        self.ctx.config.save(
            ai_provider=self.provider.currentText(),
            ai_base_url=self.base_url.text().strip().rstrip("/"),
            ai_model=self.model.text().strip(),
            ai_temperature=self.temperature.value(),
            ai_max_tokens=self.max_tokens.value(),
            ai_timeout=self.timeout.value(),
            ai_stream=self.stream.currentIndex() == 0,
        )
        self.ctx.reset_ai()

    def _save_ai_clicked(self) -> None:
        self._save_key()
        self._save_ai()
        self.notify("AI settings saved.", "success")

    def list_models(self) -> None:
        self._save_ai_clicked()
        if not self.ctx.config.get("ai_base_url"):
            self.notify("Set a base URL first.", "warning")
            return
        self.ai_status.setText("Fetching model list…")

        workers.run(
            "settings-models",
            lambda: self.ctx.ai().list_models(),
            on_result=self._on_models,
            on_error=lambda message: self._on_test_error(message),
        )

    def _on_models(self, models: list[str]) -> None:
        self.model_combo.clear()
        current = self.model.text().strip()
        for name in models:
            self.model_combo.addItem(name)
        if current in models:
            self.model_combo.setCurrentText(current)
        elif models:
            self.model_combo.setCurrentIndex(0)
            self.model.setText(models[0])
            self._save_ai()
        self.ai_status.setText(f"{len(models)} models available")
        self.notify(f"Loaded {len(models)} models.", "success")

    def test_connection(self) -> None:
        self._save_ai_clicked()
        self.ai_status.setText("Testing…")

        workers.run(
            "settings-test",
            self._ping,
            on_result=lambda text: (
                self.ai_status.setText(text),
                self.notify(text, "success"),
            ),
            on_error=lambda message: self._on_test_error(message),
        )

    def _ping(self) -> str:
        from ...core.ai_api import ChatMessage

        client = self.ctx.ai()
        answer = client.chat(
            [
                ChatMessage("system", "Reply with the single word: ready"),
                ChatMessage("user", "connection check"),
            ],
            max_tokens=16,
        )
        if not isinstance(answer, str):
            answer = "".join(answer)
        return f"Connected · {client.model} replied: {answer.strip()[:40]}"

    def _on_test_error(self, message: str) -> None:
        self.ai_status.setText(f"Failed: {message[:120]}")
        self.notify(message, "error")

    # ---------------------------------------------------------------- GitHub
    def connect_github(self) -> None:
        dlg = TokenDialog(self)
        if not dlg.exec():
            return
        token = dlg.values()["token"]
        if not token:
            return
        self.ctx.set_token(token)
        self.ai_status.setText("Verifying token…")
        self.gh_badge.setText("Verifying…")
        self.gh_badge.set_kind("Warning")
        workers.run(
            "settings-token",
            self.ctx.github.get_authenticated_user,
            on_result=self._on_token_ok,
            on_error=self._on_token_error,
        )

    def _on_token_ok(self, profile: Any) -> None:
        self.ctx.config.save(github_login=profile.login)
        self.notify(f"Signed in as {profile.login}.", "success")
        self.on_show()
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()

    def _on_token_error(self, message: str) -> None:
        self.ctx.sign_out()
        self.notify(f"Token rejected: {message}", "error")
        self.on_show()

    def sign_out(self) -> None:
        self.ctx.sign_out()
        self.notify("Signed out.", "info")
        self.on_show()
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()

    # ------------------------------------------------------------------- data
    def erase_all(self) -> None:
        from ..dialogs import confirm

        if not confirm(
            self,
            "Erase all local data?",
            "This deletes the stored GitHub token, the AI API key and every preference "
            "from the data folder. The app will return to a fresh state.",
            accept_text="Erase everything",
            danger=True,
        ):
            return
        self.ctx.secrets.clear()
        self.ctx.sign_out()
        from ...config import Settings

        self.ctx.config.settings = Settings()
        self.ctx.config.save()
        self.ctx.repos = []
        self.ctx.repos_loaded = False
        self.ctx.profile = None
        self.notify("All local data erased.", "success")
        self.on_show()
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()
