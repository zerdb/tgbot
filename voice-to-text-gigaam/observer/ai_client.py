"""Optional internet AI adapter using OpenAI-compatible chat-completions APIs.

No provider SDK is required. API keys are read from environment variables and
are never written to Observer's config or database.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIConfigurationError(RuntimeError):
    pass


class AIRequestError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, config: dict):
        settings = config.get("ai", {})
        self.enabled = bool(settings.get("enabled", False))
        self.base_url = str(settings.get("base_url", "")).strip().rstrip("/")
        self.model = str(settings.get("model", "")).strip()
        key_env = str(settings.get("api_key_env", "GIGAAM_OBSERVER_API_KEY")).strip()
        self.api_key = os.getenv(key_env, "").strip() if key_env else ""

    def is_configured(self) -> bool:
        return bool(self.enabled and self.base_url and self.model)

    def explain_summary(self, summary: str, timeout: int = 45) -> str:
        """Send only a caller-approved, minimized summary to the configured AI."""
        if not self.is_configured():
            raise AIConfigurationError("AI is disabled or provider/model/base URL is not configured.")
        if not summary or not summary.strip():
            raise ValueError("Summary cannot be empty.")

        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the reasoning component of a private Windows assistant. "
                        "Analyze only the supplied summary. Suggest practical, non-invasive "
                        "improvements. Do not claim access to files, applications, or events "
                        "beyond the summary. Be concise and distinguish facts from hypotheses."
                    )
                },
                {"role": "user", "content": summary.strip()}
            ],
            "temperature": 0.3
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        try:
            with urlopen(request, timeout=max(5, min(int(timeout), 120))) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read(1000).decode("utf-8", errors="replace")
            raise AIRequestError(f"AI provider returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise AIRequestError(f"Could not reach AI provider: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AIRequestError("AI provider returned invalid JSON.") from exc

        try:
            return result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise AIRequestError("AI provider response has an unexpected format.") from exc
