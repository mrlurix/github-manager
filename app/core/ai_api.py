"""OpenAI compatible chat client with streaming support.

Works with OpenAI, Azure-style gateways, OpenRouter, Groq, Together, LM Studio,
Ollama (``/v1`` endpoint) and any other service that speaks
``POST {base}/chat/completions``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

from .redact import redact_secrets, remember_secret

DEFAULT_TIMEOUT = 120


class AIError(RuntimeError):
    """Error raised for every AI transport or provider failure.

    The message is scrubbed of anything token-shaped on construction, so it is
    always safe to show in the UI or write to a log.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(redact_secrets(message))
        self.status = status


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "hint": "Requires an OpenAI API key (sk-...).",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "hint": "Works with any OpenRouter model id.",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "hint": "Very fast, free tier available.",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "hint": "Free credits for new accounts.",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.1",
        "hint": "Local models. No API key needed.",
    },
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "model": "local-model",
        "hint": "LM Studio local server, no key required.",
    },
    "custom": {
        "base_url": "",
        "model": "",
        "hint": "Any OpenAI compatible endpoint.",
    },
}


@dataclass
class ChatMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


class AIClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 3000,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        if api_key:
            # Same reason as the GitHub token: scrub the value we actually hold
            # from error text, not just values shaped like a key.
            remember_secret(api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    # ------------------------------------------------------------- helpers
    @property
    def needs_key(self) -> bool:
        return not self._is_loopback(self.base_url)

    @staticmethod
    def _is_loopback(url: str) -> bool:
        """True when the host is the machine itself.

        Parsed rather than substring-matched: ``http://localhost.example.com/``
        and ``http://evil.test/?next=localhost`` both contain the word but are
        not the loopback interface.
        """
        try:
            host = (urlparse(str(url or "")).hostname or "").lower()
        except ValueError:
            return False
        if host in {"localhost", "::1", "[::1]"}:
            return True
        return host.startswith("127.")

    def _headers(self) -> dict[str, str]:
        """Headers for a request to the configured provider.

        The key is withheld rather than sent when the endpoint is plaintext
        http to a host that is not this machine. Sending it would put a live
        credential on the wire in clear text, and the address is user-editable,
        so a mistyped ``http://`` would leak it silently.
        """
        headers = {"Content-Type": "application/json"}
        if not self.api_key:
            return headers
        scheme = (urlparse(self.base_url).scheme or "").lower()
        if scheme == "http" and not self._is_loopback(self.base_url):
            return headers
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["api-key"] = self.api_key
        return headers

    def _endpoint(self, suffix: str) -> str:
        if self.base_url.endswith("/chat/completions"):
            base = self.base_url[: -len("/chat/completions")]
        else:
            base = self.base_url
        return f"{base}/{suffix}"

    @staticmethod
    def _error(resp: requests.Response) -> str:
        """Build a display-safe error message.

        Provider error bodies sometimes echo the key that was sent, so the
        message is scrubbed before it reaches a toast or a message box.
        """
        try:
            data = resp.json()
            err = data.get("error", data)
            if isinstance(err, dict):
                message = err.get("message") or json.dumps(err)[:300]
            else:
                message = str(err)[:300]
        except Exception:
            message = resp.text[:300]
        return f"AI provider error {resp.status_code}: {redact_secrets(str(message))}"

    # ------------------------------------------------------------ requests
    def list_models(self) -> list[str]:
        try:
            resp = requests.get(
                self._endpoint("models"), headers=self._headers(), timeout=min(self.timeout, 30)
            )
        except requests.RequestException as exc:
            raise AIError(f"Could not reach the provider: {exc}") from exc
        if resp.status_code >= 400:
            raise AIError(self._error(resp), resp.status_code)
        try:
            data = resp.json().get("data") or []
        except ValueError as exc:
            raise AIError("Invalid model list response") from exc
        return sorted(
            {
                str(item.get("id"))
                for item in data
                if isinstance(item, dict) and item.get("id")
            }
        )

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        stream: bool = False,
        json_mode: bool = False,
    ) -> str | Iterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "temperature": self.temperature,
            "stream": bool(stream),
        }
        if self.max_tokens:
            payload["max_tokens"] = int(self.max_tokens)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return self._send(payload, stream=stream)

    def complete(self, prompt: str, system: str = "", **kwargs: Any) -> str:
        messages: list[ChatMessage] = []
        if system:
            messages.append(ChatMessage("system", system))
        messages.append(ChatMessage("user", prompt))
        result = self.chat(messages, **kwargs)
        if isinstance(result, str):
            return result
        return "".join(result)

    def _send(self, payload: dict[str, Any], *, stream: bool) -> str | Iterator[str]:
        try:
            resp = requests.post(
                self._endpoint("chat/completions"),
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
                stream=stream,
            )
        except requests.RequestException as exc:
            raise AIError(f"Could not reach the AI provider: {exc}") from exc
        if resp.status_code >= 400:
            raise AIError(self._error(resp), resp.status_code)
        if not stream:
            try:
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except (ValueError, KeyError, IndexError) as exc:
                raise AIError("Unexpected response format from the AI provider") from exc
        return self._stream(resp)

    @staticmethod
    def _stream(resp: requests.Response) -> Iterator[str]:
        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                text = line if isinstance(line, str) else line.decode("utf-8", "replace")
                text = text.strip()
                if not text.startswith("data:"):
                    continue
                data = text[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta") or {}
                    piece = delta.get("content") or ""
                except (ValueError, KeyError, IndexError):
                    continue
                if piece:
                    yield piece
        except requests.RequestException as exc:
            raise AIError(f"Stream interrupted: {exc}") from exc
        finally:
            resp.close()
