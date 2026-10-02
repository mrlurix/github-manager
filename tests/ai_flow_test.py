"""UI level tests for the AI features using a stubbed AI client.

Verifies that streaming, the GitHub-only scope lock and the README commit
path behave correctly with real widgets but no network access.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


class StubAI:
    """Returns a canned, GitHub-scoped answer word by word."""

    needs_key = False

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.base_url = "http://localhost:11434/v1"
        self.model = "stub"
        self.max_tokens = 2000
        self.temperature = 0.6
        self.calls = 0

    def chat(self, messages, stream=False, json_mode=False):
        self.calls += 1
        self.prompts.append("\n".join(f"{m.role}: {m.content}" for m in messages))
        if json_mode:
            return '{"topics": ["python", "cli"]}'
        if not stream:
            return self.reply
        return self._gen()

    def _gen(self):
        for word in self.reply.split(" "):
            yield word + " "

    def list_models(self):
        return ["stub"]


README_REPLY = (
    "# Demo Project\n\nA short description.\n\n## Features\n\n- one\n- two\n\n"
    "## Installation\n\n```bash\npip install demo\n```\n"
)
CHAT_REPLY = "Use a table of contents and add shields.io badges to the top of the README."
OFFTOPIC_REPLY = "Preheat the oven to 200 celsius and bake for twenty minutes."


def pump(app, loops: int = 120) -> None:
    """Let the event loop run in real time.

    Workers post their results from another thread, so a bare processEvents()
    spin would return before the thread had a chance to finish.
    """
    for _ in range(loops):
        app.processEvents()
        time.sleep(0.002)


def build_app(app):
    from tests.smoke_test import StubGitHub, make_repos
    from app.core.github_api import UserProfile
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow

    ctx = AppContext()
    ctx.secrets.set("github_token", "stub-token")
    ctx.github = StubGitHub()
    ctx.repos = make_repos()
    ctx.repos_loaded = True
    ctx.profile = UserProfile(login="octocat", name="The Octocat")
    ctx.orgs = [{"login": "github"}]
    # Pretend an AI provider is configured so the pages enable their buttons.
    ctx.config.save(ai_provider="ollama", ai_base_url="http://localhost:11434/v1", ai_model="stub")
    ctx.ai = lambda **kwargs: ctx._stub_ai  # type: ignore[assignment]
    ctx._stub_ai = StubAI(CHAT_REPLY)  # type: ignore[attr-defined]

    window = MainWindow(ctx)
    window.resize(1500, 940)
    window.show()
    pump(app, 30)
    return ctx, window


def test_readme_generation(app) -> None:
    ctx, window = build_app(app)
    window.goto(2)  # README Studio
    pump(app, 30)
    page = window.pages[2]

    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 20)
    check("readme page knows the repo", page.repo == "octocat/hello-world", page.repo)

    ctx._stub_ai = StubAI(README_REPLY)  # type: ignore[attr-defined]
    page.generate()
    pump(app)
    text = page.editor.text()
    check("generate produced markdown", text.startswith("# Demo Project"), text[:60])
    check("generate kept code fences", "```bash" in text)
    check("generate enabled refine", page.refine_btn.isEnabled())
    check("preview rendered", "Demo Project" in page.editor.preview.toPlainText())

    prompt = ctx._stub_ai.prompts[-1]  # type: ignore[attr-defined]
    check("prompt carried the file tree", "requirements.txt" in prompt)
    check("prompt carried repo name", "octocat/hello-world" in prompt)
    check("prompt enforced the scope", "stay strictly within GitHub" in prompt)

    # Refine replaces the document with the improved version.
    ctx._stub_ai = StubAI("# Demo Project\n\nRefined and clearer.")  # type: ignore[attr-defined]
    page.notes.setText("make the intro clearer")
    page.refine()
    pump(app)
    check("refine replaced the text", "Refined and clearer" in page.editor.text())

    window.close()


def test_offtopic_answers_are_discarded(app) -> None:
    ctx, window = build_app(app)
    window.goto(2)
    pump(app, 30)
    page = window.pages[2]
    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 20)

    ctx._stub_ai = StubAI(OFFTOPIC_REPLY)  # type: ignore[attr-defined]
    page.editor.set_text("# Old readme")
    page.generate()
    pump(app)
    check("off-topic README answer is dropped", page.editor.text().strip() == "", repr(page.editor.text()[:60]))

    window.close()


def test_assistant_scope_lock(app) -> None:
    ctx, window = build_app(app)
    page = window.pages[6]  # AI Assistant
    window.goto(6)
    pump(app, 20)

    before = ctx._stub_ai.calls  # type: ignore[attr-defined]
    page._send("What is the weather in Tehran today?")
    pump(app)
    check(
        "off-topic question never reaches the model",
        ctx._stub_ai.calls == before,  # type: ignore[attr-defined]
        str(ctx._stub_ai.calls),  # type: ignore[attr-defined]
    )
    check(
        "off-topic reply explains the scope",
        "Out of scope" in page.last_assistant_text(),
        page.last_assistant_text()[:80],
    )

    before = ctx._stub_ai.calls  # type: ignore[attr-defined]
    page._send("How do I add shields.io badges to my README?")
    pump(app)
    check(
        "on-topic question is answered",
        ctx._stub_ai.calls > before,  # type: ignore[attr-defined]
    )
    check(
        "answer was streamed into a bubble",
        "shields.io" in page.last_assistant_text(),
        page.last_assistant_text(),
    )
    check("history recorded the turn", len(page.history) == 2, str(page.history))

    window.close()


def test_committing_a_readme(app) -> None:
    """Drive the commit dialog non-interactively and assert the API call."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog

    ctx, window = build_app(app)
    window.goto(2)
    pump(app, 30)
    page = window.pages[2]
    page.repo_combo.setCurrentText("octocat/hello-world")
    pump(app, 20)

    calls: list[tuple] = []
    original = ctx.github.commit_readme

    def spy(full_name, content, message, branch=""):
        calls.append((full_name, content, message, branch))
        return original(full_name, content, message, branch)

    ctx.github.commit_readme = spy  # type: ignore[method-assign]

    page.editor.set_text("# New readme\n\nCommitted by the test.")

    def auto_accept() -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            modal.accept()

    QTimer.singleShot(120, auto_accept)
    page.commit()
    pump(app, 60)

    check("commit reached the GitHub client", bool(calls), str(calls))
    if calls:
        full_name, content, message, _branch = calls[0]
        check("commit targets the selected repo", full_name == "octocat/hello-world", full_name)
        check("commit sends the editor content", "Committed by the test" in content)
        check("commit used the default message", message.startswith("docs: update"), message)

    window.close()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    test_readme_generation(app)
    test_offtopic_answers_are_discarded(app)
    test_assistant_scope_lock(app)
    test_committing_a_readme(app)
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
