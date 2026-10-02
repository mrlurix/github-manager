"""High level AI features built on top of :mod:`ai_api`.

Every function here is GitHub specific and returns plain strings that the UI
can drop straight into an editor.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .ai_api import AIClient, AIError, ChatMessage
from .ai_guard import SYSTEM_PROMPT, SCOPE_REMINDER, wrap_prompt

MAX_TREE_ENTRIES = 400
MAX_FILE_CHARS = 6000

INTERESTING_FILES = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "composer.json",
    "gemfile",
    "makefile",
    "dockerfile",
    "docker-compose.yml",
    "compose.yml",
    ".env.example",
    "setup.py",
    "setup.cfg",
    "tsconfig.json",
    "manage.py",
    "next.config.js",
    "vite.config.ts",
)

SOURCE_EXTENSIONS = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb",
    ".php", ".cs", ".c", ".cpp", ".h", ".swift", ".vue", ".svelte", ".sh",
)


@dataclass
class RepoContext:
    repo: str
    description: str = ""
    tree: list[str] = None  # type: ignore[assignment]
    languages: list[str] = None  # type: ignore[assignment]
    topics: list[str] = None  # type: ignore[assignment]
    default_branch: str = "main"
    stars: int = 0
    readme: str = ""
    key_files: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.tree = self.tree or []
        self.languages = self.languages or []
        self.topics = self.topics or []
        self.key_files = self.key_files or {}

    def as_prompt(self) -> str:
        lines = [
            f"Repository: {self.repo}",
            f"Default branch: {self.default_branch}",
            f"Stars: {self.stars}",
        ]
        if self.description:
            lines.append(f"Declared description: {self.description}")
        if self.topics:
            lines.append(f"Topics: {', '.join(self.topics)}")
        if self.languages:
            lines.append(f"Languages detected: {', '.join(self.languages)}")

        tree = self.tree[:MAX_TREE_ENTRIES]
        if tree:
            lines.append("\nFile tree (may be truncated):\n" + "\n".join(f"  - {p}" for p in tree))

        if self.readme:
            readme = self.readme.strip()
            if len(readme) > 4000:
                readme = readme[:4000] + "\n  ...(truncated)"
            lines.append("\nExisting README.md:\n" + readme)

        for name, body in list(self.key_files.items())[:6]:
            body = body.strip()
            if len(body) > MAX_FILE_CHARS:
                body = body[:MAX_FILE_CHARS] + "\n... (truncated)"
            lines.append(f"\n--- {name} ---\n{body}")

        return "\n".join(lines)


def build_repo_context(gh: Any, full_name: str) -> RepoContext:
    """Collect enough context for the AI without hammering the API."""
    repo = gh.get_repo(full_name)
    ctx = RepoContext(
        repo=full_name,
        description=repo.description,
        default_branch=repo.default_branch,
        stars=repo.stars,
        topics=list(repo.topics),
    )

    try:
        tree = gh.get_repo_tree(full_name, repo.default_branch)
        ctx.tree = tree[:MAX_TREE_ENTRIES]
    except Exception:
        ctx.tree = []

    langs: dict[str, int] = {}
    for path in ctx.tree:
        for ext in SOURCE_EXTENSIONS:
            if path.endswith(ext):
                langs[ext] = langs.get(ext, 0) + 1
                break
    ctx.languages = [ext for ext, _ in sorted(langs.items(), key=lambda kv: -kv[1])[:6]]

    try:
        ctx.readme = gh.get_readme(full_name)
    except Exception:
        ctx.readme = ""

    wanted = [
        name
        for name in INTERESTING_FILES
        if any(p.lower().endswith(name) for p in ctx.tree)
    ]
    for name in wanted[:6]:
        path = next(p for p in ctx.tree if p.lower().endswith(name))
        try:
            content = gh.get_file(full_name, path, repo.default_branch)
        except Exception:
            content = None
        if content:
            ctx.key_files[path] = content[:MAX_FILE_CHARS]

    return ctx


def _system(extra: str = "") -> str:
    return f"{SYSTEM_PROMPT}\n\n{extra}".strip() if extra else SYSTEM_PROMPT


def _ask(
    client: AIClient,
    task: str,
    context: str = "",
    *,
    system: str = "",
    stream: bool = False,
    json_mode: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str | Iterator[str]:
    previous = (client.temperature, client.max_tokens)
    if temperature is not None:
        client.temperature = temperature
    if max_tokens is not None:
        client.max_tokens = max_tokens
    try:
        messages = [
            ChatMessage("system", _system(system)),
            ChatMessage("user", wrap_prompt(task, context)),
        ]
        return client.chat(messages, stream=stream, json_mode=json_mode)
    finally:
        client.temperature, client.max_tokens = previous


# --------------------------------------------------------------------- README
README_SYSTEM = """You write README.md files for GitHub repositories.
Rules:
- Output raw markdown only. No preamble, no explanation, no code fence around
the whole document.
- Start with an H1 title, then a one line tagline, then badges.
- Use GitHub flavoured markdown: tables, task lists, details blocks, shields.io
badges, anchored table of contents for long documents.
- Never invent features, commands, or license names that are not supported by
the context. If something is unknown, leave a clearly marked TODO placeholder.
- Keep code blocks runnable and minimal."""


def readme_prompt(
    ctx: RepoContext,
    *,
    tone: str = "Professional",
    language: str = "English",
    sections: list[str] | None = None,
    audience: str = "developers",
    extra_notes: str = "",
    include_badges: bool = True,
    keep_existing: str = "",
) -> str:
    wanted = sections or []
    section_line = ", ".join(wanted) if wanted else "choose the sections that fit"
    task = f"""Write a complete README.md for `{ctx.repo}`.

Requirements:
- Language: {language}.
- Tone: {tone}.
- Audience: {audience}.
- Sections to include: {section_line}.
- Badges at the top: {"yes" if include_badges else "no"}.
- Use a table of contents when the document is longer than 80 lines.
- Base every statement strictly on the repository context below.
"""
    if extra_notes.strip():
        task += f"\nAdditional requirements from the user:\n{extra_notes.strip()}\n"
    if keep_existing.strip():
        task += (
            "\nImprove the existing README below. Keep any accurate details, "
            "correct the wrong parts, and fill the gaps:\n\n"
            + keep_existing.strip()[:8000]
        )
    return task


def generate_readme(
    client: AIClient,
    ctx: RepoContext,
    *,
    tone: str = "Professional",
    language: str = "English",
    sections: list[str] | None = None,
    audience: str = "developers",
    extra_notes: str = "",
    include_badges: bool = True,
    keep_existing: str = "",
    stream: bool = False,
) -> str | Iterator[str]:
    return _ask(
        client,
        readme_prompt(
            ctx,
            tone=tone,
            language=language,
            sections=sections,
            audience=audience,
            extra_notes=extra_notes,
            include_badges=include_badges,
            keep_existing=keep_existing,
        ),
        ctx.as_prompt(),
        system=README_SYSTEM,
        stream=stream,
        temperature=0.6,
        max_tokens=max(2000, client.max_tokens),
    )


def improve_text(
    client: AIClient,
    text: str,
    *,
    instruction: str,
    context: str = "",
    stream: bool = True,
) -> str | Iterator[str]:
    task = (
        f"Rewrite the GitHub content below according to this instruction: {instruction}\n\n"
        f"Return only the rewritten markdown, with no commentary.\n\n{text}"
    )
    return _ask(client, task, context, stream=stream, temperature=0.6)


def summarize_readme(client: AIClient, readme: str, *, stream: bool = True) -> str | Iterator[str]:
    task = (
        "Review this README.md as a GitHub reviewer. Reply with a short markdown "
        "report: 5 to 8 bullet points of the most valuable improvements, then a "
        "'Quick wins' section with three concrete edits.\n\n" + readme
    )
    return _ask(client, task, stream=stream, temperature=0.4)


def suggest_topics(
    client: AIClient, ctx: RepoContext, *, count: int = 12
) -> list[str]:
    from .github_api import parse_json

    task = (
        f"Suggest exactly {count} lowercase GitHub topics for `{ctx.repo}`.\n"
        "Return raw JSON only, in this shape: {\"topics\": [\"a\", \"b\"]}\n"
        "Topics must be single words or short hyphenated phrases, no spaces."
    )
    raw = _ask(client, task, ctx.as_prompt(), temperature=0.2, json_mode=True)
    text = "".join(raw) if not isinstance(raw, str) else raw
    data = parse_json(text, {}) or {}
    topics = data.get("topics") or []
    cleaned: list[str] = []
    for topic in topics:
        slug = str(topic).strip().lower().replace(" ", "-")
        slug = "".join(ch for ch in slug if ch.isalnum() or ch in "-_")
        if slug and slug not in cleaned:
            cleaned.append(slug)
    return cleaned[:count]


def suggest_description(client: AIClient, ctx: RepoContext) -> str:
    raw = _ask(
        client,
        "Write a single sentence GitHub repository description for "
        f"`{ctx.repo}` (max 110 characters, no trailing period, no emoji). "
        "Return only the sentence.",
        ctx.as_prompt(),
        temperature=0.3,
    )
    text = "".join(raw) if not isinstance(raw, str) else raw
    first = text.strip().split("\n")[0].strip()
    return first.strip("\"'`* ").rstrip(".").strip()[:120]


# ------------------------------------------------------------------- account
def profile_bio(client: AIClient, profile: dict[str, Any], *, style: str = "concise") -> str:
    system = (
        "You write GitHub profile bios. Keep the result under 160 characters, "
        "first person, no hashtags, no emoji unless asked."
    )
    prompt = (
        f"Write a GitHub profile bio for this developer.\n"
        f"Style: {style}.\n"
        f"Current fields: name={profile.get('name')!r}, company={profile.get('company')!r}, "
        f"location={profile.get('location')!r}, blog={profile.get('blog')!r}, "
        f"current bio={profile.get('bio')!r}\n"
        f"Return 3 options as a markdown numbered list, each on one line."
    )
    raw = _ask(client, prompt, system=system, temperature=0.8)
    return "".join(raw) if not isinstance(raw, str) else raw


def profile_readme(client: AIClient, profile: dict[str, Any], repos: list[Any]) -> str | Iterator[str]:
    system = README_SYSTEM
    listing = "\n".join(
        f"- {getattr(r, 'full_name', '')}: {getattr(r, 'description', '') or 'no description'}"
        for r in repos[:12]
    )
    ctx = (
        f"Profile: {profile.get('login')} (name: {profile.get('name')}, "
        f"location: {profile.get('location')}, bio: {profile.get('bio')})\n"
        f"Repositories:\n{listing}"
    )
    task = (
        "Write the content of the special `username/username` profile README "
        "(shown on the user's GitHub profile page). Include a greeting, what "
        "they work on, pinned project highlights, tech stack badges and a "
        "contact / social links section. Return raw markdown only."
    )
    return _ask(client, task, ctx, system=system, stream=True, temperature=0.7)


# ------------------------------------------------------- issues, PRs, commits
def issue_draft(
    client: AIClient,
    *,
    title_hint: str,
    body_hint: str = "",
    context: str = "",
    stream: bool = True,
) -> str | Iterator[str]:
    system = (
        "You write GitHub issues. Return raw markdown only, starting with a "
        "single line '## Summary', then '## Steps to reproduce', '## Expected', "
        "'## Actual' as applicable. Do not invent version numbers."
    )
    task = (
        f"Draft a GitHub issue.\nIdea: {title_hint}\n"
        f"Extra details: {body_hint or 'none provided'}\n"
        "If the idea is a bug, include reproduction steps. If it is a feature "
        "request, include motivation and acceptance criteria."
    )
    return _ask(client, task, context, system=system, stream=stream, temperature=0.5)


def issue_triage(client: AIClient, issues: list[dict[str, Any]]) -> str:
    listing = "\n".join(
        f"#{i['number']} [{i.get('state')}] {i['title']}" for i in issues[:40]
    )
    system = (
        "You triage GitHub issues. Return a markdown table with columns "
        "Issue, Type, Priority, Suggested labels. Type is one of bug, feature, "
        "docs, question, duplicate, spam. Priority is P0..P3. Then add three "
        "bullet points with the overall backlog assessment."
    )
    task = f"Triage these GitHub issues:\n{listing}"
    raw = _ask(client, task, system=system, temperature=0.2)
    return "".join(raw) if not isinstance(raw, str) else raw


def issue_reply(client: AIClient, issue: dict[str, Any], comment_history: str = "") -> str:
    system = (
        "You write maintainer replies on GitHub issues. Be concise, friendly and "
        "specific. Return raw markdown only."
    )
    task = (
        f"Write a reply to issue #{issue.get('number')}: {issue.get('title')}\n\n"
        f"Body:\n{str(issue.get('body') or '')[:3000]}\n"
        + (f"\nPrevious comments:\n{comment_history[:2000]}\n" if comment_history else "")
        + "\nIf the issue needs more information, ask precise follow-up questions."
    )
    raw = _ask(client, task, system=system, temperature=0.5)
    return "".join(raw) if not isinstance(raw, str) else raw


def pr_draft(
    client: AIClient,
    *,
    repo: str,
    title: str,
    description: str = "",
    changed_files: list[str] | None = None,
    stream: bool = True,
) -> str | Iterator[str]:
    system = (
        "You write GitHub pull request descriptions. Return raw markdown with "
        "sections: ## Summary, ## Changes, ## Testing, ## Review checklist, "
        "## Related issues. Use the issue closing keyword only when given a real "
        "issue number (for example 'Closes #12')."
    )
    files = "\n".join(f"- {f}" for f in (changed_files or [])[:40])
    task = (
        f"Draft a pull request for `{repo}`.\nTitle: {title}\n"
        f"Description: {description or 'none'}\n"
        f"Changed files:\n{files or 'not provided'}"
    )
    return _ask(client, task, system=system, stream=stream, temperature=0.5)


def commit_message(
    client: AIClient,
    *,
    diff_summary: str,
    convention: str = "Conventional Commits",
) -> str:
    system = (
        f"You write git commit messages using {convention}. Return exactly three "
        "parts separated by a blank line: the subject line (max 72 chars), an "
        "optional body wrapped at 72 chars, and a footer with 'BREAKING CHANGE' "
        "notes only when required. No explanations."
    )
    task = f"Write a commit message for these changes:\n{diff_summary[:6000]}"
    raw = _ask(client, task, system=system, temperature=0.3)
    return "".join(raw) if not isinstance(raw, str) else raw


BRANCH_SAFE = re.compile(r"^[A-Za-z0-9._/-]+$")


def branch_name(client: AIClient, description: str) -> str:
    system = (
        "You name git branches. Return only the branch name: lowercase, words "
        "separated by hyphens, optional Conventional Commit type prefix such as "
        "feat/, fix/ or chore/. No explanation."
    )
    raw = _ask(client, f"Branch name for: {description}", system=system, temperature=0.2)
    text = "".join(raw) if not isinstance(raw, str) else raw
    candidate = text.strip().split()[0].strip("`'\"").rstrip(".,:;") if text.strip() else ""
    if not BRANCH_SAFE.match(candidate):
        candidate = re.sub(r"[^A-Za-z0-9._/-]+", "-", candidate).strip("-")
    return candidate.lower() or "feature/update"


def release_notes(
    client: AIClient,
    *,
    repo: str,
    tag: str,
    commits: list[Any],
    previous_readme: str = "",
    stream: bool = True,
) -> str | Iterator[str]:
    system = (
        "You write GitHub release notes. Return markdown that starts with a short "
        "paragraph, then '## Highlights', '## Changes', '## Fixes', "
        "'## Breaking changes' and '## Upgrade notes' (omit empty sections). "
        "Group commits by intent, not by hash."
    )
    lines = []
    for commit in commits[:80]:
        lines.append(f"- {getattr(commit, 'message', '')}")
    task = (
        f"Write release notes for `{repo}` version {tag}.\nCommits:\n"
        + "\n".join(lines)
        + (f"\n\nCurrent README for extra context:\n{previous_readme[:3000]}" if previous_readme else "")
    )
    return _ask(client, task, system=system, stream=stream, temperature=0.5)


def review_diff(
    client: AIClient,
    *,
    repo: str,
    diff: str,
    stream: bool = True,
) -> str | Iterator[str]:
    system = (
        "You review pull request diffs for GitHub. Reply with markdown: a one "
        "line verdict (Approve / Request changes / Comment), then '## Blocking "
        "issues', '## Suggestions', '## Nitpicks'. Point at real problems: "
        "correctness, security, breaking changes, missing tests. No praise "
        "filler."
    )
    task = f"Review this diff for `{repo}`:\n\n```diff\n{diff[:40000]}\n```"
    return _ask(client, task, system=system, stream=stream, temperature=0.3)


# ------------------------------------------------------- GitHub repo files
GITHUB_FILE_KINDS: dict[str, str] = {
    "CONTRIBUTING.md": "a contribution guide with setup steps, commit conventions, PR process and a code of conduct note",
    "LICENSE": "the full text of an OSI approved licence, based on the detected stack",
    ".gitignore": "a language specific .gitignore covering build output, caches, IDE folders and secrets",
    ".github/workflows/ci.yml": "a GitHub Actions workflow that installs dependencies, runs linting and tests on a matrix of Python versions, and uploads coverage",
    ".github/dependabot.yml": "a Dependabot configuration for pip, github-actions and npm ecosystems",
    "CODEOWNERS": "a CODEOWNERS file mapping paths to the repository owner as reviewer",
    "SECURITY.md": "a security policy with reporting instructions and a supported versions table",
    ".github/PULL_REQUEST_TEMPLATE.md": "a pull request template with checklists and a testing section",
    ".github/ISSUE_TEMPLATE/bug_report.md": "a bug report issue template with reproduction steps fields",
    ".github/ISSUE_TEMPLATE/feature_request.md": "a feature request issue template",
    ".editorconfig": "an .editorconfig for a Python and web project",
    "docs/CONTRIBUTING.md": "a contributor onboarding document",
    "CHANGELOG.md": "a changelog following Keep a Changelog with the Unreleased section filled in",
}

GITHUB_FILE_SYSTEM = """You write individual files that belong in a GitHub repository.
Return the raw file content only, with no markdown code fence and no commentary.
Never invent secrets, internal hostnames or credentials."""


def github_file(
    client: AIClient,
    kind: str,
    ctx: RepoContext,
    *,
    extra: str = "",
    stream: bool = False,
) -> str | Iterator[str]:
    description = GITHUB_FILE_KINDS.get(kind, kind)
    task = f"Write `{kind}` for `{ctx.repo}` - {description}."
    if extra.strip():
        task += f"\nAdditional requirements: {extra.strip()}"
    task += "\nUse the repository context to pick the right language, tooling and commands."
    return _ask(
        client,
        task,
        ctx.as_prompt(),
        system=GITHUB_FILE_SYSTEM,
        stream=stream,
        temperature=0.4,
        max_tokens=3000,
    )


# ------------------------------------------------------------------ assistant
SUGGESTION_PROMPTS = (
    "Write a README for this repository",
    "Suggest topics for this repository",
    "Draft a GitHub Actions workflow for tests",
    "Review my current README and list improvements",
    "Write a .gitignore for this project",
    "Explain how to add a LICENSE to this repo",
    "Write a pull request description for my change",
    "Improve my GitHub profile bio",
    "Triage the open issues",
    "Write release notes for the next version",
    "Create a CONTRIBUTING.md for this repo",
    "Suggest a CODEOWNERS file",
    "Write a bug report template",
    "Help me choose a license for this project",
)


def assistant_reply(
    client: AIClient,
    history: list[tuple[str, str]],
    message: str,
    *,
    context: str = "",
    stream: bool = True,
) -> str | Iterator[str]:
    messages = [ChatMessage("system", _system())]
    if context:
        messages.append(
            ChatMessage(
                "system",
                f"You have access to this live repository context:\n{context}",
            )
        )
    for role, content in history[-10:]:
        messages.append(ChatMessage("user" if role == "user" else "assistant", content))
    messages.append(ChatMessage("user", f"{SCOPE_REMINDER}\n\n{message}"))
    previous = client.temperature
    client.temperature = 0.6
    try:
        return client.chat(messages, stream=stream)
    finally:
        client.temperature = previous


def explain_concept(client: AIClient, question: str, *, stream: bool = True) -> str | Iterator[str]:
    system = (
        "You explain GitHub and git concepts for developers. Use short markdown "
        "with a one line summary first, then details, then a practical example. "
        "Mention the exact GitHub UI location or CLI command when relevant."
    )
    return _ask(client, question, system=system, stream=stream, temperature=0.3)


__all__ = [
    "AIError",
    "RepoContext",
    "SUGGESTION_PROMPTS",
    "assistant_reply",
    "branch_name",
    "build_repo_context",
    "commit_message",
    "explain_concept",
    "generate_readme",
    "github_file",
    "GITHUB_FILE_KINDS",
    "improve_text",
    "issue_draft",
    "issue_reply",
    "issue_triage",
    "pr_draft",
    "profile_bio",
    "profile_readme",
    "release_notes",
    "review_diff",
    "suggest_description",
    "suggest_topics",
    "summarize_readme",
    "json",
]
