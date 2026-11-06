"""Shared OpenAI-compatible client for Groq chat completions."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"


def chat(messages, temperature=0.2, max_tokens=1200, model=None, timeout=90):
    """Call Groq Cloud using its OpenAI-compatible chat-completions API."""
    from agent_core import get_groq_api_key, load_settings

    key = os.getenv("GROQ_API_KEY", "").strip() or get_groq_api_key()
    if not key:
        raise RuntimeError("Не задан API-ключ Groq. Добавь его в настройках Zero Control.")

    settings = load_settings()
    selected_model = str(
        model or os.getenv("GROQ_MODEL", "").strip() or settings.get("groq_model", DEFAULT_MODEL)
    ).strip()
    if not selected_model:
        raise RuntimeError("Не выбрана модель Groq.")

    payload = {"model": selected_model, "temperature": temperature,
               "max_tokens": max_tokens, "messages": messages}
    request = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "ZeroControl/1.0 (Groq API client)"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError("Groq HTTP %s: %s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Groq недоступен: %s" % exc) from exc

    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if isinstance(content, list):
        content = "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    answer = str(content or "").strip()
    if not answer:
        raise RuntimeError("Groq вернул пустой ответ.")
    return answer
