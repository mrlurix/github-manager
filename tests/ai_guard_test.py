"""Unit tests for the AI scope guard, prompts and markdown rendering."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from app.core import ai_tasks  # noqa: E402
from app.core.ai_guard import (  # noqa: E402
    SYSTEM_PROMPT,
    classify,
    refusal_message,
    validate_answer,
    wrap_prompt,
)
from app.ui.markdown import outline, render_markdown, word_count  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def test_classify() -> None:
    allowed = [
        "Write a README for my project",
        "How do I rebase a branch?",
        "Draft a pull request description",
        "Explain GitHub Actions caching",
        "What licence should I use for an open source repo?",
        "Summarise the open issues",
        "How do I protect my main branch?",
    ]
    for message in allowed:
        verdict = classify(message)
        check(f"allows: {message[:34]}", verdict.allowed, verdict.reason)

    blocked = [
        "What is the weather in Tehran?",
        "Give me a recipe for pizza dough",
        "Write me a poem about the sea",
        "Diagnose my chest pain",
        "Who are you?",
        "thanks!",
        "What is the bitcoin price?",
    ]
    for message in blocked:
        verdict = classify(message)
        check(f"blocks: {message[:34]}", not verdict.allowed, verdict.topic)


def test_validate_answer() -> None:
    ok, _ = validate_answer("## README\n\nUse `pip install` then run `python main.py`.")
    check("accepts GitHub answer", ok)

    ok, reason = validate_answer("Preheat the oven to 200 celsius and bake for 20 minutes.")
    check("rejects cooking answer", not ok, reason)

    ok, reason = validate_answer("I'm sorry, but I cannot help with that request.")
    check("rejects empty refusal", not ok, reason)

    ok, _ = validate_answer("")
    check("rejects empty answer", not ok)


def test_prompt_scope() -> None:
    prompt = wrap_prompt("Write a README", "Repository: a/b\nFile tree:\n - main.py")
    check("wrap_prompt includes context", "Repository: a/b" in prompt)
    check("wrap_prompt includes task", "Write a README" in prompt)
    check("wrap_prompt includes reminder", "stay strictly within GitHub" in prompt)
    lowered = SYSTEM_PROMPT.lower()
    check(
        "system prompt bans other topics",
        "out of scope" in lowered and "refuse" in lowered,
    )


def test_repo_context() -> None:
    ctx = ai_tasks.RepoContext(
        repo="octocat/hello",
        description="demo",
        tree=["README.md", "main.py", "requirements.txt"],
        languages=[".py"],
        topics=["python"],
        readme="# Hello",
        key_files={"requirements.txt": "requests\n"},
    )
    prompt = ctx.as_prompt()
    for needle in ("octocat/hello", "File tree", "requirements.txt", "Topics: python"):
        check(f"context contains {needle}", needle in prompt)


def test_markdown() -> None:
    html = render_markdown("# Title\n\n```python\nprint('x')\n```\n\n- a\n- b\n")
    check("renders heading", "<h1" in html)
    check("highlights code", "print" in html and "<span" in html, html[:200])
    check("code block is padded", "<table" in html and "padding" in html)
    check("renders list", "<ul" in html)

    external = render_markdown("[docs](https://docs.github.com)")
    check("external links open in browser", 'target="_blank"' in external)

    headings = outline("# A\n\n## B\n\n```\n# not a heading\n```\n\n### C")
    check("outline finds 3 headings", len(headings) == 3, str(headings))
    check("outline anchors", headings[0][2] == "a", str(headings[0]))

    check("word count", word_count("a b c\nd") == (4, 7, 2))


def test_suggestion_prompts() -> None:
    prompts = ai_tasks.SUGGESTION_PROMPTS
    check("has suggestions", len(prompts) >= 8)
    off_topic = [
        p for p in prompts if classify(p).allowed is False
    ]
    check("all suggestions are GitHub scoped", not off_topic, str(off_topic))

    github_files = ai_tasks.GITHUB_FILE_KINDS
    check("has github file templates", "CONTRIBUTING.md" in github_files)
    check(
        "all templates are github paths",
        all(
            name.endswith((".md", ".yml", ".yaml", ".gitignore", "LICENSE", "CODEOWNERS", ".editorconfig"))
            or "/" in name
            or name in {"LICENSE", ".gitignore", "CODEOWNERS", ".editorconfig"}
            for name in github_files
        ),
    )


def test_refusal_message() -> None:
    message = refusal_message()
    check("refusal mentions README", "README" in message)
    check("refusal is markdown", message.startswith("**Out of scope.**"))


def main() -> int:
    test_classify()
    test_validate_answer()
    test_prompt_scope()
    test_repo_context()
    test_markdown()
    test_suggestion_prompts()
    test_refusal_message()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
