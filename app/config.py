"""Application paths and persisted configuration.

The app is designed to be *portable*: every mutable file lives next to the
executable (``data/`` folder) so the whole folder can be moved or shipped on a
USB stick. If that location is not writable we transparently fall back to the
per-user application data directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "GitHub Manager"
APP_VERSION = "1.0.0"
ORG_NAME = "GitHubManager"

_ENV_PORTABLE = "GHM_PORTABLE"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Directory that holds the executable (or the project root in dev mode)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    """Writable directory used for settings + secrets.

    Portable by default. Set ``GHM_PORTABLE=0`` to force the user-data folder.
    """
    portable = os.environ.get(_ENV_PORTABLE, "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    if portable:
        candidate = app_root() / "data"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError as exc:
            # Read-only install location (Program Files, a network share, ...).
            print(f"[config] portable folder unavailable ({exc}); using AppData")
    fallback = Path(os.environ.get("APPDATA", str(Path.home()))) / ORG_NAME
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def settings_file() -> Path:
    return data_dir() / "settings.json"


def secrets_file() -> Path:
    return data_dir() / "secrets.json"


def open_path(path: str | Path) -> bool:
    """Open a file or folder with the OS default handler.

    Uses argument lists rather than a shell string so a path containing shell
    metacharacters can never be interpreted as a command.
    """
    target = str(path)
    try:
        if sys.platform.startswith("win"):
            # startfile goes through the shell association, not a command line,
            # so quoting is irrelevant here.
            os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
            return True
        opener = ["open"] if sys.platform == "darwin" else ["xdg-open"]
        subprocess.Popen(
            [*opener, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return True
    except Exception:
        return False


def default_readme_sections() -> list[str]:
    return [
        "Header & badges",
        "Description",
        "Features",
        "Tech stack",
        "Installation",
        "Usage",
        "Screenshots",
        "Contributing",
        "License",
        "Roadmap",
    ]


@dataclass
class Settings:
    """Non sensitive user preferences (stored as plain JSON)."""

    # appearance
    theme: str = "dark"  # dark | light
    accent: str = "violet"  # violet | blue | emerald | amber
    font_family: str = ""
    ui_scale: float = 1.0

    # github
    github_login: str = ""
    github_token_present: bool = False

    # ai provider (any OpenAI compatible endpoint)
    ai_provider: str = "openai"  # openai | ollama | custom
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_key_present: bool = False
    ai_temperature: float = 0.7
    ai_max_tokens: int = 3000
    ai_timeout: int = 120
    ai_stream: bool = True

    # readme studio defaults
    readme_language: str = "English"
    readme_tone: str = "Professional"
    readme_sections: list[str] = field(default_factory=default_readme_sections)

    # assistant
    assistant_grounded: bool = True
    last_page: int = 0
    last_repo: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        defaults = cls()
        bools = {"github_token_present", "ai_key_present", "assistant_grounded", "ai_stream"}
        ints = {"ai_max_tokens", "ai_timeout", "last_page"}
        floats = {"ai_temperature", "ui_scale"}
        strs = {
            "theme",
            "accent",
            "github_login",
            "ai_provider",
            "ai_base_url",
            "ai_model",
            "readme_language",
            "readme_tone",
            "font_family",
            "last_repo",
        }
        clean: dict[str, Any] = {}
        for key, value in (data or {}).items():
            if not hasattr(defaults, key):
                continue
            try:
                if key == "readme_sections":
                    value = [str(item) for item in (value or [])] or list(
                        defaults.readme_sections
                    )
                elif key in bools:
                    value = bool(value)
                elif key in ints:
                    value = int(value)
                elif key in floats:
                    value = float(value)
                elif key in strs:
                    value = str(value)
                else:
                    continue
            except (TypeError, ValueError):
                continue
            clean[key] = value
        return cls(**clean)


class ConfigStore:
    """Loads / saves :class:`Settings` and keeps them in memory."""

    def __init__(self) -> None:
        self.path = settings_file()
        self.settings = Settings()
        self.load()

    def load(self) -> Settings:
        raw: dict[str, Any] = {}
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        self.settings = Settings.from_dict(raw)
        return self.settings

    def save(self, **updates: Any) -> Settings:
        for key, value in updates.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        payload = self.settings.to_dict()
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(self.path)
        except Exception as exc:  # pragma: no cover - disk failure
            print(f"[config] could not persist settings: {exc}")
        return self.settings

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self.settings, key, default)
