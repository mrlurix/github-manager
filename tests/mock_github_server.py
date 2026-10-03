"""A local stand-in for the GitHub REST API.

The rest of the test suite swaps the GitHub client for a stub object, which
proves the UI calls the right methods but never proves the HTTP layer works:
status codes, pagination headers, base64 content, error bodies and rate-limit
responses are exactly where the real bugs hide.

This server speaks real HTTP over a real socket and returns payloads shaped like
GitHub's, so ``GitHubClient`` is exercised end to end without a network or a
token. It is deliberately strict - unknown routes 404, and unauthenticated
requests are rejected - so a client bug shows up as a failure rather than a
silently empty screen.

Usage::

    server = MockGitHubServer()
    server.start()
    client = GitHubClient("token", api_url=server.url)
    ...
    server.stop()
"""

from __future__ import annotations

import base64
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

NOW = "2026-01-15T10:30:00Z"

#: Token the server accepts. Anything else is a 401, like the real API.
VALID_TOKEN = "mock-token-abc123"

REPO = {
    "id": 101,
    "name": "hello-world",
    "full_name": "octocat/hello-world",
    "owner": {"login": "octocat", "id": 1, "avatar_url": "", "html_url": "https://github.com/octocat"},
    "html_url": "https://github.com/octocat/hello-world",
    "clone_url": "https://github.com/octocat/hello-world.git",
    "description": "A tiny demo repo used by the tests.",
    "fork": False,
    "url": "https://api.github.com/repos/octocat/hello-world",
    "default_branch": "main",
    "stargazers_count": 128,
    "watchers_count": 128,
    "forks_count": 7,
    "open_issues_count": 3,
    "language": "Python",
    "topics": ["python", "demo"],
    "size": 412,
    "archived": False,
    "disabled": False,
    "visibility": "public",
    "private": False,
    "has_issues": True,
    "has_wiki": True,
    "has_projects": False,
    "homepage": "https://example.com",
    "pushed_at": NOW,
    "updated_at": NOW,
    "created_at": "2024-03-01T00:00:00Z",
}

REPOS = [
    REPO,
    {
        **REPO,
        "id": 102,
        "name": "secret-tools",
        "full_name": "octocat/secret-tools",
        "private": True,
        "visibility": "private",
        "description": "Internal helpers.",
        "stargazers_count": 3,
        "language": "Go",
        "topics": ["go", "internal"],
    },
    {
        **REPO,
        "id": 103,
        "name": "old-thing",
        "full_name": "octocat/old-thing",
        "archived": True,
        "description": "Deprecated.",
        "stargazers_count": 0,
        "language": None,
        "topics": [],
    },
]

USER = {
    "login": "octocat",
    "id": 1,
    "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
    "html_url": "https://github.com/octocat",
    "name": "The Octocat",
    "company": "GitHub",
    "location": "San Francisco",
    "blog": "https://github.blog",
    "bio": "Mascot, mostly.",
    "twitter_username": "github",
    "email": "octocat@github.com",
    "public_repos": 3,
    "followers": 9000,
    "following": 9,
    "created_at": "2011-01-25T18:44:36Z",
    "updated_at": NOW,
}

ISSUES = [
    {
        "number": 12,
        "title": "Crash when the token expires",
        "state": "open",
        "user": {"login": "contributor1"},
        "comments": 3,
        "labels": [{"name": "bug"}, {"name": "good first issue"}],
        "body": "Steps to reproduce:\n\n1. sign in\n2. wait\n3. boom",
        "html_url": "https://github.com/octocat/hello-world/issues/12",
        "created_at": NOW,
        "updated_at": NOW,
        "pull_request": None,
    },
    {
        "number": 11,
        "title": "Add dark mode",
        "state": "open",
        "user": {"login": "octocat"},
        "comments": 1,
        "labels": [{"name": "enhancement"}],
        "body": "The UI is very bright.",
        "html_url": "https://github.com/octocat/hello-world/issues/11",
        "created_at": NOW,
        "updated_at": NOW,
        "pull_request": None,
    },
]

COMMITS = [
    {
        "sha": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
        "commit": {
            "message": "feat: add README studio\n\nLong body that should be trimmed.",
            "author": {"name": "octocat", "date": NOW},
        },
        "author": {"login": "octocat"},
    },
    {
        "sha": "f6a7b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f",
        "commit": {"message": "fix: handle empty topics", "author": {"name": "octocat", "date": NOW}},
        "author": {"login": "octocat"},
    },
    {
        "sha": "1122334455667788990011223344556677889900",
        "commit": {"message": "docs: clarify install steps", "author": {"name": "octocat", "date": NOW}},
        "author": {"login": "octocat"},
    },
]

RELEASES = [
    {
        "id": 1,
        "tag_name": "v1.2.0",
        "name": "1.2.0",
        "body": "Notes for 1.2.0.",
        "draft": False,
        "prerelease": False,
        "published_at": NOW,
        "html_url": "https://github.com/octocat/hello-world/releases/tag/v1.2.0",
    },
    {
        "id": 2,
        "tag_name": "v1.1.0",
        "name": "1.1.0",
        "body": "",
        "draft": False,
        "prerelease": False,
        "published_at": "2025-06-01T00:00:00Z",
        "html_url": "https://github.com/octocat/hello-world/releases/tag/v1.1.0",
    },
]

TREE = [
    {"path": "README.md", "type": "blob", "size": 120},
    {"path": "main.py", "type": "blob", "size": 2048},
    {"path": "requirements.txt", "type": "blob", "size": 42},
    {"path": ".github", "type": "tree"},
    {"path": ".github/workflows", "type": "tree"},
    {"path": ".github/workflows/ci.yml", "type": "blob", "size": 300},
    {"path": "docs", "type": "tree"},
    {"path": "docs/guide.md", "type": "blob", "size": 900},
]

README_TEXT = """# Hello World

> A tiny demo repo.

## Install

```bash
pip install hello-world
```

## Usage

```python
from hello import main

main()
```
"""


def _content(path: str, text: str, sha: str = "deadbeef") -> dict[str, Any]:
    """Shape a contents response the way GitHub does."""
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return {
        "name": path.rsplit("/", 1)[-1],
        "path": path,
        "sha": sha,
        "size": len(text.encode("utf-8")),
        "url": f"https://api.github.com/repos/octocat/hello-world/contents/{path}",
        "html_url": f"https://github.com/octocat/hello-world/blob/main/{path}",
        "git_url": f"https://api.github.com/repos/octocat/hello-world/git/blobs/{sha}",
        "type": "file",
        "content": encoded,
        "encoding": "base64",
    }


def mock_repos(count: int) -> list[dict[str, Any]]:
    """Generate ``count`` synthetic repositories for pagination tests."""
    return [
        {
            **REPO,
            "id": 1000 + index,
            "name": f"repo-{index:03d}",
            "full_name": f"octocat/repo-{index:03d}",
            "html_url": f"https://github.com/octocat/repo-{index:03d}",
            "stargazers_count": index,
        }
        for index in range(count)
    ]


class _State:
    """Mutable server state, so writes are visible to later reads."""

    def __init__(self) -> None:
        self.repos = [dict(repo) for repo in REPOS]
        self.topics: dict[str, list[str]] = {
            repo["full_name"]: list(repo["topics"]) for repo in REPOS
        }
        self.user = dict(USER)
        self.files: dict[str, str] = {
            "README.md": README_TEXT,
            "main.py": "def main():\n    print('hello')\n",
            "requirements.txt": "requests\npygments\n",
            ".github/workflows/ci.yml": "name: ci\non: [push]\n",
        }
        self.branches = ["main", "develop"]
        self.issues = [dict(item) for item in ISSUES]
        self.releases = [dict(item) for item in RELEASES]
        self.comments: dict[int, list[dict[str, Any]]] = {}
        self.requests: list[dict[str, Any]] = []
        #: Force a status code for the next N requests, to test error handling.
        self.fail_next: dict[str, Any] | None = None


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MockGitHub/1.0"

    # Requests are noisy otherwise.
    def log_message(self, *_args: Any) -> None:  # noqa: D102
        return

    # ----------------------------------------------------------------- verbs
    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    # --------------------------------------------------------------- helpers
    @property
    def state(self) -> _State:
        return self.server.state  # type: ignore[attr-defined]

    def _read_raw(self) -> bytes:
        """Read the request body, chunked or not.

        Multipart uploads are sent chunked, so relying on Content-Length alone
        would desynchronise the connection and hang the client.
        """
        encoding = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in encoding:
            chunks: list[bytes] = []
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                try:
                    size = int(line.split(b";")[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()  # trailing CRLF
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _body(self) -> dict[str, Any]:
        self._last_raw = b""
        raw = self._read_raw()
        self._last_raw = raw
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # Multipart upload: keep the raw bytes for the route that cares.
            return {}

    def _send(
        self,
        status: int,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        raw: bytes | None = None,
    ) -> None:
        if raw is None:
            raw = b"" if payload is None else json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if raw:
                self.wfile.write(raw)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # The client gave up (timeout, cancel, retry). Normal here; it says
            # nothing about the route being correct.
            self.close_connection = True

    def _error(self, status: int, message: str, **extra: Any) -> None:
        body = {"message": message, "documentation_url": "https://docs.github.com/rest"}
        body.update(extra)
        if status == 403 and "rate limit" in message.lower():
            self._send(
                status,
                body,
                headers={
                    "X-RateLimit-Limit": "60",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "2000000000",
                },
            )
            return
        self._send(status, body)

    def _authed(self) -> bool:
        header = self.headers.get("Authorization") or ""
        return header == f"Bearer {VALID_TOKEN}"

    # -------------------------------------------------------------- dispatch
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        body = self._body()

        self.state.requests.append(
            {
                "method": method,
                "path": path,
                "query": {k: v[0] for k, v in query.items()},
                "body": body,
                "authed": self._authed(),
            }
        )

        # Injected failure mode, used by the error-path tests.
        forced = self.state.fail_next
        if forced:
            self.state.fail_next = None
            status = int(forced.get("status", 500))
            self._error(status, str(forced.get("message", "Injected failure")))
            return

        if not self._authed():
            self._error(401, "Bad credentials")
            return

        try:
            self._route(method, path, query, body)
        except Exception as exc:  # pragma: no cover - surfaces as a 500
            import traceback

            traceback.print_exc()
            self._error(500, f"mock server bug: {exc}")

    def _route(self, method: str, path: str, query: dict[str, Any], body: dict[str, Any]) -> None:
        state = self.state

        # ------------------------------------------------------------- /user
        if path == "/user" and method == "GET":
            self._send(200, state.user)
            return
        if path == "/user" and method == "PATCH":
            user = {**state.user, **{k: v for k, v in body.items() if v is not None}}
            # GitHub rejects a bio over 160 characters rather than truncating.
            if len(str(user.get("bio") or "")) > 160:
                self._error(422, "Validation Failed", errors=[{"field": "bio", "code": "too_long"}])
                return
            if not str(user.get("name") or "").strip():
                self._error(422, "Validation Failed", errors=[{"field": "name", "code": "missing_field"}])
                return
            state.user = user
            self._send(200, user)
            return
        if path == "/user/orgs" and method == "GET":
            self._send(200, [{"login": "github", "id": 9, "description": "How people build software"}])
            return
        if path == "/user/avatars" and method == "POST":
            # The body was already drained by _body(); it is a multipart upload.
            if b"filename=" not in getattr(self, "_last_raw", b""):
                self._error(400, "Problem parsing multipart upload")
                return
            self._send(201, {"avatar_url": "https://avatars.githubusercontent.com/u/1?v=4&new=1"})
            return
        if path == "/user/starred/octocat/hello-world":
            self._send(204)
            return
        if path == "/user/repos" and method == "GET":
            self._paginate(state.repos, query, "repos")
            return
        if path == "/user/repos" and method == "POST":
            name = str(body.get("name") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name or ""):
                self._error(422, "Validation Failed", errors=[{"field": "name", "code": "invalid"}])
                return
            created = {
                **REPO,
                "id": 900 + len(state.repos),
                "name": name,
                "full_name": f"octocat/{name}",
                "description": body.get("description") or "",
                "private": bool(body.get("private")),
                "html_url": f"https://github.com/octocat/{name}",
                "homepage": body.get("homepage") or "",
            }
            state.repos.append(created)
            state.topics[created["full_name"]] = []
            self._send(201, created)
            return

        # ----------------------------------------------------- /users/{login}
        if path == "/users/octocat/events":
            self._send(
                200,
                [
                    {
                        "type": "PushEvent",
                        "actor": {"login": "octocat"},
                        "repo": {"name": "octocat/hello-world"},
                        "created_at": NOW,
                        "payload": {"ref": "refs/heads/main", "commits": COMMITS},
                    }
                ],
            )
            return

        # ----------------------------------------------------------- /rate_limit
        if path == "/rate_limit":
            self._send(
                200,
                {
                    "resources": {
                        "core": {
                            "limit": 5000,
                            "remaining": 4987,
                            "reset": 2000000000,
                        }
                    }
                },
            )
            return

        # -------------------------------------------------------------- /repos
        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)", path)
        if match:
            full = f"{match.group(1)}/{match.group(2)}"
            repo = next((r for r in state.repos if r["full_name"] == full), None)
            if repo is None:
                self._error(404, "Not Found")
                return
            if method == "GET":
                self._send(200, repo)
                return
            if method == "PATCH":
                updated = {**repo, **{k: v for k, v in body.items() if v is not None}}
                state.repos[state.repos.index(repo)] = updated
                self._send(200, updated)
                return
            if method == "DELETE":
                state.repos.remove(repo)
                self._send(204)
                return

        # --------------------------------------------------------- repo extras
        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/topics", path)
        if match:
            full = f"{match.group(1)}/{match.group(2)}"
            if method == "GET":
                self._send(200, {"names": list(state.topics.get(full, []))})
                return
            names = [str(t).strip() for t in (body.get("names") or []) if str(t).strip()]
            if len(names) > 20:
                self._error(422, "Validation Failed", errors=[{"field": "names", "code": "too_many"}])
                return
            state.topics[full] = names
            repo = next((r for r in state.repos if r["full_name"] == full), None)
            if repo is not None:
                repo["topics"] = list(names)
            self._send(200, {"names": names})
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/branches", path)
        if match and method == "GET":
            self._send(200, [{"name": b, "commit": {"sha": "a" * 40}} for b in state.branches])
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/forks", path)
        if match and method == "POST":
            fork = {**REPO, "id": 555, "full_name": f"octocat/{match.group(2)}-fork", "fork": True}
            self._send(202, fork)
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/refs", path)
        if match and method == "POST":
            ref = str(body.get("ref") or "")
            if not ref.startswith("refs/heads/"):
                self._error(422, "Validation Failed", errors=[{"field": "ref", "code": "invalid"}])
                return
            name = ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref.split("/")[-1]
            if name in state.branches:
                self._error(422, "Reference already exists")
                return
            state.branches.append(name)
            self._send(201, {"ref": ref, "object": {"sha": "b" * 40}})
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/ref/heads/(.+)", path)
        if match and method == "GET":
            name = match.group(3)
            if name not in state.branches:
                self._error(404, "Not Found")
                return
            self._send(200, {"ref": f"refs/heads/{name}", "object": {"sha": "a" * 40}})
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/git/trees/(.+)", path)
        if match and method == "GET":
            self._send(200, {"sha": "c" * 40, "tree": TREE, "truncated": False})
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/readme", path)
        if match and method == "GET":
            # GitHub has a dedicated endpoint for the rendered README; it
            # returns the same shape as any other contents response.
            self._send(200, _content("README.md", state.files.get("README.md", README_TEXT)))
            return

        # ------------------------------------------------------------ contents
        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/contents/(.+)", path)
        if match:
            target = match.group(3)
            if method == "GET":
                text = state.files.get(target)
                if text is None:
                    self._error(404, "Not Found")
                    return
                self._send(200, _content(target, text))
                return
            if method == "PUT":
                encoded = str(body.get("content") or "")
                try:
                    decoded = base64.b64decode(encoded).decode("utf-8")
                except Exception:
                    self._error(422, "Validation Failed", errors=[{"field": "content", "code": "invalid"}])
                    return
                if not str(body.get("message") or "").strip():
                    self._error(422, "Validation Failed", errors=[{"field": "message", "code": "missing_field"}])
                    return
                existed = target in state.files
                if existed and not body.get("sha"):
                    self._error(422, "sha wasn't supplied", errors=[{"field": "sha", "code": "invalid"}])
                    return
                state.files[target] = decoded
                self._send(
                    200 if existed else 201,
                    {
                        "content": _content(target, decoded),
                        "commit": {"sha": "d" * 40, "message": body.get("message")},
                    },
                )
                return
            if method == "DELETE":
                state.files.pop(target, None)
                self._send(204)
                return

        # -------------------------------------------------------------- issues
        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues", path)
        if match:
            if method == "GET":
                self._paginate(state.issues, query, "issues", per_page=2)
                return
            if method == "POST":
                title = str(body.get("title") or "").strip()
                if not title:
                    self._error(422, "Validation Failed", errors=[{"field": "title", "code": "missing_field"}])
                    return
                number = max((i["number"] for i in state.issues), default=0) + 1
                created = {
                    "number": number,
                    "title": title,
                    "state": "open",
                    "user": {"login": "octocat"},
                    "comments": 0,
                    "labels": [],
                    "body": body.get("body") or "",
                    "html_url": f"https://github.com/octocat/hello-world/issues/{number}",
                    "created_at": NOW,
                    "updated_at": NOW,
                }
                state.issues.append(created)
                self._send(201, created)
                return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/pulls", path)
        if match and method == "GET":
            self._send(
                200,
                [
                    {
                        "number": 7,
                        "title": "Add a release notes panel",
                        "state": "open",
                        "user": {"login": "octocat"},
                        "comments": 0,
                        "labels": [],
                        "body": "Draft PR.",
                        "html_url": "https://github.com/octocat/hello-world/pull/7",
                        "created_at": NOW,
                        "updated_at": NOW,
                        "draft": False,
                    }
                ],
            )
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)", path)
        if match:
            number = int(match.group(3))
            issue = next((i for i in state.issues if i["number"] == number), None)
            if issue is None:
                self._error(404, "Not Found")
                return
            if method == "GET":
                self._send(200, issue)
                return
            if method == "PATCH":
                if body.get("state") not in {None, "open", "closed"}:
                    self._error(422, "Validation Failed")
                    return
                issue.update({k: v for k, v in body.items() if v is not None})
                self._send(200, issue)
                return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/issues/(\d+)/comments", path)
        if match:
            number = int(match.group(3))
            if method == "GET":
                self._send(200, state.comments.get(number, []))
                return
            if method == "POST":
                text = str(body.get("body") or "").strip()
                if not text:
                    self._error(422, "Validation Failed", errors=[{"field": "body", "code": "missing_field"}])
                    return
                created = {"id": len(state.comments.get(number, [])) + 1, "user": {"login": "octocat"}, "body": text}
                state.comments.setdefault(number, []).append(created)
                self._send(201, created)
                return

        # ------------------------------------------------------------ releases
        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/releases", path)
        if match:
            if method == "GET":
                self._paginate(state.releases, query, "releases")
                return
            if method == "POST":
                tag = str(body.get("tag_name") or "").strip()
                if not tag:
                    self._error(422, "Validation Failed", errors=[{"field": "tag_name", "code": "missing_field"}])
                    return
                if any(r["tag_name"] == tag for r in state.releases):
                    self._error(422, "Validation Failed", errors=[{"field": "tag_name", "code": "already_exists"}])
                    return
                created = {
                    "id": 100 + len(state.releases),
                    "tag_name": tag,
                    "name": body.get("name") or tag,
                    "body": body.get("body") or "",
                    "draft": bool(body.get("draft")),
                    "prerelease": bool(body.get("prerelease")),
                    "published_at": NOW,
                    "html_url": f"https://github.com/octocat/hello-world/releases/tag/{tag}",
                }
                state.releases.append(created)
                self._send(201, created)
                return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/releases/latest", path)
        if match and method == "GET":
            if not state.releases:
                self._error(404, "Not Found")
                return
            self._send(200, state.releases[0])
            return

        match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/commits", path)
        if match and method == "GET":
            self._send(200, COMMITS)
            return

        self._error(404, "Not Found")

    # -------------------------------------------------------------- helpers
    def _paginate(
        self,
        items: list[dict[str, Any]],
        query: dict[str, Any],
        name: str,
        per_page: int = 2,
    ) -> None:
        """Serve a page and a real ``Link: <...>; rel="next"`` header.

        The client follows that header, so this exercises the pagination code
        that a stub can never reach.
        """
        try:
            page = max(1, int(query.get("page", ["1"])[0]))
            size = max(1, int(query.get("per_page", [str(per_page)])[0]))
        except (TypeError, ValueError):
            page, size = 1, per_page
        window = items[(page - 1) * size : page * size]
        headers = {}
        if page * size < len(items):
            base = f"https://api.github.com{urlparse(self.path).path}"
            headers["Link"] = f'<{base}?page={page + 1}&per_page={size}>; rel="next"'
        self._send(200, window, headers=headers)


class MockGitHubServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.state = _State()
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    # ------------------------------------------------------------------ api
    def start(self) -> "MockGitHubServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        self._thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "MockGitHubServer":
        return self.start()

    def __exit__(self, *_exc: Any) -> None:
        self.stop()

    # -------------------------------------------------------------- helpers
    def requests_for(self, method: str, needle: str = "") -> list[dict[str, Any]]:
        method = method.upper()
        return [
            r
            for r in self.state.requests
            if r["method"] == method and needle in r["path"]
        ]

    def paths(self) -> list[str]:
        return [f"{r['method']} {r['path']}" for r in self.state.requests]

    def fail_next(self, status: int, message: str = "Injected failure") -> None:
        """Make the next request fail, to exercise the error paths."""
        self.state.fail_next = {"status": status, "message": message}

    def reset(self) -> None:
        self.state = _State()