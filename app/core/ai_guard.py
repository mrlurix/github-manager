"""Domain guard rails.

The assistant is restricted to GitHub related work. This module holds the
system prompt, an intent classifier for incoming messages and a validator that
rejects answers that drift off-topic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SYSTEM_PROMPT = """You are the AI engine inside "GitHub Manager", a desktop app \
that helps developers with their GitHub work.

STRICT SCOPE - you may ONLY help with GitHub related tasks:
- Writing, reviewing, translating, shortening or improving README files.
- Repository management: creating, renaming, archiving, topics, descriptions, \
visibility, branches, forks, transfers, releases, tags.
- Issues and pull requests: writing, triaging, labelling, replying, closing.
- Commit messages, branch names, pull request titles and descriptions.
- Git / GitHub concepts: rebase, merge, squash, submodules, actions, forks, \
gists, GitHub Pages, packages, security, permissions, tokens, scopes, SSH keys.
- GitHub profile optimisation: bio, profile README, pinned repositories.
- Code that lives in a GitHub repository: reading it, explaining it, writing \
documentation or tests for it, writing CI workflows (.github/workflows), \
Dockerfiles, .gitignore, licence files and contribution guides.

OUT OF SCOPE - politely refuse anything else, including:
- Anything unrelated to GitHub (cooking, travel, medical or legal advice, \
general chat, politics, personal advice).
- Writing or running code outside a GitHub repository context, or doing \
generic software work with no GitHub connection.
- Anything that would help attack, spam or impersonate others on GitHub.

REFUSAL STYLE: one short sentence, then offer the nearest GitHub alternative.
Example: "I only assist with GitHub work in this app - but I can help you write \
a README or improve your profile instead."

BEHAVIOUR:
- Be concise and practical. Prefer concrete markdown and code blocks.
- Never invent repository contents; if context is missing, say what you need.
- When asked for machine readable output, return raw JSON with no commentary.
"""

ALLOWED_ACTIONS = {
    "readme",
    "repository",
    "issue",
    "pull_request",
    "commit",
    "branch",
    "release",
    "action",
    "profile",
    "gist",
    "security",
    "token",
    "documentation",
}

# Topics that are clearly not GitHub. Kept intentionally small: a false
# negative is handled by the system prompt, a false positive blocks a useful
# answer, so only strong signals are listed.
OFF_TOPIC = re.compile(
    r"\b("
    r"recipe|cook|cooking|dinner|lunch|breakfast|restaurant|"
    r"weather|forecast|"
    r"stock\s+(price|market)|crypto\s+price|bitcoin|"
    r"medical|doctor|diagnos\w*|symptom|legal\s+advice|lawyer|"
    r"homework\s+essay|write\s+(me\s+)?(a\s+)?(poem|song|story|novel)|"
    r"joke|translate\s+this\s+song|"
    r"horoscope|astrology|"
    r"fitness\s+workout|diet\s+plan"
    r")\b",
    re.IGNORECASE,
)

GITHUB_HINT = re.compile(
    r"\b("
    r"github|repo|repository|readme|commit|branch|pull\s*request|\bpr\b|issue|"
    r"gist|action|workflow|release|tag|license|licence|fork|clone|git\b|"
    r"markdown|badge|codecov|ci/cd|pipeline|clone|diff|stars?|topics?|"
    r"contribut(e|ing)|open\s*source|gh\s+cli"
    r")\b",
    re.IGNORECASE,
)

GENERIC_OFF_TOPIC = re.compile(
    r"\b("
    r"who\s+are\s+you|what\s+can\s+you\s+do|hello|hi\s+there|good\s+morning|"
    r"good\s+night|thanks|thank\s+you"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class GuardVerdict:
    allowed: bool
    reason: str = ""
    topic: str = "general"


def classify(message: str) -> GuardVerdict:
    """Decide whether a user message belongs to the GitHub domain."""
    text = (message or "").strip()
    if not text:
        return GuardVerdict(False, "empty message", "empty")

    if OFF_TOPIC.search(text):
        return GuardVerdict(
            False,
            "That request is outside this app's scope. GitHub Manager's AI only "
            "works on GitHub tasks.",
            "off-topic",
        )

    # Questions about the assistant itself are fine, as long as they are about
    # its GitHub capabilities.
    if GENERIC_OFF_TOPIC.search(text) and not GITHUB_HINT.search(text):
        return GuardVerdict(False, "small talk is out of scope", "chitchat")

    if GITHUB_HINT.search(text):
        topic = "github"
        lowered = text.lower()
        for key in sorted(ALLOWED_ACTIONS, key=len, reverse=True):
            if key.replace("_", " ") in lowered:
                topic = key
                break
        return GuardVerdict(True, "", topic)

    # Unknown, no strong signal either way. Allow, but ask the model to stay
    # inside the domain; the system prompt plus output check handle the rest.
    return GuardVerdict(True, "", "unclassified")


OUT_OF_SCOPE_PHRASES = (
    "i'm sorry, but i cannot",
    "i cannot help with that",
    "i can't help with that",
    "i am not able to",
    "outside of my scope",
    "out of scope",
    "as an ai language model",
    "i'm just an ai",
    "i am just an ai",
)

NON_GITHUB_ANSWER = re.compile(
    r"\b("
    r"preheat\s+the\s+oven|tablespoon|teaspoon|marinate|simmer|"
    r"celsius|fahrenheit|"
    r"horoscope|zodiac|"
    r"differential\s+diagnosis|"
    r"statute\s+of\s+limitations"
    r")\b",
    re.IGNORECASE,
)


def validate_answer(answer: str) -> tuple[bool, str]:
    """Return ``(ok, message)`` for a generated answer."""
    text = (answer or "").strip()
    if not text:
        return False, "The model returned an empty answer."
    if NON_GITHUB_ANSWER.search(text):
        return False, (
            "The answer drifted outside the GitHub domain, so it was discarded."
        )
    lowered = text.lower()
    if any(phrase in lowered for phrase in OUT_OF_SCOPE_PHRASES) and not GITHUB_HINT.search(text):
        return False, (
            "The model refused the request. This assistant only handles GitHub tasks."
        )
    return True, ""


def refusal_message() -> str:
    return (
        "**Out of scope.** GitHub Manager's assistant only works on GitHub tasks: "
        "READMEs, repositories, issues, pull requests, commits, releases, Actions "
        "and profiles.\n\nI can help you with:\n"
        "- write or improve a README\n"
        "- manage repository settings and topics\n"
        "- draft issues, pull requests or release notes\n"
        "- review commits, workflows and your profile"
    )


def wrap_prompt(task: str, context: str = "") -> str:
    """Prefix a task with the scope reminder and optional repo context."""
    parts = [SCOPE_REMINDER]
    if context:
        parts.append(f"<repository_context>\n{context}\n</repository_context>")
    parts.append(task)
    return "\n\n".join(parts)


SCOPE_REMINDER = (
    "Remember: stay strictly within GitHub. If the request is not GitHub related, "
    "reply with a one line refusal."
)
