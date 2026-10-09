"""Dashboard: profile snapshot, metrics and AI powered insights."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from .. import workers
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
    icon_svg,
    label,
    spacer,
)
from .base import Page

def _clear_layout(layout: Any) -> None:
    """Remove and destroy every widget currently inside ``layout``."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


EVENT_ICONS = {
    "PushEvent": "git-branch",
    "CreateEvent": "folder",
    "IssuesEvent": "issue",
    "IssueCommentEvent": "chat",
    "PullRequestEvent": "pull",
    "PullRequestReviewEvent": "pull",
    "WatchEvent": "star",
    "ForkEvent": "fork",
    "ReleaseEvent": "release",
    "PublicEvent": "dot",
}


class DashboardPage(Page):
    title = "Dashboard"
    subtitle = "Everything about your GitHub presence, at a glance."
    icon = "home"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.scroll = ScrollPage(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)

        # ---------------------------------------------------------- profile
        self.header = PageHeader("Dashboard", "Connect a GitHub token to get started.")
        refresh = icon_button("refresh", tooltip="Refresh data (Ctrl+R)", on_click=self.refresh)
        self.header.add_action(refresh)
        self.scroll.add(self.header)

        # The identity block and the meta badges are stacked in a column so the
        # badges always start at the card's left margin.
        self.profile_card = Card()
        profile_host = QWidget()
        profile_col = QVBoxLayout(profile_host)
        profile_col.setContentsMargins(0, 0, 0, 0)
        profile_col.setSpacing(10)

        identity = QHBoxLayout()
        identity.setContentsMargins(0, 0, 0, 0)
        identity.setSpacing(14)
        self.avatar = Avatar(56)
        identity.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)
        self.name_label = label("Not connected", "h2")
        self.handle_label = label("", "dim")
        self.bio_label = label("", "dim", wrap=True)
        info.addWidget(self.name_label)
        info.addWidget(self.handle_label)
        info.addWidget(self.bio_label)
        identity.addLayout(info, 1)
        profile_col.addLayout(identity)

        self.meta_flow = FlowWidget(spacing=6)
        profile_col.addWidget(self.meta_flow)
        self.profile_card.add(profile_host)
        self.scroll.add(self.profile_card)

        # ----------------------------------------------------------- metrics
        self.tiles: dict[str, StatTile] = {}
        tiles_card = Card("At a glance", "Live numbers from the GitHub API")
        grid = QGridLayout()
        grid.setSpacing(12)
        specs = [
            ("repos", "Repositories", "folder", ""),
            ("stars", "Stars earned", "star", ""),
            ("followers", "Followers", "users", ""),
            ("following", "Following", "user", ""),
            ("orgs", "Organisations", "shield", ""),
            ("private", "Private repos", "lock", "text_faint"),
        ]
        for index, (key, caption, icon, color) in enumerate(specs):
            tile = StatTile("-", caption, icon=icon, accent=color)
            tile.clicked.connect(lambda: self.notify("Tip: open Repositories for the full list."))
            self.tiles[key] = tile
            grid.addWidget(tile, index // 3, index % 3)
        tiles_card.add_layout(grid)
        self.scroll.add(tiles_card)

        # ------------------------------------------------------- two columns
        columns = QHBoxLayout()
        columns.setSpacing(16)

        # repositories
        self.repos_card = Card("Top repositories", "Sorted by stars")
        self.repos_flow = FlowWidget(spacing=8)
        self.repos_card.add(self.repos_flow)
        repos_card_actions = QHBoxLayout()
        repos_card_actions.addStretch(1)
        open_readme = button("README studio", variant="ghost", icon="wand", on_click=self._goto_readme)
        repos_card_actions.addWidget(open_readme)
        self.repos_card.add_layout(repos_card_actions)
        columns.addWidget(self.repos_card, 3)

        # activity
        self.activity_card = Card("Recent activity", "Public events")
        self.activity_host = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_host)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setSpacing(8)
        self.activity_card.add(self.activity_host)
        columns.addWidget(self.activity_card, 2)
        self.scroll.add_layout(columns)

        # ------------------------------------------------------- AI insights
        self.ai_card = Card(
            "AI profile review",
            "The assistant reads your profile and repository metadata, then suggests "
            "concrete GitHub improvements.",
        )
        ai_actions = QHBoxLayout()
        ai_actions.setSpacing(8)
        self.ai_button = button(
            "Analyse my GitHub",
            variant="primary",
            icon="sparkles",
            on_click=self.run_insights,
        )
        ai_actions.addWidget(self.ai_button)
        self.ai_body_button = button(
            "Improve my bio",
            variant="outline",
            icon="edit",
            on_click=self.improve_bio,
        )
        ai_actions.addWidget(self.ai_body_button)
        ai_actions.addWidget(spacer())
        self.ai_hint = label("", "faint")
        ai_actions.addWidget(self.ai_hint)
        self.ai_card.add_layout(ai_actions)

        self.ai_view = QTextBrowser()
        self.ai_view.setObjectName("MarkdownView")
        self.ai_view.setMinimumHeight(150)
        self.ai_view.setHtml(
            '<div style="color:#737373">Connect the AI provider in Settings to get '
            "a personalised review of your GitHub presence.</div>"
        )
        self.ai_card.add(self.ai_view)
        self.scroll.add(self.ai_card)

        # -------------------------------------------------------- quick start
        self.quick = Card("Quick start", "Common GitHub jobs, one click away")
        self.quick_flow = FlowWidget(spacing=8)
        for text, icon, handler in (
            ("Generate a README", "wand", self._goto_readme),
            ("Manage repositories", "folder", self._goto_repos),
            ("Triage issues", "issue", self._goto_issues),
            ("Ask the assistant", "chat", self._goto_assistant),
        ):
            self.quick_flow.add(button(text, variant="outline", icon=icon, on_click=handler))
        self.quick.add(self.quick_flow)
        self.scroll.add(self.quick)

        self.scroll.add_stretch()
        self._nav = None

    # ------------------------------------------------------------------ nav
    def set_navigator(self, nav: Any) -> None:
        self._nav = nav

    def _goto(self, index: int) -> None:
        if self._nav:
            self._nav.setCurrentIndex(index)

    def _goto_readme(self) -> None:
        self._goto(1)

    def _goto_repos(self) -> None:
        self._goto(2)

    def _goto_issues(self) -> None:
        self._goto(3)

    def _goto_assistant(self) -> None:
        self._goto(4)

    # --------------------------------------------------------------- loading
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self._render_signed_out()
            return
        if self.ctx.profile is not None:
            self._render_profile()
        self.refresh()

    def _render_signed_out(self) -> None:
        self.header.set_subtitle("Connect a GitHub token to load your dashboard.")
        self.name_label.setText("Not connected")
        self.handle_label.setText("Open Settings to add a personal access token.")
        self.bio_label.setText("")
        self.avatar.set_initials("?")
        for tile in self.tiles.values():
            tile.set_value("-")

    def refresh(self) -> None:
        if not self.ctx.signed_in:
            self._render_signed_out()
            return
        self.busy(True)
        workers.run(
            "dash-profile",
            self.ctx.github.get_authenticated_user,
            on_result=self._on_profile,
            on_error=self._on_error,
            on_finish=lambda: self.busy(False),
        )
        workers.run(
            "dash-repos",
            lambda: self.ctx.github.list_repos(sort="updated"),
            on_result=self._on_repos,
            on_error=self._on_error,
            on_finish=lambda: self.busy(False),
        )

    def _on_error(self, message: str) -> None:
        self.notify(message, "error")
        self.busy(False)

    def _on_profile(self, profile: Any) -> None:
        self.ctx.profile = profile
        self.ctx.config.save(github_login=profile.login)
        self._render_profile()
        workers.run(
            "dash-events",
            lambda: self.ctx.github.get_events(profile.login),
            on_result=self._on_events,
            on_error=lambda _m: None,
        )
        workers.run(
            "dash-orgs",
            self.ctx.github.get_orgs,
            on_result=self._on_orgs,
            on_error=lambda _m: None,
        )

    def _on_repos(self, repos: list[Any]) -> None:
        self.ctx.repos = repos
        self.ctx.repos_loaded = True
        self.ctx.config.save(last_repo=repos[0].full_name if repos else "")
        self._render_repos()
        self._render_tiles()

    def _on_orgs(self, orgs: list[dict[str, Any]]) -> None:
        self.ctx.orgs = orgs
        self._render_meta()
        self._render_tiles()

    def _on_events(self, events: list[dict[str, Any]]) -> None:
        self._render_activity(events)

    # -------------------------------------------------------------- rendering
    def _render_profile(self) -> None:
        profile = self.ctx.profile
        if not profile:
            return
        self.name_label.setText(profile.name or profile.login)
        self.handle_label.setText(
            f"@{profile.login}"
            + (f" · {profile.followers} followers · {profile.following} following" if profile.login else "")
        )
        self.bio_label.setText(profile.bio or "No bio set. Add one so people know what you build.")
        self.avatar.set_initials(profile.login or "?")
        if profile.avatar_url:
            self.avatar.load(profile.avatar_url)
        self.header.set_subtitle(f"Signed in as {profile.login} · data refreshes on demand.")
        self._render_meta()
        self._render_tiles()

    def _render_meta(self) -> None:
        self.meta_flow.clear()
        profile = self.ctx.profile
        if not profile:
            return
        badges: list[tuple[str, str]] = []
        if profile.company:
            badges.append((profile.company, ""))
        if profile.location:
            badges.append((profile.location, ""))
        if profile.blog:
            badges.append((profile.blog.replace("https://", ""), "Accent"))
        if profile.twitter:
            badges.append((f"@{profile.twitter}", ""))
        if profile.plan:
            badges.append((f"{profile.plan} plan", "Success"))
        if not badges:
            badges.append(("No company, location or website set", ""))
        for text, kind in badges:
            self.meta_flow.add(Badge(text, kind))

    def _render_tiles(self) -> None:
        profile = self.ctx.profile
        repos = self.ctx.repos
        if profile:
            total_stars = sum(r.stars for r in repos) if repos else 0
            private = getattr(profile, "owned_private_repos", 0) or 0
            self.tiles["repos"].set_value(len(repos) if repos else profile.public_repos)
            self.tiles["stars"].set_value(f"{total_stars:,}" if repos else "-")
            self.tiles["followers"].set_value(f"{profile.followers:,}")
            self.tiles["following"].set_value(f"{profile.following:,}")
            self.tiles["orgs"].set_value(len(self.ctx.orgs))
            self.tiles["private"].set_value(private if private else "-")

    def _render_repos(self) -> None:
        self.repos_flow.clear()
        repos = sorted(self.ctx.repos, key=lambda r: -r.stars)[:6]
        if not repos:
            self.repos_flow.add(label("No repositories loaded yet.", "dim"))
            return
        for repo in repos:
            self.repos_flow.add(RepoChip(repo))

    def _render_activity(self, events: list[dict[str, Any]]) -> None:
        _clear_layout(self.activity_layout)
        if not events:
            self.activity_layout.addWidget(label("No recent public activity.", "dim"))
            return
        for event in events[:12]:
            row = QHBoxLayout()
            row.setSpacing(9)
            icon = QLabel()
            icon.setPixmap(icon_svg(EVENT_ICONS.get(event.get("type", ""), "dot"), "accent", 16).pixmap(16, 16))
            row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            text = describe_event(event)
            lab = label(text, "dim")
            lab.setWordWrap(True)
            row.addWidget(lab, 1)
            holder = QWidget()
            holder.setLayout(row)
            self.activity_layout.addWidget(holder)
        self.activity_layout.addStretch(1)

    # ------------------------------------------------------------- AI actions
    def run_insights(self) -> None:
        if not self.require_ai():
            return
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first so the AI has real data.", "warning")
            return
        self.ai_button.setEnabled(False)
        self.ai_button.setText("Analysing...")
        self.ai_view.setHtml('<div style="color:#a1a1a1">Reading profile, repositories and topics…</div>')

        def build() -> Any:
            profile = self.ctx.profile or self.ctx.github.get_authenticated_user()
            repos = self.ctx.repos or self.ctx.github.list_repos(sort="updated")
            ctx_lines = [
                f"Login: {profile.login}",
                f"Name: {profile.name}",
                f"Bio: {profile.bio or '(empty)'}",
                f"Company: {profile.company or '(empty)'}",
                f"Location: {profile.location or '(empty)'}",
                f"Website: {profile.blog or '(empty)'}",
                f"Twitter: {profile.twitter or '(empty)'}",
                f"Followers: {profile.followers}, Following: {profile.following}",
                "",
                "Repositories:",
            ]
            for repo in repos[:20]:
                ctx_lines.append(
                    f"- {repo.full_name}: {repo.description or '(no description)'} | "
                    f"topics={','.join(repo.topics) or 'none'} | lang={repo.language or 'n/a'} | "
                    f"stars={repo.stars} | readme={'yes' if repo.description else 'unknown'}"
                )
            task = (
                "Review this developer's GitHub presence and give a concrete improvement plan.\n"
                "Structure the answer in markdown with these sections:\n"
                "1. Profile review (bio, avatar, links, name)\n"
                "2. Repository portfolio (descriptions, topics, naming consistency)\n"
                "3. README quality issues worth fixing first\n"
                "4. Visibility and community actions (issues, discussions, releases)\n"
                "5. Top 5 actions for the next week, ordered by impact\n"
                "Be specific and reference repository names. No generic advice."
            )
            return ai_tasks.assistant_reply(self.ctx.ai(), [], task, context="\n".join(ctx_lines), stream=True)

        workers.run(
            "dash-insights",
            build,
            on_progress=self._on_ai_chunk,
            on_result=self._on_ai_done,
            on_error=self._on_ai_error,
            on_finish=lambda: self._reset_ai_button(),
        )

    def improve_bio(self) -> None:
        if not self.require_ai():
            return
        profile = self.ctx.profile
        if not profile:
            self.notify("Load the profile first.", "warning")
            return
        self.ai_body_button.setEnabled(False)
        workers.run(
            "dash-bio",
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
            ),
            on_result=self._on_bio,
            on_error=self._on_ai_error,
            on_finish=lambda: self.ai_body_button.setEnabled(True),
        )

    def _on_bio(self, text: str) -> None:
        self.ai_view.setHtml(f"<style>{markdown_css()}</style>" + _md(text))

    def _on_ai_chunk(self, chunk: str) -> None:
        current = getattr(self, "_ai_buffer", "") + chunk
        self._ai_buffer = current
        self.ai_view.setHtml(f"<style>{markdown_css()}</style>" + _md(current))

    def _on_ai_done(self, text: str) -> None:
        self.ai_view.setHtml(f"<style>{markdown_css()}</style>" + _md(text))

    def _on_ai_error(self, message: str) -> None:
        # Read from the palette rather than written out. Red for an error is
        # information, so it stays - but it has to be the same red as every other
        # error, and this was the one place in the app still carrying a hex that
        # happened to look right.
        from ..theme import build_palette

        colour = build_palette(self.ctx.config.get("theme", "dark"))["danger"]
        self.ai_view.setHtml(f'<div style="color:{colour}">{message}</div>')
        self.notify(message, "error")

    def _reset_ai_button(self) -> None:
        self.ai_button.setEnabled(True)
        self.ai_button.setText("Analyse my GitHub")
        self._ai_buffer = ""


class RepoChip(QWidget):
    """Small repository tile used on the dashboard."""

    def __init__(self, repo: Any) -> None:
        super().__init__()
        self.setObjectName("Inset")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(190)
        self.setMaximumWidth(280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        name = label(repo.name, "")
        name.setStyleSheet("font-weight:600;")
        top.addWidget(name)
        top.addStretch(1)
        stars = QLabel()
        stars.setPixmap(icon_svg("star", "warning", 13).pixmap(13, 13))
        stars.setToolTip(f"{repo.stars} stars")
        top.addWidget(stars)
        count = label(str(repo.stars), "faint")
        top.addWidget(count)
        layout.addLayout(top)

        desc = label(repo.description or "No description yet", "faint")
        desc.setWordWrap(True)
        desc.setFixedHeight(34)
        desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(desc)

        meta = QHBoxLayout()
        meta.setSpacing(6)
        if repo.language:
            meta.addWidget(Badge(repo.language, ""))
        if repo.private:
            meta.addWidget(Badge("private", "Warning"))
        meta.addStretch(1)
        layout.addLayout(meta)


def describe_event(event: dict[str, Any]) -> str:
    kind = str(event.get("type", "")).replace("Event", "")
    repo = (event.get("repo") or {}).get("name", "")
    actor = (event.get("actor") or {}).get("login", "")
    payload = event.get("payload") or {}
    detail = ""
    if kind == "Push":
        commits = payload.get("commits") or []
        ref = str(payload.get("ref", "")).replace("refs/heads/", "")
        detail = f"pushed {len(commits) or 1} commit(s) to {ref}"
    elif kind == "Create":
        detail = f"created {payload.get('ref_type', 'ref')} {str(payload.get('ref', '')).replace('refs/heads/', '')}"
    elif kind == "Issues":
        detail = f"{payload.get('action', '')} issue #{payload.get('issue', {}).get('number', '')}"
    elif kind == "IssueComment":
        detail = f"commented on #{payload.get('issue', {}).get('number', '')}"
    elif kind == "PullRequest":
        number = (payload.get("pull_request") or {}).get("number", "")
        detail = f"{payload.get('action', '')} pull request #{number}"
    elif kind == "PullRequestReview":
        detail = f"reviewed pull request #{(payload.get('pull_request') or {}).get('number', '')}"
    elif kind == "Watch":
        detail = "starred a repository"
    elif kind == "Fork":
        detail = "forked a repository"
    elif kind == "Release":
        detail = f"{payload.get('action', '')} release {payload.get('release', {}).get('tag_name', '')}"
    else:
        detail = str(payload.get("action", "activity")).strip() or "activity"
    return f"<b>{actor}</b> {detail}" + (f" in {repo}" if repo else "")


def _md(text: str) -> str:
    from ..markdown import render_markdown

    return render_markdown(text)
