"""Thin, UI agnostic wrapper around the GitHub REST API.

Uses PyGithub when it is available and falls back to plain ``requests`` calls
so the app keeps working in constrained environments.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from .redact import redact_secrets, remember_secret

try:  # optional, only used for a couple of convenience helpers
    from github import Auth, Github  # type: ignore
    from github.GithubException import GithubException  # type: ignore

    PY_GITHUB = True
except Exception:  # pragma: no cover
    Github = None  # type: ignore
    GithubException = Exception  # type: ignore
    PY_GITHUB = False

import requests

API = "https://api.github.com"
TIMEOUT = 45

# The token is sent as a header, so requests must never leave GitHub.
ALLOWED_HOSTS = frozenset({"api.github.com", "uploads.github.com"})

# GitHub owner names: alphanumerics and single hyphens, max 39 characters.
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
# Repository names: alphanumerics, dots, hyphens and underscores.
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
# A single path segment inside a repository (no traversal, no separators).
#: A path segment may not contain a separator or a control character. Control
#: characters matter as much as the separators: NUL truncates a path in some
#: stacks, and CR or LF inside a URL is what turns a path into a header.
PATH_SEGMENT_RE = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,255}$")
# git check-ref-format: no spaces, no ~ ^ : ? * [ \ , no leading/trailing slash.
# Control characters are excluded for the same reason they are in a path.
BRANCH_RE = re.compile(r"^[^~^:?*\[\\ \x00-\x1f\x7f]{1,255}$")


class GitHubError(RuntimeError):
    """User facing error with an optional HTTP status code.

    The message is scrubbed of anything token-shaped so it can be shown
    directly in the UI.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(redact_secrets(message))
        self.status = status


def validate_repo(full_name: str) -> str:
    """Check an ``owner/repo`` identifier before it is put into a URL.

    Repository names can come from a text box (the picker allows manual entry),
    so they are validated rather than trusted. Rejecting ``..`` and extra
    segments prevents a crafted name from redirecting a request to another API
    endpoint.
    """
    text = str(full_name or "").strip()
    parts = text.split("/")
    if len(parts) != 2 or not OWNER_RE.match(parts[0]) or not REPO_RE.match(parts[1]):
        raise GitHubError(
            f"'{text}' is not a valid owner/repository name.",
            status=400,
        )
    return f"{parts[0]}/{parts[1]}"


def validate_repo_path(path: str) -> str:
    """Validate a repository-relative file path used in a contents request."""
    text = str(path or "").strip().replace("\\", "/").strip("/")
    if not text:
        raise GitHubError("A file path is required.", status=400)
    for segment in text.split("/"):
        if not PATH_SEGMENT_RE.match(segment) or segment in {".", ".."}:
            raise GitHubError(f"Invalid file path '{path}'.", status=400)
    return text


def validate_branch_name(name: str) -> str:
    """Validate a branch name before it is used to build a git ref path.

    A branch name reaches a URL, so ``..`` has to be refused even though git
    would allow it in a name: ``refs/heads/../evil`` collapses to a different
    endpoint than the one the caller meant, and the request still carries the
    token. A leading ``refs/heads/`` is refused for the same reason - it would be
    prefixed a second time.
    """
    text = str(name or "").strip()
    if not text or not BRANCH_RE.match(text) or text.endswith("/"):
        raise GitHubError(f"'{text}' is not a valid branch name.", status=400)
    if text.startswith("/") or "//" in text:
        raise GitHubError(f"'{text}' is not a valid branch name.", status=400)
    if any(segment in {".", ".."} for segment in text.split("/")):
        raise GitHubError(f"'{text}' is not a valid branch name.", status=400)
    if text.startswith("refs/"):
        raise GitHubError(
            f"'{text}' looks like a full ref. Give the branch name on its own.",
            status=400,
        )
    return text


@dataclass
class RepoSummary:
    full_name: str
    name: str = ""
    description: str = ""
    private: bool = False
    fork: bool = False
    archived: bool = False
    language: str = ""
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    topics: list[str] = field(default_factory=list)
    default_branch: str = "main"
    homepage: str = ""
    updated_at: str = ""
    created_at: str = ""
    size_kb: int = 0
    has_wiki: bool = True
    has_issues: bool = True
    has_discussions: bool = False
    license_name: str = ""
    html_url: str = ""
    owner: str = ""
    visibility: str = "public"

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "RepoSummary":
        owner = (raw.get("owner") or {}).get("login", "")
        name = raw.get("name", "")
        return cls(
            full_name=raw.get("full_name") or f"{owner}/{name}",
            name=name,
            description=raw.get("description") or "",
            private=bool(raw.get("private")),
            fork=bool(raw.get("fork")),
            archived=bool(raw.get("archived")),
            language=raw.get("language") or "",
            stars=int(raw.get("stargazers_count") or 0),
            forks=int(raw.get("forks_count") or 0),
            watchers=int(raw.get("subscribers_count") or raw.get("watchers_count") or 0),
            open_issues=int(raw.get("open_issues_count") or 0),
            topics=list(raw.get("topics") or []),
            default_branch=raw.get("default_branch") or "main",
            homepage=raw.get("homepage") or "",
            updated_at=raw.get("updated_at") or "",
            created_at=raw.get("created_at") or "",
            size_kb=int(raw.get("size") or 0),
            has_wiki=bool(raw.get("has_wiki", True)),
            has_issues=bool(raw.get("has_issues", True)),
            has_discussions=bool(raw.get("has_discussions")),
            license_name=((raw.get("license") or {}) or {}).get("spdx_id") or "",
            html_url=raw.get("html_url") or "",
            owner=owner,
            visibility=raw.get("visibility") or ("private" if raw.get("private") else "public"),
        )


@dataclass
class UserProfile:
    login: str = ""
    name: str = ""
    bio: str = ""
    company: str = ""
    location: str = ""
    blog: str = ""
    twitter: str = ""
    email: str = ""
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    created_at: str = ""
    updated_at: str = ""
    avatar_url: str = ""
    html_url: str = ""
    plan: str = ""
    total_private_repos: int = 0
    owned_private_repos: int = 0

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "UserProfile":
        return cls(
            login=raw.get("login", ""),
            name=raw.get("name") or "",
            bio=raw.get("bio") or "",
            company=raw.get("company") or "",
            location=raw.get("location") or "",
            blog=raw.get("blog") or "",
            twitter=raw.get("twitter_username") or "",
            email=raw.get("email") or "",
            public_repos=int(raw.get("public_repos") or 0),
            public_gists=int(raw.get("public_gists") or 0),
            followers=int(raw.get("followers") or 0),
            following=int(raw.get("following") or 0),
            created_at=raw.get("created_at") or "",
            updated_at=raw.get("updated_at") or "",
            avatar_url=raw.get("avatar_url") or "",
            html_url=raw.get("html_url") or "",
            plan=(raw.get("plan") or {}).get("name", "") if raw.get("plan") else "",
            total_private_repos=int(raw.get("total_private_repos") or 0),
            owned_private_repos=int(raw.get("owned_private_repos") or 0),
        )


@dataclass
class IssueItem:
    number: int
    title: str
    state: str = "open"
    user: str = ""
    created_at: str = ""
    updated_at: str = ""
    comments: int = 0
    labels: list[str] = field(default_factory=list)
    body: str = ""
    is_pr: bool = False
    url: str = ""

    @classmethod
    def from_api(cls, raw: dict[str, Any], is_pr: bool = False) -> "IssueItem":
        return cls(
            number=int(raw.get("number") or 0),
            title=raw.get("title") or "",
            state=raw.get("state") or "open",
            user=(raw.get("user") or {}).get("login", ""),
            created_at=raw.get("created_at") or "",
            updated_at=raw.get("updated_at") or "",
            comments=int(raw.get("comments") or 0),
            labels=[
                (lbl.get("name") if isinstance(lbl, dict) else str(lbl)) or ""
                for lbl in (raw.get("labels") or [])
            ],
            body=raw.get("body") or "",
            is_pr=is_pr,
            url=raw.get("html_url") or "",
        )


@dataclass
class ReleaseItem:
    tag: str
    name: str = ""
    draft: bool = False
    prerelease: bool = False
    published_at: str = ""
    body: str = ""

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ReleaseItem":
        return cls(
            tag=raw.get("tag_name") or "",
            name=raw.get("name") or "",
            draft=bool(raw.get("draft")),
            prerelease=bool(raw.get("prerelease")),
            published_at=raw.get("published_at") or "",
            body=raw.get("body") or "",
        )


@dataclass
class CommitItem:
    sha: str
    message: str = ""
    author: str = ""
    date: str = ""

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "CommitItem":
        commit = raw.get("commit") or {}
        info = commit.get("author") or {}
        return cls(
            sha=(raw.get("sha") or "")[:7],
            message=(commit.get("message") or "").split("\n")[0],
            author=(raw.get("author") or {}).get("login") or info.get("name", ""),
            date=info.get("date") or "",
        )


class GitHubClient:
    """Authenticated GitHub REST client.

    All network calls happen on the calling thread; the UI layer is responsible
    for moving them onto a worker thread.

    ``api_url`` points at the REST root. It exists so the client can be aimed at
    a GitHub Enterprise instance, and so the test suite can run it against a
    local stand-in for the API without touching the real one.
    """

    def __init__(self, token: str = "", api_url: str = "") -> None:
        self.token = token or ""
        self.api_url = (api_url or API).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "GitHubManager/1.0",
            }
        )
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"
            # Redact this exact value from anything the user might read, rather
            # than depending on its shape being one we recognise.
            remember_secret(self.token)
        self._py_client = None
        if PY_GITHUB and self.token:
            try:
                self._py_client = Github(auth=Auth.Token(self.token))
            except Exception:
                self._py_client = None

    # ------------------------------------------------------------------ core
    def set_token(self, token: str) -> None:
        # Deliberately not __init__(): that would reset api_url back to the
        # public API and silently un-point an Enterprise client.
        self.token = token or ""
        if self.token:
            self._session.headers["Authorization"] = f"Bearer {self.token}"
        else:
            self._session.headers.pop("Authorization", None)
        self._py_client = None
        if PY_GITHUB and self.token:
            try:
                self._py_client = Github(auth=Auth.Token(self.token))
            except Exception:
                self._py_client = None

    @staticmethod
    def _is_loopback(host: str) -> bool:
        return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")

    def _build_url(self, path: str) -> str:
        """Resolve an API path to an absolute URL, refusing other hosts.

        The session carries the ``Authorization`` header, so an absolute URL
        pointing somewhere else would hand the token to that host. Only the
        configured API (and GitHub's upload endpoint) is allowed, and only over
        TLS: plaintext would put the token on the wire in a form anyone on the
        path could read.
        """
        text = str(path or "").strip()
        if text.startswith(("https://", "http://")):
            host = (urlparse(text).hostname or "").lower()
            allowed = set(ALLOWED_HOSTS)
            base_host = (urlparse(self.api_url).hostname or "").lower()
            if base_host:
                allowed.add(base_host)
            if host not in allowed:
                raise GitHubError(
                    f"Refusing to send the GitHub token to '{host or text}'.", status=400
                )
            if urlparse(text).scheme.lower() != "https" and not self._is_loopback(host):
                raise GitHubError(
                    "Refusing to send the GitHub token over plain HTTP.", status=400
                )
            return text
        if not text.startswith("/"):
            text = "/" + text
        return f"{self.api_url}{text}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = self._build_url(path)
        files = None
        data = None
        json_body = None
        merged = dict(self._session.headers)
        if headers:
            merged.update(headers)

        if raw_body is not None:
            # GitHub's avatar endpoint expects multipart with a "file" field.
            content_type = str(merged.pop("Content-Type", "image/png"))
            files = {"file": ("avatar", raw_body, content_type)}
            data = {}
        elif payload is not None:
            json_body = payload
            merged.pop("Content-Type", None)

        for attempt in range(3):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                    headers=merged,
                    timeout=TIMEOUT,
                )
            except requests.RequestException as exc:
                if attempt == 2:
                    raise GitHubError(f"Network error: {exc}") from exc
                time.sleep(1.2 * (attempt + 1))
                continue

            if resp.status_code == 204 or not resp.content:
                if resp.status_code >= 400:
                    raise GitHubError(self._error(resp), resp.status_code)
                return None

            if resp.status_code >= 400:
                # A hard rate limit is not transient: retrying after a couple of
                # seconds cannot help and just freezes the UI before the user
                # finally sees why. 5xx is retried above; this is reported now.
                raise GitHubError(self._error(resp), resp.status_code)

            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                try:
                    return resp.json()
                except ValueError as exc:
                    raise GitHubError("Malformed JSON in GitHub response") from exc
            return resp.content

        raise GitHubError("Request failed after retries")

    @staticmethod
    def _error(resp: requests.Response) -> str:
        """Turn an error response into a message that is safe to display.

        Response bodies can echo request data, so any credential-looking text is
        replaced before it reaches a toast or a message box.
        """
        try:
            data = resp.json()
            message = data.get("message") or ""
            errors = data.get("errors") or []
            if errors and isinstance(errors[0], dict):
                first = errors[0]
                detail = first.get("message") or first.get("field") or ""
                if detail:
                    message = f"{message}: {detail}"
        except Exception:
            message = resp.text[:200]
        message = redact_secrets(str(message))
        friendly = {
            401: "Invalid or expired token.",
            403: "Access denied (missing scope or rate limit).",
            404: "Not found, or the token lacks access.",
            422: "Validation failed.",
        }.get(resp.status_code, "")
        base = f"GitHub API {resp.status_code}: {message}".strip()

        # For a rate limit, say when it lifts: the user can do nothing else.
        if resp.status_code == 403 and "rate limit" in str(message).lower():
            reset = resp.headers.get("X-RateLimit-Reset") or ""
            remaining = resp.headers.get("X-RateLimit-Remaining") or ""
            when = ""
            if reset.isdigit():
                import time as _time

                minutes = max(0, int(int(reset) - _time.time()) // 60)
                when = f" Try again in about {minutes} min."
            elif remaining == "0":
                when = " The hourly quota is used up."
            base = f"{base}{when}"
        return f"{base} {friendly}".strip()

    @staticmethod
    def _paginate(
        client: "GitHubClient",
        path: str,
        *,
        params: dict[str, Any] | None = None,
        max_items: int = 1000,
        per_page: int = 100,
    ) -> list[Any]:
        out: list[Any] = []
        for page in range(1, max_items // per_page + 2):
            query = dict(params or {})
            query.update({"per_page": per_page, "page": page})
            chunk = client.request("GET", path, params=query)
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < per_page or len(out) >= max_items:
                break
        return out[:max_items]

    # --------------------------------------------------------------- account
    def get_authenticated_user(self) -> UserProfile:
        raw = self.request("GET", "/user")
        return UserProfile.from_api(raw)

    def upload_avatar(self, data: bytes, mime: str = "image/png") -> dict[str, Any]:
        """Upload a new profile avatar.

        ``data`` must already be validated by the caller; GitHub rejects
        anything over 1 MB with a confusing 422 otherwise.
        """
        return self.request(
            "POST",
            "/user/avatars",
            raw_body=data,
            payload={"Content-Type": mime},
            headers={"Content-Type": mime},
        )

    def update_profile(self, **fields: dict[str, Any]) -> UserProfile:
        payload = {k: v for k, v in fields.items() if v is not None}
        raw = self.request("PATCH", "/user", payload=payload)
        return UserProfile.from_api(raw)

    def get_rate_limit(self) -> dict[str, Any]:
        return self.request("GET", "/rate_limit").get("resources", {}).get("core", {})

    def get_orgs(self) -> list[dict[str, Any]]:
        return self._paginate(self, "/user/orgs")

    def get_followers(self, login: str) -> list[dict[str, Any]]:
        return self._paginate(self, f"/users/{login}/followers")

    def get_following(self, login: str) -> list[dict[str, Any]]:
        return self._paginate(self, f"/users/{login}/following")

    def get_events(self, login: str) -> list[dict[str, Any]]:
        return self._paginate(self, f"/users/{login}/events", per_page=50, max_items=150)

    def search_users(self, query: str) -> list[dict[str, Any]]:
        data = self.request(
            "GET", "/search/users", params={"q": query, "per_page": 20}
        )
        return data.get("items", [])

    def set_follow(self, login: str, follow: bool) -> None:
        method = "PUT" if follow else "DELETE"
        self.request(method, f"/user/following/{login}")

    # ------------------------------------------------------------ repository
    def list_repos(
        self,
        *,
        scope: str = "all",
        sort: str = "updated",
        direction: str = "desc",
        affiliation: str = "owner,collaborator,organization_member",
    ) -> list[RepoSummary]:
        path = "/user/repos"
        if scope == "public":
            profile = self.get_authenticated_user()
            path = f"/users/{profile.login}/repos"
        params = {
            "sort": sort,
            "direction": direction,
            "per_page": 100,
            "affiliation": affiliation,
        }
        if scope == "public":
            params.pop("affiliation", None)
        raw = self._paginate(self, path, params=params, max_items=600)
        return [RepoSummary.from_api(item) for item in raw]

    def get_repo(self, full_name: str) -> RepoSummary:
        return RepoSummary.from_api(self.request("GET", f"/repos/{full_name}"))

    def create_repo(
        self,
        name: str,
        *,
        description: str = "",
        private: bool = False,
        auto_init: bool = True,
        homepage: str = "",
        topics: Iterable[str] = (),
        has_issues: bool = True,
        has_wiki: bool = True,
        has_projects: bool = False,
        license_template: str = "",
    ) -> RepoSummary:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
            "homepage": homepage,
            "has_issues": has_issues,
            "has_wiki": has_wiki,
            "has_projects": has_projects,
        }
        if license_template:
            payload["license_template"] = license_template
        raw = self.request("POST", "/user/repos", payload=payload)
        topic_list = [t.strip() for t in topics if str(t).strip()]
        if topic_list:
            try:
                self.request("PUT", f"/repos/{raw['full_name']}/topics", payload={"names": topic_list})
            except GitHubError:
                pass
        return RepoSummary.from_api(raw)

    def update_repo(self, full_name: str, **fields: dict[str, Any]) -> RepoSummary:
        payload = {k: v for k, v in fields.items() if v is not None}
        raw = self.request("PATCH", f"/repos/{full_name}", payload=payload)
        topics = fields.get("topics")
        if topics is not None:
            try:
                self.request(
                    "PUT",
                    f"/repos/{full_name}/topics",
                    payload={"names": [str(t).strip() for t in topics if str(t).strip()]},
                )
            except GitHubError:
                pass
        return RepoSummary.from_api(raw)

    def delete_repo(self, full_name: str) -> None:
        self.request("DELETE", f"/repos/{full_name}")

    def transfer_repo(self, full_name: str, new_owner: str) -> RepoSummary:
        raw = self.request(
            "POST",
            f"/repos/{full_name}/transfer",
            payload={"new_owner": new_owner, "team_ids": []},
        )
        return RepoSummary.from_api(raw)

    def star_repo(self, full_name: str, star: bool = True) -> None:
        self.request("PUT" if star else "DELETE", f"/user/starred/{full_name}")

    def list_branches(self, full_name: str) -> list[str]:
        raw = self._paginate(self, f"/repos/{full_name}/branches", max_items=300)
        return [str(item.get("name")) for item in raw]

    def list_topics(self, full_name: str) -> list[str]:
        try:
            raw = self.request("GET", f"/repos/{full_name}/topics")
            return list(raw.get("names") or [])
        except GitHubError:
            return []

    def get_repo_tree(self, full_name: str, branch: str = "", recursive: bool = True) -> list[str]:
        # Validated before anything is requested, and the ref can come from the
        # edit dialog, which is a free-text field: it is not a value we can
        # assume was ever a real branch name.
        ref = validate_branch_name(branch) if branch else self.get_repo(full_name).default_branch
        raw = self.request(
            "GET",
            f"/repos/{full_name}/git/trees/{ref}",
            params={"recursive": "1" if recursive else "0"},
        )
        return [item.get("path", "") for item in raw.get("tree", []) if item.get("type") == "blob"]

    def get_file(self, full_name: str, path: str, ref: str = "") -> str | None:
        params = {"ref": ref} if ref else None
        target = (
            f"/repos/{validate_repo(full_name)}/contents/{validate_repo_path(path)}"
        )
        try:
            raw = self.request("GET", target, params=params)
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise
        if isinstance(raw, list):
            return None
        if raw.get("encoding") == "base64":
            return base64.b64decode(raw.get("content", "")).decode("utf-8", "replace")
        return raw.get("content") or ""

    def list_dir(self, full_name: str, path: str = "", ref: str = "") -> list[dict[str, Any]]:
        params = {"ref": ref} if ref else None
        target = f"/repos/{full_name}/contents/{path}" if path else f"/repos/{full_name}/contents"
        raw = self.request("GET", target, params=params)
        return raw if isinstance(raw, list) else []

    def get_readme(self, full_name: str) -> str:
        raw = self.request("GET", f"/repos/{full_name}/readme")
        return base64.b64decode(raw.get("content", "")).decode("utf-8", "replace")

    def write_file(
        self,
        full_name: str,
        path: str,
        content: str,
        message: str,
        branch: str = "",
        sha: str = "",
    ) -> dict[str, Any]:
        target = f"/repos/{validate_repo(full_name)}/contents/{validate_repo_path(path)}"
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
        }
        if branch:
            payload["branch"] = branch
        if sha:
            payload["sha"] = sha
        return self.request("PUT", target, payload=payload)

    def list_files(self, full_name: str, branch: str = "") -> list[dict[str, Any]]:
        """Every file in a repository, with the sha a delete has to quote.

        One request for the whole tree, unlike asking per file: deleting needs
        each file's sha, and a repository of a few hundred files would otherwise
        cost a few hundred round trips before the dialog could even open.
        """
        repo = validate_repo(full_name)
        # See get_repo_tree: validated before the request, because a caller-
        # supplied ref is user input, not a ref git vouched for.
        ref = validate_branch_name(branch) if branch else self.get_repo(full_name).default_branch
        raw = self.request(
            "GET",
            f"/repos/{repo}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        out: list[dict[str, Any]] = []
        for item in raw.get("tree", []):
            if item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            if not path:
                continue
            out.append(
                {
                    "path": path,
                    "sha": str(item.get("sha") or ""),
                    "size": int(item.get("size") or 0),
                }
            )
        out.sort(key=lambda entry: entry["path"].lower())
        return out

    def get_file_meta(self, full_name: str, path: str, ref: str = "") -> dict[str, Any] | None:
        """Metadata for one file, including the sha an update has to quote.

        ``write_file`` needs that sha when the file already exists; without it
        GitHub answers 422. Returns ``None`` when the file is not there, which is
        the normal case for a first upload.
        """
        params = {"ref": ref} if ref else None
        target = f"/repos/{validate_repo(full_name)}/contents/{validate_repo_path(path)}"
        try:
            raw = self.request("GET", target, params=params)
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise
        return raw if isinstance(raw, dict) else None

    def put_file(
        self,
        full_name: str,
        path: str,
        data: bytes,
        message: str,
        branch: str = "",
        *,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Create or replace a file from raw bytes.

        Binary safe, unlike :meth:`write_file`, which takes text. That matters
        for an upload feature: a PNG cannot survive an encode/decode round trip
        through str, so the bytes are encoded straight to base64.

        The sha of an existing file is looked up and sent along, because GitHub
        rejects an update that does not quote it. With ``overwrite`` off, an
        existing path is an error instead.
        """
        repo = validate_repo(full_name)
        clean = validate_repo_path(path)
        sha = ""
        existing = self.get_file_meta(repo, clean, branch)
        if existing:
            if not overwrite:
                raise GitHubError(f"'{clean}' already exists in {repo}.", status=409)
            sha = str(existing.get("sha") or "")
        payload: dict[str, Any] = {
            "message": message,
            # GitHub wraps lines in the JSON body; the newline keeps that from
            # growing the payload for anything but a very large file.
            "content": base64.b64encode(data).decode(),
        }
        if branch:
            payload["branch"] = branch
        if sha:
            payload["sha"] = sha
        return self.request("PUT", f"/repos/{repo}/contents/{clean}", payload=payload)

    def delete_file(self, full_name: str, path: str, message: str, sha: str, branch: str = "") -> None:
        target = f"/repos/{validate_repo(full_name)}/contents/{validate_repo_path(path)}"
        payload: dict[str, Any] = {"message": message, "sha": sha}
        if branch:
            payload["branch"] = branch
        self.request("DELETE", target, payload=payload)

    def commit_readme(
        self, full_name: str, content: str, message: str, branch: str = ""
    ) -> dict[str, Any]:
        """Create or update README.md, handling the sha of an existing file."""
        repo = validate_repo(full_name)
        existing_sha = ""
        try:
            raw = self.request(
                "GET",
                f"/repos/{repo}/contents/README.md",
                params={"ref": branch} if branch else None,
            )
            if isinstance(raw, dict):
                existing_sha = raw.get("sha", "")
        except GitHubError:
            existing_sha = ""
        return self.write_file(
            repo, "README.md", content, message, branch=branch, sha=existing_sha
        )

    def create_branch(self, full_name: str, name: str, from_branch: str = "") -> dict[str, Any]:
        repo = validate_repo(full_name)
        validate_branch_name(name)
        if not from_branch:
            from_branch = self.get_repo(repo).default_branch
        validate_branch_name(from_branch)
        ref = self.request("GET", f"/repos/{repo}/git/ref/heads/{from_branch}")
        return self.request(
            "POST",
            f"/repos/{repo}/git/refs",
            payload={"ref": f"refs/heads/{name}", "sha": ref["object"]["sha"]},
        )

    def fork_repo(self, full_name: str, organization: str = "") -> RepoSummary:
        path = f"/repos/{full_name}/forks"
        payload = {"organization": organization} if organization else None
        raw = self.request("POST", path, payload=payload)
        return RepoSummary.from_api(raw)

    def list_collaborators(self, full_name: str) -> list[dict[str, Any]]:
        return self._paginate(self, f"/repos/{full_name}/collaborators", max_items=200)

    def add_collaborator(self, full_name: str, username: str, permission: str = "push") -> None:
        self.request("PUT", f"/repos/{full_name}/collaborators/{username}", payload={"permission": permission})

    def remove_collaborator(self, full_name: str, username: str) -> None:
        self.request("DELETE", f"/repos/{full_name}/collaborators/{username}")

    def list_hooks(self, full_name: str) -> list[dict[str, Any]]:
        return self._paginate(self, f"/repos/{full_name}/hooks", max_items=100)

    # ------------------------------------------------------- issues / pulls
    def list_issues(self, full_name: str, state: str = "open", per_repo: int = 60) -> list[IssueItem]:
        raw = self._paginate(
            self,
            f"/repos/{full_name}/issues",
            params={"state": state, "sort": "updated"},
            max_items=per_repo,
        )
        return [IssueItem.from_api(item, is_pr="pull_request" in item) for item in raw]

    def list_pulls(self, full_name: str, state: str = "open") -> list[IssueItem]:
        raw = self._paginate(
            self, f"/repos/{full_name}/pulls", params={"state": state}, max_items=60
        )
        return [IssueItem.from_api(item, is_pr=True) for item in raw]

    def create_issue(self, full_name: str, title: str, body: str = "", labels: Iterable[str] = ()) -> IssueItem:
        payload: dict[str, Any] = {"title": title, "body": body}
        label_list = [str(x) for x in labels if str(x).strip()]
        if label_list:
            payload["labels"] = label_list
        return IssueItem.from_api(self.request("POST", f"/repos/{full_name}/issues", payload=payload))

    def update_issue(self, full_name: str, number: int, **fields: dict[str, Any]) -> IssueItem:
        return IssueItem.from_api(
            self.request("PATCH", f"/repos/{full_name}/issues/{number}", payload=fields)
        )

    def comment_issue(self, full_name: str, number: int, body: str) -> dict[str, Any]:
        return self.request("POST", f"/repos/{full_name}/issues/{number}/comments", payload={"body": body})

    def list_comments(self, full_name: str, number: int) -> list[dict[str, Any]]:
        return self._paginate(self, f"/repos/{full_name}/issues/{number}/comments", max_items=100)

    # ------------------------------------------------------------ releases
    def list_releases(self, full_name: str) -> list[ReleaseItem]:
        raw = self._paginate(self, f"/repos/{full_name}/releases", max_items=60)
        return [ReleaseItem.from_api(item) for item in raw]

    def create_release(
        self,
        full_name: str,
        tag: str,
        name: str = "",
        body: str = "",
        draft: bool = False,
        prerelease: bool = False,
        target: str = "",
    ) -> ReleaseItem:
        payload: dict[str, Any] = {
            "tag_name": tag,
            "name": name or tag,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
        }
        if target:
            payload["target_commitish"] = target
        return ReleaseItem.from_api(self.request("POST", f"/repos/{full_name}/releases", payload=payload))

    def list_commits(self, full_name: str, limit: int = 30) -> list[CommitItem]:
        raw = self._paginate(
            self, f"/repos/{full_name}/commits", params={"per_page": 30}, max_items=limit
        )
        return [CommitItem.from_api(item) for item in raw]

    def list_workflows(self, full_name: str) -> list[dict[str, Any]]:
        try:
            raw = self.request("GET", f"/repos/{full_name}/actions/workflows")
            return list(raw.get("workflows") or [])
        except GitHubError:
            return []

    def get_latest_release(self, full_name: str) -> str:
        try:
            raw = self.request("GET", f"/repos/{full_name}/releases/latest")
            return str(raw.get("tag_name") or "")
        except GitHubError:
            return ""


def parse_json(text: str, fallback: Any = None) -> Any:
    """Best effort JSON extraction from an LLM answer."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.removeprefix("json").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                continue
    return fallback


ProgressFn = Callable[[str], None]
