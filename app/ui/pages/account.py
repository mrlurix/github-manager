"""Account management: profile, organisation access, security."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from .. import workers
from ..dialogs import DiffDialog, PromptDialog, confirm
from ..markdown import render_markdown
from ..theme import markdown_css
from ..widgets import (
    Avatar,
    Badge,
    Card,
    FlowWidget,
    PageHeader,
    ScrollPage,
    StatTile,
    button,
    icon_button,
    label,
    spacer,
)
from .base import Page


class AccountPage(Page):
    title = "Account"
    subtitle = "Your GitHub profile, organisations and token status."
    icon = "user"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.avatar_url = ""
        self._readme_actions: QHBoxLayout | None = None
        self._readme_source = ""

        # A scroll area is required: the page holds several cards plus a form
        # and would otherwise squash its rows to zero height on small windows.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollPage(self)
        outer.addWidget(self.scroll)

        self.header = PageHeader("Account", "Everything about the signed-in GitHub account")
        self.header.add_action(icon_button("refresh", tooltip="Refresh", on_click=self.refresh))
        self.scroll.add(self.header)

        # ------------------------------------------------------------ identity
        identity = Card()
        row = QHBoxLayout()
        row.setSpacing(16)
        self.avatar = Avatar(72)
        row.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        self.name_label = label("Not connected", "h2")
        self.handle_label = label("", "dim")
        self.bio_label = label("", "dim")
        self.bio_label.setWordWrap(True)
        col.addWidget(self.name_label)
        col.addWidget(self.handle_label)
        col.addWidget(self.bio_label)
        row.addLayout(col, 1)

        avatar_col = QVBoxLayout()
        avatar_col.setSpacing(8)
        avatar_col.addWidget(
            button("Change avatar", variant="outline", icon="upload", on_click=self.change_avatar)
        )
        avatar_col.addWidget(button("Open profile", variant="ghost", icon="external", on_click=self.open_profile))
        row.addLayout(avatar_col)
        identity.add_layout(row)

        stats = QGridLayout()
        stats.setSpacing(12)
        self.tiles: dict[str, StatTile] = {}
        for index, (key, caption, icon) in enumerate(
            (
                ("repos", "Public repos", "folder"),
                ("followers", "Followers", "users"),
                ("following", "Following", "user"),
                ("gists", "Gists", "code"),
            )
        ):
            tile = StatTile("-", caption, icon=icon)
            self.tiles[key] = tile
            stats.addWidget(tile, 0, index)
        identity.add_layout(stats)
        self.scroll.add(identity)

        # -------------------------------------------------------------- fields
        details = Card("Profile details", "Saved directly to your GitHub profile")
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.fields: dict[str, QLineEdit] = {}
        for key, caption, placeholder in (
            ("name", "Name", "Your display name"),
            ("bio", "Bio", "160 characters max"),
            ("company", "Company", "Where you work"),
            ("location", "Location", "City, Country"),
            ("blog", "Website", "https://example.com"),
            ("twitter", "Twitter", "username without @"),
            ("email", "Email", "public email"),
        ):
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            self.fields[key] = field
            form.addRow(label(caption, "dim"), field)
        details.add_layout(form)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        save = button("Save profile", variant="primary", icon="save", on_click=self.save_profile)
        actions.addWidget(save)
        actions.addWidget(button("Revert", variant="ghost", on_click=self._fill_fields))
        actions.addWidget(spacer())
        actions.addWidget(
            button("Improve bio with AI", variant="outline", icon="sparkles", on_click=self.improve_bio)
        )
        actions.addWidget(
            button("Profile README", variant="outline", icon="book", on_click=self.generate_profile_readme)
        )
        details.add_layout(actions)
        self.scroll.add(details)

        # ------------------------------------------------------------- profile readme
        self.readme_card = Card(
            "Profile README",
            "The special <login>/<login> repository renders at the top of your GitHub profile.",
        )
        self.readme_subtitle = self.readme_card.header.layout().itemAt(0).layout().itemAt(1).widget()
        self.readme_view = QTextBrowser()
        self.readme_view.setObjectName("MarkdownView")
        self.readme_view.setMinimumHeight(140)
        self.readme_view.setHtml(
            '<div style="color:#6b7690">Generate a profile README to fill this space.</div>'
        )
        self.readme_card.add(self.readme_view)
        self.scroll.add(self.readme_card)

        # ---------------------------------------------------------------- orgs
        self.org_card = Card("Organisations", "Teams you belong to")
        self.org_flow = FlowWidget(spacing=8)
        self.org_card.add(self.org_flow)
        self.scroll.add(self.org_card)

        # -------------------------------------------------------------- session
        session = Card("Session & security", "How this app talks to GitHub")
        session.add(
            label(
                "The personal access token is encrypted with Windows DPAPI and stored in the "
                "portable data folder next to this executable. It never leaves your machine "
                "except in HTTPS requests to api.github.com and your chosen AI provider.",
                "dim",
            )
        )
        session_actions = QHBoxLayout()
        session_actions.addWidget(button("Replace token", variant="outline", icon="shield-key", on_click=self.replace_token))
        session_actions.addWidget(button("Show data folder", variant="ghost", icon="folder", on_click=self.show_data_folder))
        session_actions.addWidget(spacer())
        session_actions.addWidget(button("Sign out", variant="danger", icon="logout", on_click=self.sign_out))
        session.add_layout(session_actions)
        self.scroll.add(session)

    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self._render_signed_out()
            return
        self.refresh()

    def _apply_css(self) -> None:
        css = markdown_css(self.ctx.config.get("theme", "dark"), self.ctx.config.get("accent", "violet"))
        self.readme_view.document().setDefaultStyleSheet(css)

    def on_theme_changed(self) -> None:
        self._apply_css()

    def _render_signed_out(self) -> None:
        self.name_label.setText("Not connected")
        self.handle_label.setText("Add a token to manage your GitHub account.")
        self.bio_label.setText("")
        self.avatar.set_initials("?")
        for tile in self.tiles.values():
            tile.set_value("-")
        for field in self.fields.values():
            field.clear()
            field.setEnabled(False)

    def refresh(self) -> None:
        if not self.ctx.signed_in:
            self._render_signed_out()
            return
        for field in self.fields.values():
            field.setEnabled(True)
        workers.run(
            "account-profile",
            self.ctx.github.get_authenticated_user,
            on_result=self._on_profile,
            on_error=lambda message: self.notify(message, "error"),
        )
        workers.run(
            "account-orgs",
            self.ctx.github.get_orgs,
            on_result=self._on_orgs,
            on_error=lambda _m: None,
        )
        workers.run(
            "account-rate",
            self.ctx.github.get_rate_limit,
            on_result=self._on_rate,
            on_error=lambda _m: None,
        )

    def _on_profile(self, profile: Any) -> None:
        self.ctx.profile = profile
        self.ctx.config.save(github_login=profile.login)
        self._render_profile(profile)
        workers.run(
            "account-readme",
            lambda: self.ctx.github.get_readme(f"{profile.login}/{profile.login}"),
            on_result=self._on_profile_readme,
            on_error=lambda _m: None,
        )

    def _render_profile(self, profile: Any) -> None:
        self.name_label.setText(profile.name or profile.login)
        self.handle_label.setText(f"@{profile.login}")
        self.bio_label.setText(profile.bio or "No bio yet — use the AI button below to write one.")
        self.avatar.set_initials(profile.login or "?")
        if profile.avatar_url:
            self.avatar.load(profile.avatar_url)
        self.tiles["repos"].set_value(profile.public_repos)
        self.tiles["followers"].set_value(profile.followers)
        self.tiles["following"].set_value(profile.following)
        self.tiles["gists"].set_value(profile.public_gists)
        self._fill_fields()
        self.readme_subtitle.setText(
            f"The {profile.login}/{profile.login} repository renders at the top of your profile."
        )

    def _fill_fields(self) -> None:
        profile = self.ctx.profile
        if not profile:
            return
        self.fields["name"].setText(profile.name or "")
        self.fields["bio"].setText(profile.bio or "")
        self.fields["company"].setText(profile.company or "")
        self.fields["location"].setText(profile.location or "")
        self.fields["blog"].setText(profile.blog or "")
        self.fields["twitter"].setText(profile.twitter or "")
        self.fields["email"].setText(profile.email or "")

    def _on_profile_readme(self, text: str) -> None:
        self._apply_css()
        self._set_readme_source(text)
        self.readme_view.setHtml(f"<style>{markdown_css()}</style>" + render_markdown(text))
        if self._readme_actions is None:
            self._readme_actions = QHBoxLayout()
            self._readme_actions.addWidget(
                button(
                    "Commit to profile README",
                    variant="primary",
                    icon="upload",
                    on_click=lambda: self._commit_profile_readme(self._readme_source),
                )
            )
            self._readme_actions.addWidget(
                button(
                    "Regenerate",
                    variant="outline",
                    icon="refresh",
                    on_click=self.generate_profile_readme,
                )
            )
            self._readme_actions.addWidget(spacer())
            self.readme_card.add_layout(self._readme_actions)

    def _set_readme_source(self, text: str) -> None:
        self._readme_source = text

    def _on_orgs(self, orgs: list[dict[str, Any]]) -> None:
        self.ctx.orgs = orgs
        self.org_flow.clear()
        if not orgs:
            self.org_flow.add(label("You are not a member of any organisation.", "dim"))
            return
        for org in orgs:
            self.org_flow.add(Badge(f"{org.get('login')} · {org.get('role', '')}", "Accent"))

    def _on_rate(self, rate: dict[str, Any]) -> None:
        remaining = rate.get("remaining", "?")
        limit = rate.get("limit", "?")
        reset = rate.get("reset", 0)
        when = ""
        if isinstance(reset, (int, float)) and reset:
            from datetime import datetime, timezone

            when = datetime.fromtimestamp(reset, tz=timezone.utc).strftime(" %H:%M UTC")
        self.notify(f"API rate limit: {remaining}/{limit} remaining{when}", "info")

    # ------------------------------------------------------------ operations
    def save_profile(self) -> None:
        if not self.ctx.signed_in:
            return
        payload = {key: field.text().strip() for key, field in self.fields.items()}
        if len(payload["bio"]) > 160:
            self.notify("GitHub limits the bio to 160 characters.", "warning")
            payload["bio"] = payload["bio"][:160]
        if payload["blog"] and not payload["blog"].startswith(("http://", "https://")):
            payload["blog"] = "https://" + payload["blog"]
        self.notify("Saving profile…")
        workers.run(
            "account-save",
            lambda: self.ctx.github.update_profile(**payload),
            on_result=self._render_profile,
            on_error=lambda message: self.notify(message, "error"),
        )

    def improve_bio(self) -> None:
        if not self.require_ai():
            return
        profile = self.ctx.profile
        if not profile:
            self.notify("Load the profile first.", "warning")
            return
        style = PromptDialog(
            self,
            "Bio style",
            "Pick the tone you want for the new bio options.",
            value="concise",
            placeholder="concise / technical / friendly / bold",
            accept_text="Generate",
        )
        if not style.exec():
            return

        workers.run(
            "account-bio",
            lambda: ai_tasks.profile_bio(
                self.ctx.ai(),
                {
                    "login": profile.login,
                    "name": profile.name,
                    "company": profile.company,
                    "location": profile.location,
                    "blog": profile.blog,
                    "bio": profile.bio,
                },
                style=style.value().strip() or "concise",
            ),
            on_result=self._show_bio,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _show_bio(self, text: str) -> None:
        dlg = DiffDialog(
            self,
            "Bio options",
            text,
            subtitle="Pick the line you like, it is copied into the bio field.",
            accept_text="Use first option",
        )
        if not dlg.exec():
            return
        first = dlg.text().strip().split("\n")[0]
        first = first.lstrip("123. ").strip().strip("*")
        if first:
            self.fields["bio"].setText(first[:160])
            self.notify("Bio updated locally — press Save profile to publish.", "success")

    def generate_profile_readme(self) -> None:
        if not self.require_ai():
            return
        profile = self.ctx.profile
        if not profile:
            self.notify("Load the profile first.", "warning")
            return
        self.notify("Generating profile README…")

        def task() -> Any:
            repos = self.ctx.repos or self.ctx.github.list_repos(sort="stars")
            return ai_tasks.profile_readme(
                self.ctx.ai(),
                {
                    "login": profile.login,
                    "name": profile.name,
                    "location": profile.location,
                    "bio": profile.bio,
                    "blog": profile.blog,
                },
                repos,
            )

        workers.run(
            "account-profile-readme",
            task,
            on_result=self._show_profile_readme,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _show_profile_readme(self, text: str) -> None:
        self._apply_css()
        self._set_readme_source(text)
        self.readme_view.setHtml(f"<style>{markdown_css()}</style>" + render_markdown(text))
        self.notify("Profile README drafted. Commit it to publish.", "success")

    def _commit_profile_readme(self, text: str) -> None:
        profile = self.ctx.profile
        if not profile or not text.strip():
            return
        repo_name = f"{profile.login}/{profile.login}"
        if not confirm(
            self,
            f"Commit to {repo_name}?",
            "This creates or updates the profile README repository and makes it visible "
            "on your GitHub profile page.",
            accept_text="Commit",
        ):
            return
        self.notify("Committing profile README…")

        def task() -> Any:
            gh = self.ctx.github
            try:
                gh.get_repo(repo_name)
            except Exception:
                gh.create_repo(
                    repo_name,
                    description=f"Profile README for {profile.login}",
                    private=False,
                    auto_init=True,
                )
            return gh.commit_readme(repo_name, text, "docs: update profile README")

        workers.run(
            "account-commit-readme",
            task,
            on_result=lambda _r: self.notify(f"Profile README published to {repo_name}.", "success"),
            on_error=lambda message: self.notify(message, "error"),
        )

    #: GitHub's avatar endpoint accepts at most 1 MB.
    AVATAR_MAX_BYTES = 1024 * 1024
    AVATAR_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    def change_avatar(self) -> None:
        if not self.ctx.signed_in:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an avatar",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp)",
        )
        if not path:
            return

        source = Path(path)
        suffix = source.suffix.lower()
        mime = self.AVATAR_TYPES.get(suffix)
        if mime is None:
            self.notify("Choose a PNG, JPEG, GIF or WebP image.", "warning")
            return
        try:
            size = source.stat().st_size
        except OSError as exc:
            self.notify(f"Could not read the file: {exc}", "error")
            return
        if size == 0:
            self.notify("That file is empty.", "warning")
            return
        if size > self.AVATAR_MAX_BYTES:
            self.notify(
                f"That image is {size // 1024} KB. GitHub accepts at most 1 MB.", "warning"
            )
            return
        try:
            data = source.read_bytes()
        except OSError as exc:
            self.notify(f"Could not read the file: {exc}", "error")
            return

        self.notify("Uploading avatar…")

        def task() -> Any:
            # Uses the shared client so the token never has to be handled here.
            client = self.ctx.github
            return client.upload_avatar(data, mime)

        workers.run(
            "account-avatar",
            task,
            on_result=self._on_avatar_uploaded,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_avatar_uploaded(self, payload: dict[str, Any]) -> None:
        self.avatar.load(str(payload.get("avatar_url", "")))
        if self.ctx.profile is not None:
            self.ctx.profile.avatar_url = str(payload.get("avatar_url", ""))
        self.notify("Avatar updated.", "success")

    def open_profile(self) -> None:
        import webbrowser

        if self.ctx.profile:
            webbrowser.open(self.ctx.profile.html_url)

    def replace_token(self) -> None:
        from ..dialogs import TokenDialog

        dlg = TokenDialog(self)
        if not dlg.exec():
            return
        token = dlg.values()["token"]
        if not token:
            return
        self._connect(token)

    def sign_out(self) -> None:
        if not confirm(
            self,
            "Sign out?",
            "The stored token is deleted from the portable data folder. You can add it "
            "again at any time.",
            accept_text="Sign out",
            danger=True,
        ):
            return
        self.ctx.sign_out()
        self._render_signed_out()
        self.notify("Signed out.", "success")
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()

    def show_data_folder(self) -> None:
        from ...config import data_dir, open_path

        open_path(data_dir())

    def _connect(self, token: str) -> None:
        self.ctx.set_token(token)
        self.notify("Verifying token…")
        workers.run(
            "account-verify",
            self.ctx.github.get_authenticated_user,
            on_result=lambda profile: (
                self.notify(f"Signed in as {profile.login}.", "success"),
                self.refresh(),
                self._maybe_sync_auth(),
            ),
            on_error=lambda message: (
                self.notify(f"Could not verify the token: {message}", "error"),
                self.ctx.sign_out(),
            ),
        )

    def _maybe_sync_auth(self) -> None:
        window = self.window()
        if hasattr(window, "refresh_auth_state"):
            window.refresh_auth_state()
