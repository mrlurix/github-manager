"""Shared application context: settings, secrets, GitHub and AI clients."""

from __future__ import annotations

from typing import Any

from ..config import ConfigStore, Settings
from ..core.ai_api import AIClient
from ..core.github_api import GitHubClient
from ..core.secure import AI_API_KEY, GH_TOKEN, SecretStore


class AppContext:
    """Single object handed to every page."""

    def __init__(self) -> None:
        self.config = ConfigStore()
        self.secrets = SecretStore()
        self.github = GitHubClient(self.token)
        self._ai: AIClient | None = None
        self.profile: Any = None
        self.repos: list[Any] = []
        self.repos_loaded = False
        self.orgs: list[dict[str, Any]] = []

    # ----------------------------------------------------------------- auth
    @property
    def token(self) -> str:
        return self.secrets.get(GH_TOKEN)

    @property
    def signed_in(self) -> bool:
        return bool(self.token)

    def set_token(self, token: str) -> None:
        self.secrets.set(GH_TOKEN, token.strip())
        self.github = GitHubClient(token.strip())
        self.config.save(github_token_present=bool(token.strip()))

    def sign_out(self) -> None:
        self.secrets.set(GH_TOKEN, "")
        self.github = GitHubClient("")
        self.profile = None
        self.repos = []
        self.repos_loaded = False
        self.config.save(github_token_present=False, github_login="")

    # ------------------------------------------------------------------- ai
    @property
    def api_key(self) -> str:
        return self.secrets.get(AI_API_KEY)

    def set_api_key(self, key: str) -> None:
        self.secrets.set(AI_API_KEY, key.strip())
        self.config.save(ai_key_present=bool(key.strip()))

    def ai(self, *, model: str = "", base_url: str = "") -> AIClient:
        """Build (or reuse) an AI client from the current settings."""
        s: Settings = self.config.settings
        key = (model, base_url)
        if self._ai is not None and getattr(self, "_ai_key", None) == key:
            return self._ai
        self._ai = AIClient(
            base_url=base_url or s.ai_base_url,
            api_key=self.api_key,
            model=model or s.ai_model,
            temperature=s.ai_temperature,
            max_tokens=s.ai_max_tokens,
            timeout=s.ai_timeout,
        )
        self._ai_key = key
        return self._ai

    def ai_ready(self) -> bool:
        s = self.config.settings
        client = self.ai()
        if not s.ai_model or not s.ai_base_url:
            return False
        if client.needs_key and not self.api_key:
            return False
        return True

    def ai_missing_reason(self) -> str:
        s = self.config.settings
        if not s.ai_base_url or not s.ai_model:
            return "No AI provider configured. Open Settings to pick a provider and model."
        if self.ai().needs_key and not self.api_key:
            return "Missing AI API key. Open Settings and paste your key."
        return ""

    def reset_ai(self) -> None:
        self._ai = None
        self._ai_key = None

    # -------------------------------------------------------------- helpers
    def repo_names(self) -> list[str]:
        return [repo.full_name for repo in self.repos]

    def find_repo(self, full_name: str):
        for repo in self.repos:
            if repo.full_name == full_name:
                return repo
        return None
