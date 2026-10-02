"""Integration tests: AI task flows, config/secrets, GitHub client behaviour."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def drain(iterator) -> str:
    return "".join(iterator) if not isinstance(iterator, str) else iterator


# ------------------------------------------------------------------ stub AI
class StubAI:
    def __init__(self, reply: str = "ok", json_reply: str = "") -> None:
        self.reply = reply
        self.json_reply = json_reply
        self.prompts: list[str] = []
        self.base_url = "http://localhost:1/v1"
        self.model = "stub"
        self.max_tokens = 1000
        self.temperature = 0.7

    def _stream(self, text: str):
        for chunk in text.split(" "):
            yield chunk + " "

    def chat(self, messages, stream=False, json_mode=False):
        self.prompts.append("\n".join(f"{m.role}: {m.content}" for m in messages))
        if json_mode:
            return self.json_reply or '{"topics": ["a", "b"]}'
        return self._stream(self.reply) if stream else self.reply

    def complete(self, prompt, system="", **kwargs):
        self.prompts.append(prompt)
        return self.reply


class FakeCommit:
    def __init__(self, message: str) -> None:
        self.message = message


class FakeRepo:
    def __init__(self, name: str) -> None:
        self.full_name = name
        self.description = "demo repo"


def test_readme_flow() -> None:
    from app.core import ai_tasks

    ctx = ai_tasks.RepoContext(
        repo="octocat/demo",
        description="demo",
        tree=["README.md", "main.py"],
        languages=[".py"],
        topics=["python"],
        readme="# Old",
    )
    ai = StubAI(reply="# Demo\n\nA python demo repository with a usage section.")
    result = drain(
        ai_tasks.generate_readme(
            ai,
            ctx,
            tone="Friendly",
            language="English",
            sections=["Features", "Installation"],
            audience="Developers",
            extra_notes="include a Docker section",
            stream=True,
        )
    )
    check("generate_readme returns markdown", result.startswith("# Demo"))
    prompt = ai.prompts[-1]
    check("readme prompt has tone", "Friendly" in prompt)
    check("readme prompt has language", "English" in prompt)
    check("readme prompt has sections", "Features, Installation" in prompt)
    check("readme prompt has notes", "Docker section" in prompt)
    check("readme prompt carries repo context", "octocat/demo" in prompt)
    check("readme prompt has scope reminder", "stay strictly within GitHub" in prompt)
    check("readme prompt has system role", "GitHub Manager" in prompt)

    ai2 = StubAI(reply="Improved text with a better table of contents.")
    improved = drain(ai_tasks.improve_text(ai2, "# Old", instruction="add a TOC"))
    check("improve_text returns text", "table of contents" in improved)
    check("improve_text keeps instruction", "add a TOC" in ai2.prompts[-1])


def test_topics_and_description() -> None:
    from app.core import ai_tasks

    ctx = ai_tasks.RepoContext(repo="octocat/demo", tree=["main.py"])
    ai = StubAI(json_reply='{"topics": ["Python", "CLI tools", "automation-tool", "bad topic!"]}')
    topics = ai_tasks.suggest_topics(ai, ctx, count=10)
    check(
        "topics are slugified",
        topics == ["python", "cli-tools", "automation-tool", "bad-topic"],
        str(topics),
    )
    check("topics are unique", len(topics) == len(set(topics)))

    ai2 = StubAI(reply='"A friendly python CLI for automation."\nignored second line')
    description = ai_tasks.suggest_description(ai2, ctx)
    check("description strips quotes", description == "A friendly python CLI for automation", description)
    check("description is single line", "\n" not in description)


def test_github_text_features() -> None:
    from app.core import ai_tasks

    ai = StubAI(reply="## Draft\n\nbody")
    issue = drain(ai_tasks.issue_draft(ai, title_hint="Login crashes", body_hint="stack trace"))
    check("issue draft returned", "Draft" in issue)
    check("issue draft prompt mentions idea", "Login crashes" in issue or "Login crashes" in ai.prompts[-1])

    ai2 = StubAI(reply="| Issue | Type | Priority |")
    triage = drain(ai_tasks.issue_triage(ai2, [{"number": 1, "title": "bug", "state": "open"}]))
    check("triage returns markdown table", "Priority" in triage)
    check("triage lists issues", "#1" in ai2.prompts[-1])

    ai3 = StubAI(reply="Thanks, could you share the stack trace?")
    reply = drain(
        ai_tasks.issue_reply(ai3, {"number": 4, "title": "Crash", "body": "boom"})
    )
    check("issue reply returned", "stack trace" in reply)

    ai4 = StubAI(reply="## Summary\n\nAdds the studio\n\n## Changes\n\n- one")
    pr = drain(ai_tasks.pr_draft(ai4, repo="a/b", title="Add studio", changed_files=["main.py"]))
    check("pr draft has summary", "Summary" in pr)
    check("pr draft lists files", "main.py" in ai4.prompts[-1])

    ai5 = StubAI(reply="feat: add readme studio\n\nLong body text.\n\nCloses #12")
    message = ai_tasks.commit_message(ai5, diff_summary="added a new page")
    check("commit message uses convention", message.startswith("feat:"), message)
    check("commit prompt includes diff", "added a new page" in ai5.prompts[-1])

    ai6 = StubAI(reply="`feat/readme-studio` and some noise")
    branch = ai_tasks.branch_name(ai6, "add the readme studio")
    check("branch name is clean", branch == "feat/readme-studio", branch)

    ai7 = StubAI(reply="## Highlights\n\n- Faster")
    notes = drain(
        ai_tasks.release_notes(ai7, repo="a/b", tag="v2.0.0", commits=[FakeCommit("feat: x")])
    )
    check("release notes returned", "Highlights" in notes)
    check("release notes mention tag", "v2.0.0" in ai7.prompts[-1])

    ai8 = StubAI(reply="## Blocking issues\n\n- SQL injection in login")
    review = drain(ai_tasks.review_diff(ai8, repo="a/b", diff="+ query = f'...'"))
    check("diff review returned", "Blocking" in review)
    check("diff review prompt contains diff", "query" in ai8.prompts[-1])


def test_github_file_templates() -> None:
    from app.core import ai_tasks

    ctx = ai_tasks.RepoContext(repo="octocat/demo", tree=["main.py"])
    for kind in ("CONTRIBUTING.md", "LICENSE", ".gitignore", ".github/workflows/ci.yml"):
        ai = StubAI(reply=f"content for {kind}")
        out = drain(ai_tasks.github_file(ai, kind, ctx, stream=False))
        check(f"drafts {kind}", out == f"content for {kind}")
        check(f"{kind} prompt names the file", kind in ai.prompts[-1])
        check(f"{kind} prompt forbids fences", "no markdown code fence" in ai.prompts[-1])


def test_assistant_history() -> None:
    from app.core import ai_tasks

    ai = StubAI(reply="Use a table of contents.")
    out = drain(
        ai_tasks.assistant_reply(
            ai,
            [("user", "hi there, my readme is weak"), ("assistant", "Add badges.")],
            "How do I improve it?",
            context="Repository: octocat/demo",
        )
    )
    prompt = ai.prompts[-1]
    check("assistant keeps history", "my readme is weak" in prompt)
    check("assistant injects context", "Repository: octocat/demo" in prompt)
    check("assistant output", "table of contents" in out)
    check("assistant system prompt is scoped", "GitHub Manager" in prompt)
    check("assistant keeps a scope reminder", "stay strictly within GitHub" in prompt)


def test_profile_helpers() -> None:
    from app.core import ai_tasks

    ai = StubAI(reply="1. Backend engineer building tools.\n2. Python + cloud.\n3. Open source.")
    out = drain(ai_tasks.profile_bio(ai, {"login": "octocat", "name": "Octo"}, style="concise"))
    check("bio returns options", out.count("\n") >= 2)

    ai2 = StubAI(reply="# Hi\n\nWelcome to my corner.")
    readme = drain(
        ai_tasks.profile_readme(
            ai2,
            {"login": "octocat", "name": "Octo", "location": "SF", "bio": "dev"},
            [FakeRepo("octocat/demo")],
        )
    )
    check("profile readme returned", readme.startswith("# Hi"))
    check("profile readme mentions login", "octocat" in ai2.prompts[-1])


def test_parse_json() -> None:
    from app.core.github_api import parse_json

    check("plain json", parse_json('{"a": 1}') == {"a": 1})
    check("fenced json", parse_json('```json\n{"a": 2}\n```') == {"a": 2})
    check("json with prose", parse_json('Here you go: {"a": 3} done') == {"a": 3})
    check("fallback", parse_json("nonsense", {"z": 0}) == {"z": 0})


def test_config_roundtrip() -> None:
    from app.config import ConfigStore, Settings

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(
            json.dumps({"theme": "light", "accent": "emerald", "ai_max_tokens": 4096, "bogus": 1}),
            encoding="utf-8",
        )
        store = ConfigStore.__new__(ConfigStore)
        store.path = path
        store.settings = Settings()
        store.load()
        check("loads theme", store.settings.theme == "light")
        check("loads accent", store.settings.accent == "emerald")
        check("loads ints", store.settings.ai_max_tokens == 4096)
        check("ignores unknown keys", not hasattr(store.settings, "bogus"))

        store.save(theme="dark")
        check("persists change", json.loads(path.read_text(encoding="utf-8"))["theme"] == "dark")
        check("in-memory updated", store.settings.theme == "dark")


def test_secrets_encryption() -> None:
    from app.core.secure import SecretStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "secrets.json"
        store = SecretStore(path)
        store.set("github_token", "ghp_supersecret")
        raw = path.read_text(encoding="utf-8")
        check("token is not stored in plain text", "ghp_supersecret" not in raw, raw)
        check("token round-trips", store.get("github_token") == "ghp_supersecret")
        check("has() works", store.has("github_token"))
        check("reopen keeps value", SecretStore(path).get("github_token") == "ghp_supersecret")

        store.delete("github_token")
        check("delete clears", not store.has("github_token"))
        store.set("github_token", "x")
        store.clear()
        check("clear empties store", not store.has("github_token"))


def test_repo_summary_parsing() -> None:
    from app.core.github_api import IssueItem, RepoSummary, UserProfile

    repo = RepoSummary.from_api(
        {
            "full_name": "a/b",
            "name": "b",
            "owner": {"login": "a"},
            "stargazers_count": 5,
            "forks_count": 2,
            "open_issues_count": 1,
            "topics": ["x"],
            "license": {"spdx_id": "MIT"},
            "visibility": "public",
            "private": False,
        }
    )
    check("repo fields", repo.full_name == "a/b" and repo.stars == 5 and repo.license_name == "MIT")

    profile = UserProfile.from_api({"login": "a", "followers": 3, "total_private_repos": 2})
    check("profile fields", profile.login == "a" and profile.followers == 3 and profile.total_private_repos == 2)

    issue = IssueItem.from_api({"number": 7, "title": "t", "pull_request": {}}, is_pr=True)
    check("pr flag", issue.is_pr is True and issue.number == 7)


def test_github_error_message() -> None:

    from app.core.github_api import GitHubClient

    class FakeResponse:
        status_code = 401
        headers = {"Content-Type": "application/json"}
        content = b'{"message": "Bad credentials"}'

        def json(self):
            return {"message": "Bad credentials"}

    message = GitHubClient._error(FakeResponse())
    check("401 gets friendly text", "Invalid or expired token" in message, message)
    check("401 keeps api text", "Bad credentials" in message, message)


def main() -> int:
    test_readme_flow()
    test_topics_and_description()
    test_github_text_features()
    test_github_file_templates()
    test_assistant_history()
    test_profile_helpers()
    test_parse_json()
    test_config_roundtrip()
    test_secrets_encryption()
    test_repo_summary_parsing()
    test_github_error_message()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
