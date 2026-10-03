"""Issues and pull requests: triage, draft, reply."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core import ai_tasks
from ...core.github_api import IssueItem
from .. import workers
from ..dialogs import DiffDialog, RepoPickerDialog, TextInputDialog
from ..markdown import render_markdown
from ..theme import markdown_css
from ..widgets import (
    Badge,
    Card,
    FlowWidget,
    PageHeader,
    button,
    hline,
    icon_button,
    icon_svg,
    label,
    spacer,
)
from .base import Page


class IssueList(QListWidget):
    """List widget that forwards clicks landing on its embedded row widgets."""

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = (
            event.position().toPoint() if hasattr(event, "position") else event.pos()
        )
        index = self.indexAt(position)
        if index.isValid() and self.currentItem() is not self.item(index):
            self.setCurrentItem(self.item(index))


class IssueRow(QWidget):
    """One row in the issue list.

    The row widget sits above the list's own selection highlight, so it paints
    its own active state instead of relying on ``QListWidget::item:selected``.
    """

    def __init__(self, item: IssueItem) -> None:
        super().__init__()
        # Styling lives in the global QSS (#IssueRow) so that descendant badges
        # and labels keep their appearance - a per-widget stylesheet would take
        # over the whole subtree.
        self.setObjectName("IssueRow")
        self.setProperty("active", False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)

        icon = QLabel()
        name = "pull" if item.is_pr else "issue"
        color = "#31c48d" if item.state == "open" else "#7c6cff"
        icon.setPixmap(icon_svg(name, color, 16).pixmap(16, 16))
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = label(item.title, "")
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        col.addLayout(title_row)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(label(f"#{item.number}", "faint"))
        meta.addWidget(label(f"by {item.user}" if item.user else "", "faint"))
        if item.comments:
            meta.addWidget(label(f"💬 {item.comments}", "faint"))
        for lbl in item.labels[:3]:
            meta.addWidget(Badge(lbl, "Accent"))
        meta.addStretch(1)
        col.addLayout(meta)

        holder = QWidget()
        holder.setLayout(col)
        layout.addWidget(holder, 1)

    def set_active(self, active: bool) -> None:
        if self.property("active") == active:
            return
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)


class IssuesPage(Page):
    title = "Issues & PRs"
    subtitle = "Triage the backlog, draft issues and reply as a maintainer."
    icon = "issue"

    def __init__(self, ctx: Any, parent: QWidget | None = None) -> None:
        super().__init__(ctx, parent)
        self.repo = ""
        self.items: list[IssueItem] = []
        self.current: IssueItem | None = None
        #: Issue to reselect once the next load lands; 0 means "first row".
        self._wanted_number = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)

        self.header = PageHeader("Issues & pull requests", "Filter, triage and respond")
        self.header.add_action(
            button("AI triage", variant="outline", icon="sparkles", on_click=self.run_triage)
        )
        self.header.add_action(
            button("Draft issue", variant="outline", icon="edit", on_click=self.draft_issue)
        )
        self.header.add_action(icon_button("refresh", tooltip="Refresh", on_click=self.refresh))
        layout.addWidget(self.header)

        # ------------------------------------------------------------- toolbar
        bar = Card(flat=True)
        # A flow row rather than a fixed one: the repository picker plus the two
        # filters plus the link is more than a narrow window can hold, and a
        # plain QHBoxLayout would let them overlap.
        row = FlowWidget(spacing=10)
        self.repo_combo = QComboBox()
        self.repo_combo.setMinimumWidth(200)
        self.repo_combo.currentTextChanged.connect(self._on_repo_changed)
        row.add(self.repo_combo)
        row.add(button("Choose…", variant="outline", icon="folder", on_click=self.pick_repo))
        self.kind = QComboBox()
        self.kind.addItems(["Issues", "Pull requests"])
        self.kind.currentIndexChanged.connect(self.refresh)
        row.add(self.kind)
        self.state = QComboBox()
        self.state.addItems(["Open", "Closed", "All"])
        self.state.currentIndexChanged.connect(self.refresh)
        row.add(self.state)
        row.add(button("Open on GitHub", variant="ghost", icon="external", on_click=self.open_browser))
        bar.add(row)
        layout.addWidget(bar)

        self.split = QSplitter(Qt.Orientation.Horizontal)

        # ------------------------------------------------------------- the list
        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)
        self.list = IssueList()
        self.list.setObjectName("IssueList")
        self.list.setSpacing(4)
        self.list.currentItemChanged.connect(self._on_selected)
        left_layout.addWidget(self.list)
        self.split.addWidget(left)

        # ---------------------------------------------------------- the detail
        right = QFrame()
        right.setObjectName("Card")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 14, 16, 14)
        right_layout.setSpacing(10)
        self.detail_title = label("Select an item", "h3")
        self.detail_title.setWordWrap(True)
        right_layout.addWidget(self.detail_title)
        self.detail_meta = label("", "faint")
        right_layout.addWidget(self.detail_meta)
        right_layout.addWidget(hline())
        self.detail_view = QTextBrowser()
        self.detail_view.setObjectName("MarkdownView")
        right_layout.addWidget(self.detail_view, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.reply_btn = button("AI reply", variant="primary", icon="sparkles", on_click=self.ai_reply)
        actions.addWidget(self.reply_btn)
        self.close_btn = button("Close / reopen", variant="outline", icon="check", on_click=self.toggle_state)
        actions.addWidget(self.close_btn)
        actions.addWidget(spacer())
        right_layout.addLayout(actions)
        self.split.addWidget(right)
        self.split.setSizes([420, 620])
        layout.addWidget(self.split, 1)

        self.triage_view = QTextBrowser()
        self.triage_view.setObjectName("MarkdownView")
        self.triage_view.setVisible(False)
        self.triage_view.setMaximumHeight(260)
        layout.addWidget(self.triage_view)

    # ------------------------------------------------------------ lifecycle
    def on_show(self) -> None:
        if not self.ctx.signed_in:
            self.notify("Connect GitHub first.", "warning")
            return
        current = self.repo or self.ctx.config.get("last_repo", "")
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        for repo in self.ctx.repos:
            self.repo_combo.addItem(repo.full_name)
        self.repo_combo.blockSignals(False)
        if not self.ctx.repos_loaded:
            self.notify("Loading repositories…")
            workers.run(
                "issues-repos",
                lambda: self.ctx.github.list_repos(sort="updated"),
                on_result=lambda repos: self._fill_repos(repos, current),
                on_error=lambda message: self.notify(message, "error"),
            )
            return
        # Signals stay blocked so the selection change does not fire a refresh;
        # a single explicit call keeps it to one API round trip.
        if current and self.repo_combo.findText(current) >= 0:
            self.repo_combo.setCurrentText(current)
        if self.repo_combo.count():
            self._on_repo_changed(self.repo_combo.currentText())
        self._apply_css()

    def _apply_css(self) -> None:
        """Re-apply theme dependent styling to the rendered markdown views."""
        css = markdown_css(
            self.ctx.config.get("theme", "dark"),
            self.ctx.config.get("accent", "violet"),
        )
        self.detail_view.document().setDefaultStyleSheet(css)
        self.triage_view.document().setDefaultStyleSheet(css)
        # Issue row colours come from the global QSS; nothing per-widget to redo.

    def on_theme_changed(self) -> None:
        self._apply_css()
        if self.current:
            self._render_detail(self.current)

    def _fill_repos(self, repos: list[Any], current: str) -> None:
        self.ctx.repos = repos
        self.ctx.repos_loaded = True
        self.repo_combo.blockSignals(True)
        self.repo_combo.clear()
        for repo in repos:
            self.repo_combo.addItem(repo.full_name)
        self.repo_combo.blockSignals(False)
        if current and self.repo_combo.findText(current) >= 0:
            self.repo_combo.setCurrentText(current)
        if self.repo_combo.count():
            self._on_repo_changed(self.repo_combo.currentText())

    # ----------------------------------------------------------------- logic
    def _on_repo_changed(self, full_name: str) -> None:
        self.repo = full_name
        if full_name:
            self.ctx.config.save(last_repo=full_name)
            self.refresh()

    def pick_repo(self) -> None:
        if not self.ctx.repos:
            self.notify("Repositories are still loading.", "info")
            return
        dlg = RepoPickerDialog(self, self.ctx.repos)
        if dlg.exec():
            picked = dlg.selection()
            if picked:
                self.repo_combo.setCurrentText(picked[0])

    def refresh(self) -> None:
        if not self.repo:
            return
        state = {"Open": "open", "Closed": "closed", "All": "all"}[self.state.currentText()]
        wants_prs = self.kind.currentText() == "Pull requests"
        # Captured before the list is cleared, because clearing drops the
        # selection. Refreshing must not move the user to a different issue.
        self._wanted_number = self.current.number if self.current else 0
        self.list.clear()
        self.detail_title.setText("Loading…")

        def task() -> list[IssueItem]:
            if wants_prs:
                return self.ctx.github.list_pulls(self.repo, state="open" if state == "all" else state)
            return self.ctx.github.list_issues(self.repo, state=state)

        workers.run(
            "issues-load",
            task,
            on_result=self._on_loaded,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _on_loaded(self, items: list[IssueItem]) -> None:
        # Remember what the user was reading, so the restored selection lands on
        # the same issue rather than the first row.
        wanted = self._wanted_number
        self._wanted_number = 0
        self.items = items
        self.list.clear()
        if not items:
            empty = QListWidgetItem("Nothing here — no open items.")
            self.list.addItem(empty)
            self.detail_title.setText("Nothing to show")
            self.detail_view.setHtml("")
            return
        for item in items:
            widget = IssueRow(item)
            entry = QListWidgetItem()
            entry.setSizeHint(widget.sizeHint())
            entry.setData(Qt.ItemDataRole.UserRole, item)
            self.list.addItem(entry)
            self.list.setItemWidget(entry, widget)

        # Signals stay blocked while the selection is restored: re-selecting by
        # index would fire _on_selected twice and, if the list order changed,
        # land on a different issue than the one being restored.
        self.list.blockSignals(True)
        row = self._row_for_number(wanted)
        self.list.setCurrentRow(row if row >= 0 else 0)
        self.list.blockSignals(False)
        entry = self.list.currentItem()
        if entry is not None:
            self._select_entry(entry)

    def _row_for_number(self, number: int) -> int:
        """Index of ``number`` in the list, or -1 when it is gone."""
        for row in range(self.list.count()):
            item = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            if isinstance(item, IssueItem) and item.number == number:
                return row
        return -1

    def _on_selected(self, current: QListWidgetItem | None, _prev: Any) -> None:
        if not current:
            # Nothing is highlighted, so no issue is the current one. Leaving a
            # stale value here would let an action target the wrong issue.
            self.current = None
            return
        self._select_entry(current)

    def _select_entry(self, current: QListWidgetItem) -> None:
        item = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item, IssueItem):
            self.current = None
            return
        self.current = item
        selected_row = self.list.row(current)
        for row in range(self.list.count()):
            widget = self.list.itemWidget(self.list.item(row))
            if isinstance(widget, IssueRow):
                widget.set_active(row == selected_row)
        self._render_detail(item)
        workers.run(
            "issue-comments",
            lambda: self.ctx.github.list_comments(self.repo, item.number),
            on_result=lambda comments: self._render_comments(item, comments),
            on_error=lambda _m: None,
        )

    def _render_detail(self, item: IssueItem) -> None:
        self.detail_title.setText(f"#{item.number} · {item.title}")
        meta = [f"{item.state}", f"by {item.user}" if item.user else "", f"{item.comments} comments"]
        meta += list(item.labels)
        self.detail_meta.setText(" · ".join(part for part in meta if part))
        body = item.body.strip() or "_No description provided._"
        self.detail_view.setHtml(
            f"<style>{markdown_css()}</style>" + render_markdown(body)
        )

    def _render_comments(self, item: IssueItem, comments: list[dict[str, Any]]) -> None:
        if self.current is None or self.current.number != item.number:
            return
        if not comments:
            return
        html = [f"<style>{markdown_css()}</style>", render_markdown(item.body or "_No description._")]
        for comment in comments:
            author = (comment.get("user") or {}).get("login", "unknown")
            body = comment.get("body") or ""
            html.append(
                f"<hr><p><b>{author}</b></p>" + render_markdown(body)
            )
        self.detail_view.setHtml("".join(html))

    # ------------------------------------------------------------ operations
    def toggle_state(self) -> None:
        if not self.current or not self.repo:
            return
        item = self.current
        new_state = "closed" if item.state == "open" else "open"
        workers.run(
            "issue-toggle",
            lambda: self.ctx.github.update_issue(self.repo, item.number, state=new_state),
            on_result=lambda updated: self._after_update(updated),
            on_error=lambda message: self.notify(message, "error"),
        )

    def _after_update(self, updated: IssueItem) -> None:
        self.notify(f"#{updated.number} is now {updated.state}.", "success")
        self.refresh()

    def draft_issue(self) -> None:
        if not self.require_ai():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        idea = TextInputDialog(
            self,
            "Draft an issue",
            f"Describe the bug or feature in one or two sentences. The AI expands it "
            f"into a well structured issue for {self.repo}.",
            fields=[
                ("Title", "", "Short issue title"),
                ("Notes", "", "Extra context, error messages, expected behaviour"),
            ],
            accept_text="Draft with AI",
        )
        if not idea.exec():
            return
        values = idea.values()
        if not values.get("Title", "").strip():
            return
        self.notify("Drafting issue…")

        def task() -> Any:
            return ai_tasks.issue_draft(
                self.ctx.ai(),
                title_hint=values["Title"],
                body_hint=values.get("Notes", ""),
                context=f"Repository: {self.repo}",
                stream=True,
            )

        workers.run(
            "issue-draft",
            task,
            on_result=self._show_draft,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _show_draft(self, text: str) -> None:
        dlg = DiffDialog(
            self,
            f"New issue for {self.repo}",
            text,
            subtitle="This will create a real GitHub issue when you confirm.",
            accept_text="Create issue",
        )
        if not dlg.exec():
            return
        body = dlg.text()
        title = body.strip().split("\n", 1)[0].lstrip("# ").strip()[:120]

        def task() -> Any:
            return self.ctx.github.create_issue(self.repo, title, body)

        workers.run(
            "issue-create",
            task,
            on_result=lambda item: self.notify(f"Created issue #{item.number}.", "success"),
            on_error=lambda message: self.notify(message, "error"),
            on_finish=self.refresh,
        )

    def ai_reply(self) -> None:
        if not self.require_ai():
            return
        if not self.current or not self.repo:
            self.notify("Select an item first.", "warning")
            return
        item = self.current
        self.notify("Writing a reply…")

        def task() -> Any:
            comments = self.ctx.github.list_comments(self.repo, item.number)
            history = "\n".join(
                f"{c.get('user', {}).get('login', '')}: {str(c.get('body', ''))[:400]}"
                for c in comments[-6:]
            )
            return ai_tasks.issue_reply(
                self.ctx.ai(),
                {"number": item.number, "title": item.title, "body": item.body},
                history,
            )

        workers.run(
            "issue-reply",
            task,
            on_result=self._show_reply,
            on_error=lambda message: self.notify(message, "error"),
        )

    def _show_reply(self, text: str) -> None:
        # Pin the target now: reading self.current inside the worker would post
        # the comment to whatever is selected by the time the thread runs.
        target = self.current
        if target is None:
            return
        dlg = DiffDialog(
            self,
            f"Reply to #{target.number}",
            text,
            subtitle="Posting is optional — edit freely before sending.",
            accept_text="Post comment",
        )
        if not dlg.exec():
            return
        body = dlg.text()
        number = target.number

        def task() -> Any:
            return self.ctx.github.comment_issue(self.repo, number, body)

        workers.run(
            "issue-comment",
            task,
            on_result=lambda _r: self.notify("Comment posted.", "success"),
            on_error=lambda message: self.notify(message, "error"),
            on_finish=self.refresh,
        )

    def run_triage(self) -> None:
        if not self.require_ai():
            return
        if not self.repo:
            self.notify("Choose a repository first.", "warning")
            return
        self.triage_view.setVisible(True)
        self.triage_view.setHtml(f"<style>{markdown_css()}</style><div>Triaging…</div>")

        def task() -> Any:
            items = self.ctx.github.list_issues(self.repo, state="open")
            payload = [
                {"number": i.number, "title": i.title, "state": i.state, "labels": i.labels}
                for i in items
            ]
            return ai_tasks.issue_triage(self.ctx.ai(), payload)

        workers.run(
            "issue-triage",
            task,
            on_result=lambda text: self.triage_view.setHtml(
                f"<style>{markdown_css()}</style>" + render_markdown(text)
            ),
            on_error=lambda message: self.notify(message, "error"),
        )

    def open_browser(self) -> None:
        import webbrowser

        if self.current and self.current.url:
            webbrowser.open(self.current.url)
        elif self.repo:
            webbrowser.open(f"https://github.com/{self.repo}/issues")
